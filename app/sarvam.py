"""Async client for the three Sarvam AI APIs the app is built on.

  Saaras      speech-to-text    POST /speech-to-text
  Bulbul      text-to-speech    POST /text-to-speech
  Sarvam-105B chat completions  POST /v1/chat/completions (structured JSON output)

Every call returns a `meta` dict ({api, model, task, ms}) so the UI can show
which model handled each step of the pipeline and how long it took.
"""
import asyncio
import base64
import json
import logging
import os
import re
import time

import httpx

BASE_URL = "https://api.sarvam.ai"
log = logging.getLogger("aawaz.sarvam")
STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4")
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
LLM_MODEL = os.getenv("SARVAM_LLM_MODEL", "sarvam-105b")
# Reasoning makes Sarvam-105B slower and can eat the whole token budget before the
# JSON is written, so it is off unless SARVAM_REASONING is set (low|medium|high).
REASONING = os.getenv("SARVAM_REASONING", "").strip() or None

TTS_MAX_CHARS = 2400
TTS_CHUNK_CHARS = 160
# Bulbul's tail latency is spiky (the same request can take 3 s or 20 s), so each attempt
# gets a short read timeout and a stalled request is retried; the last attempt waits longer.
# (Racing duplicate requests and cancelling the loser was faster locally, but on Vercel's
# Python runtime the response never completed after the cancellation.)
TTS_ATTEMPT_TIMEOUTS = (6.0, 8.0, 30.0)
RETRY_STATUSES = {429, 500, 502, 503, 504}


class SarvamError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _error_message(resp):
    try:
        err = resp.json().get("error", {})
        return err.get("message") or resp.text[:300]
    except ValueError:
        return resp.text[:300]


