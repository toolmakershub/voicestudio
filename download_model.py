"""Run once while online: downloads the Chatterbox model weights into the
local Hugging Face cache so the studio can run fully offline afterwards."""
from chatterbox.tts import ChatterboxTTS

print("Downloading Chatterbox model (~3 GB, one time only)...")
ChatterboxTTS.from_pretrained(device="cpu")
print("Done. You can now run the studio offline.")
