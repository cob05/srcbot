from pydantic import BaseModel

class QuantizationInfo(BaseModel):
    quant: str
    file: str
    size_bytes: int
    size_gb: float

class SmartModelListResponse(BaseModel):
    repo_id: str
    model_name: str
    quantizations: list[QuantizationInfo]

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
