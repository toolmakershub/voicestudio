# Voice Studio Lite

The lightweight edition of ToolMakersHub Voice Studio: a desktop text-to-audio generator for video voiceovers. It uses **Piper** neural voices and runs entirely on your computer — no API keys, no accounts, no per-minute costs. Internet is only used once, to download each voice you pick.

**Lite vs full studio:** Lite needs no GPU, installs in a minute and uses ~100 MB per voice, but has no voice cloning and only Piper voices. The full studio (repo root) clones voices and has better Tamil and Indian-language quality, but needs an NVIDIA GPU and ~15 GB.

## Setup

1. Install **Python 3.10+** from python.org (on Windows, tick *"Add Python to PATH"*; tkinter is included by default).
2. Open the `lite` folder of Voice Studio.
3. Start it:
   - **Windows:** double-click `run_lite.bat`
   - **macOS / Linux:** run `./run_lite.sh`

The first launch installs `piper-tts` and `lameenc` into a private `.venv` folder (takes a minute). After that it opens straight away.

4. In the app, pick a voice and click **Download voice** (one time, ~60–110 MB). From then on, it works with Wi-Fi off.

## Using it

| What | How |
|---|---|
| New paragraph | Leave a blank line. Paragraphs get a longer pause, and become separate files with *One file per paragraph*. |
| Exact pause | Type `[pause 1.5]` anywhere (seconds). |
| Hear a part | Select some text → **Preview**. With nothing selected, it previews the first paragraph. |
| Final audio | **Generate & Save…** → MP3 (192 kbps) or WAV. |
| Subtitles | Tick *Subtitles (.srt)* — a sentence-timed `.srt` is saved next to the audio. Drop both into CapCut, Premiere, DaVinci, etc. |
| Scenes | Tick *One file per paragraph* → `voiceover_01.mp3`, `voiceover_02.mp3`, … one per scene. |

**Delivery controls:** *Speed* (0.5–2×), *Expressiveness* (higher = livelier intonation, lower = flatter/more stable), *Volume*, and the two pause lengths. Settings and your last script are remembered between sessions.

## Voices

Recommended for voiceovers: `en_US-lessac-high` (female narrator), `en_US-ryan-high` (male narrator), `en_GB-cori-high` (UK female). `high` = best quality; `medium` = smaller and faster.

`en_US-libritts_r-medium` contains 900+ different speakers — set *Speaker #* to try them.

The list also includes Hindi, Arabic and **Tamil** (`ta_IN-rasa_male-medium`, a male community voice trained on AI4Bharat's Rasa dataset, CC-BY-4.0 — credit AI4Bharat Rasa when you use it). Type Tamil script directly into the editor; sentence pauses, `[pause …]` and subtitles all work the same. Any other Piper voice name can be typed into the voice box (browse them at <https://huggingface.co/rhasspy/piper-voices>), or use **Import .onnx…** to add a model you already downloaded (the `.onnx.json` file must sit next to it). Voices are stored in the `voices` folder — copy that folder to set up another machine with no internet at all.

## Files

- `app.py` — the desktop app (Tkinter)
- `tts_engine.py` — rendering, pauses, subtitles and export; usable from your own scripts:

```python
from tts_engine import VoiceManager, RenderSettings, render, export
vm = VoiceManager("voices")
voice = vm.load("en_US-lessac-medium")
result = render(voice, open("script.txt").read(), RenderSettings(speed=1.05))
export(result, "voiceover.mp3", subtitles=True)
```

## Optional: build a single .exe

```
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --noconsole --onedir --name VoiceStudioLite --collect-all piper app.py
```

Copy your `voices` folder next to `VoiceStudioLite.exe` inside `dist\VoiceStudioLite`.

## Licence note

Piper is GPL-3.0. Each voice has its own licence, set by the dataset it was trained on, and some datasets restrict commercial use. Check the voice's `MODEL_CARD` on its Hugging Face page before using it in monetised videos.
