"""
Offline text-to-speech engine built on Piper (https://github.com/OHF-Voice/piper1-gpl).

No GUI code lives here, so the engine can also be used from scripts:

    from tts_engine import VoiceManager, RenderSettings, render, export
    vm = VoiceManager("voices")
    voice = vm.load("en_US-lessac-medium")
    result = render(voice, "Hello there. [pause 1] Welcome back!", RenderSettings())
    export(result, "out.mp3", subtitles=True)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

import numpy as np

# --------------------------------------------------------------------------
# Voice catalogue (downloaded once from Hugging Face, then used offline)
# Any other Piper voice name can be typed in the app as well, see:
# https://huggingface.co/rhasspy/piper-voices
# --------------------------------------------------------------------------
VOICE_CATALOG = {
    "en_US-lessac-high": "US English · female · clear narrator (best quality)",
    "en_US-lessac-medium": "US English · female · clear narrator",
    "en_US-ryan-high": "US English · male · deep narrator (best quality)",
    "en_US-joe-medium": "US English · male · casual",
    "en_US-norman-medium": "US English · male · mature",
    "en_US-hfc_male-medium": "US English · male · neutral",
    "en_US-hfc_female-medium": "US English · female · neutral",
    "en_US-amy-medium": "US English · female · bright",
    "en_US-kristin-medium": "US English · female · warm",
    "en_US-libritts_r-medium": "US English · 900+ speakers (pick a speaker number)",
    "en_GB-alan-medium": "UK English · male",
    "en_GB-northern_english_male-medium": "UK English · male · northern accent",
    "en_GB-cori-high": "UK English · female (best quality)",
    "en_GB-jenny_dioco-medium": "UK English · female",
    "hi_IN-pratham-medium": "Hindi · male",
    "hi_IN-priyamvada-medium": "Hindi · female",
    "ar_JO-kareem-medium": "Arabic · male",
    "ta_IN-rasa_male-medium": "Tamil · male · community voice (CC-BY-4.0, AI4Bharat Rasa data)",
}

# Voices that live outside the official rhasspy/piper-voices repo: name -> Hugging Face repo.
COMMUNITY_VOICES = {
    "ta_IN-rasa_male-medium": "tinisoft/piper-ta_IN-rasa_male-medium",
}

PAUSE_RE = re.compile(r"\[\s*pause\s+(\d+(?:\.\d+)?)\s*s?\s*\]", re.IGNORECASE)
# Split after . ! ? (and the Hindi danda) when followed by whitespace.
SENTENCE_RE = re.compile(r"(?<=[.!?।…])[\"'”’)\]]*\s+")


@dataclass
class RenderSettings:
    speed: float = 1.0             # 0.5 – 2.0  (1.0 = voice's natural pace)
    expressiveness: float = 0.667  # Piper noise_scale; higher = more varied intonation
    volume: float = 1.0
    speaker_id: Optional[int] = None
    sentence_pause: float = 0.35   # seconds of silence between sentences
    paragraph_pause: float = 0.9   # seconds between paragraphs (blank-line separated)
    lead_in: float = 0.25          # silence at the very start
    tail: float = 0.5              # silence at the very end


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class Clip:
    """Audio for one paragraph, plus its sentence timings (relative to clip start)."""
    audio: np.ndarray
    cues: list[Cue] = field(default_factory=list)


@dataclass
class RenderResult:
    sample_rate: int
    clips: list[Clip]
    gap_seconds: float  # silence inserted between clips when joined

    def joined(self) -> Clip:
        gap = np.zeros(int(self.gap_seconds * self.sample_rate), dtype=np.float32)
        parts, cues, offset = [], [], 0.0
        for i, clip in enumerate(self.clips):
            if i:
                parts.append(gap)
                offset += self.gap_seconds
            parts.append(clip.audio)
            cues += [Cue(c.start + offset, c.end + offset, c.text) for c in clip.cues]
            offset += len(clip.audio) / self.sample_rate
        audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        return Clip(audio, cues)

    @property
    def duration(self) -> float:
        return len(self.joined().audio) / self.sample_rate


# --------------------------------------------------------------------------
# Voices
# --------------------------------------------------------------------------
class VoiceManager:
    def __init__(self, voices_dir: Path | str):
        self.dir = Path(voices_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, object] = {}

    def installed(self) -> list[str]:
        return sorted(
            p.stem for p in self.dir.glob("*.onnx") if p.with_suffix(".onnx.json").exists()
        )

    def is_installed(self, name: str) -> bool:
        return (self.dir / f"{name}.onnx").exists() and (self.dir / f"{name}.onnx.json").exists()

    def download(self, name: str) -> None:
        """One-time internet download of a voice (~60–110 MB). Everything after is offline."""
        name = name.strip()
        repo = COMMUNITY_VOICES.get(name)
        if repo is None:
            from piper.download_voices import download_voice
            download_voice(name, self.dir)
            return
        from urllib.request import urlopen
        for ext in (".onnx.json", ".onnx"):
            target = self.dir / f"{name}{ext}"
            part = target.with_name(target.name + ".part")
            url = f"https://huggingface.co/{repo}/resolve/main/{name}{ext}?download=true"
            with urlopen(url) as resp, open(part, "wb") as f:
                shutil.copyfileobj(resp, f)
            part.replace(target)  # only appears once fully downloaded

    def import_model(self, onnx_path: Path | str) -> str:
        """Copy an already-downloaded .onnx (+ .onnx.json beside it) into the voices folder."""
        src = Path(onnx_path)
        cfg = Path(str(src) + ".json")
        if not cfg.exists():
            raise FileNotFoundError(f"Missing config file next to the model:\n{cfg.name}")
        shutil.copy2(src, self.dir / src.name)
        shutil.copy2(cfg, self.dir / cfg.name)
        return src.stem

    def load(self, name: str):
        if name not in self._cache:
            from piper import PiperVoice
            path = self.dir / f"{name}.onnx"
            if not path.exists():
                raise FileNotFoundError(f"Voice '{name}' is not installed.")
            self._cache[name] = PiperVoice.load(path)
        return self._cache[name]

    def speaker_count(self, name: str) -> int:
        try:
            cfg = json.loads((self.dir / f"{name}.onnx.json").read_text(encoding="utf-8"))
            return int(cfg.get("num_speakers", 1))
        except Exception:
            return 1


# --------------------------------------------------------------------------
# Script parsing
# --------------------------------------------------------------------------
def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if p.strip()]


def paragraph_items(paragraph: str) -> list[tuple[str, object]]:
    """Turn a paragraph into ('say', sentence) and ('pause', seconds) items."""
    items: list[tuple[str, object]] = []
    pos = 0
    for m in PAUSE_RE.finditer(paragraph):
        items += _sentences(paragraph[pos:m.start()])
        items.append(("pause", float(m.group(1))))
        pos = m.end()
    items += _sentences(paragraph[pos:])
    return items


def _sentences(chunk: str) -> list[tuple[str, object]]:
    chunk = " ".join(chunk.split())  # single line breaks inside a paragraph = spaces
    return [("say", s.strip()) for s in SENTENCE_RE.split(chunk) if s.strip()]


def estimate_seconds(text: str, speed: float = 1.0) -> float:
    words = len(PAUSE_RE.sub(" ", text).split())
    pauses = sum(float(x) for x in PAUSE_RE.findall(text))
    return words / (2.5 * speed) + pauses  # ~150 words per minute at 1.0x


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
class Cancelled(Exception):
    pass


def render(
    voice,
    text: str,
    settings: RenderSettings,
    progress: Optional[Callable[[int, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> RenderResult:
    from piper import SynthesisConfig

    sr = voice.config.sample_rate
    cfg = SynthesisConfig(
        speaker_id=settings.speaker_id,
        length_scale=1.0 / max(0.25, settings.speed),
        noise_scale=settings.expressiveness,
        volume=settings.volume,
        normalize_audio=True,
    )

    def silence(sec: float) -> np.ndarray:
        return np.zeros(int(max(0.0, sec) * sr), dtype=np.float32)

    paragraphs = [paragraph_items(p) for p in split_paragraphs(text)]
    total = sum(1 for p in paragraphs for kind, _ in p if kind == "say") or 1
    done = 0
    clips: list[Clip] = []

    for items in paragraphs:
        parts: list[np.ndarray] = []
        cues: list[Cue] = []
        t = 0.0
        prev_was_speech = False
        for kind, value in items:
            if should_stop and should_stop():
                raise Cancelled()
            if kind == "pause":
                parts.append(silence(value))
                t += value
                prev_was_speech = False
                continue
            if prev_was_speech:
                parts.append(silence(settings.sentence_pause))
                t += settings.sentence_pause
            audio = _trim(np.concatenate(
                [c.audio_float_array.astype(np.float32) for c in voice.synthesize(value, cfg)]
                or [np.zeros(0, dtype=np.float32)]
            ), sr)
            dur = len(audio) / sr
            parts.append(audio)
            cues.append(Cue(t, t + dur, value))
            t += dur
            prev_was_speech = True
            done += 1
            if progress:
                progress(done, total)
        if parts:
            clips.append(Clip(np.concatenate(parts), cues))

    # Lead-in / tail silence on the outer edges only.
    if clips:
        lead = silence(settings.lead_in)
        clips[0] = Clip(np.concatenate([lead, clips[0].audio]),
                        [Cue(c.start + settings.lead_in, c.end + settings.lead_in, c.text)
                         for c in clips[0].cues])
        clips[-1] = Clip(np.concatenate([clips[-1].audio, silence(settings.tail)]), clips[-1].cues)

    return RenderResult(sr, clips, settings.paragraph_pause)


def _trim(audio: np.ndarray, sr: int, threshold: float = 0.01, keep: float = 0.04) -> np.ndarray:
    """Remove Piper's built-in leading/trailing silence so our pause settings are exact."""
    if audio.size == 0:
        return audio
    loud = np.flatnonzero(np.abs(audio) > threshold)
    if loud.size == 0:
        return audio[:0]
    pad = int(keep * sr)
    return audio[max(0, loud[0] - pad): loud[-1] + pad]


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def to_int16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def mp3_backend() -> Optional[str]:
    try:
        import lameenc  # noqa: F401
        return "lameenc"
    except ImportError:
        pass
    return "ffmpeg" if shutil.which("ffmpeg") else None


