import { MAX_SECONDS, VoiceRecorder } from "./recorder.js";
import { escapeHtml as esc, renderBars, renderMasteryChart, renderNumberLine, renderSkillMap } from "./viz.js";

const $ = (sel, root = document) => root.querySelector(sel);
const stage = $("#stage");
const player = $("#player");

const ICON = {
  play: '<svg viewBox="0 0 12 12"><path d="M2.5 1.5v9l8-4.5z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 12 12"><rect x="2" y="1.5" width="3" height="9" rx="1" fill="currentColor"/><rect x="7" y="1.5" width="3" height="9" rx="1" fill="currentColor"/></svg>',
  load: '<svg viewBox="0 0 12 12"><path d="M6 1a5 5 0 1 0 5 5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>',
  mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  stop: '<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor"/></svg>',
};

const state = {
  config: null,
  students: [],
  student: null,
  skillId: null,
  selectedSkill: null,
  question: null,
  diagnosis: null,
  lesson: null,
  lessonsSeen: new Set(),
  drill: null,
  trace: [],
  showTable: false,
};

// ------------------------------------------------------------------ API
function saveRecord(summary) {
  if (!summary?.record) return;
  try { localStorage.setItem(`aawaz.record.${summary.id}`, JSON.stringify(summary.record)); } catch { /* storage unavailable */ }
}

async function restoreStudent(id) {
  let record = null;
  try { record = JSON.parse(localStorage.getItem(`aawaz.record.${id}`)); } catch { /* ignore */ }
  if (!record) return false;
  const res = await fetch("/api/students/import", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ record }),
  });
  return res.ok;
}

async function api(path, opts = {}, retried = false) {
  try {
    return await rawApi(path, opts);
  } catch (e) {
    // A serverless instance may have lost the learner: restore from the browser's copy and retry once.
    if (!retried && e.message === "Student not found") {
      const id = state.student?.id || localStorage.getItem("aawaz.student");
      if (id && await restoreStudent(id)) return api(path, opts, true);
    }
    if (e.message === "Drill not found") throw new Error("This practice round expired on the server — please start a new one.");
    throw e;
  }
}

async function rawApi(path, { method = "GET", json, form } = {}) {
  const opts = { method, headers: {} };
  if (json) {
    opts.body = JSON.stringify(json);
    opts.headers["Content-Type"] = "application/json";
  }
  if (form) opts.body = form;
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON error */ }
  if (!res.ok) {
    const detail = body?.error || body?.detail;
    const msg = Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : detail;
    throw new Error(msg || `Request failed (${res.status})`);
  }
  if (body?.trace) addTrace(body.trace);
  saveRecord(body?.student || (body?.record ? body : null));
  return body;
}

const skillById = (id) => state.config.skills.find((s) => s.id === id);
const modalityById = (id) => state.config.modalities.find((m) => m.id === id);
const pct = (p) => (p == null ? "—" : `${Math.round(p * 100)}%`);
const langAttr = () => (state.student?.language || "hi-IN").split("-")[0];

// ------------------------------------------------------------------ audio
const ttsCache = new Map();
let activeBtn = null;

function speakFn(text, task) {
  return async () => {
    const key = `${state.student.language}|${state.student.voice}|${text}`;
    if (!ttsCache.has(key)) {
      const { id: student_id, language, voice } = state.student;
      const promise = api("/api/tts", { method: "POST", json: { student_id, language, voice, text, task } })
        .then((r) => r.audio_url)
        .catch((e) => { ttsCache.delete(key); throw e; });
      ttsCache.set(key, promise);
    }
    return ttsCache.get(key);
  };
}

function setBtn(btn, mode) {
  if (!btn) return;
  btn.classList.toggle("loading", mode === "loading");
  btn.classList.toggle("playing", mode === "playing");
  btn.querySelector(".icon").innerHTML = mode === "loading" ? ICON.load : mode === "playing" ? ICON.pause : ICON.play;
  btn.setAttribute("aria-label", mode === "playing" ? "Pause" : btn.dataset.label);
}

function stopAudio() {
  player.pause();
  setBtn(activeBtn, "idle");
  activeBtn = null;
}

player.addEventListener("ended", () => { setBtn(activeBtn, "idle"); activeBtn = null; });
player.addEventListener("pause", () => { if (activeBtn && !activeBtn.classList.contains("loading")) setBtn(activeBtn, "idle"); });

function playButton(label, getUrl, { autoplay = false } = {}) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "play";
  btn.dataset.label = label;
  btn.innerHTML = `<span class="icon">${ICON.play}</span><span>${esc(label)}</span>`;
  btn.setAttribute("aria-label", label);
  const start = async () => {
    if (activeBtn === btn && !player.paused) return stopAudio();
    stopAudio();
    activeBtn = btn;
    setBtn(btn, "loading");
    try {
      const url = await getUrl();
      if (activeBtn !== btn) return;
      player.src = url;
      setBtn(btn, "playing");
      await player.play();
    } catch (e) {
      if (activeBtn === btn) setBtn(btn, "idle");
      if (e.name !== "NotAllowedError" && e.name !== "AbortError") toast(`Couldn't play audio: ${e.message}`);
    }
  };
  btn.addEventListener("click", start);
  if (autoplay) setTimeout(start, 0);
  return btn;
}

