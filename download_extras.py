"""Downloads optional models used by newer features (run via update.bat)."""
from huggingface_hub import snapshot_download

print("Downloading speech-to-text model (Whisper large-v3-turbo, about 1.6 GB)...")
snapshot_download("openai/whisper-large-v3-turbo",
                  allow_patterns=["*.json", "*.txt", "*.safetensors"])
print("Speech-to-text model ready.")