def save_audio(audio: np.ndarray, sr: int, path: Path | str, mp3_kbps: int = 192) -> Path:
    path = Path(path)
    pcm = to_int16(audio)
    if path.suffix.lower() == ".mp3":
        backend = mp3_backend()
        if backend == "lameenc":
            import lameenc
            enc = lameenc.Encoder()
            enc.set_bit_rate(mp3_kbps)
            enc.set_in_sample_rate(sr)
            enc.set_channels(1)
            enc.set_quality(2)
            path.write_bytes(enc.encode(pcm) + enc.flush())
            return path
        if backend == "ffmpeg":
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1",
                 "-i", "-", "-b:a", f"{mp3_kbps}k", str(path)],
                input=pcm, check=True,
            )
            return path
        path = path.with_suffix(".wav")  # no MP3 encoder available → fall back to WAV
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return path


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def save_srt(cues: list[Cue], path: Path | str) -> Path:
    path = Path(path)
    lines = []
    for i, c in enumerate(cues, 1):
        lines += [str(i), f"{_ts(c.start)} --> {_ts(c.end)}", c.text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export(result: RenderResult, path: Path | str, split: bool = False,
           subtitles: bool = False) -> list[Path]:
    """Save the render. With split=True, writes name_01.ext, name_02.ext … (one per paragraph)."""
    path = Path(path)
    written: list[Path] = []
    if split and len(result.clips) > 1:
        for i, clip in enumerate(result.clips, 1):
            p = path.with_name(f"{path.stem}_{i:02}{path.suffix}")
            written.append(save_audio(clip.audio, result.sample_rate, p))
            if subtitles:
                written.append(save_srt(clip.cues, p.with_suffix(".srt")))
    else:
        clip = result.joined()
        written.append(save_audio(clip.audio, result.sample_rate, path))
        if subtitles:
            written.append(save_srt(clip.cues, path.with_suffix(".srt")))
    return written


def settings_to_dict(s: RenderSettings) -> dict:
    return asdict(s)