// ------------------------------------------------------------------ UI helpers
let thinkingTimer = null;

function render(html) {
  clearInterval(thinkingTimer);
  stage.innerHTML = html;
  stage.scrollIntoView({ block: "nearest" });
  return stage;
}

function thinking(lines) {
  render(`<div class="thinking"><div class="spinner" aria-hidden="true"></div><div><b id="thinkLine">${esc(lines[0])}</b><small id="thinkSub">${esc(lines[1] || "")}</small></div></div>`);
  let i = 0;
  if (lines.length > 1) {
    thinkingTimer = setInterval(() => {
      i = Math.min(i + 1, lines.length - 1);
      const line = $("#thinkLine");
      if (!line) return clearInterval(thinkingTimer);
      line.textContent = lines[i];
      $("#thinkSub").textContent = lines[i + 1] || "";
    }, 2200);
  }
}

function errorBox(message, retry) {
  const box = document.createElement("div");
  box.className = "error";
  box.setAttribute("role", "alert");
  box.innerHTML = `<span>${esc(message)}</span>`;
  if (retry) {
    const b = document.createElement("button");
    b.className = "btn small";
    b.textContent = "Try again";
    b.onclick = retry;
    box.appendChild(b);
  }
  return box;
}

function showError(message, retry) {
  render("");
  stage.appendChild(errorBox(message, retry));
  const back = document.createElement("button");
  back.className = "btn link";
  back.textContent = "← Back to skills";
  back.onclick = viewSkills;
  stage.appendChild(back);
}

function toast(message) {
  const box = errorBox(message);
  stage.prepend(box);
  setTimeout(() => box.remove(), 6000);
}

function setStep(step) {
  const order = ["ask", "diagnose", "reteach", "practice"];
  const idx = order.indexOf(step);
  document.querySelectorAll("#stepper li").forEach((li) => {
    const i = order.indexOf(li.dataset.step);
    li.classList.toggle("active", i === idx);
    li.classList.toggle("done", idx > -1 && i < idx);
  });
}

function addTrace(entries) {
  entries.filter(Boolean).forEach((e) => state.trace.unshift({ ...e, at: new Date() }));
  state.trace = state.trace.slice(0, 40);
  const list = $("#traceList");
  list.innerHTML = state.trace.map((t) => {
    const cls = t.api === "Saaras" ? "api-saaras" : t.api === "Bulbul" ? "api-bulbul" : "api-llm";
    const ms = t.cached ? "cached" : t.ms >= 1000 ? `${(t.ms / 1000).toFixed(1)} s` : `${t.ms} ms`;
    return `<li><span class="api ${cls}">${esc(t.api)}</span><span>${esc(t.task)} <span class="tip-muted">· ${esc(t.model)}</span></span><span class="ms">${ms}</span></li>`;
  }).join("");
  $("#traceCount").textContent = `· ${state.trace.length} calls`;
}

// ------------------------------------------------------------------ answer input (mic / type / upload)
function answerBox(container, { onSubmit, compact = false, placeholder = "Type what you would say…" }) {
  container.innerHTML = `
    <div class="answer-box">
      <div class="mic-row">
        <button class="mic ${compact ? "small" : ""}" type="button" aria-label="Start recording">${ICON.mic}</button>
        <div class="mic-status" aria-live="polite"><b>Tap to speak</b><span>Tap again when you're done · up to ${MAX_SECONDS} seconds</span></div>
      </div>
      <div class="alt-inputs">
        <button class="btn link small" type="button" data-act="type">Type instead</button>
        <span aria-hidden="true">·</span>
        <label class="btn link small">Upload a recording<input type="file" accept="audio/*" hidden></label>
      </div>
      <div class="type-box" hidden>
        <textarea lang="${langAttr()}" placeholder="${esc(placeholder)}" aria-label="Your answer"></textarea>
        <div><button class="btn primary small" type="button" data-act="send">Submit answer</button></div>
      </div>
    </div>`;
  const mic = $(".mic", container);
  const status = $(".mic-status", container);
  const typeBox = $(".type-box", container);
  const textarea = $("textarea", container);
  let recorder = null;

  const setStatus = (title, sub) => { status.innerHTML = `<b>${esc(title)}</b><span>${esc(sub)}</span>`; };
  const openTyping = () => { typeBox.hidden = false; textarea.focus(); };

  if (!VoiceRecorder.supported()) {
    mic.disabled = true;
    setStatus("Microphone not available here", "Type your answer or upload a recording instead.");
  }

  const finish = async () => {
    if (!recorder) return;
    const r = recorder;
    recorder = null;
    mic.classList.remove("recording");
    mic.innerHTML = ICON.mic;
    mic.style.removeProperty("--level");
    const secs = (performance.now() - r.startedAt) / 1000;
    setStatus("Processing…", "");
    const result = await r.stop();
    if (!result || secs < 0.7) {
      setStatus("That was very short", "Tap the mic and explain your thinking in a sentence or two.");
      return;
    }
    onSubmit({ audio: result.blob, filename: result.filename });
  };

  mic.addEventListener("click", async () => {
    if (recorder) return finish();
    stopAudio();
    recorder = new VoiceRecorder({
      onLevel: (l) => mic.style.setProperty("--level", l.toFixed(2)),
      onTick: (s) => setStatus("Listening…", `0:${String(Math.floor(s)).padStart(2, "0")} · tap to finish`),
      onAutoStop: finish,
    });
    try {
      await recorder.start();
      mic.classList.add("recording");
      mic.innerHTML = ICON.stop;
      mic.setAttribute("aria-label", "Stop recording");
    } catch (e) {
      recorder = null;
      setStatus("Couldn't use the microphone", e.name === "NotAllowedError" ? "Allow microphone access, or type instead." : e.message);
      openTyping();
    }
  });
  $('[data-act="type"]', container).addEventListener("click", openTyping);
  $('[data-act="send"]', container).addEventListener("click", () => {
    const text = textarea.value.trim();
    if (!text) return textarea.focus();
    onSubmit({ text });
  });
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $('[data-act="send"]', container).click();
  });
  $('input[type="file"]', container).addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) onSubmit({ audio: file, filename: file.name });
  });
  return { cancel: () => recorder && recorder.cancel() };
}

