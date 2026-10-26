"""Aawaz se Diagnosis — FastAPI server.

Pipeline for one learning loop (narration is fetched separately via /api/tts so text
shows first while Bulbul renders audio):
  1. question   -> Bulbul reads the diagnostic question aloud
  2. diagnose   -> Saaras transcribes the child's spoken reasoning,
                   Sarvam-105B classifies the misconception, BKT updates mastery
  3. reteach    -> Sarvam-105B re-teaches in an adaptively chosen modality, Bulbul narrates
  4. drills     -> Sarvam-105B writes targeted spoken drills, Bulbul speaks them,
                   Saaras + Sarvam-105B grade each spoken answer, mastery graph updates
"""
import base64
import hashlib
import os
import random
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from . import learner, prompts  # noqa: E402
from .curriculum import (LANGUAGE_NAMES, LANGUAGES, MISCONCEPTION_BY_ID, MODALITIES,  # noqa: E402
                         SKILLS, VOICE_GENDER, VOICES, get_question, get_skill)
from .sarvam import LLM_MODEL, STT_MODEL, TTS_MODEL, Sarvam, SarvamError  # noqa: E402
from .store import Store  # noqa: E402

# Serverless hosts (Vercel) only allow writes under /tmp, and each instance has its own disk,
# so there audio is returned inline as a data: URI instead of a /audio/ file URL.
ON_SERVERLESS = bool(os.getenv("VERCEL"))
DATA_DIR = Path(os.getenv("AAWAZ_DATA_DIR") or ("/tmp/aawaz" if ON_SERVERLESS else ROOT / "data"))
INLINE_AUDIO = os.getenv("AAWAZ_INLINE_AUDIO", "1" if ON_SERVERLESS else "0") == "1"
AUDIO_DIR = DATA_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = ROOT / "static"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

store = Store(DATA_DIR / "store.json")
sarvam: Sarvam | None = None


@asynccontextmanager
async def lifespan(_app):
    global sarvam
    sarvam = Sarvam(os.getenv("SARVAM_API_KEY", ""))
    yield
    await sarvam.close()


app = FastAPI(title="Aawaz se Diagnosis", lifespan=lifespan)


@app.exception_handler(SarvamError)
async def sarvam_error_handler(_request: Request, exc: SarvamError):
    return JSONResponse({"error": str(exc)}, status_code=exc.status)


# --------------------------------------------------------------------------- helpers
MINUS_WORD = {"en-IN": "minus", "hi-IN": "माइनस", "mr-IN": "उणे"}


def speakable(text, lang):
    """Bulbul skips a leading minus sign ("−8" is read as "eight"), so spell signs out."""
    minus = MINUS_WORD.get(lang, "minus")
    text = re.sub(r"(^|[\s(\[:,])[−-]\s?(?=\d)", rf"\1{minus} ", text)
    text = text.replace("°C", " degree Celsius").replace("°", " degree")
    return text


async def tts_url(text, lang, voice, task):
    """Synthesize with Bulbul (cached on disk by content hash). Returns (url, meta|None)."""
    text = speakable(text.strip(), lang)
    if not text:
        return None, None
    key = hashlib.sha1(f"{TTS_MODEL}|{voice}|{lang}|{text}".encode()).hexdigest()[:20]
    path = AUDIO_DIR / f"{key}.wav"
    if path.exists():
        meta = {"api": "Bulbul", "model": TTS_MODEL, "task": task, "ms": 0, "cached": True}
    else:
        audio, meta = await sarvam.speak(text, lang, speaker=voice, task=task)
        path.write_bytes(audio)
    if INLINE_AUDIO:
        return "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode(), meta
    return f"/audio/{key}.wav", meta


async def question_text(skill, question, lang):
    """Question in the child's language: authored for en/hi, translated by Sarvam-105B otherwise."""
    if lang == "en-IN":
        return question["en"], None
    if lang == "hi-IN":
        return question["hi"], None
    cache_key = f"{lang}|{skill['id']}|{question['id']}"
    cached = store.get_translation(cache_key)
    if cached:
        return cached, None
    result, meta = await sarvam.chat_json(prompts.translate_messages(question["en"], lang),
                                          prompts.TRANSLATE_SCHEMA, "translation",
                                          task=f"Translate question to {LANGUAGE_NAMES[lang]}",
                                          max_tokens=600)
    text = (result.get("text") or "").strip() or question["en"]
    store.set_translation(cache_key, text)
    return text, meta


def require_student(student_id):
    student = store.get_student(student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    return student


def require_skill(skill_id):
    skill = get_skill(skill_id)
    if not skill:
        raise HTTPException(404, "Unknown skill")
    return skill


def clamp(value, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return lo


async def transcribe_upload(upload, student, skill, task):
    audio = await upload.read()
    if not audio:
        raise HTTPException(400, "The recording was empty")
    if len(audio) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Recording is too long — keep it under 30 seconds")
    return await sarvam.transcribe(audio, filename=upload.filename or "speech.wav",
                                   content_type=upload.content_type or "audio/wav",
                                   language_code=student["language"],
                                   keyterms=skill["keyterms"], task=task)


def gender_of(student):
    return VOICE_GENDER.get(student["voice"], "female")


def misconception_info(student, mc_id, skill):
    if mc_id in MISCONCEPTION_BY_ID:
        mc = MISCONCEPTION_BY_ID[mc_id]
        return {"id": mc_id, "label": mc["label"], "description": mc["description"]}
    rec = student["misconceptions"].get(mc_id)
    if rec:
        return {"id": mc_id, "label": rec["label"], "description": rec.get("description", rec["label"])}
    return None


# --------------------------------------------------------------------------- config & students
@app.get("/api/config")
async def config():
    return {
        "languages": LANGUAGES,
        "voices": VOICES,
        "modalities": [{"id": k, **v} for k, v in MODALITIES.items()],
        "skills": [{"id": s["id"], "name": s["name"], "short": s["short"], "name_hi": s["name_hi"],
                    "prereqs": s["prereqs"],
                    "misconceptions": [{"id": m["id"], "label": m["label"]} for m in s["misconceptions"]]}
                   for s in SKILLS],
        "models": {"stt": STT_MODEL, "tts": TTS_MODEL, "llm": LLM_MODEL},
    }


class NewStudent(BaseModel):
    name: str
    grade: int = 5
    language: str = "hi-IN"
    voice: str = "priya"


class StudentPatch(BaseModel):
    language: str | None = None
    voice: str | None = None


@app.get("/api/students")
async def list_students():
    return [{"id": s["id"], "name": s["name"], "grade": s["grade"], "language": s["language"]}
            for s in store.list_students()]


@app.post("/api/students")
async def create_student(body: NewStudent):
    if body.language not in LANGUAGE_NAMES:
        raise HTTPException(400, "Unsupported language")
    student = store.create_student(body.name, body.grade, body.language, body.voice)
    return learner.summary(student)


class ImportBody(BaseModel):
    record: dict


@app.post("/api/students/import")
async def import_student(body: ImportBody):
    """Restore a learner from the copy the browser keeps (serverless disks are ephemeral)."""
    record = body.record
    required = {"id", "name", "grade", "language", "voice", "created_at", "mastery", "history",
                "misconceptions", "sessions", "asked"}
    if not required <= set(record) or not re.fullmatch(r"[0-9a-f]{10}", str(record["id"])):
        raise HTTPException(400, "Invalid learner record")
    if record["language"] not in LANGUAGE_NAMES:
        raise HTTPException(400, "Unsupported language")
    record.setdefault("modality_stats", {})
    record.setdefault("last_lesson", None)
    if not store.get_student(record["id"]):
        store.import_student(record)
    return learner.summary(store.get_student(record["id"]))


@app.get("/api/students/{student_id}")
async def get_student(student_id: str):
    return learner.summary(require_student(student_id))


@app.patch("/api/students/{student_id}")
async def patch_student(student_id: str, body: StudentPatch):
    student = require_student(student_id)
    if body.language:
        if body.language not in LANGUAGE_NAMES:
            raise HTTPException(400, "Unsupported language")
        student["language"] = body.language
    if body.voice:
        student["voice"] = body.voice
    store.save()
    return learner.summary(student)


# --------------------------------------------------------------------------- 1. question
@app.get("/api/question")
async def next_question(student_id: str, skill_id: str):
    student = require_student(student_id)
    skill = require_skill(skill_id)
    recent = student["asked"].get(skill_id, [])
    pool = [q for q in skill["questions"] if q["id"] not in recent] or skill["questions"]
    question = random.choice(pool)
    student["asked"][skill_id] = (recent + [question["id"]])[-(len(skill["questions"]) - 1 or 1):]
    store.save()

    text, meta = await question_text(skill, question, student["language"])
    return {"question_id": question["id"], "skill_id": skill_id, "text": text,
            "trace": [meta] if meta else []}


class SpeakBody(BaseModel):
    student_id: str
    text: str
    task: str = "Speak"


@app.post("/api/tts")
async def speak(body: SpeakBody):
    """Bulbul narration. The UI calls this separately so text appears while audio renders."""
    student = require_student(body.student_id)
    url, meta = await tts_url(body.text[:2400], student["language"], student["voice"], body.task[:60])
    return {"audio_url": url, "trace": [meta] if meta else []}


# --------------------------------------------------------------------------- 2. diagnose
@app.post("/api/diagnose")
async def diagnose(student_id: str = Form(...), skill_id: str = Form(...),
                   question_id: str = Form(...), text: str = Form(""),
                   audio: UploadFile | None = File(None)):
    student = require_student(student_id)
    skill = require_skill(skill_id)
    question = get_question(skill_id, question_id)
    if not question:
        raise HTTPException(404, "Unknown question")
    lang = student["language"]
    trace = []

    stt = None
    if audio is not None:
        stt, meta = await transcribe_upload(audio, student, skill, "Transcribe spoken reasoning")
        trace.append(meta)
        transcript = stt["transcript"]
    else:
        transcript = text.strip()
    if not transcript:
        raise HTTPException(422, "I couldn't hear anything — please try speaking again, a little closer to the mic.")

    q_text, _ = await question_text(skill, question, lang)
    prior = learner.active_misconceptions(student, skill_id)
    diag, meta = await sarvam.chat_json(
        prompts.diagnosis_messages(skill, q_text, question["answer"], transcript, lang, prior,
                                   gender_of(student)),
        prompts.DIAGNOSIS_SCHEMA, "misconception_diagnosis", task="Classify misconception")
    trace.append(meta)

    # Clean up the model output before it touches the student model.
    catalog = {m["id"]: m for m in skill["misconceptions"]}
    found = []
    for m in diag.get("misconceptions") or []:
        confidence = clamp(m.get("confidence"))
        if confidence < 0.35:
            continue
        mc_id = (m.get("id") or "").strip()
        if mc_id not in catalog:
            slug = re.sub(r"[^a-z0-9]+", "_", (m.get("label") or mc_id).lower()).strip("_")[:40]
            mc_id = mc_id if mc_id.startswith("new_") else f"new_{slug or 'misconception'}"
        found.append({
            "id": mc_id,
            "label": catalog[mc_id]["label"] if mc_id in catalog else (m.get("label") or mc_id),
            "description": catalog[mc_id]["description"] if mc_id in catalog else m.get("why", ""),
            "evidence_quote": m.get("evidence_quote", ""),
            "confidence": round(confidence, 2),
            "why": m.get("why", ""),
            "in_catalog": mc_id in catalog,
        })
    found.sort(key=lambda m: -m["confidence"])
    primary = diag.get("primary_misconception_id")
    if primary not in {m["id"] for m in found}:
        primary = found[0]["id"] if found else ""

    correct = bool(diag.get("answer_correct"))
    quality = diag.get("reasoning_quality", "unclear")
    score = clamp(diag.get("understanding_score"))
    if found:
        score = min(score, 0.45 if correct else 0.2)
    elif correct and quality == "sound":
        score = max(score, 0.9)

    mastery_before = mastery_after = None
    if not (quality == "unclear" and not correct and not found):
        mastery_before, mastery_after = learner.record_observation(
            student, skill_id, score, "diagnosis",
            f"{question_id}: " + (", ".join(m["label"] for m in found) or "no misconception"))
    for m in found:
        rec = learner.record_misconception(student, skill_id, m, m["evidence_quote"])
        if not m["in_catalog"]:
            rec["description"] = m["description"]
    if not found and correct:
        learner.record_clean_attempt(student, skill_id)
    student["sessions"].append({"ts": time.time(), "skill": skill_id, "question_id": question_id,
                                "transcript": transcript, "correct": correct,
                                "misconceptions": [m["id"] for m in found]})
    student["sessions"] = student["sessions"][-50:]
    store.save()

    return {
        "transcript": transcript,
        "stt": stt,
        "student_answer": diag.get("student_answer", ""),
        "answer_correct": correct,
        "reasoning_quality": quality,
        "understanding_score": round(score, 2),
        "misconceptions": found,
        "primary_misconception_id": primary,
        "strengths": diag.get("strengths") or [],
        "feedback": diag.get("feedback", ""),
        "recommended_modality": diag.get("recommended_modality") if diag.get("recommended_modality") in MODALITIES else "story",
        "teacher_note": diag.get("teacher_note", ""),
        "mastery_before": mastery_before,
        "mastery_after": mastery_after,
        "trace": trace,
        "student": learner.summary(student),
    }


# --------------------------------------------------------------------------- 3. re-teach
class ReteachBody(BaseModel):
    student_id: str
    skill_id: str
    misconception_id: str = ""
    modality: str = ""
    recommended: str = ""
    transcript: str = ""


def _label_value(label):
    """Numeric value written in a mark label like "2/7", "−3", "0.45" (None if not a number)."""
    text = (label or "").strip().replace("−", "-").replace(",", "")
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(?:\s*/\s*(\d+))?", text)
    if not match:
        return None
    value = float(match.group(1))
    if match.group(2):
        if int(match.group(2)) == 0:
            return None
        value /= int(match.group(2))
    return value


def _clean_lesson(lesson, modality):
    nl = lesson.get("number_line") or {}
    # The model sometimes misplaces a labelled point (e.g. puts "2/7" at 0.14); trust the label.
    moved = {}
    for mark in nl.get("marks") or []:
        exact = _label_value(mark.get("label"))
        if exact is not None and abs(exact - float(mark.get("value", 0))) > 1e-3:
            moved[round(float(mark.get("value", 0)), 6)] = exact
            mark["value"] = round(exact, 6)
    for jump in nl.get("jumps") or []:
        for end in ("from", "to"):
            jump[end] = moved.get(round(float(jump.get(end, 0)), 6), jump.get(end, 0))
    lo, hi = float(nl.get("min", 0) or 0), float(nl.get("max", 1) or 1)
    if hi <= lo:
        hi = lo + 1
    step = float(nl.get("step") or 1)
    if step <= 0 or (hi - lo) / step > 40:
        step = (hi - lo) / 10
    marks = [m for m in nl.get("marks") or [] if lo - 1e-9 <= float(m.get("value", lo)) <= hi + 1e-9][:14]
    jumps = [j for j in nl.get("jumps") or []
             if lo - 1e-9 <= float(j.get("from", lo)) <= hi + 1e-9 and lo - 1e-9 <= float(j.get("to", lo)) <= hi + 1e-9][:8]
    lesson["number_line"] = {"show": bool(nl.get("show") or modality == "number_line") and bool(marks or jumps),
                             "min": lo, "max": hi, "step": step, "marks": marks, "jumps": jumps}
    bars = lesson.get("bars") or {}
    items = []
    for b in bars.get("items") or []:
        parts = int(clamp(b.get("parts", 1), 1, 24))
        items.append({"label": b.get("label", ""), "parts": parts,
                      "shaded": int(clamp(b.get("shaded", 0), 0, parts))})
    lesson["bars"] = {"show": bool(bars.get("show") or modality == "visual") and bool(items),
                      "items": items[:6]}
    lesson["key_points"] = (lesson.get("key_points") or [])[:4]
    return lesson


@app.post("/api/reteach")
async def reteach(body: ReteachBody):
    student = require_student(body.student_id)
    skill = require_skill(body.skill_id)
    lang = student["language"]
    mc = misconception_info(student, body.misconception_id, skill) if body.misconception_id else None
    target = mc or {"id": "core", "label": f"Core idea of {skill['name']}",
                    "description": f"Strengthen the core idea of {skill['name']}."}

    if body.modality in MODALITIES:
        modality, reason = body.modality, "You picked this way."
    else:
        modality, reason = learner.choose_modality(student, body.misconception_id, body.recommended)
    tried = list(student["misconceptions"].get(body.misconception_id, {}).get("modalities", {}))

    trace = []
    lesson, meta = await sarvam.chat_json(
        prompts.lesson_messages(skill, target, modality, lang, body.transcript, tried, gender_of(student)),
        prompts.LESSON_SCHEMA, "reteach_lesson", task=f"Re-teach via {MODALITIES[modality]['label'].lower()}",
        temperature=0.4)
    trace.append(meta)
    lesson = _clean_lesson(lesson, modality)
    learner.note_lesson(student, skill["id"], body.misconception_id, modality)
    store.save()
    return {"modality": modality, "reason": reason, "lesson": lesson,
            "misconception": target, "trace": trace}


# --------------------------------------------------------------------------- 4. drills
class DrillBody(BaseModel):
    student_id: str
    skill_id: str
    misconception_id: str = ""
    modality: str = ""


@app.post("/api/drills")
async def create_drill(body: DrillBody):
    student = require_student(body.student_id)
    skill = require_skill(body.skill_id)
    lang = student["language"]
    mc = misconception_info(student, body.misconception_id, skill) if body.misconception_id else None

    trace = []
    result, meta = await sarvam.chat_json(
        prompts.drill_messages(skill, mc, lang, body.modality, gender_of(student)), prompts.DRILL_SCHEMA,
        "practice_drills", task="Generate targeted drills", temperature=0.7)
    trace.append(meta)
    items = [i for i in result.get("items") or [] if i.get("prompt_display")][:5]
    if not items:
        raise HTTPException(502, "Sarvam-105B returned no drill items — please try again")
    missing = [i for i in items if not i["expected_answer"].strip()]
    if missing:
        # The grader compares against expected_answer, so solve any item that came back without one.
        key, meta = await sarvam.chat_json(prompts.answer_key_messages([i["prompt_display"] for i in missing]),
                                           prompts.ANSWER_KEY_SCHEMA, "answer_key", task="Fill drill answer key",
                                           max_tokens=400, temperature=0.0)
        trace.append(meta)
        for item, answer in zip(missing, key["answers"]):
            item["expected_answer"] = answer.strip()

    entry = student["mastery"].get(skill["id"])
    drill = store.create_drill({
        "student_id": student["id"], "skill_id": skill["id"],
        "misconception_id": body.misconception_id, "modality": body.modality,
        "items": items, "answers": {}, "p_before": entry["p"] if entry else learner.P_INIT,
        "finished": False,
    })
    return {"drill_id": drill["id"], "items": [
        {"index": n, "prompt": i["prompt_display"], "spoken": i.get("prompt_spoken") or i["prompt_display"],
         "hint": i.get("hint", "")}
        for n, i in enumerate(items)], "trace": trace}


SCORES = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}


@app.post("/api/drills/{drill_id}/answer")
async def answer_drill(drill_id: str, item_index: int = Form(...), text: str = Form(""),
                       audio: UploadFile | None = File(None)):
    drill = store.get_drill(drill_id)
    if not drill:
        raise HTTPException(404, "Drill not found")
    if not 0 <= item_index < len(drill["items"]):
        raise HTTPException(400, "Bad item index")
    student = require_student(drill["student_id"])
    skill = require_skill(drill["skill_id"])
    item = drill["items"][item_index]
    lang = student["language"]
    trace = []

    if audio is not None:
        stt, meta = await transcribe_upload(audio, student, skill, "Transcribe drill answer")
        trace.append(meta)
        transcript = stt["transcript"]
    else:
        transcript = text.strip()
    if not transcript:
        raise HTTPException(422, "I couldn't hear an answer — try again?")

    catalog = [{"id": m["id"], "label": m["label"]} for m in skill["misconceptions"]]
    grade, meta = await sarvam.chat_json(prompts.grade_messages(skill, item, transcript, lang, catalog,
                                                                gender_of(student)),
                                         prompts.GRADE_SCHEMA, "drill_grade", task="Grade spoken answer",
                                         max_tokens=800, temperature=0.1)
    trace.append(meta)
    verdict = "correct" if grade.get("matches_expected") else grade.get("verdict", "unclear")
    mastery = None
    if verdict in SCORES:
        _, mastery = learner.record_observation(student, skill["id"], SCORES[verdict], "drill",
                                                f"drill: {item['prompt_display'][:60]}", weight=0.6)
    mc_id = grade.get("misconception_id", "")
    if verdict == "incorrect" and mc_id in MISCONCEPTION_BY_ID and MISCONCEPTION_BY_ID[mc_id]["skill"] == skill["id"]:
        learner.record_misconception(student, skill["id"], MISCONCEPTION_BY_ID[mc_id], transcript)
    drill["answers"][str(item_index)] = {"transcript": transcript, "verdict": verdict,
                                         "misconception_id": mc_id}
    store.save()

    return {"transcript": transcript, "verdict": verdict, "student_answer": grade.get("student_answer", ""),
            "expected_answer": item["expected_answer"], "feedback": grade.get("feedback", ""),
            "misconception_id": mc_id, "mastery": mastery, "trace": trace}


@app.post("/api/drills/{drill_id}/finish")
async def finish_drill(drill_id: str):
    drill = store.get_drill(drill_id)
    if not drill:
        raise HTTPException(404, "Drill not found")
    student = require_student(drill["student_id"])
    graded = [SCORES[a["verdict"]] for a in drill["answers"].values() if a["verdict"] in SCORES]
    accuracy = sum(graded) / len(graded) if graded else 0.0
    success, mc_status = None, None
    if not drill["finished"]:
        success, mc_status = learner.close_drill(student, drill, accuracy)
        drill["finished"] = True
        store.save()
    entry = student["mastery"].get(drill["skill_id"])
    return {"accuracy": round(accuracy, 2), "answered": len(graded), "total": len(drill["items"]),
            "mastery_before": drill["p_before"], "mastery_after": entry["p"] if entry else None,
            "modality": drill["modality"], "modality_worked": success,
            "misconception_id": drill["misconception_id"], "misconception_status": mc_status,
            "student": learner.summary(student)}


# --------------------------------------------------------------------------- static files
app.mount("/audio", StaticFiles(directory=AUDIO_DIR), name="audio")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")
