import shutil

def check_disk_space(required_bytes: int):
    _total, _used, free = shutil.disk_usage("/")
    return free >= required_bytes
