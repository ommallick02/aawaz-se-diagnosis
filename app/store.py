"""Tiny JSON-file store for student profiles and in-flight drill sessions."""
import json
import os
import threading
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        if self.path.exists():
            self.data = json.loads(self.path.read_text("utf-8"))
        else:
            self.data = {}
        self.data.setdefault("students", {})
        self.data.setdefault("drills", {})
        self.data.setdefault("translations", {})

    def save(self):
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
            os.replace(tmp, self.path)

    # students -------------------------------------------------------------
    def list_students(self):
        return sorted(self.data["students"].values(), key=lambda s: s["created_at"])

    def get_student(self, student_id):
        return self.data["students"].get(student_id)

    def create_student(self, name, grade, language, voice):
        student = {
            "id": uuid.uuid4().hex[:10],
            "name": name.strip() or "Student",
            "grade": grade,
            "language": language,
            "voice": voice,
            "created_at": time.time(),
            "mastery": {},         # skill_id -> {p, attempts, correct, updated_at}
            "history": [],         # [{ts, skill, p, event, detail}]
            "misconceptions": {},  # mc_id -> {skill, label, count, status, evidence, modalities}
            "modality_stats": {},  # modality -> {tries, successes}
            "sessions": [],        # recent diagnoses
            "asked": {},           # skill_id -> recently asked question ids
            "last_lesson": None,   # {misconception_id, modality, skill}
        }
        self.data["students"][student["id"]] = student
        self.save()
        return student

    def import_student(self, record):
        self.data["students"][record["id"]] = record
        self.save()
        return record

    # drills ---------------------------------------------------------------
    def create_drill(self, drill):
        drill_id = uuid.uuid4().hex[:12]
        drill["id"] = drill_id
        drill["created_at"] = time.time()
        self.data["drills"][drill_id] = drill
        # Keep only recent drills so the file stays small.
        if len(self.data["drills"]) > 200:
            oldest = sorted(self.data["drills"].values(), key=lambda d: d["created_at"])[:50]
            for d in oldest:
                self.data["drills"].pop(d["id"], None)
        self.save()
        return drill

    def get_drill(self, drill_id):
        return self.data["drills"].get(drill_id)

    # translation cache ----------------------------------------------------
    def get_translation(self, key):
        return self.data["translations"].get(key)

    def set_translation(self, key, text):
        self.data["translations"][key] = text
        self.save()
