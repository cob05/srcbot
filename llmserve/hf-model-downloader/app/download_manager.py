import os
import threading
import uuid
from .hf_service import (
    get_file_metadata,
    stream_download,
    find_mmproj_files,
    select_mmproj
)
from .utils import check_disk_space
from .logger import get_logger
from .config import CACHE_DIR

logger = get_logger("download_manager")

class DownloadJob:
    def __init__(self, repo_id: str, filename: str):
        self.id = str(uuid.uuid4())
        self.repo_id: str = repo_id
        self.filename: str = filename
        self.status: str = "queued"
        self.progress: float = 0.0
        self.size: int | None = None
        self.downloaded: int = 0
        self.sha256: str | None = None
        self.cancelled: bool = False
        self.files = []

class DownloadManager:
    def __init__(self):
        self.jobs: dict[str, DownloadJob] = {}
        self.active_lock = threading.Lock()

    def create_job(self, repo_id: str, filename: str) -> DownloadJob:
        job = DownloadJob(repo_id, filename)
        self.jobs[job.id] = job

        thread = threading.Thread(
            target=self._run_download,
            args=(job,),
            daemon=True
        )
        thread.start()
        return job

    def _run_download(self, job):
        with self.active_lock:
            try:
                job.status = "preparing"

                files_to_download = [job.filename]

                mmproj_files = find_mmproj_files(job.repo_id)

                if mmproj_files:
                    selected_mmproj = select_mmproj(job.filename, mmproj_files)
                    if selected_mmproj:
                        files_to_download.append(selected_mmproj)

                total_size = 0

                for f in files_to_download:
                    size = get_file_metadata(job.repo_id, f)
                    total_size += size

                job.size = total_size

                if not check_disk_space(total_size):
                    job.status = "error: insufficient disk"
                    return

                job.status = "downloading"

                repo_dir = os.path.join(
                    CACHE_DIR,
                    job.repo_id.replace("/", "_")
                )
                os.makedirs(repo_dir, exist_ok=True)

                sha_results = {}

                for file in files_to_download:

                    if job.cancelled:
                        job.status = "cancelled"
                        return

                    path = os.path.join(repo_dir, file)

                    sha = stream_download(
                        job.repo_id,
                        file,
                        path,
                        job
                    )

                    sha_results[file] = sha
                    job.files.append(path)

                job.sha256 = sha_results
                job.progress = 100.0
                job.status = "completed"

            except Exception as e:
                logger.error(str(e))
                job.status = f"error: {str(e)}"

    def cancel_job(self, job_id: str):
        if job_id in self.jobs:
            self.jobs[job_id].cancelled = True

    def get_job(self, job_id: str) -> DownloadJob | None:
        return self.jobs.get(job_id)

download_manager = DownloadManager()