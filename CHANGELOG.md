# Changelog

## v0.4 — 2026-11-12
- Automatic sample transcripts with Whisper large-v3-turbo ("✨ Auto-fill").
- Samples longer than 15 s are cut at a natural pause (IndicF5 uses the first 15 s).
- Indian-language text clean-up: numbers, ₹/Rs amounts, %, dates, times and
  decimals spoken as words in 11 languages (indic-numtowords).
- Pronunciation dictionary (e.g. "YouTube" → "யூடியூப்") + "Preview how it will be read".
- GPU swap: only the active engine stays on the 6 GB GPU (Tamil 13× → ~2.5× real time).
- Fix: default English voice failed after using Tamil.
- Self-restart endpoint + auto-restart loops in run.bat / run_indic.bat.

## v0.3 — 2026-11-12
- Indian-language engine: IndicF5 (AI4Bharat, MIT) as a separate worker process
  in its own Python 3.10 environment (port 7861).
- Language-engine selector, built-in Indic voice, voice transcripts.
- Fix: IndicF5 produced noise when TorchDynamo was disabled.

## v0.2 — 2026-11-12
- Background generation jobs with sentence-by-sentence streaming playback, Stop.
- MP3 export and SRT subtitles. Text limit 20,000 characters.
- Fix: page layout stretched by long history items.

## v0.1 — 2026-11-12
- MVP: offline text-to-speech + voice cloning with Chatterbox (MIT), FastAPI + SQLite,
  voice library, history, WAV download, consent checkbox.
