"""
Indic TTS worker (IndicF5, AI4Bharat, MIT license).

Runs in its own Python 3.10 environment (.venv-indic) because IndicF5 needs
older library versions than Chatterbox. The main studio talks to it over HTTP
on 127.0.0.1:7861 — the same contract a cloud GPU worker would use later.
"""
import os

# NOTE: do NOT disable TorchDynamo here. IndicF5's saved weights are keyed for
# torch.compile-wrapped modules ("_orig_mod."); without the wrapper the weights
# silently fail to load and the model outputs noise. Inference never actually
# triggers compilation (it calls .sample(), not forward), so Windows is fine.
os.environ.pop("TORCHDYNAMO_DISABLE", None)

import io
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

REPO_ID = "ai4bharat/IndicF5"
SR = 24000

# Built-in reference voice shipped with the model (prompt clip + its transcript).
BUILTIN = {
    "builtin:pan_f": {
        "name": "Indic female (built-in)",
        "file": "prompts/PAN_F_HAPPY_00001.wav",
        "text": "ਭਹੰਪੀ ਵਿੱਚ ਸਮਾਰਕਾਂ ਦੇ ਭਵਨ ਨਿਰਮਾਣ ਕਲਾ ਦੇ ਵੇਰਵੇ ਗੁੰਝਲਦਾਰ ਅਤੇ ਹੈਰਾਨ ਕਰਨ ਵਾਲੇ ਹਨ, ਜੋ ਮੈਨੂੰ ਖੁਸ਼ ਕਰਦੇ  ਹਨ।",
    },
}

app = FastAPI(title="Indic TTS worker")
_model = None
_device = None
_on_gpu = False
_error = None
_lock = threading.Lock()


def get_model():
    global _model, _device, _error
    if _model is not None:
        return _model
    with _lock:
        if _model is None:
            import torch
            from transformers import AutoModel
            try:
                m = AutoModel.from_pretrained(REPO_ID, trust_remote_code=True)
                dev = "cuda" if torch.cuda.is_available() else "cpu"
                try:
                    m = m.to(dev)
                except Exception as e:  # wrapper may manage its own device
                    print(f"[warn] .to({dev}) failed: {e}")
                m.eval()
                _device = dev
                globals()["_on_gpu"] = dev == "cuda"
                _model = m
                print(f"[ok] IndicF5 loaded on {dev}")
            except Exception as e:
                _error = str(e)
                raise
    return _model


def _ref_path(ref):
    if ref in BUILTIN:
        from huggingface_hub import hf_hub_download
        return hf_hub_download(REPO_ID, BUILTIN[ref]["file"]), BUILTIN[ref]["text"]
    return None, None


class SynthReq(BaseModel):
    text: str
    ref_audio: str          # absolute path on this machine, or a builtin:* id
    ref_text: str = ""


@app.on_event("startup")
def _warm():
    def load():
        try:
            get_model()
        except Exception as e:
            print(f"[error] IndicF5 load failed: {e}")
    threading.Thread(target=load, daemon=True).start()


def _to(dev):
    """Move IndicF5 between GPU and RAM (the studio keeps one engine on the GPU)."""
    global _on_gpu
    if _model is None or _device != "cuda" or _on_gpu == (dev == "cuda"):
        return
    import torch
    t0 = time.time()
    _model.to(dev)
    _on_gpu = dev == "cuda"
    if dev == "cpu":
        torch.cuda.empty_cache()
    print(f"[gpu] IndicF5 -> {dev} in {time.time() - t0:.1f}s")


@app.get("/health")
def health():
    return {"loaded": _model is not None, "device": _device, "error": _error,
            "on_gpu": _on_gpu}


@app.post("/restart")
def restart():
    threading.Timer(0.3, lambda: os._exit(3)).start()   # run_indic.bat restarts on exit code 3
    return {"restarting": True}


@app.post("/offload")
def offload():
    with _lock:
        _to("cpu")
    return {"ok": True, "on_gpu": _on_gpu}


@app.get("/voices")
def voices():
    return [{"id": k, "name": v["name"]} for k, v in BUILTIN.items()]


@app.post("/synthesize")
def synthesize(req: SynthReq):
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "Empty text.")
    ref_audio, ref_text = req.ref_audio, req.ref_text.strip()
    if ref_audio.startswith("builtin:"):
        ref_audio, ref_text = _ref_path(ref_audio)
        if not ref_audio:
            raise HTTPException(404, "Unknown built-in voice.")
    elif not Path(ref_audio).exists():
        raise HTTPException(404, "Reference audio not found.")
    if not ref_text:
        raise HTTPException(400, "This voice needs the transcript of its sample.")

    model = get_model()
    import torch
    t0 = time.time()
    with _lock, torch.inference_mode():
        _to("cuda")
        audio = model(text, ref_audio_path=ref_audio, ref_text=ref_text)
    audio = np.asarray(audio)
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    audio = audio.astype(np.float32).squeeze()
    buf = io.BytesIO()
    sf.write(buf, audio, SR, format="WAV")
    print(f"[ok] {len(audio)/SR:.1f}s audio in {time.time()-t0:.1f}s")
    return Response(buf.getvalue(), media_type="audio/wav")
