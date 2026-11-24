# Third-party software and models

Voice Studio's own code is AGPL-3.0. It uses these projects, each under its own licence:

| Component | Used for | Licence |
|---|---|---|
| Chatterbox (Resemble AI) | English speech and voice cloning | MIT |
| IndicF5 (AI4Bharat) | 11 Indian languages and voice cloning | MIT (check the model card before commercial use) |
| Whisper (OpenAI) | Automatic transcripts for voice samples | MIT |
| indic-numtowords | Numbers as words in Indian languages | MIT |
| FastAPI, Uvicorn | Local web server | MIT / BSD-3-Clause |
| Piper (Voice Studio Lite) | Lightweight voices | GPL-3.0 |
| Piper voice `ta_IN-rasa_male-medium` (Lite) | Tamil voice | CC-BY-4.0, AI4Bharat Rasa dataset — credit required |
| Other Piper voices (Lite) | | Each voice's own licence (see its model card on Hugging Face) |

Model weights are downloaded during setup and are **not** part of this repository.
Only clone voices you own or have explicit permission to use.
