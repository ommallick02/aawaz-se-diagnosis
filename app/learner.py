"""Student model: per-skill mastery (Bayesian Knowledge Tracing), misconception
lifecycle, and adaptive choice of re-teaching modality."""
import time

from .curriculum import MODALITIES, SKILLS, SKILL_BY_ID, misconception_label

# BKT parameters: prior knowledge, learning rate, slip and guess probabilities.
P_INIT, P_LEARN, P_SLIP, P_GUESS = 0.3, 0.12, 0.1, 0.2
MASTERED, DEVELOPING = 0.8, 0.45


def bkt_update(p, score):
    """Update P(known) from a soft observation: score 1 = correct, 0 = wrong."""
    score = max(0.0, min(1.0, score))
    if_correct = p * (1 - P_SLIP) / (p * (1 - P_SLIP) + (1 - p) * P_GUESS)
    if_wrong = p * P_SLIP / (p * P_SLIP + (1 - p) * (1 - P_GUESS))
    posterior = score * if_correct + (1 - score) * if_wrong
    return round(posterior + (1 - posterior) * P_LEARN, 4)


def level(entry):
    if not entry or not entry.get("attempts"):
        return "not_started"
    if entry["p"] >= MASTERED:
        return "mastered"
    if entry["p"] >= DEVELOPING:
        return "developing"
    return "needs_help"


def record_observation(student, skill_id, score, event, detail="", weight=1.0):
    """weight < 1 damps the update — short spoken drill answers are easier to guess than a
    full explained diagnosis, so they move mastery less."""
    entry = student["mastery"].setdefault(skill_id, {"p": P_INIT, "attempts": 0, "correct": 0})
    before = entry["p"]
    if not entry["attempts"]:
        # Seed the history so the chart starts from the prior.
        student["history"].append({"ts": time.time() - 1, "skill": skill_id, "p": P_INIT,
                                   "event": "start", "detail": ""})
    entry["p"] = round(before + weight * (bkt_update(before, score) - before), 4)
    entry["attempts"] += 1
    entry["correct"] += 1 if score >= 0.75 else 0
    entry["updated_at"] = time.time()
    student["history"].append({"ts": time.time(), "skill": skill_id, "p": entry["p"],
                               "event": event, "detail": detail})
    student["history"] = student["history"][-600:]
    return before, entry["p"]


def record_misconception(student, skill_id, mc, transcript_quote=""):
    mc_id = mc["id"]
    rec = student["misconceptions"].setdefault(mc_id, {
        "skill": skill_id, "label": mc.get("label") or misconception_label(mc_id), "count": 0,
        "first_seen": time.time(), "status": "active", "evidence": [], "modalities": {},
        "clean_streak": 0,
    })
    rec["count"] += 1
    rec["last_seen"] = time.time()
    rec["status"] = "active"
    rec["clean_streak"] = 0
    if transcript_quote:
        rec["evidence"] = ([transcript_quote] + rec["evidence"])[:3]
    return rec


def record_clean_attempt(student, skill_id):
    """A diagnosis on this skill with no misconception moves resolving ones to resolved."""
    for rec in student["misconceptions"].values():
        if rec["skill"] == skill_id and rec["status"] == "resolving":
            rec["status"] = "resolved"
            rec["resolved_at"] = time.time()


def active_misconceptions(student, skill_id=None):
    return [
        {"id": mc_id, "label": rec["label"], "count": rec["count"], "status": rec["status"]}
        for mc_id, rec in student["misconceptions"].items()
        if rec["status"] != "resolved" and (skill_id is None or rec["skill"] == skill_id)
    ]


