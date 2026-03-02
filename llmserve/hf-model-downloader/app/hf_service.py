import shutil
import hashlib
from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import RepositoryNotFoundError
from .config import HF_TOKEN
from .logger import get_logger

logger = get_logger("hf_service")
api = HfApi(token=HF_TOKEN)

def list_gguf_files(repo_id: str):
    try:
        files = api.list_repo_files(repo_id=repo_id)
    except RepositoryNotFoundError:
        raise ValueError("Repository not found")

    ggufs = [f for f in files if f.endswith(".gguf")]
    mmproj = [f for f in files if "mmproj" in f]

    return sorted(ggufs + mmproj)

def get_file_metadata(repo_id: str, filename: str):
    info = api.repo_file_info(repo_id, filename)
    return info.size, info.lfs

def download_file(repo_id: str, filename: str, progress_callback=None):
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        token=HF_TOKEN,
        resume_download=True,
    )
    return path

def compute_sha256(path):
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