function toForm(fields, answer) {
  const form = new FormData();
  Object.entries(fields).forEach(([k, v]) => form.append(k, v));
  if (answer.audio) form.append("audio", answer.audio, answer.filename || "speech.wav");
  else form.append("text", answer.text);
  return form;
}

// ------------------------------------------------------------------ views
function viewWelcome() {
  setStep(null);
  render(`
    <div class="welcome">
      <p class="eyebrow">Welcome</p>
      <h2>Let's hear how you think.</h2>
      <p class="lead">A maths tutor that listens to your explanation — in your language — and finds the exact idea that's tripping you up.</p>
      <ol class="how">
        <li><span class="num">1</span><span><b>Explain out loud.</b> Saaras turns your voice into text, even when you mix Hindi and English.</span></li>
        <li><span class="num">2</span><span><b>Get diagnosed.</b> Sarvam-105B spots the misconception behind your answer, not just whether it's right.</span></li>
        <li><span class="num">3</span><span><b>Learn it another way.</b> A story, number line, real-life example or picture — Bulbul narrates it.</span></li>
        <li><span class="num">4</span><span><b>Practise by speaking.</b> Spoken drills target your mistake and update your mastery graph.</span></li>
      </ol>
      <form id="welcomeForm" class="form-grid">
        <label class="field block"><span>Learner's name</span><input name="name" required maxlength="40" placeholder="e.g. Riya"></label>
        <label class="field block"><span>Class</span><select name="grade">${[3, 4, 5, 6, 7].map((g) => `<option ${g === 5 ? "selected" : ""}>${g}</option>`).join("")}</select></label>
        <label class="field block"><span>Language</span><select name="language">${langOptions("hi-IN")}</select></label>
        <label class="field block"><span>Voice</span><select name="voice">${voiceOptions("priya")}</select></label>
      </form>
      <div class="actions"><button class="btn primary" type="submit" form="welcomeForm">Start learning</button></div>
    </div>`);
  $("#welcomeForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    await createStudent(Object.fromEntries(new FormData(e.target)));
  });
}

function viewSkills() {
  stopAudio();
  setStep(null);
  const s = state.student;
  const stats = Object.fromEntries(s.skills.map((x) => [x.id, x]));
  const rec = s.recommended_skill && skillById(s.recommended_skill);
  const levelText = { not_started: "Not started", needs_help: "Needs help", developing: "Developing", mastered: "Mastered" };
  render(`
    <p class="eyebrow">Hi ${esc(s.name)} · Class ${s.grade}</p>
    <h2 style="font-size:22px;margin-bottom:14px">What shall we work on?</h2>
    ${rec ? `<div class="recommend">
      <div><div class="eyebrow" style="margin:0">Recommended next</div><div class="name">${esc(rec.name)} <span class="tip-muted" lang="hi" style="font-weight:500;font-size:14px">${esc(rec.name_hi)}</span></div>
      <div class="tip-muted" style="font-size:13px">${stats[rec.id].active_misconceptions ? "Has an open misconception to fix." : stats[rec.id].attempts ? `Mastery ${pct(stats[rec.id].p)} — let's push it past 80%.` : "Prerequisites look ready."}</div></div>
      <button class="btn primary" data-skill="${rec.id}">Start</button></div>` : ""}
    <div class="skill-grid">
      ${state.config.skills.map((sk) => {
        const st = stats[sk.id];
        return `<button class="skill-card" data-skill="${sk.id}">
          <span class="name">${esc(sk.name)}</span>
          <span class="sub" lang="hi">${esc(sk.name_hi)}</span>
          <span class="sub">${st.attempts ? `${pct(st.p)} · ${levelText[st.level]}` : "Not started"}${st.active_misconceptions ? ` · <span class="tip-alert">⚠ ${st.active_misconceptions} open</span>` : ""}</span>
          <span class="meter" aria-hidden="true"><i style="width:${st.attempts ? Math.round(st.p * 100) : 0}%"></i></span>
        </button>`;
      }).join("")}
    </div>`);
  stage.querySelectorAll("[data-skill]").forEach((b) => b.addEventListener("click", () => startSkill(b.dataset.skill)));
}

