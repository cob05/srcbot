from pydantic import BaseModel

class ModelListResponse(BaseModel):
    repo_id: str
    gguf_files: list[str]

class DownloadRequest(BaseModel):
    repo_id: str
    filename: str

class DownloadStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    size_bytes: int | None = None
    downloaded_bytes: int | None = None
    sha256: str | None = None
    files: list[str] | None = None
