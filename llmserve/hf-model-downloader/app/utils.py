import shutil

def check_disk_space(required_bytes: int):
    total, used, free = shutil.disk_usage("/")
    return free >= required_bytes