async function startSkill(skillId) {
  stopAudio();
  state.skillId = skillId;
  state.selectedSkill = skillId;
  state.lessonsSeen = new Set();
  state.lesson = null;
  state.diagnosis = null;
  renderSide();
  setStep("ask");
  thinking(["Picking a question…"]);
  try {
    state.question = await api(`/api/question?student_id=${state.student.id}&skill_id=${skillId}`);
    viewQuestion();
  } catch (e) {
    showError(e.message, () => startSkill(skillId));
  }
}

function viewQuestion() {
  setStep("ask");
  const q = state.question;
  const skill = skillById(state.skillId);
  render(`
    <p class="eyebrow">${esc(skill.name)} · Diagnostic question</p>
    <div class="question-text" lang="${langAttr()}">${esc(q.text)}</div>
    <div id="qplay"></div>
    <p class="lead">Answer <b>out loud</b> and say <b>how</b> you got it. Your reasoning is what we listen for — it's fine to mix languages.</p>
    <div id="answer"></div>
    <div class="actions">
      <button class="btn link" id="backBtn">← Choose another skill</button>
      <button class="btn link" id="otherBtn">Ask a different question</button>
    </div>`);
  $("#qplay").appendChild(playButton("Listen to the question", speakFn(q.text, "Read the question aloud"), { autoplay: true }));
  answerBox($("#answer"), { onSubmit: submitDiagnosis, placeholder: "e.g. I think 1/3 is bigger because 3 is bigger than 2…" });
  $("#backBtn").onclick = viewSkills;
  $("#otherBtn").onclick = () => startSkill(state.skillId);
}

async function submitDiagnosis(answer) {
  stopAudio();
  setStep("diagnose");
  thinking(answer.audio
    ? ["Saaras is transcribing your explanation…", "Sarvam-105B is looking for the idea behind your answer…", "Updating your mastery graph…"]
    : ["Sarvam-105B is looking for the idea behind your answer…", "Updating your mastery graph…"]);
  try {
    const form = toForm({ student_id: state.student.id, skill_id: state.skillId, question_id: state.question.question_id }, answer);
    const d = await api("/api/diagnose", { method: "POST", form });
    state.diagnosis = d;
    updateStudent(d.student);
    viewDiagnosis();
  } catch (e) {
    showError(e.message, viewQuestion);
  }
}

function deltaHtml(before, after) {
  if (before == null || after == null) return "";
  const cls = after > before + 0.005 ? "up" : after < before - 0.005 ? "down" : "";
  return `<span class="delta">${pct(before)}</span> → <span class="delta ${cls}">${pct(after)}</span>`;
}

