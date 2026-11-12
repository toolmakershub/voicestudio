"""
Offline Voice Studio
Local text-to-speech with voice cloning (Chatterbox, MIT license).
Runs fully offline after the one-time model download.

v0.2: background generation jobs, sentence-by-sentence streaming playback,
      MP3 export and SRT subtitles.
v0.3: Indian-language engine (IndicF5) running as a separate worker process.
v0.4: automatic sample transcripts (Whisper), number/currency/date clean-up for
      Indian languages, pronunciation dictionary, one-engine-on-GPU swapping.
"""
import copy
import json
import os
import queue
import re
import shutil
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response

BASE = Path(__file__).parent
DATA = BASE / "data"
VOICES = DATA / "voices"
OUTPUTS = DATA / "outputs"
JOBS_DIR = DATA / "jobs"
DB_PATH = DATA / "studio.db"
for d in (VOICES, OUTPUTS, JOBS_DIR):
    d.mkdir(parents=True, exist_ok=True)

MAX_TEXT = 20000         # characters per job
CHUNK_CHARS = 280        # model works best on short chunks
FIRST_CHUNK_CHARS = 120  # short first chunk -> playback starts sooner
GAP_SEC = 0.25           # silence between chunks
MIN_REF_SEC, MAX_REF_SEC = 5, 15   # IndicF5 only uses the first 15 s of a sample
INDIC_URL = os.environ.get("VS_INDIC_URL", "http://127.0.0.1:7861")
ENGINES = {"chatterbox": "English (Chatterbox)", "indic": "Indian languages (IndicF5)"}

app = FastAPI(title="Offline Voice Studio")

# ---------------------------------------------------------------- model ----
_model = None
_default_conds = None
_device = None
_load_error = None
_load_lock = threading.Lock()


def _pick_device():
    import torch
    forced = os.environ.get("VS_DEVICE")
    if forced:
        return forced
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def get_model():
    global _model, _default_conds, _device, _load_error, _cb_where
    if _model is not None:
        return _model
    with _load_lock:
        if _model is None:
            from chatterbox.tts import ChatterboxTTS
            dev = _pick_device()
            try:
                m = ChatterboxTTS.from_pretrained(device=dev)
            except Exception as e:  # e.g. MPS quirks -> fall back to CPU
                if dev == "cpu":
                    _load_error = str(e)
                    raise
                print(f"[warn] loading on {dev} failed ({e}); using CPU")
                dev = "cpu"
                m = ChatterboxTTS.from_pretrained(device=dev)
            _default_conds = _move(copy.deepcopy(m.conds), dev)
            _device = dev
            _cb_where = dev
            _model = m
            print(f"[ok] model loaded on {dev}")
    return _model


