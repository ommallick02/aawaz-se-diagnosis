"""Prompts and JSON schemas for every Sarvam-105B call."""
import json

from .curriculum import LANGUAGE_NAMES, MODALITIES

MODALITY_IDS = list(MODALITIES)


def _obj(properties):
    """Strict JSON-schema object: every property required, nothing extra."""
    return {"type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties}


STR = {"type": "string"}
NUM = {"type": "number"}
BOOL = {"type": "boolean"}
INT = {"type": "integer"}


def _lang(code):
    return LANGUAGE_NAMES.get(code, "Hindi")


def _language_rule(code, gender="female"):
    name = _lang(code)
    voice = (f" The text is read aloud by a {gender} voice: whenever you refer to yourself, use "
             f"{gender} grammatical forms (e.g. Hindi \"मैं दिखाती हूँ\" if female, \"मैं दिखाता हूँ\" "
             f"if male).")
    if code == "en-IN":
        return "Write all child-facing text in simple Indian English." + voice
    return (f"Write all child-facing text in simple, spoken {name} as a child in India would hear "
            f"it at home, in {name}'s native script. Common English school words (fraction, "
            f"denominator, decimal) may be mixed in naturally." + voice)


# --------------------------------------------------------------------------- diagnosis
DIAGNOSIS_SCHEMA = _obj({
    "student_answer": STR,
    "answer_correct": BOOL,
    "reasoning_quality": {"type": "string", "enum": ["unclear", "flawed", "partial", "sound"]},
    "understanding_score": NUM,
    "misconceptions": {"type": "array", "items": _obj({
        "id": STR, "label": STR, "evidence_quote": STR, "confidence": NUM, "why": STR,
    })},
    "primary_misconception_id": STR,
    "strengths": {"type": "array", "items": STR},
    "feedback": STR,
    "recommended_modality": {"type": "string", "enum": MODALITY_IDS},
    "teacher_note": STR,
})


def diagnosis_messages(skill, question_text, answer, transcript, language, prior_active, gender):
    catalog = [{"id": m["id"], "label": m["label"], "description": m["description"]}
               for m in skill["misconceptions"]]
    system = f"""You are an expert primary-school maths teacher and learning scientist in India.
A child answered a diagnostic question OUT LOUD; you receive the speech-recognition transcript.
Your job: work out what the child is actually thinking and name the misconception behind any error.

How to read the transcript:
- It comes from speech recognition, so expect filler words, restarts, code-mixing (e.g. Hinglish),
  numbers written as words or digits ("teen bata chaar", "3/4"), and small recognition errors.
  Be charitable about recognition noise but strict about the maths reasoning.
- A correct final answer reached through faulty reasoning still counts as a misconception.
- Only report a misconception if the transcript contains evidence for it. Quote that evidence
  verbatim (in the transcript's own words/script) in evidence_quote.
- Prefer ids from the catalog. If the error is genuinely not in the catalog, use an id of the form
  "new_<short_snake_case>" with a clear label.
- confidence is 0..1. understanding_score is 0..1 (1 = correct answer AND sound reasoning).
- primary_misconception_id is the most important misconception to re-teach, or "" if none.
- recommended_modality: which re-teaching mode would most likely fix THIS misconception for THIS
  child: story, number_line, analogy (real-life), or visual (picture model / fraction bars).
- feedback: 2-3 warm sentences spoken directly to the child. Praise something specific they did,
  then gently point at the exact slip without lecturing. {_language_rule(language, gender)}
- strengths and teacher_note are for the teacher, in English. teacher_note: one or two sentences.
- If the child did not really answer (silence, off-topic), set reasoning_quality "unclear",
  answer_correct false, misconceptions [] and ask them kindly to try again in feedback."""
    user = json.dumps({
        "skill": skill["name"],
        "question": question_text,
        "correct_answer": answer,
        "misconception_catalog": catalog,
        "misconceptions_seen_before_for_this_child": prior_active,
        "child_language": _lang(language),
        "transcript": transcript,
    }, ensure_ascii=False, indent=1)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# --------------------------------------------------------------------------- re-teaching
LESSON_SCHEMA = _obj({
    "title": STR,
    "script": STR,
    "key_points": {"type": "array", "items": STR},
    "number_line": _obj({
        "show": BOOL, "min": NUM, "max": NUM, "step": NUM,
        "marks": {"type": "array", "items": _obj({"value": NUM, "label": STR, "highlight": BOOL})},
        "jumps": {"type": "array", "items": _obj({"from": NUM, "to": NUM, "label": STR})},
    }),
    "bars": _obj({
        "show": BOOL,
        "items": {"type": "array", "items": _obj({"label": STR, "parts": INT, "shaded": INT})},
    }),
    "check_question": STR,
    "check_answer": STR,
})


def lesson_messages(skill, misconception, modality, language, transcript, tried_modalities, gender):
    mode = MODALITIES[modality]
    system = f"""You are a gifted, warm maths teacher in India re-teaching ONE concept to a child
who just revealed a specific misconception while explaining their thinking out loud.

Re-teach using this modality: {mode['label']}. {mode['brief']}

Rules:
- Every number and comparison you state must be mathematically correct — check it.
- Target the misconception directly: make the child SEE why their idea breaks, then rebuild the
  correct idea. Do not just restate the rule.
- script: the narration that will be read aloud by a text-to-speech voice, 90-160 words. Talk to
  the child as "you". Write maths the way it is SPOKEN (e.g. "one by two", "ek bata do",
  "minus three", "zero point five"), never as symbols — no "/", "−", "×" or "=" in the script.
  Short sentences, natural pauses, no headings, no bullet points, no emojis.
- key_points: 2-4 very short on-screen takeaways; symbols like 1/2, −3, 0.5 are fine here.
- number_line: set show=true when a number line helps (always for the number_line modality).
  Choose min/max/step so all marks fit (at most 24 steps between min and max). marks are the
  points the script talks about, each placed at its EXACT numeric value (2/7 = 0.2857, not 0.14);
  highlight the key ones. jumps are arrows between values.
  If not used: show=false, min=0, max=1, step=1, marks=[], jumps=[].
- bars: set show=true for part-whole pictures (always for the visual modality). Each item is one
  whole split into `parts` equal parts with `shaded` of them coloured (0 <= shaded <= parts,
  parts <= 24). Use the same-sized wholes so they can be compared. If not used: show=false, items=[].
- check_question: one quick question to check the idea has landed; check_answer: its answer.
- {_language_rule(language, gender)}
- title: a short, friendly title for the lesson (in the child's language)."""
    user = json.dumps({
        "skill": skill["name"],
        "misconception": misconception,
        "what_the_child_said": transcript,
        "modalities_already_tried_for_this_misconception": tried_modalities,
        "child_language": _lang(language),
    }, ensure_ascii=False, indent=1)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# --------------------------------------------------------------------------- practice drills
DRILL_SCHEMA = _obj({
    "items": {"type": "array", "items": _obj({
        "prompt_display": STR,
        "prompt_spoken": STR,
        "expected_answer": STR,
        "hint": STR,
        "targets": STR,
    })},
})


def drill_messages(skill, misconception, language, modality, gender, count=4):
    target = (f"the misconception \"{misconception['label']}\" ({misconception['description']})"
              if misconception else f"the core ideas of {skill['name']}")
    system = f"""You design short SPOKEN practice drills for a child in India. The child hears each
question through a text-to-speech voice and answers out loud, so every item must be answerable in
one short spoken sentence — no writing, no long working.

Write exactly {count} items that target {target}.
- Order them from easy to harder. Make at least two items "trap" items where the misconception
  would give a specific wrong answer, and one transfer item in a fresh real-life context.
- Every item must be a complete, self-contained, unambiguous question with exactly one correct
  answer; it must contain every number the child needs.
- prompt_display: the full question as a sentence shown on screen (symbols like 1/2, −3, 0.45
  allowed), e.g. "Which is bigger: 1/2 or 2/7?" — never just a list of numbers.
- prompt_spoken: the SAME question written exactly as it should be SPOKEN, maths in words
  ("one by two", "minus three", "zero point four five"), no symbols. Under 30 words.
- expected_answer: REQUIRED, never empty — the short correct answer in symbols
  (e.g. "3/4", "−3", "0.9", "yes", "Riya").
- hint: one gentle sentence that nudges without giving the answer.
- targets: the misconception id it probes ("{misconception['id'] if misconception else 'core'}") or "core".
- If the child recently learned with a {MODALITIES.get(modality, {}).get('label', 'lesson')},
  echo that context in one or two items so the practice connects to the lesson.
- {_language_rule(language, gender)}"""
    user = json.dumps({"skill": skill["name"], "misconception": misconception,
                       "child_language": _lang(language)}, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


GRADE_SCHEMA = _obj({
    "student_answer": STR,
    "matches_expected": BOOL,
    "verdict": {"type": "string", "enum": ["unclear", "incorrect", "partial", "correct"]},
    "misconception_id": STR,
    "feedback": STR,
})


def grade_messages(skill, item, transcript, language, misconception_catalog, gender):
    system = f"""You grade a child's SPOKEN answer to a short maths drill question. The answer is a
speech-recognition transcript: numbers may appear as words or digits, in any Indian language or
code-mixed, with filler words. Judge the mathematics, not the phrasing.
Work in this order:
1. student_answer: the child's final answer rewritten in the SAME notation as expected_answer —
   convert number words from any language or romanisation to digits and symbols
   ("teen degree" -> "3°C", "ek bata do" -> "1/2", "minus teen" -> "−3", "zero point five" -> "0.5",
   "haan" -> "yes"). Use "" if no answer was given.
2. matches_expected: true if student_answer means the same as expected_answer (equivalent forms
   such as 2/4 = 1/2 or "3 degrees" = 3°C count as the same).
3. verdict: "correct" whenever matches_expected is true; otherwise partial (right idea, small slip
   or incomplete), incorrect, or unclear (no real answer heard).
- misconception_id: if the wrong answer matches a catalog misconception, give its id, else "".
- feedback: ONE or two short, warm sentences spoken to the child. If correct, celebrate briefly
  and say why it is right. If not, name the slip and give the correct answer with a reason.
  Write maths in spoken words, not symbols. {_language_rule(language, gender)}"""
    user = json.dumps({
        "skill": skill["name"],
        "question": item["prompt_display"],
        "expected_answer": item["expected_answer"],
        "misconception_catalog": misconception_catalog,
        "child_said": transcript,
    }, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


ANSWER_KEY_SCHEMA = _obj({"answers": {"type": "array", "items": STR}})


def answer_key_messages(questions):
    system = ("Solve each maths question for a primary-school answer key. Return one short final "
              "answer per question, in order, using digits and symbols (e.g. \"3/4\", \"−3\", "
              "\"0.9\", \"yes\"). No working, no explanations.")
    user = json.dumps({"questions": questions}, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# --------------------------------------------------------------------------- translation
TRANSLATE_SCHEMA = _obj({"text": STR})


def translate_messages(text, language):
    system = (f"Translate this maths question for a primary-school child into simple, natural "
              f"{_lang(language)} in its native script. Keep every number, fraction, decimal and "
              f"symbol exactly as written (1/2, −8, 0.125, 3,456, °C). Return only the translation.")
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]
