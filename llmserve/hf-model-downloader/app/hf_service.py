from huggingface_hub import HfApi, hf_hub_download, get_paths_info
from huggingface_hub.errors import RepositoryNotFoundError
from huggingface_hub.hf_api import RepoFile
from .config import HF_TOKEN
from .logger import get_logger
import hashlib

logger = get_logger("hf_service")

api = HfApi(token=HF_TOKEN)


def list_gguf_files(repo_id: str):
    """
    Lists GGUF files and mmproj files in a repository.
    """
    try:
        files = api.list_repo_files(repo_id=repo_id)
    except RepositoryNotFoundError:
        raise ValueError("Repository not found")

    ggufs = [f for f in files if f.endswith(".gguf")]
    mmproj = [f for f in files if "mmproj" in f.lower()]

    return sorted(ggufs + mmproj)


def get_file_metadata(repo_id: str, filename: str):
    """
    Returns file size in bytes using get_paths_info.
    """
    try:
        info = get_paths_info(
            repo_id=repo_id,
            paths=[filename],
            repo_type="model"
        )
    except Exception as e:
        raise ValueError(f"Unable to fetch metadata: {str(e)}")

    if not info:
        raise ValueError("File not found in repository")

    file_info = info[0]

    # Check if it's a file (RepoFile) and not a folder (RepoFolder)
    if not isinstance(file_info, RepoFile) or file_info.size is None:
        raise ValueError("Path is not a file")

    return file_info.size


def download_file(repo_id: str, filename: str):
    """
    Downloads a file with resume support.
    """
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        token=HF_TOKEN,
        resume_download=True,
    )
    return path


def compute_sha256(path: str):
    """
    Computes SHA256 of a downloaded file.
    """
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()