"""One-time download of the IndicF5 model (gated on Hugging Face).

Before running: sign in at huggingface.co, accept the conditions on
https://huggingface.co/ai4bharat/IndicF5 and create a Read token.
"""
import sys

from huggingface_hub import HfApi, login, snapshot_download

REPO_ID = "ai4bharat/IndicF5"

try:
    HfApi().model_info(REPO_ID)
    snapshot_download(REPO_ID)
except Exception:
    print("\nHugging Face sign-in needed for IndicF5.")
    print("Paste your Read token below (it will not be shown) and press Enter.\n")
    login(add_to_git_credential=False)
    try:
        snapshot_download(REPO_ID)
    except Exception as e:
        print(f"\nDownload failed: {e}")
        print("Check that you accepted the conditions on huggingface.co/ai4bharat/IndicF5")
        sys.exit(1)

print("Model files downloaded. Loading once to fetch the vocoder and test...")
from indic_worker.server import get_model, synthesize, SynthReq  # noqa: E402

get_model()
synthesize(SynthReq(text="வணக்கம், இது ஒரு சோதனை.", ref_audio="builtin:pan_f"))
print("IndicF5 is ready.")