class Sarvam:
    def __init__(self, api_key):
        if not api_key:
            raise RuntimeError("SARVAM_API_KEY is not set — add it to .env")
        self.api_key = api_key
        self.http = httpx.AsyncClient(base_url=BASE_URL, timeout=httpx.Timeout(120, connect=15))

    async def close(self):
        await self.http.aclose()

    async def _post(self, path, attempt_timeouts=None, **kwargs):
        headers = {"api-subscription-key": self.api_key}
        if path.startswith("/v1/"):
            headers["Authorization"] = f"Bearer {self.api_key}"
        for attempt in range(3):
            if attempt_timeouts:
                kwargs["timeout"] = httpx.Timeout(attempt_timeouts[attempt], connect=10)
            started = time.perf_counter()
            try:
                resp = await self.http.post(path, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                log.warning("sarvam %s attempt %d failed after %d ms: %r", path, attempt + 1, _ms(started), exc)
                if attempt == 2:
                    raise SarvamError(f"Could not reach Sarvam API: {exc!r}") from exc
                if not isinstance(exc, httpx.TimeoutException):
                    await asyncio.sleep(1.5 * (attempt + 1))
                continue
            log.info("sarvam %s attempt %d -> %d in %d ms", path, attempt + 1, resp.status_code, _ms(started))
            if resp.status_code in RETRY_STATUSES and attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                status = 401 if resp.status_code == 403 else 502
                raise SarvamError(f"Sarvam {path} failed ({resp.status_code}): {_error_message(resp)}", status)
            return resp.json()

    # ---------------------------------------------------------------- Saaras (STT)
    async def transcribe(self, audio, filename="speech.wav", content_type="audio/wav",
                         language_code="unknown", keyterms=None, task="Transcribe speech"):
        data = {"model": STT_MODEL, "language_code": language_code or "unknown"}
        if keyterms and STT_MODEL == "saaras:v4":
            terms = [t[:64] for t in dict.fromkeys(keyterms)][:50]
            data["keyterms"] = json.dumps(terms, ensure_ascii=False)
        if STT_MODEL == "saaras:v3":
            data["mode"] = "codemix"
        start = time.perf_counter()
        body = await self._post("/speech-to-text", data=data,
                                files={"file": (filename, audio, content_type or "application/octet-stream")})
        meta = {"api": "Saaras", "model": STT_MODEL, "task": task, "ms": _ms(start)}
        return {
            "transcript": (body.get("transcript") or "").strip(),
            "language_code": body.get("language_code"),
            "language_probability": body.get("language_probability"),
        }, meta

    # ---------------------------------------------------------------- Bulbul (TTS)
    async def speak(self, text, language_code, speaker="priya", pace=1.0, task="Speak"):
        """Return MP3 bytes (about a tenth the size of WAV, which keeps long lessons well under
        serverless response limits when audio is sent inline). Bulbul's latency grows with text length, so longer text is
        split at sentence boundaries, synthesized in parallel and stitched back together."""
        chunks = _split_for_tts(text)
        start = time.perf_counter()
        limit = asyncio.Semaphore(6)

        async def one(chunk):
            async with limit:
                return await self._post("/text-to-speech", attempt_timeouts=TTS_ATTEMPT_TIMEOUTS, json={
                    "text": chunk, "language_code": language_code, "model": TTS_MODEL,
                    "speaker": speaker, "pace": pace, "speech_sample_rate": 22050,
                    "output_audio_codec": "mp3",
                })

        results = await asyncio.gather(*[one(chunk) for chunk in chunks])
        # MP3 is a stream of self-contained frames, so chunks can simply be joined.
        clips = [base64.b64decode(r["audios"][0]) for r in results]
        meta = {"api": "Bulbul", "model": TTS_MODEL, "task": task, "ms": _ms(start)}
        return b"".join(clips), meta

    # ---------------------------------------------------------------- Sarvam-105B (LLM)
    async def chat_json(self, messages, schema, name, task="Reason", max_tokens=3000,
                        temperature=0.3):
        """Chat completion returning JSON shaped like `schema`; returns (dict, meta).

        Uses JSON mode with the schema in the prompt rather than strict `json_schema`
        decoding: on nested schemas the constrained decoder tends to loop on whitespace
        until it runs out of tokens. The reply is then coerced to the schema in code.
        """
        start = time.perf_counter()
        messages = [dict(m) for m in messages]
        messages[0]["content"] += (
            "\n\nRespond with ONE compact JSON object (no markdown, no indentation, no wrapper key) "
            f"whose top-level keys are exactly {list(schema['properties'])} and that validates "
            f"against this JSON Schema:\n{json.dumps(schema, separators=(',', ':'))}")
        body = {
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_effort": REASONING,
            "response_format": {"type": "json_object"},
        }
        result = await self._post("/v1/chat/completions", json=body)
        parsed = _parse_json(result)
        if parsed is None:
            body["reasoning_effort"] = None
            body["max_tokens"] = max_tokens * 2
            body["temperature"] = 0.2
            result = await self._post("/v1/chat/completions", json=body)
            parsed = _parse_json(result)
        if parsed is None:
            raise SarvamError("Sarvam-105B did not return valid JSON — please try again")
        # Unwrap {"some_name": {...the real object...}} replies.
        if (isinstance(parsed, dict) and len(parsed) == 1 and isinstance(next(iter(parsed.values())), dict)
                and next(iter(parsed)) not in schema["properties"]):
            parsed = next(iter(parsed.values()))
        usage = result.get("usage") or {}
        meta = {"api": "Sarvam-105B", "model": LLM_MODEL, "task": task, "ms": _ms(start),
                "tokens": usage.get("total_tokens")}
        return conform(parsed, schema), meta


def _ms(start):
    return int((time.perf_counter() - start) * 1000)


def _parse_json(result):
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not content:
        return None
    content = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, re.S)
    if fenced:
        content = fenced.group(1)
    try:
        return json.loads(content)
    except ValueError:
        match = re.search(r"\{.*\}", content, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except ValueError:
                return None
    return None


def conform(value, schema):
    """Coerce a parsed reply into `schema`: fill missing keys, fix types, and fall back
    to the first enum value (enums list their safest value first)."""
    kind = schema.get("type")
    if "enum" in schema:
        return value if value in schema["enum"] else schema["enum"][0]
    if kind == "object":
        value = value if isinstance(value, dict) else {}
        return {k: conform(value.get(k), sub) for k, sub in schema["properties"].items()}
    if kind == "array":
        return [conform(v, schema["items"]) for v in value] if isinstance(value, list) else []
    if kind == "string":
        return value if isinstance(value, str) else ("" if value is None else str(value))
    if kind in ("number", "integer"):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0
        return int(round(number)) if kind == "integer" else number
    if kind == "boolean":
        if isinstance(value, str):
            return value.strip().lower() in ("true", "yes", "1")
        return bool(value)
    return value


def _split_for_tts(text, target=TTS_CHUNK_CHARS):
    text = text.strip()
    if len(text) <= target:
        return [text]
    sentences = re.split(r"(?<=[.!?।])\s+", text)
    chunks, current = [], ""
    for sentence in sentences:
        while len(sentence) > TTS_MAX_CHARS:
            chunks.append(sentence[:TTS_MAX_CHARS])
            sentence = sentence[TTS_MAX_CHARS:]
        if current and len(current) + len(sentence) + 1 > target:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks
