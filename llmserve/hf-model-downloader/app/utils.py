import shutil

def check_disk_space(required_bytes: int):
    _total, _used, free = shutil.disk_usage("/data")
    return free >= required_bytes
