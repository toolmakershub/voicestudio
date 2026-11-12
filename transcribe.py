"""
Speech-to-text for voice samples (Whisper large-v3-turbo, MIT license).
Used to auto-fill the transcript that IndicF5 needs for voice cloning.
Loaded on first use; parked in RAM between uses so it doesn't hold GPU memory.
"""
import threading
import time

MODEL_ID = "openai/whisper-large-v3-turbo"
WHISPER_LANG = {"ta": "tamil", "hi": "hindi", "te": "telugu", "kn": "kannada",
                "ml": "malayalam", "bn": "bengali", "gu": "gujarati", "pa": "punjabi",
                "mr": "marathi", "or": "odia", "as": "assamese", "en": "english"}

_pipe = None
_lock = threading.Lock()


def _load():
    global _pipe
    if _pipe is None:
        import torch
        from transformers import pipeline
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        try:
            _pipe = pipeline("automatic-speech-recognition", model=MODEL_ID, dtype=dtype, device="cpu")
        except TypeError:   # older transformers use torch_dtype
            _pipe = pipeline("automatic-speech-recognition", model=MODEL_ID,
                             torch_dtype=dtype, device="cpu")
    return _pipe


def transcribe(path, lang=None, use_gpu=True):
    """Return transcript text for an audio file (first 30 s)."""
    import librosa
    import torch
    y, _ = librosa.load(str(path), sr=16000, mono=True)
    y = y[: 16000 * 30]
    with _lock:
        pipe = _load()
        dev = "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
        t0 = time.time()
        pipe.model.to(dev)
        pipe.device = torch.device(dev)
        try:
            kw = {"task": "transcribe"}
            if lang and lang in WHISPER_LANG:
                kw["language"] = WHISPER_LANG[lang]
            out = pipe({"raw": y, "sampling_rate": 16000}, generate_kwargs=kw)
        finally:
            pipe.model.to("cpu")
            pipe.device = torch.device("cpu")
            if dev == "cuda":
                torch.cuda.empty_cache()
        print(f"[ok] transcribed {len(y)/16000:.1f}s audio in {time.time()-t0:.1f}s on {dev}")
    return out["text"].strip()


def is_downloaded():
    try:
        from huggingface_hub import try_to_load_from_cache
        r = try_to_load_from_cache(MODEL_ID, "config.json")
        return isinstance(r, str)
    except Exception:
        return False
