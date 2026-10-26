# Aawaz se Diagnosis — Spoken Misconception Detector

**आवाज़ से डायग्नोसिस.** A maths tutor that *listens* to a child explain their reasoning out loud, in their own language, works out which misconception is behind the answer, re-teaches that idea another way, and then runs spoken practice drills that update a per-skill mastery graph.

It is built on three [Sarvam AI](https://www.sarvam.ai) models:

| Model | API | What it does here |
|---|---|---|
| **Saaras v4** | `POST /speech-to-text` | Transcribes the child's spoken reasoning and drill answers. Handles code-mixed Hinglish and is biased with each skill's key terms (`भिन्न`, `denominator`, …). |
| **Sarvam-105B** | `POST /v1/chat/completions` | Classifies the misconception (with a verbatim evidence quote and a confidence score), writes the re-teaching lesson, generates targeted drills, grades spoken answers, and translates questions. |
| **Bulbul v3** | `POST /text-to-speech` | Reads questions, feedback, lessons and drills aloud in 11 Indian languages, with a choice of voices. |

## The learning loop

1. **Ask.** The app picks a diagnostic question for the chosen skill (or the recommended next skill) and Bulbul reads it out.
2. **Diagnose.** The child taps the mic and explains *how* they got the answer. Saaras transcribes it, and Sarvam-105B compares the reasoning against the skill's misconception catalog. For example, "1/3 बड़ा है क्योंकि 3, 2 से बड़ा है" is classified as *Bigger denominator → bigger fraction*. A correct answer reached through faulty reasoning still counts as a misconception. Errors outside the catalog get a new `new_*` label.
3. **Re-teach adaptively.** The lesson uses one of four modalities: **story**, **number line**, **real-life analogy**, or **picture model** (fraction bars). The first choice is Sarvam-105B's recommendation for that misconception. If an explanation doesn't land (the drills afterwards score below 75%), the next lesson switches to a modality that hasn't been tried, preferring whatever has worked best for this learner. Number lines and fraction bars are drawn from structured data the model returns; mark positions are checked against their labels.
4. **Practise by speaking.** Sarvam-105B writes four targeted drills, including "trap" items where the misconception would give a specific wrong answer. Bulbul speaks each one, the child answers aloud, and Saaras plus Sarvam-105B grade the answer. The grader first converts "teen bata chaar" into "3/4", then compares.
5. **Mastery graph.** Each observation updates a Bayesian Knowledge Tracing estimate for the skill. The side panel shows:
   - a prerequisite **skill map** with mastery bars and open-misconception badges
   - a **mastery-over-time** chart per skill
   - a **misconception log** with each misconception's lifecycle (active → resolving → resolved)
   - which explanation styles have worked for this learner

The **Sarvam pipeline** panel under the main card shows every API call, the model that handled it, and its latency.

### Curriculum

There are 9 skills, from place value to adding fractions, each with 3 catalogued misconceptions and 2–3 questions designed to make the child explain their reasoning. Questions are authored in English and Hindi, and Sarvam-105B translates them on demand (cached) for Bengali, Marathi, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi and Odia. Everything lives in [`app/curriculum.py`](app/curriculum.py) and is easy to extend.

## Run locally

Requires Python 3.10+.

```bash
pip install -r requirements.txt
cp .env.example .env        # then put your Sarvam key in .env
python -m uvicorn app.main:app --port 8765 --reload
```

Open <http://localhost:8765>. Microphone access needs `localhost` or HTTPS. If a mic isn't available, you can type an answer or upload a recording instead.

## Configuration

| Variable | Default | |
|---|---|---|
| `SARVAM_API_KEY` | — | **Required.** Read from the environment or `.env`. Never commit it. |
| `SARVAM_STT_MODEL` | `saaras:v4` | `saaras:v3` also works (uses `codemix` mode). |
| `SARVAM_TTS_MODEL` | `bulbul:v3` | |
| `SARVAM_LLM_MODEL` | `sarvam-105b` | |
| `SARVAM_REASONING` | off | `low`/`medium`/`high` turns on Sarvam-105B reasoning: more careful, but about 10× slower. |
| `AAWAZ_DATA_DIR` | `./data` (`/tmp/aawaz` on Vercel) | Where learner profiles and the audio cache are stored. |

## Deployment (Vercel)

`index.py` exposes the FastAPI app and `vercel.json` routes every path to it. The GitHub Actions workflow in `.github/workflows/deploy.yml` deploys on every push to `main`, using these **GitHub repository secrets** (no keys are stored in the repo):

| Secret | Purpose |
|---|---|
| `SARVAM_API_KEY` | Passed to the Vercel deployment as a runtime environment variable. |
| `VERCEL_TOKEN` | A Vercel access token (Vercel → Account Settings → Tokens). |
| `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` | From `.vercel/project.json` after `vercel link`. |

On Vercel the disk is ephemeral. Learner profiles live in `/tmp`, and the browser keeps a backup copy that it restores automatically if a fresh instance doesn't know the learner. Audio is returned inline as data URIs.

> **Note:** a public deployment spends your Sarvam credits for anyone who opens it.

## Implementation notes

- **Structured output.** Sarvam-105B's strict `json_schema` mode looped on whitespace for nested schemas. The app uses JSON mode with the schema in the prompt, then coerces the reply to the schema in code (`conform()` in `app/sarvam.py`).
- **Latency.** With reasoning off, each Sarvam-105B call takes about 1–3 s. Narration is requested as MP3 (about a tenth the size of WAV, so a long lesson sent inline stays well under Vercel’s 4.5 MB response limit). Bulbul’s tail latency is spiky (the same request measured 3 s and 22 s), so long text is split into sentence chunks that are synthesized in parallel, and each chunk request has a short read timeout (6 s, then 8 s, then 30 s) with a retry. Narration is fetched separately from the main response, so text appears first.
- **Speakable maths.** Bulbul reads "−8" as "eight", so signs and units are spelled out before synthesis.
- **Gendered speech.** Prompts tell the model the narrator voice's gender so Hindi verb forms match it ("मैं दिखाती हूँ" vs "दिखाता हूँ").

## Project layout

```
app/
  main.py        FastAPI routes: question → diagnose → reteach → drills
  sarvam.py      Saaras / Bulbul / Sarvam-105B client (retries, hedging, JSON coercion)
  prompts.py     Prompts + JSON schemas for every Sarvam-105B call
  learner.py     BKT mastery, misconception lifecycle, adaptive modality choice
  curriculum.py  Skills, prerequisites, misconception catalog, question bank
  store.py       JSON-file store
static/          Vanilla JS front end (recorder → 16 kHz WAV, SVG skill map / charts / number line)
index.py         Vercel entrypoint
```
