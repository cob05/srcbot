import os
from pathlib import Path

HF_TOKEN = os.getenv("HF_TOKEN")

CACHE_DIR = os.getenv(
    "HF_HOME",
    str(Path.home() / ".cache" / "huggingface")
)

MAX_CONCURRENT_DOWNLOADS = 1
