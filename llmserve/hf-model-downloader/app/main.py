from fastapi import FastAPI, HTTPException
from .schemas import *
from .download_manager import download_manager
from .hf_service import build_smart_quant_list
from .logger import get_logger

logger = get_logger("main")

app = FastAPI(title="HF GGUF Downloader")

@app.get("/models/{repo_id:path}", response_model=SmartModelListResponse)
def list_models(repo_id: str):
    logger.info(f"Listing models for repo: {repo_id}")

    result = build_smart_quant_list(repo_id)

    if not result:
        raise HTTPException(status_code=404, detail="No GGUF models found")

    model_name, quantizations = result

    logger.info(f"Model: {model_name}, quantizations found: {len(quantizations)}")

    return SmartModelListResponse(
        repo_id=repo_id,
        model_name=model_name,
        quantizations=[
            QuantizationInfo(**q)
            for q in quantizations
        ]
    )

@app.post("/download", response_model=DownloadStatus)
def start_download(req: DownloadRequest):
    job = download_manager.create_job(req.repo_id, req.filename)
    logger.info(f"Download started: job_id={job.id}, repo_id={req.repo_id}, filename={req.filename}")
    return DownloadStatus(
        job_id=job.id,
        status=job.status,
        progress=job.progress
    )

@app.get("/download/{job_id}", response_model=DownloadStatus)
def get_status(job_id: str):
    logger.debug(f"Status queried for job: {job_id}")
    job = download_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return DownloadStatus(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        size_bytes=job.size,
        downloaded_bytes=job.downloaded,
        sha256=job.sha256,
        files=job.files
    )

@app.post("/download/{job_id}/cancel")
def cancel_download(job_id: str):
    logger.info(f"Download cancel requested for job: {job_id}")
    download_manager.cancel_job(job_id)
    return {"status": "cancelling"}

@app.get("/health")
def health():
    logger.debug("Health check called")
    return {"status": "ok"}
