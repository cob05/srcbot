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
    logger.info(f"Listing GGUF files for repo: {repo_id}")
    try:
        files = api.list_repo_files(repo_id=repo_id)
    except RepositoryNotFoundError:
        raise ValueError("Repository not found")

    ggufs = [f for f in files if f.endswith(".gguf")]
    mmproj = [f for f in files if "mmproj" in f.lower()]
    result = sorted(ggufs + mmproj)
    logger.info(f"Found {len(result)} GGUF files in {repo_id}")
    return result


def get_file_metadata(repo_id: str, filename: str):
    """
    Returns file size in bytes using get_paths_info.
    """
    logger.debug(f"Fetching metadata for {filename} in {repo_id}")
    try:
        info = get_paths_info(
            repo_id=repo_id,
            paths=[filename],
            repo_type="model"
        )
    except Exception as e:
        logger.error(f"Error fetching metadata for {filename} in {repo_id}: {str(e)}")
        raise ValueError(f"Unable to fetch metadata: {str(e)}")

    if not info:
        logger.error(f"File {filename} not found in repository {repo_id}")
        raise ValueError("File not found in repository")

    file_info = info[0]

    # Check if it's a file (RepoFile) and not a folder (RepoFolder)
    if not isinstance(file_info, RepoFile) or file_info.size is None:
        logger.error(f"Path {filename} in {repo_id} is not a file")
        raise ValueError("Path is not a file")

    logger.info(f"File {filename} size: {file_info.size} bytes")
    return file_info.size


def find_mmproj_files(repo_id: str):
    """
    Returns all mmproj files in the repository.
    """
    logger.debug(f"Searching for mmproj files in {repo_id}")
    files = api.list_repo_files(repo_id=repo_id)
    result = [f for f in files if f.lower().startswith("mmproj") and f.endswith(".gguf")]
    logger.info(f"Found {len(result)} mmproj files in {repo_id}")
    return result


def select_mmproj(main_filename: str, mmproj_files: list[str]):
    """
    Attempts to find the best mmproj match for the selected GGUF quantization.
    """

    if not mmproj_files:
        logger.debug("No mmproj files available for selection")
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
                logger.info(f"Selected mmproj file: {f} (quantization match)")
                return f

    # try f16 mmproj match
    for f in mmproj_files:
        if "bf16" not in f.lower():  # avoid bfloat16 files
            if "f16" in f.lower():
                logger.info(f"Selected mmproj file: {f} (f16 fallback)")
                return f

    # fallback: first mmproj
    logger.info(f"Selected mmproj file: {mmproj_files[0]} (fallback)")
    return mmproj_files[0]


def parse_quant_from_filename(filename: str):
    """
    Extract quantization string from GGUF filename.
    Works for common formats like:
    Q4_K_M, Q8_0, Q6_K, F16, IQ2_XS, etc.
    It even captures the new UD- prefix format from Unsloth.
    """
    pattern = r"((?:UD-)?(?:Q\d+_[A-Z0-9_]+|Q\d+|F16|BF16|IQ\d+_[A-Z0-9_]+))"
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
    logger.info(f"Building quantization list for repo: {repo_id}")
    files = api.list_repo_files(repo_id=repo_id)

    ggufs = [
        f for f in files
        if f.endswith(".gguf") and "mmproj" not in f.lower()
    ]

    if not ggufs:
        return None

    model_name = detect_base_model_name(ggufs)
    logger.info(f"Detected model name: {model_name}")

    quantizations = []

    for file in ggufs:
        size = get_file_metadata(repo_id, file)

        quant = parse_quant_from_filename(file)

        quantizations.append({
            "quant": quant.upper(),
            "file": file,
            "size_bytes": size,
            "size_gb": round(size / (1024**3), 2)
        })

    # sort smallest → largest
    quantizations.sort(key=lambda x: x["size_bytes"])

    logger.info(f"Found {len(quantizations)} quantizations for {model_name}")
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

    logger.info(f"Starting download: {filename} to {destination_path}")
    url = hf_hub_url(repo_id, filename)

    headers = {}
    mode = "wb"
    downloaded_bytes = 0

    if os.path.exists(destination_path):
        downloaded_bytes = os.path.getsize(destination_path)
        headers["Range"] = f"bytes={downloaded_bytes}-"
        mode = "ab"
        logger.info(f"Resuming download from {downloaded_bytes} bytes")

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

    sha256_hash = sha256.hexdigest()
    logger.info(f"Download completed: {filename}, sha256: {sha256_hash}")
    return sha256_hash