from fastapi import FastAPI, HTTPException
from .schemas import *
from .hf_service import list_gguf_files
from .download_manager import download_manager

app = FastAPI(title="HF GGUF Downloader")

@app.get("/models/{repo_id}", response_model=ModelListResponse)
def list_models(repo_id: str):
    files = list_gguf_files(repo_id)
    return ModelListResponse(repo_id=repo_id, gguf_files=files)

@app.post("/download", response_model=DownloadStatus)
def start_download(req: DownloadRequest):
    job = download_manager.create_job(req.repo_id, req.filename)
    return DownloadStatus(
        job_id=job.id,
        status=job.status,
        progress=job.progress
    )

@app.get("/download/{job_id}", response_model=DownloadStatus)
def get_status(job_id: str):
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
    download_manager.cancel_job(job_id)
    return {"status": "cancelling"}

@app.get("/health")
def health():
    return {"status": "ok"}
