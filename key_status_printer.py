import time
import os
from datetime import datetime
from collections import defaultdict
from database import get_model_aggregated_stats
from config import STATUS_FILE_PATH, MAX_STATUS_FILE_SIZE_MB, KEY_STATUS_PRINTER_INTERVAL_SECONDS

def clean_status_file_if_too_large():
    """
    如果 status.txt 文件大小超过 MAX_FILE_SIZE_MB，则清空文件。
    """
    if os.path.exists(STATUS_FILE_PATH):
        file_size_bytes = os.path.getsize(STATUS_FILE_PATH)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        if file_size_mb > MAX_STATUS_FILE_SIZE_MB:
            with open(STATUS_FILE_PATH, "w") as f:
                f.truncate(0)
            print(f"'{STATUS_FILE_PATH}' 文件大小超过 {MAX_STATUS_FILE_SIZE_MB}MB，已清空。")

def print_key_status():
    """
    获取并打印按模型聚合的密钥状态和请求统计到 status.txt 文件。
    """
    clean_status_file_if_too_large()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_content = f"--- Model Status Report ({timestamp}) ---\n\n"

    model_stats = get_model_aggregated_stats()

    if not model_stats:
        status_content += "No model stats available.\n"
    else:
        for stats in model_stats:
            status_content += f"Model: {stats['model_name']}\n"
            status_content += f"  - Available Keys: {stats['available_keys']}\n"
            status_content += f"  - Unavailable Keys: {stats['unavailable_keys']}\n"
            status_content += f"  - Requests (Last 30 mins): {stats['requests_last_30_mins']}\n\n"

    with open(STATUS_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(status_content)
    print(f"Model status report has been written to {STATUS_FILE_PATH} at {timestamp}")


if __name__ == "__main__":
    while True:
        print_key_status()
        time.sleep(KEY_STATUS_PRINTER_INTERVAL_SECONDS)