function viewDiagnosis() {
  const d = state.diagnosis;
  const skill = skillById(state.skillId);
  const quality = { sound: ["good", "Sound reasoning"], partial: ["warn", "Partly sound reasoning"], flawed: ["bad", "Flawed reasoning"], unclear: ["", "Couldn't follow the reasoning"] }[d.reasoning_quality];
  const primary = d.misconceptions.find((m) => m.id === d.primary_misconception_id);
  const lang = d.stt?.language_code;
  render(`
    <p class="eyebrow">${esc(skill.name)} · Diagnosis</p>
    <div class="panel soft">
      <h4>${d.stt ? "What Saaras heard" : "Your answer"}</h4>
      <p class="transcript" lang="${langAttr()}">“${esc(d.transcript)}”</p>
      ${d.stt ? `<p class="transcript-meta">Detected language: ${esc(lang || "unknown")}${d.stt.language_probability ? ` · ${Math.round(d.stt.language_probability * 100)}% sure` : ""}</p>` : ""}
    </div>
    <div class="verdict">
      ${d.answer_correct ? '<span class="chip good">✓ Correct answer</span>' : `<span class="chip bad">✗ Answer not right${d.student_answer ? ` <span style="font-weight:500">(you said ${esc(d.student_answer)})</span>` : ""}</span>`}
      <span class="chip ${quality[0]}"><span class="dot"></span>${quality[1]}</span>
      <span class="chip info">Understanding ${pct(d.understanding_score)}</span>
    </div>
    ${d.misconceptions.length ? d.misconceptions.map((m) => `
      <div class="mc-card ${m.id === d.primary_misconception_id ? "" : "secondary"}">
        <div class="head">
          <span class="title">${m.id === d.primary_misconception_id ? "Misconception: " : "Also noticed: "}${esc(m.label)}</span>
          <span class="conf">confidence <span class="meter"><i style="width:${Math.round(m.confidence * 100)}%"></i></span> ${pct(m.confidence)}</span>
        </div>
        ${m.evidence_quote ? `<blockquote lang="${langAttr()}">“${esc(m.evidence_quote)}”</blockquote>` : ""}
        <p class="why">${esc(m.why || m.description)}${m.in_catalog ? "" : ' <span class="chip warn" style="font-size:11px;padding:1px 7px">new pattern</span>'}</p>
      </div>`).join("") : d.reasoning_quality !== "unclear" ? `<div class="panel"><h4>No misconception detected</h4><p>${d.strengths.length ? esc(d.strengths.join(" ")) : "Your reasoning holds up."}</p></div>` : ""}
    <div class="panel">
      <h4>Feedback for you</h4>
      <p class="feedback" lang="${langAttr()}">${esc(d.feedback)}</p>
      <div id="fbplay" style="margin-top:10px"></div>
    </div>
    ${d.mastery_after != null ? `<p class="tip-muted" style="font-size:14px">Mastery of ${esc(skill.name)}: ${deltaHtml(d.mastery_before, d.mastery_after)}</p>` : ""}
    ${d.teacher_note ? `<details class="note"><summary>Teacher's note</summary><p>${esc(d.teacher_note)}</p>${d.strengths.length ? `<p><b>Strengths:</b> ${esc(d.strengths.join("; "))}</p>` : ""}</details>` : ""}
    <div class="actions" id="dxActions"></div>`);
  $("#fbplay").appendChild(playButton("Hear feedback", speakFn(d.feedback, "Speak feedback"), { autoplay: true }));
  const actions = $("#dxActions");
  const add = (label, cls, fn) => {
    const b = document.createElement("button");
    b.className = `btn ${cls}`;
    b.textContent = label;
    b.onclick = fn;
    actions.appendChild(b);
  };
  if (primary) {
    add(`Re-teach: ${primary.label}`, "primary", () => startLesson(""));
    add("Skip to spoken practice", "", startDrill);
    add("Try another question", "ghost", () => startSkill(state.skillId));
  } else if (d.reasoning_quality === "unclear" && !d.answer_correct) {
    add("Try answering again", "primary", viewQuestion);
    add("Choose another skill", "ghost", viewSkills);
  } else {
    add("Practise with spoken drills", "primary", startDrill);
    add("Next question", "", () => startSkill(state.skillId));
    add("Choose another skill", "ghost", viewSkills);
  }
}

async function startLesson(modality) {
  stopAudio();
  setStep("reteach");
  const d = state.diagnosis;
  const label = modality ? modalityById(modality).label.toLowerCase() : "the best way to explain this";
  thinking([`Choosing ${label}…`, "Sarvam-105B is writing a lesson aimed at your exact mistake…", "Almost ready…"]);
  try {
    state.lesson = await api("/api/reteach", {
      method: "POST",
      json: {
        student_id: state.student.id, skill_id: state.skillId,
        misconception_id: d?.primary_misconception_id || "", modality,
        recommended: d?.recommended_modality || "", transcript: d?.transcript || "",
      },
    });
    state.lessonsSeen.add(state.lesson.modality);
    viewLesson();
  } catch (e) {
    showError(e.message, () => startLesson(modality));
  }
}

function viewLesson() {
  const L = state.lesson;
  const lesson = L.lesson;
  render(`
    <p class="eyebrow">Re-teach · ${esc(L.misconception.label)}</p>
    <div class="modality-tabs" role="group" aria-label="Ways to explain">
      ${state.config.modalities.map((m) => `<button type="button" data-mod="${m.id}" aria-pressed="${m.id === L.modality}" class="${state.lessonsSeen.has(m.id) ? "seen" : ""}">${esc(m.label)}</button>`).join("")}
    </div>
    <p class="reason">${esc(L.reason)}</p>
    <div class="lesson-title" lang="${langAttr()}">${esc(lesson.title)}</div>
    <div id="lplay"></div>
    <div id="visuals"></div>
    <div class="panel"><h4>Read along</h4><p class="script" lang="${langAttr()}">${esc(lesson.script)}</p></div>
    ${lesson.key_points.length ? `<div class="panel soft"><h4>Remember</h4><ul class="key-points" lang="${langAttr()}">${lesson.key_points.map((k) => `<li>${esc(k)}</li>`).join("")}</ul></div>` : ""}
    ${lesson.check_question ? `<div class="panel"><h4>Quick check — answer in your head</h4><p lang="${langAttr()}">${esc(lesson.check_question)}</p>
      <button class="btn link small reveal" id="revealBtn">Show answer</button><p id="checkAns" hidden lang="${langAttr()}" style="margin-top:6px;font-weight:600">${esc(lesson.check_answer)}</p></div>` : ""}
    <div class="actions">
      <button class="btn primary" id="practiceBtn">Start spoken practice</button>
      <button class="btn" id="anotherBtn">Explain it another way</button>
    </div>`);
  $("#lplay").appendChild(playButton("Listen to the lesson", speakFn(lesson.script, "Narrate lesson"), { autoplay: true }));
  const vis = $("#visuals");
  if (lesson.number_line.show) {
    const box = document.createElement("div");
    box.className = "visual";
    vis.appendChild(box);
    renderNumberLine(box, lesson.number_line);
  }
  if (lesson.bars.show) {
    const box = document.createElement("div");
    box.className = "visual";
    vis.appendChild(box);
    renderBars(box, lesson.bars.items);
  }
  stage.querySelectorAll("[data-mod]").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.mod !== L.modality) startLesson(b.dataset.mod);
  }));
  $("#revealBtn")?.addEventListener("click", (e) => { $("#checkAns").hidden = false; e.target.remove(); });
  $("#practiceBtn").onclick = startDrill;
  $("#anotherBtn").onclick = () => {
    const next = state.config.modalities.find((m) => !state.lessonsSeen.has(m.id));
    startLesson(next ? next.id : state.config.modalities.find((m) => m.id !== L.modality).id);
  };
}

async function startDrill() {
  stopAudio();
  setStep("practice");
  thinking(["Sarvam-105B is writing practice questions that target this mistake…", "Getting Bulbul ready to read them out…"]);
  try {
    const res = await api("/api/drills", {
      method: "POST",
      json: {
        student_id: state.student.id, skill_id: state.skillId,
        misconception_id: state.diagnosis?.primary_misconception_id || "",
        modality: state.lesson?.modality || "",
      },
    });
    state.drill = { id: res.drill_id, items: res.items, idx: 0, results: [] };
    // Warm Bulbul for every prompt so later items play instantly.
    res.items.forEach((it) => speakFn(it.spoken, "Speak drill prompt")().catch(() => {}));
    viewDrillItem();
  } catch (e) {
    showError(e.message, startDrill);
  }
}

function viewDrillItem() {
  const D = state.drill;
  const item = D.items[D.idx];
  const dots = D.items.map((_, i) => `<i class="${D.results[i]?.verdict || (i === D.idx ? "current" : "")}" title="Question ${i + 1}"></i>`).join("");
  render(`
    <p class="eyebrow">Spoken practice · ${D.idx + 1} of ${D.items.length}</p>
    <div class="progress-dots" aria-hidden="true">${dots}</div>
    <div class="drill-prompt" lang="${langAttr()}">${esc(item.prompt)}</div>
    <div id="dplay"></div>
    <p><button class="btn link small" id="hintBtn">Need a hint?</button></p>
    <p id="hint" hidden class="panel soft" lang="${langAttr()}">${esc(item.hint)}</p>
    <div id="answer"></div>
    <div id="result"></div>`);
  $("#dplay").appendChild(playButton("Hear the question", speakFn(item.spoken, "Speak drill prompt"), { autoplay: true }));
  $("#hintBtn").onclick = (e) => { $("#hint").hidden = false; e.target.remove(); };
  answerBox($("#answer"), { onSubmit: submitDrillAnswer, compact: true, placeholder: "Type your answer…" });
}

async function submitDrillAnswer(answer) {
  stopAudio();
  const D = state.drill;
  const resultBox = $("#result");
  $("#answer").hidden = true;
  resultBox.innerHTML = `<div class="thinking"><div class="spinner"></div><div><b>${answer.audio ? "Saaras is listening, Sarvam-105B is checking…" : "Sarvam-105B is checking…"}</b></div></div>`;
  try {
    const r = await api(`/api/drills/${D.id}/answer`, { method: "POST", form: toForm({ item_index: D.idx }, answer) });
    if (r.verdict === "unclear") {
      $("#answer").hidden = false;
    } else {
      D.results[D.idx] = r;
    }
    if (r.mastery != null) {
      const sk = state.student.skills.find((s) => s.id === state.skillId);
      if (sk) { sk.p = r.mastery; sk.attempts += 1; }
      refreshStudent();
    }
    const head = { correct: "✓ Correct!", partial: "Almost there", incorrect: "Not quite", unclear: "I couldn't catch an answer" }[r.verdict];
    const last = D.idx === D.items.length - 1;
    resultBox.innerHTML = `
      <div class="result ${r.verdict}" role="status">
        <b>${head}</b>
        <p class="feedback" lang="${langAttr()}" style="margin:6px 0 0">${esc(r.feedback)}</p>
        <p class="heard">${answer.audio ? "Saaras heard" : "You wrote"}: “<span lang="${langAttr()}">${esc(r.transcript)}</span>”${r.student_answer && r.student_answer !== r.transcript ? ` → understood as <b>${esc(r.student_answer)}</b>` : ""}${r.verdict !== "correct" && r.verdict !== "unclear" ? ` · Expected: <b>${esc(r.expected_answer)}</b>` : ""}</p>
        <div id="fb2" style="margin-top:10px"></div>
      </div>
      ${r.verdict === "unclear" ? "" : `<div class="actions"><button class="btn primary" id="nextBtn">${last ? "See how you did" : "Next question →"}</button></div>`}`;
    $("#fb2").appendChild(playButton("Hear feedback", speakFn(r.feedback, "Speak drill feedback"), { autoplay: true }));
    $("#nextBtn")?.addEventListener("click", () => {
      if (last) finishDrill();
      else { D.idx += 1; viewDrillItem(); }
    });
  } catch (e) {
    $("#answer").hidden = false;
    resultBox.innerHTML = "";
    resultBox.appendChild(errorBox(e.message));
  }
}

async function finishDrill() {
  stopAudio();
  thinking(["Updating your mastery graph…"]);
  try {
    const r = await api(`/api/drills/${state.drill.id}/finish`, { method: "POST" });
    updateStudent(r.student);
    viewSummary(r);
  } catch (e) {
    showError(e.message, finishDrill);
  }
}

function viewSummary(r) {
  setStep("practice");
  const skill = skillById(state.skillId);
  const mod = r.modality && modalityById(r.modality);
  const statusText = { active: "Still active — we'll keep working on it", resolving: "Getting better — one more clean round to resolve it", resolved: "Resolved!" };
  const correct = state.drill.results.filter((x) => x?.verdict === "correct").length;
  render(`
    <p class="eyebrow">${esc(skill.name)} · Practice complete</p>
    <h2 style="font-size:22px">${r.accuracy >= 0.75 ? "Great work!" : r.accuracy >= 0.5 ? "Good effort — getting there." : "This one needs another look."}</h2>
    <div class="stat-row">
      <div class="stat"><div class="label">Score</div><div class="value">${correct}<small> / ${r.total} correct</small></div></div>
      <div class="stat"><div class="label">Mastery</div><div class="value" style="font-size:20px">${deltaHtml(r.mastery_before, r.mastery_after)}</div></div>
      ${r.misconception_status ? `<div class="stat"><div class="label">Misconception</div><div class="value" style="font-size:16px"><span class="status ${r.misconception_status}">${r.misconception_status}</span></div><div class="tip-muted" style="font-size:12.5px;margin-top:4px">${statusText[r.misconception_status]}</div></div>` : ""}
    </div>
    ${mod ? `<p class="lead">${r.modality_worked ? `The <b>${esc(mod.label.toLowerCase())}</b> explanation worked for you — we'll use it more often.` : `The <b>${esc(mod.label.toLowerCase())}</b> explanation didn't fully land, so next time we'll try a different way.`}</p>` : ""}
    <div class="actions" id="sumActions"></div>`);
  const actions = $("#sumActions");
  const add = (label, cls, fn) => {
    const b = document.createElement("button");
    b.className = `btn ${cls}`;
    b.textContent = label;
    b.onclick = fn;
    actions.appendChild(b);
  };
  if (r.misconception_id && !r.modality_worked) add("Re-teach it another way", "primary", () => {
    const next = state.config.modalities.find((m) => !state.lessonsSeen.has(m.id));
    startLesson(next ? next.id : "");
  });
  add("New diagnostic question", r.misconception_id && !r.modality_worked ? "" : "primary", () => startSkill(state.skillId));
  add("Choose another skill", "ghost", viewSkills);
}

// ------------------------------------------------------------------ side panel
function renderSide() {
  const s = state.student;
  if (!s) return;
  $("#side").hidden = false;
  const selected = state.selectedSkill || state.skillId || s.recommended_skill || state.config.skills[0].id;
  renderSkillMap($("#skillMap"), state.config.skills, s.skills, selected, (id) => { state.selectedSkill = id; renderSide(); });
  const levelText = { not_started: "Not started", needs_help: "Needs help", developing: "Developing", mastered: "Mastered" };
  $("#skillTable tbody").innerHTML = s.skills.map((x) => `<tr><td>${esc(skillById(x.id).name)}</td><td class="num">${x.attempts ? pct(x.p) : "—"}</td><td>${levelText[x.level]}</td><td class="num">${x.active_misconceptions || ""}</td></tr>`).join("");
  $("#skillMap").hidden = state.showTable;
  $("#skillTable").hidden = !state.showTable;

  const skill = skillById(selected);
  $("#chartTitle").textContent = `Mastery over time — ${skill.name}`;
  const chartBox = $("#masteryChart");
  chartBox.querySelector(".chart-legend")?.remove();
  const history = s.history.filter((h) => h.skill === selected);
  renderMasteryChart(chartBox, history, skill.name);
  if (history.length) {
    const legend = document.createElement("div");
    legend.className = "chart-legend";
    legend.innerHTML = '<span><i class="filled"></i>Spoken diagnosis</span><span><i></i>Practice drill</span>';
    chartBox.appendChild(legend);
  }

  const mcs = s.misconceptions;
  $("#mcList").innerHTML = mcs.length ? mcs.map((m) => `
    <li>
      <div class="top"><span class="lbl">${esc(m.label)}</span><span class="status ${m.status}">${m.status}</span></div>
      <div class="meta">${esc(m.skill_name)} · seen ${m.count}×${Object.keys(m.modalities).length ? ` · tried ${Object.keys(m.modalities).map((k) => modalityById(k)?.label.toLowerCase()).join(", ")}` : ""}</div>
      ${m.evidence?.[0] ? `<div class="meta" lang="${langAttr()}" style="margin-top:3px">“${esc(m.evidence[0])}”</div>` : ""}
    </li>`).join("") : '<li class="empty" style="border:none;padding:0">No misconceptions recorded yet.</li>';

  const ms = s.modality_stats;
  $("#modalityStats").innerHTML = Object.keys(ms).length
    ? state.config.modalities.map((m) => {
        const st = ms[m.id];
        if (!st) return `<li><span>${esc(m.label)}</span><span class="meter"><i style="width:0"></i></span><span class="num">not tried</span></li>`;
        return `<li><span>${esc(m.label)}</span><span class="meter"><i style="width:${Math.round((st.successes / st.tries) * 100)}%"></i></span><span class="num">${st.successes}/${st.tries} worked</span></li>`;
      }).join("")
    : '<li class="empty">Finish a practice round after a lesson to learn which explanations work best.</li>';
}

function refreshStudent() { renderSide(); }

function updateStudent(summary) {
  state.student = summary;
  renderSide();
}

// ------------------------------------------------------------------ controls & boot
function langOptions(selected) {
  return state.config.languages.map((l) => `<option value="${l.code}" ${l.code === selected ? "selected" : ""}>${esc(l.name)} · ${esc(l.english)}</option>`).join("");
}
function voiceOptions(selected) {
  return state.config.voices.map((v) => `<option value="${v.id}" ${v.id === selected ? "selected" : ""}>${esc(v.label)} (${v.gender})</option>`).join("");
}

function renderControls() {
  $("#controls").hidden = !state.student;
  if (!state.student) return;
  $("#studentSelect").innerHTML = state.students.map((s) => `<option value="${s.id}" ${s.id === state.student.id ? "selected" : ""}>${esc(s.name)} · Class ${s.grade}</option>`).join("");
  $("#langSelect").innerHTML = langOptions(state.student.language);
  $("#voiceSelect").innerHTML = voiceOptions(state.student.voice);
}

async function createStudent(fields) {
  try {
    const s = await api("/api/students", { method: "POST", json: { ...fields, grade: Number(fields.grade) } });
    state.students = await api("/api/students");
    await loadStudent(s.id);
  } catch (e) {
    toast(e.message);
  }
}

async function loadStudent(id) {
  stopAudio();
  state.student = await api(`/api/students/${id}`);
  state.selectedSkill = null;
  state.skillId = null;
  try { localStorage.setItem("aawaz.student", id); } catch { /* storage unavailable */ }
  renderControls();
  renderSide();
  viewSkills();
}

async function patchStudent(fields) {
  stopAudio();
  state.student = await api(`/api/students/${state.student.id}`, { method: "PATCH", json: fields });
  renderControls();
  renderSide();
  // Content already on screen is in the old language/voice; restart from the current question.
  if (fields.language && state.skillId) startSkill(state.skillId);
}

async function boot() {
  try {
    state.config = await api("/api/config");
    state.students = await api("/api/students");
  } catch (e) {
    render("");
    stage.appendChild(errorBox(`Couldn't reach the server: ${e.message}`, boot));
    return;
  }
  $("#dialogLang").innerHTML = langOptions("hi-IN");
  $("#dialogVoice").innerHTML = voiceOptions("priya");
  let saved = null;
  try { saved = localStorage.getItem("aawaz.student"); } catch { /* storage unavailable */ }
  const pick = state.students.find((s) => s.id === saved) || state.students[state.students.length - 1];
  if (pick) await loadStudent(pick.id);
  else viewWelcome();
}

$("#studentSelect").addEventListener("change", (e) => loadStudent(e.target.value));
$("#langSelect").addEventListener("change", (e) => patchStudent({ language: e.target.value }));
$("#voiceSelect").addEventListener("change", (e) => patchStudent({ voice: e.target.value }));
$("#newStudentBtn").addEventListener("click", () => $("#studentDialog").showModal());
$("#studentDialog").addEventListener("close", async () => {
  const dlg = $("#studentDialog");
  if (dlg.returnValue !== "ok") return;
  const form = $("#studentForm");
  await createStudent(Object.fromEntries(new FormData(form)));
  form.reset();
});
$("#mapTableToggle").addEventListener("click", (e) => {
  state.showTable = !state.showTable;
  e.target.setAttribute("aria-pressed", String(state.showTable));
  e.target.textContent = state.showTable ? "Graph view" : "Table view";
  renderSide();
});

boot();