# ------------------------------------------------------------------- db ----
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS voices(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, file TEXT NOT NULL,
            seconds REAL, created REAL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS history(
            id TEXT PRIMARY KEY, text TEXT, voice_id TEXT, voice_name TEXT,
            file TEXT, seconds REAL, gen_seconds REAL, created REAL)""")
        cols = {r["name"] for r in con.execute("PRAGMA table_info(history)")}
        if "segments" not in cols:  # migration from v0.1
            con.execute("ALTER TABLE history ADD COLUMN segments TEXT")
        if "engine" not in cols:  # migration from v0.2
            con.execute("ALTER TABLE history ADD COLUMN engine TEXT")
        vcols = {r["name"] for r in con.execute("PRAGMA table_info(voices)")}
        if "transcript" not in vcols:
            con.execute("ALTER TABLE voices ADD COLUMN transcript TEXT")
        con.execute("""CREATE TABLE IF NOT EXISTS pronunciations(
            id TEXT PRIMARY KEY, term TEXT NOT NULL, replacement TEXT NOT NULL, created REAL)""")


# ---------------------------------------------------------------- utils ----
def _split_long(s, limit):
    """Split one over-long sentence at commas/spaces into pieces <= limit."""
    parts = []
    while len(s) > limit:
        cut = s.rfind(",", 0, limit)
        if cut < limit // 3:
            cut = s.rfind(" ", 0, limit)
        if cut < 1:
            cut = limit - 1
        parts.append(s[:cut + 1].strip())
        s = s[cut + 1:].strip()
    if s:
        parts.append(s)
    return parts


def chunk_text(text, max_chars=CHUNK_CHARS, first_max=FIRST_CHUNK_CHARS):
    """Split text into sentence-based chunks no longer than max_chars.
    The first chunk is kept short (<= first_max) so streaming playback starts fast."""
    text = re.sub(r"\s+", " ", text).strip()
    pieces = []
    for s in re.split(r"(?<=[.!?।])\s+", text):
        pieces += _split_long(s, max_chars)
    chunks, cur = [], ""
    for p in pieces:
        limit = first_max if not chunks else max_chars
        if not chunks and not cur and len(p) > first_max:
            sub = _split_long(p, first_max)   # shorten the very first sentence
            chunks.append(sub[0])
            p = " ".join(sub[1:])
            if not p:
                continue
            limit = max_chars
        if len(cur) + len(p) + 1 <= limit:
            cur = f"{cur} {p}".strip()
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()]


def _ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def make_srt(segments):
    """segments: [{start, end, text}] -> SRT text (long chunks split into ~2 lines)."""
    out, n = [], 1
    for seg in segments:
        words = seg["text"].split()
        # split a chunk into caption-sized pieces (~12 words), timed by length
        pieces, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= 12 or re.search(r"[.!?।,;:]$", w) and len(cur) >= 6:
                pieces.append(" ".join(cur))
                cur = []
        if cur:
            pieces.append(" ".join(cur))
        total = sum(len(p) for p in pieces) or 1
        t = seg["start"]
        dur = seg["end"] - seg["start"]
        for p in pieces:
            d = dur * len(p) / total
            out.append(f"{n}\n{_ts(t)} --> {_ts(t + d)}\n{p}\n")
            n += 1
            t += d
    return "\n".join(out)


# --------------------------------------------------------- indic worker ----
def indic_call(path, payload=None, timeout=300):
    """Call the IndicF5 worker. Returns raw bytes."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(INDIC_URL + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail")
        except Exception:
            detail = str(e)
        raise RuntimeError(f"Indian-language engine: {detail}")
    except urllib.error.URLError:
        raise RuntimeError("Indian-language engine is not running. "
                           "Run setup_indic.bat once, then restart with run.bat.")


def indic_health():
    try:
        return json.loads(indic_call("/health", timeout=2))
    except Exception:
        return None


# ------------------------------------------------------------ GPU swap ----
# A 6 GB laptop GPU can't hold Chatterbox and IndicF5 at the same time without
# spilling into (very slow) shared system memory. Keep only the engine that is
# in use on the GPU and park the other one in RAM. Switching takes ~1-3 s.
GPU_SWAP = os.environ.get("VS_GPU_SWAP", "1") != "0"
_cb_where = None   # "cuda" / "cpu" — where Chatterbox weights currently live


