from pydantic import BaseModel
from typing import Optional, List

class ModelListResponse(BaseModel):
    repo_id: str
    gguf_files: List[str]

class DownloadRequest(BaseModel):
    repo_id: str
    filename: str

class DownloadStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    size_bytes: Optional[int] = None
    downloaded_bytes: Optional[int] = None
    sha256: Optional[str] = None
    