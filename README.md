# ToolMakersHub Voice Studio

An ElevenLabs-style text-to-speech studio that runs **entirely on your own PC** —
no internet, API keys or per-character fees after the one-time setup.

- **English** — Chatterbox (Resemble AI, MIT): expressive speech + voice cloning
- **11 Indian languages** — IndicF5 (AI4Bharat, MIT): Tamil, Hindi, Telugu, Malayalam,
  Kannada, Bengali, Marathi, Gujarati, Punjabi, Odia, Assamese — with voice cloning
- Clone a voice from a 6–15 s sample (upload or record); transcripts auto-filled by Whisper
- Streaming playback while generating, Stop, history, WAV / MP3 / SRT subtitles
- Numbers, ₹ amounts, %, dates spoken correctly in Indian languages; pronunciation dictionary
- Consent check before any voice is cloned; outputs carry Chatterbox's inaudible watermark

## Requirements
- Windows 10/11, NVIDIA GPU with 6 GB+ VRAM recommended (tested: RTX 4050 Laptop, 24 GB RAM)
- Python **3.11** (studio) and **3.10** (Indian-language engine) from python.org
- ~15 GB free disk for models and libraries

## Setup (once, needs internet)
| Step | Run | What it does |
|---|---|---|
| 1 | `setup_gpu.bat` | Studio environment + English model (~3 GB) |
| 2 | `setup_indic.bat` | Indian-language engine (needs a free Hugging Face account; accept the terms at huggingface.co/ai4bharat/IndicF5 and paste a *Read* token when asked) |
| 3 | `update.bat` | Extra libraries + Whisper speech-to-text (~1.6 GB) |

Then start with **`run.bat`** → http://127.0.0.1:7860 (works offline).

### Get the code
Recommended (lets `update.bat` move you to new releases):
```
cd C:\toolmakershub.com
git clone https://github.com/toolmakershub/voicestudio.git voice.toolmakershub.com
```
Or download a zip from **Releases** on GitHub.

### Updating
Run **`update.bat`**: it switches to the newest release, then installs any new libraries
and models. The version you are on is shown in the studio header.

## Editions
| | Voice Studio (this folder) | Voice Studio Lite (`lite/`) |
|---|---|---|
| Engines | Chatterbox + IndicF5 | Piper |
| Voice cloning | Yes | No |
| Tamil / Indian languages | 11 languages, best quality | Tamil (male), Hindi |
| Needs | NVIDIA GPU 6 GB+, ~15 GB disk | Any PC, ~100 MB per voice |
| Start | `run.bat` | `lite\run_lite.bat` |

## Versions and releases
See [CHANGELOG.md](CHANGELOG.md) for what changed and [RELEASING.md](RELEASING.md) for how a release is made.

## Architecture
```
Browser UI (static/index.html)
   │
Studio API — app.py (FastAPI, Python 3.11, port 7860)
   ├─ job queue + single GPU worker thread (streaming chunks, cancel)
   ├─ Chatterbox (English)              ┐ only one engine kept on the GPU;
   ├─ Whisper (transcripts, on demand)  │ the others wait in RAM
   ├─ text_normalize.py (numbers, dictionary)
   ├─ SQLite: voices, history, pronunciations (data/studio.db)
   └─ HTTP → Indic worker — indic_worker/server.py (Python 3.10, port 7861) ┘
```

## API (local)
| Method | Path | Purpose |
|---|---|---|
| GET | /api/status | Engines, GPU memory, speech-to-text ready |
| GET/POST | /api/voices | List / add voice (name, consent, transcript, audio) |
| PATCH/DELETE | /api/voices/{id} | Edit transcript / delete |
| POST | /api/transcribe | Transcribe an uploaded sample or saved voice |
| POST | /api/jobs | Start generation (text, engine, voice_id, exaggeration, cfg_weight) |
| GET | /api/jobs/{id}, /api/jobs/{id}/chunks/{n} | Progress / streamed chunk |
| POST | /api/jobs/{id}/cancel | Stop |
| GET | /api/audio/{id}?format=wav\|mp3, /api/subtitles/{id} | Downloads |
| GET/POST/DELETE | /api/pronunciations | Pronunciation dictionary |
| POST | /api/preview-text | How text will be read |
| POST | /api/admin/restart | Restart studio / Indic engine (localhost only) |

## Never committed (see .gitignore)
`models/` (includes the Hugging Face token), `.venv*/`, `data/` (voice samples & audio).

## Licenses
Chatterbox — MIT · IndicF5 — MIT · Whisper — MIT · indic-numtowords — MIT.
Only clone voices you own or have explicit permission to use.