def choose_modality(student, mc_id, recommended):
    """Pick how to re-teach: try something new for this misconception first (starting with
    the LLM's recommendation), otherwise reuse whatever has worked best for this child."""
    tried = student["misconceptions"].get(mc_id, {}).get("modalities", {}) if mc_id else {}
    overall = student.get("modality_stats", {})

    def preference(m):
        stats = overall.get(m, {"tries": 0, "successes": 0})
        return (stats["successes"] + 1) / (stats["tries"] + 2)

    untried = [m for m in MODALITIES if m not in tried]
    if recommended in untried:
        return recommended, "Sarvam-105B judged this the best way to explain this misconception."
    if untried:
        best = max(untried, key=preference)
        if tried:
            failed = ", ".join(MODALITIES[m]["label"].lower() for m in tried)
            return best, f"Already tried {failed} for this mistake — switching to a new way."
        return best, "Picked from what has worked best for this learner so far."
    best = max(tried, key=lambda m: (tried[m]["successes"] + 1) / (tried[m]["tries"] + 2))
    return best, "Every way has been tried once — reusing the one that worked best."


def note_lesson(student, skill_id, mc_id, modality):
    student["last_lesson"] = {"skill": skill_id, "misconception_id": mc_id, "modality": modality,
                              "ts": time.time()}


def close_drill(student, drill, accuracy):
    """Credit the re-teaching modality if the drill afterwards went well and move the
    misconception along its lifecycle."""
    success = accuracy >= 0.75
    mc_id, modality = drill.get("misconception_id"), drill.get("modality")
    outcome = None
    if modality in MODALITIES:
        stats = student.setdefault("modality_stats", {}).setdefault(modality, {"tries": 0, "successes": 0})
        stats["tries"] += 1
        stats["successes"] += int(success)
    rec = student["misconceptions"].get(mc_id) if mc_id else None
    if rec:
        if modality in MODALITIES:
            m = rec["modalities"].setdefault(modality, {"tries": 0, "successes": 0})
            m["tries"] += 1
            m["successes"] += int(success)
        if success:
            rec["clean_streak"] = rec.get("clean_streak", 0) + 1
            rec["status"] = "resolved" if rec["clean_streak"] >= 2 else "resolving"
            if rec["status"] == "resolved":
                rec["resolved_at"] = time.time()
        else:
            rec["clean_streak"] = 0
            rec["status"] = "active"
        outcome = rec["status"]
    return success, outcome


def recommend_skill(student):
    """Lowest-mastery skill whose prerequisites are reasonably in place; active
    misconceptions pull a skill forward."""
    best, best_score = None, None
    for skill in SKILLS:
        entry = student["mastery"].get(skill["id"])
        p = entry["p"] if entry else P_INIT
        if p >= MASTERED:
            continue
        prereq_ok = all(student["mastery"].get(pr, {}).get("p", P_INIT) >= DEVELOPING
                        or not student["mastery"].get(pr) for pr in skill["prereqs"])
        active = len(active_misconceptions(student, skill["id"]))
        score = p - 0.25 * active + (0 if prereq_ok else 0.5) + (0.05 if not entry else 0)
        if best_score is None or score < best_score:
            best, best_score = skill["id"], score
    return best


def summary(student):
    skills = []
    for skill in SKILLS:
        entry = student["mastery"].get(skill["id"])
        skills.append({
            "id": skill["id"],
            "p": entry["p"] if entry else None,
            "attempts": entry["attempts"] if entry else 0,
            "level": level(entry),
            "active_misconceptions": len(active_misconceptions(student, skill["id"])),
        })
    misconceptions = [
        {"id": mc_id, **{k: rec[k] for k in ("skill", "label", "count", "status", "evidence")},
         "skill_name": SKILL_BY_ID.get(rec["skill"], {}).get("name", rec["skill"]),
         "modalities": rec.get("modalities", {}), "last_seen": rec.get("last_seen")}
        for mc_id, rec in student["misconceptions"].items()
    ]
    misconceptions.sort(key=lambda m: ({"active": 0, "resolving": 1, "resolved": 2}[m["status"]],
                                       -(m["last_seen"] or 0)))
    return {
        "id": student["id"], "name": student["name"], "grade": student["grade"],
        "language": student["language"], "voice": student["voice"],
        "skills": skills, "history": student["history"], "misconceptions": misconceptions,
        "modality_stats": student.get("modality_stats", {}),
        "recommended_skill": recommend_skill(student),
        "sessions": student["sessions"][-10:],
        # Raw record so the browser can restore the learner if a serverless instance lost it.
        "record": student,
    }
