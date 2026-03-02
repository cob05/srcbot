import os
import re
import httpx
import hashlib
from huggingface_hub import HfApi, hf_hub_url
from huggingface_hub.hf_api import RepoFile
from huggingface_hub.errors import RepositoryNotFoundError
from huggingface_hub import get_paths_info
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


def find_mmproj_files(repo_id: str):
    """
    Returns all mmproj files in the repository.
    """
    files = api.list_repo_files(repo_id=repo_id)
    return [f for f in files if f.lower().startswith("mmproj") and f.endswith(".gguf")]


def select_mmproj(main_filename: str, mmproj_files: list[str]):
    """
    Attempts to find the best mmproj match for the selected GGUF quantization.
    """

    if not mmproj_files:
        return None

    # extract quantization string
    quant = None
    parts = main_filename.split("-")

    for p in parts:
        if p.startswith("Q"):
            quant = p
            break

    # try exact quantized mmproj match
    if quant:
        for f in mmproj_files:
            if quant in f:
                return f

    # try f16 mmproj match
    for f in mmproj_files:
        if "bf16" not in f.lower():  # avoid bfloat16 files
            if "f16" in f.lower():
                return f

    # fallback: first mmproj
    return mmproj_files[0]


def parse_quant_from_filename(filename: str):
    """
    Extract quantization string from GGUF filename.
    Works for common formats like:
    Q4_K_M, Q8_0, Q6_K, F16, IQ2_XS, etc.
    """
    pattern = r"(Q\d+_[A-Z0-9_]+|Q\d+|F16|BF16|IQ\d+_[A-Z0-9_]+)"
    match = re.search(pattern, filename, re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return "UNKNOWN"


def detect_base_model_name(files: list[str]):
    """
    Attempt to detect base model name by removing quant suffix.
    """
    if not files:
        return "unknown"

    sample = files[0]

    # remove .gguf
    name = sample.replace(".gguf", "")

    # remove quant portion
    quant = parse_quant_from_filename(sample)
    name = name.replace(f"-{quant}", "")
    name = name.replace(f"_{quant}", "")

    return name


def build_smart_quant_list(repo_id: str):
    files = api.list_repo_files(repo_id=repo_id)

    ggufs = [
        f for f in files
        if f.endswith(".gguf") and "mmproj" not in f.lower()
    ]

    if not ggufs:
        return None

    model_name = detect_base_model_name(ggufs)

    quantizations = []

    for file in ggufs:
        size = get_file_metadata(repo_id, file)

        quant = parse_quant_from_filename(file)

        quantizations.append({
            "quant": quant,
            "file": file,
            "size_bytes": size,
            "size_gb": round(size / (1024**3), 2)
        })

    # sort smallest → largest
    quantizations.sort(key=lambda x: x["size_bytes"])

    return model_name, quantizations


def stream_download(
    repo_id: str,
    filename: str,
    destination_path: str,
    job
):
    """
    Streams file with resume + byte-level progress tracking.
    """

    url = hf_hub_url(repo_id, filename)

    headers = {}
    mode = "wb"
    downloaded_bytes = 0

    if os.path.exists(destination_path):
        downloaded_bytes = os.path.getsize(destination_path)
        headers["Range"] = f"bytes={downloaded_bytes}-"
        mode = "ab"

    job.downloaded = downloaded_bytes

    sha256 = hashlib.sha256()

    with httpx.stream(
        "GET",
        url,
        headers=headers,
        timeout=None,
        follow_redirects=True,
    ) as response:

        response.raise_for_status()

        with open(destination_path, mode) as f:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):

                if job.cancelled:
                    logger.info("Download cancelled")
                    return None

                f.write(chunk)
                sha256.update(chunk)

                downloaded_bytes += len(chunk)
                job.downloaded = downloaded_bytes

                if job.size:
                    job.progress = (downloaded_bytes / job.size) * 100

    return sha256.hexdigest()