def _move(obj, dev):
    """Move every tensor inside Chatterbox's conditioning objects to `dev`,
    detached, so the result stays deep-copyable (plain .to() on tensors that
    carry autograd history makes later copy.deepcopy calls fail)."""
    import dataclasses
    import torch
    if torch.is_tensor(obj):
        return obj.detach().to(dev)
    if isinstance(obj, dict):
        return {k: _move(v, dev) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(_move(v, dev) for v in obj)
    if isinstance(obj, torch.nn.Module):
        return obj.to(dev)
    if dataclasses.is_dataclass(obj) or hasattr(obj, "__dict__"):
        for k, v in list(vars(obj).items()):
            setattr(obj, k, _move(v, dev))
        return obj
    return obj


def _default_voice_conds(device):
    """Fresh copy of Chatterbox's built-in voice, loaded from its conds.pt file
    (avoids deep-copying tensors that were moved between GPU and RAM)."""
    try:
        from chatterbox.tts import REPO_ID, Conditionals
        from huggingface_hub import hf_hub_download
        return Conditionals.load(hf_hub_download(REPO_ID, "conds.pt"), map_location="cpu").to(device)
    except Exception as e:
        print(f"[warn] reloading default voice failed ({e}); using in-memory copy")
        return _move(copy.deepcopy(_default_conds), device)


def _chatterbox_to(dev):
    global _cb_where, _default_conds
    m = _model
    if m is None or _device != "cuda" or _cb_where == dev:
        return
    import torch
    t0 = time.time()
    for part in ("t3", "s3gen", "ve"):
        mod = getattr(m, part, None)
        if mod is not None:
            mod.to(dev)
    if getattr(m, "conds", None) is not None:
        m.conds = _move(m.conds, dev)
    if _default_conds is not None:
        _default_conds = _move(_default_conds, dev)
    m.device = dev
    _cb_where = dev
    if dev == "cpu":
        torch.cuda.empty_cache()
    print(f"[gpu] Chatterbox -> {dev} in {time.time() - t0:.1f}s")


def use_engine(engine):
    """Make sure only `engine` occupies the GPU."""
    if not GPU_SWAP:
        return
    if engine == "indic":
        try:
            _chatterbox_to("cpu")
        except Exception as e:
            print(f"[warn] could not park Chatterbox: {e}")
    else:
        try:
            indic_call("/offload", {}, timeout=30)
        except Exception:
            pass   # worker not running or older version: nothing to free
        try:
            _chatterbox_to("cuda")
        except Exception as e:
            print(f"[warn] could not restore Chatterbox to GPU: {e}")


def gpu_info():
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        free, total = torch.cuda.mem_get_info()
        return {"free_gb": round(free / 1e9, 2), "total_gb": round(total / 1e9, 2),
                "chatterbox_on": _cb_where or _device}
    except Exception:
        return None


# ----------------------------------------------------------------- jobs ----
# In-memory job table + single GPU worker thread. The cloud version swaps this
# for Redis/RabbitMQ and a pool of GPU workers with the same job contract.
JOBS = {}
_job_q: "queue.Queue[str]" = queue.Queue()
_gpu_lock = threading.Lock()   # one GPU user at a time (generation or transcription)


def _run_job(jid):
    import io
    import soundfile as sf
    import numpy as np

    job = JOBS[jid]
    job["status"] = "running"
    jdir = JOBS_DIR / jid
    jdir.mkdir(exist_ok=True)
    t0 = time.time()
    try:
        use_engine(job["engine"])
        if job["engine"] == "indic":
            sr = 24000

            def synth(chunk):
                wav = indic_call("/synthesize", {"text": chunk, "ref_audio": job["prompt"],
                                                 "ref_text": job["ref_text"]})
                a, _ = sf.read(io.BytesIO(wav), dtype="float32")
                return a
        else:
            model = get_model()
            if job["prompt"]:
                model.prepare_conditionals(job["prompt"], exaggeration=job["exaggeration"])
            else:
                model.conds = _default_voice_conds(model.device)
            sr = model.sr

            def synth(chunk):
                wav = model.generate(chunk, exaggeration=job["exaggeration"],
                                     cfg_weight=job["cfg_weight"])
                return wav.detach().cpu().squeeze(0).numpy().astype("float32")
        gap = np.zeros(int(sr * GAP_SEC), dtype="float32")
        pieces, segments, t = [], [], 0.0
        for i, chunk in enumerate(job["chunks"]):
            if job.get("cancel"):
                raise RuntimeError("Cancelled")
            a = synth(chunk)
            sf.write(str(jdir / f"{i}.wav"), a, sr)   # playable immediately
            dur = len(a) / sr
            segments.append({"start": round(t, 3), "end": round(t + dur, 3), "text": chunk})
            t += dur + GAP_SEC
            pieces += [a, gap]
            job["done"] = i + 1

        audio = np.concatenate(pieces[:-1])
        hid = jid
        sf.write(str(OUTPUTS / f"{hid}.wav"), audio, sr)
        secs, gen = len(audio) / sr, time.time() - t0
        with db() as con:
            con.execute("""INSERT INTO history(id,text,voice_id,voice_name,file,seconds,
                           gen_seconds,created,segments,engine) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (hid, job["text"], job["voice_id"] or None, job["voice_name"],
                         f"{hid}.wav", secs, gen, time.time(), json.dumps(segments),
                         job["engine"]))
        job.update(status="done", history_id=hid, seconds=round(secs, 2),
                   gen_seconds=round(gen, 2))
    except Exception as e:
        if job.get("cancel"):
            job.update(status="cancelled")
        else:
            job.update(status="error", error=str(e))
            print(f"[error] job {jid}: {e}")
    finally:
        job["finished"] = time.time()


def _worker():
    while True:
        jid = _job_q.get()
        try:
            with _gpu_lock:
                _run_job(jid)
        finally:
            _job_q.task_done()


def _janitor():
    """Remove streamed chunk files of jobs finished more than 30 minutes ago."""
    while True:
        time.sleep(300)
        now = time.time()
        for jid, job in list(JOBS.items()):
            if job.get("finished") and now - job["finished"] > 1800:
                shutil.rmtree(JOBS_DIR / jid, ignore_errors=True)
                JOBS.pop(jid, None)


@app.on_event("startup")
def _startup():
    init_db()
    shutil.rmtree(JOBS_DIR, ignore_errors=True)  # stale chunks from last run
    JOBS_DIR.mkdir(parents=True, exist_ok=True)

    def load():
        try:
            get_model()
        except Exception as e:
            print(f"[error] model load failed: {e}")
    threading.Thread(target=load, daemon=True).start()
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_janitor, daemon=True).start()


# ------------------------------------------------------------------ api ----
@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/status")
def status():
    return {"loaded": _model is not None, "device": _device, "error": _load_error,
            "queue": _job_q.qsize(), "indic": indic_health(), "gpu": gpu_info(),
            "stt": _stt_ready()}


def _stt_ready():
    try:
        import transcribe as tr
        return tr.is_downloaded()
    except Exception:
        return False


# ---- voices
@app.get("/api/voices")
def list_voices():
    with db() as con:
        rows = con.execute("SELECT id,name,seconds,created,transcript FROM voices ORDER BY created DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/voices")
async def add_voice(name: str = Form(...), consent: bool = Form(False),
                    transcript: str = Form(""), audio: UploadFile = File(...)):
    if not consent:
        raise HTTPException(400, "Please confirm you own this voice or have the speaker's permission.")
    name = name.strip()[:60]
    if not name:
        raise HTTPException(400, "Voice name is required.")

    import soundfile as sf

    vid = uuid.uuid4().hex[:12]
    y, sr, full = _prepare_sample(await audio.read(), audio.filename)
    out = VOICES / f"{vid}.wav"
    sf.write(str(out), y, sr)
    secs = len(y) / sr

    with db() as con:
        con.execute("INSERT INTO voices(id,name,file,seconds,created,transcript) VALUES (?,?,?,?,?,?)",
                    (vid, name, out.name, secs, time.time(), transcript.strip() or None))
    note = None
    if full > secs + 0.5:
        note = (f"Sample was shortened to {secs:.1f}s at a natural pause. Auto-fill already "
                f"matches this; if you typed the transcript yourself, keep only the words in that part.")
    return {"id": vid, "name": name, "seconds": secs, "note": note}


def _prepare_sample(data, filename=None):
    """Decode, trim silence, and shorten to <= MAX_REF_SEC at a natural pause.
    Returns (audio, sample_rate, original_seconds)."""
    import tempfile
    import librosa
    suffix = Path(filename or "a.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, dir=DATA) as f:
        f.write(data)
        tmp = f.name
    try:
        y, sr = librosa.load(tmp, sr=None, mono=True)
    except Exception:
        raise HTTPException(400, "Could not read that audio. Use WAV, MP3 or FLAC.")
    finally:
        Path(tmp).unlink(missing_ok=True)
    y, _ = librosa.effects.trim(y, top_db=35)
    full = len(y) / sr
    if full < MIN_REF_SEC:
        raise HTTPException(400, f"Sample is {full:.1f}s; need at least {MIN_REF_SEC}s of clear speech.")
    if full > MAX_REF_SEC:
        limit = int(MAX_REF_SEC * sr)
        ends = [e for _, e in librosa.effects.split(y, top_db=35) if MIN_REF_SEC * sr <= e <= limit]
        y = y[: (max(ends) if ends else limit)]
    return y, sr, full


@app.patch("/api/voices/{vid}")
def update_voice(vid: str, transcript: str = Form(""), name: str = Form("")):
    with db() as con:
        if not con.execute("SELECT 1 FROM voices WHERE id=?", (vid,)).fetchone():
            raise HTTPException(404)
        if name.strip():
            con.execute("UPDATE voices SET name=? WHERE id=?", (name.strip()[:60], vid))
        con.execute("UPDATE voices SET transcript=? WHERE id=?", (transcript.strip() or None, vid))
    return {"ok": True}


# ---- restart (used to apply updates without closing windows by hand)
@app.post("/api/admin/restart")
def restart(request: Request, target: str = Form("studio")):
    if request.client and request.client.host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(403, "Restart is only allowed from this computer.")
    done = []
    if target in ("indic", "all"):
        try:
            indic_call("/restart", {}, timeout=5)
        except Exception:
            pass   # worker exits before replying
        done.append("indic")
    if target in ("studio", "all"):
        threading.Timer(0.5, lambda: os._exit(3)).start()   # run.bat restarts on exit code 3
        done.append("studio")
    return {"restarting": done}


# ---- transcription (Whisper)
def _transcribe_on_gpu(path, lang):
    import transcribe as tr
    with _gpu_lock:                       # wait for any running generation
        if GPU_SWAP:
            try:
                indic_call("/offload", {}, timeout=30)
            except Exception:
                pass
            try:
                _chatterbox_to("cpu")
            except Exception as e:
                print(f"[warn] {e}")
        return tr.transcribe(path, lang=lang)


@app.post("/api/transcribe")
async def transcribe_sample(audio: UploadFile = File(None), voice_id: str = Form(""),
                            lang: str = Form("")):
    """Transcribe an uploaded sample (exactly as it will be saved) or a saved voice."""
    import soundfile as sf
    import transcribe as tr
    if not tr.is_downloaded():
        raise HTTPException(503, "Speech-to-text model isn't installed yet. Run update.bat once.")
    tmp = None
    try:
        if voice_id:
            with db() as con:
                r = con.execute("SELECT file FROM voices WHERE id=?", (voice_id,)).fetchone()
            if not r:
                raise HTTPException(404, "Voice not found.")
            path = VOICES / r["file"]
        elif audio is not None:
            y, sr, _ = _prepare_sample(await audio.read(), audio.filename)
            tmp = DATA / f"tr_{uuid.uuid4().hex[:8]}.wav"
            sf.write(str(tmp), y, sr)
            path = tmp
        else:
            raise HTTPException(400, "Send an audio sample or a voice id.")
        import asyncio
        text = await asyncio.to_thread(_transcribe_on_gpu, path, lang or None)
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)


# ---- pronunciation dictionary + text preview
def _dictionary():
    with db() as con:
        return [(r["term"], r["replacement"]) for r in
                con.execute("SELECT term,replacement FROM pronunciations")]


@app.get("/api/pronunciations")
def list_pronunciations():
    with db() as con:
        rows = con.execute("SELECT id,term,replacement FROM pronunciations ORDER BY term COLLATE NOCASE").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/pronunciations")
def add_pronunciation(term: str = Form(...), replacement: str = Form(...)):
    term, replacement = term.strip()[:80], replacement.strip()[:200]
    if not term or not replacement:
        raise HTTPException(400, "Both the word and how to say it are needed.")
    with db() as con:
        old = con.execute("SELECT id FROM pronunciations WHERE lower(term)=lower(?)", (term,)).fetchone()
        if old:
            con.execute("UPDATE pronunciations SET term=?, replacement=? WHERE id=?",
                        (term, replacement, old["id"]))
            return {"id": old["id"], "updated": True}
        pid = uuid.uuid4().hex[:12]
        con.execute("INSERT INTO pronunciations VALUES (?,?,?,?)", (pid, term, replacement, time.time()))
    return {"id": pid}


@app.delete("/api/pronunciations/{pid}")
def delete_pronunciation(pid: str):
    with db() as con:
        con.execute("DELETE FROM pronunciations WHERE id=?", (pid,))
    return {"ok": True}


@app.post("/api/preview-text")
def preview_text(text: str = Form(...), engine: str = Form("chatterbox")):
    import text_normalize as tn
    spoken, lang = tn.prepare(text, engine, _dictionary())
    return {"text": spoken, "lang": lang, "lang_name": tn.LANG_NAMES.get(lang)}


@app.get("/api/engines")
def engines():
    h = indic_health()
    return [
        {"id": "chatterbox", "name": ENGINES["chatterbox"], "available": True,
         "builtin_voices": [{"id": "", "name": "Default voice"}]},
        {"id": "indic", "name": ENGINES["indic"], "available": bool(h),
         "ready": bool(h and h.get("loaded")),
         "builtin_voices": [{"id": "builtin:pan_f", "name": "Indic female (built-in)"}]},
    ]


@app.get("/api/voices/{vid}/audio")
def voice_audio(vid: str):
    with db() as con:
        r = con.execute("SELECT file FROM voices WHERE id=?", (vid,)).fetchone()
    if not r:
        raise HTTPException(404)
    return FileResponse(VOICES / r["file"], media_type="audio/wav")


@app.delete("/api/voices/{vid}")
def delete_voice(vid: str):
    with db() as con:
        r = con.execute("SELECT file FROM voices WHERE id=?", (vid,)).fetchone()
        if not r:
            raise HTTPException(404)
        con.execute("DELETE FROM voices WHERE id=?", (vid,))
    (VOICES / r["file"]).unlink(missing_ok=True)
    return {"ok": True}


# ---- generation jobs
@app.post("/api/jobs")
def create_job(text: str = Form(...), voice_id: str = Form(""),
               exaggeration: float = Form(0.5), cfg_weight: float = Form(0.5),
               engine: str = Form("chatterbox")):
    text = text.strip()
    if not text:
        raise HTTPException(400, "Text is empty.")
    if len(text) > MAX_TEXT:
        raise HTTPException(400, f"Text is too long (max {MAX_TEXT} characters).")

    if engine not in ENGINES:
        raise HTTPException(400, "Unknown engine.")
    voice_name, prompt, ref_text = "Default", None, ""
    if voice_id.startswith("builtin:"):
        if engine != "indic":
            raise HTTPException(400, "That built-in voice is for Indian languages.")
        voice_name, prompt = "Indic female (built-in)", voice_id
    elif voice_id:
        with db() as con:
            r = con.execute("SELECT name,file,transcript FROM voices WHERE id=?", (voice_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Voice not found.")
        voice_name, prompt = r["name"], str((VOICES / r["file"]).resolve())
        ref_text = r["transcript"] or ""
        if engine == "indic" and not ref_text:
            raise HTTPException(400, f"'{voice_name}' needs the transcript of its sample for "
                                     "Indian languages. Add it in the Voice library.")
    elif engine == "indic":
        voice_name, prompt = "Indic female (built-in)", "builtin:pan_f"
    if engine == "indic" and not indic_health():
        raise HTTPException(503, "Indian-language engine is not running. "
                                 "Run setup_indic.bat once, then restart with run.bat.")

    import text_normalize as tn
    spoken, _lang = tn.prepare(text, engine, _dictionary())
    chunks = chunk_text(spoken)
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {"id": jid, "status": "queued", "text": text, "chunks": chunks,
                 "total": len(chunks), "done": 0, "voice_id": voice_id,
                 "voice_name": voice_name, "prompt": prompt, "ref_text": ref_text,
                 "engine": engine,
                 "exaggeration": min(max(exaggeration, 0.25), 2.0),
                 "cfg_weight": min(max(cfg_weight, 0.0), 1.0), "created": time.time()}
    _job_q.put(jid)
    return _job_public(JOBS[jid])


def _job_public(job):
    keys = ("id", "status", "total", "done", "error", "history_id", "seconds", "gen_seconds")
    return {k: job.get(k) for k in keys}


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "Job not found.")
    return _job_public(job)


@app.get("/api/jobs/{jid}/chunks/{n}")
def job_chunk(jid: str, n: int):
    job = JOBS.get(jid)
    if not job or n >= job.get("done", 0):
        raise HTTPException(404, "Chunk not ready.")
    return FileResponse(JOBS_DIR / jid / f"{n}.wav", media_type="audio/wav")


@app.post("/api/jobs/{jid}/cancel")
def job_cancel(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404)
    job["cancel"] = True
    return {"ok": True}


# Backwards-compatible blocking endpoint (v0.1 API clients)
@app.post("/api/tts")
def tts(text: str = Form(...), voice_id: str = Form(""),
        exaggeration: float = Form(0.5), cfg_weight: float = Form(0.5)):
    j = create_job(text, voice_id, exaggeration, cfg_weight, "chatterbox")
    while JOBS[j["id"]]["status"] in ("queued", "running"):
        time.sleep(0.2)
    job = JOBS[j["id"]]
    if job["status"] != "done":
        raise HTTPException(500, job.get("error") or "Generation failed.")
    return {"id": job["history_id"], "seconds": job["seconds"],
            "gen_seconds": job["gen_seconds"], "url": f"/api/audio/{job['history_id']}"}


# ---- history / downloads
def _history_row(hid):
    with db() as con:
        r = con.execute("SELECT * FROM history WHERE id=?", (hid,)).fetchone()
    if not r:
        raise HTTPException(404)
    return r


@app.get("/api/audio/{hid}")
def get_audio(hid: str, format: str = "wav"):
    r = _history_row(hid)
    wav = OUTPUTS / r["file"]
    if format == "mp3":
        mp3 = wav.with_suffix(".mp3")
        if not mp3.exists():
            import soundfile as sf
            data, sr = sf.read(str(wav), dtype="float32")
            try:
                sf.write(str(mp3), data, sr, format="MP3")
            except Exception as e:
                raise HTTPException(500, f"MP3 encoding not available: {e}")
        return FileResponse(mp3, media_type="audio/mpeg", filename=f"speech_{hid}.mp3")
    return FileResponse(wav, media_type="audio/wav", filename=f"speech_{hid}.wav")


@app.get("/api/subtitles/{hid}")
def get_subtitles(hid: str):
    r = _history_row(hid)
    if not r["segments"]:
        raise HTTPException(404, "No subtitle timing for this clip (made before v0.2).")
    srt = make_srt(json.loads(r["segments"]))
    return Response(srt, media_type="application/x-subrip",
                    headers={"Content-Disposition": f'attachment; filename="speech_{hid}.srt"'})


@app.get("/api/history")
def history(limit: int = 30):
    with db() as con:
        rows = con.execute("""SELECT id,text,voice_name,seconds,gen_seconds,created,engine,
                              segments IS NOT NULL AS has_srt
                              FROM history ORDER BY created DESC LIMIT ?""", (limit,)).fetchall()
    return [dict(r) for r in rows]


@app.delete("/api/history/{hid}")
def delete_history(hid: str):
    r = _history_row(hid)
    with db() as con:
        con.execute("DELETE FROM history WHERE id=?", (hid,))
    for ext in (".wav", ".mp3"):
        (OUTPUTS / Path(r["file"]).with_suffix(ext).name).unlink(missing_ok=True)
    return {"ok": True}
