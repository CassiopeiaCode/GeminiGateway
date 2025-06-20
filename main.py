import threading
import time
import config  # 导入配置文件
from database import (
    initialize_database,
    cleanup_old_logs,
)
from key_sync import sync_keys_to_db
from key_tester import run_key_tester
from key_status_printer import print_key_status
from proxy_service import app


def run_key_sync_periodically():
    """Runs key sync in a loop."""
    while True:
        sync_keys_to_db()
        time.sleep(config.KEY_SYNC_INTERVAL_SECONDS)


def run_key_tester_periodically():
    """Runs key tester in a loop."""
    while True:
        run_key_tester()
        time.sleep(config.KEY_TESTER_INTERVAL_SECONDS)


def run_key_status_printer_periodically():
    """Runs key status printer in a loop."""
    while True:
        print_key_status()
        time.sleep(config.KEY_STATUS_PRINTER_INTERVAL_SECONDS)


def run_log_cleaner_periodically():
    """Runs log cleaner in a loop."""
    while True:
        cleanup_old_logs()
        time.sleep(config.LOG_CLEANER_INTERVAL_SECONDS)


if __name__ == "__main__":
    # 1. Initialize database
    initialize_database()

    # 2. Start key sync in a separate thread
    key_sync_thread = threading.Thread(target=run_key_sync_periodically, daemon=True)
    key_sync_thread.start()
    print("Key sync thread started.")

    # 3. Start key tester in a separate thread
    key_tester_thread = threading.Thread(
        target=run_key_tester_periodically, daemon=True
    )
    key_tester_thread.start()
    print("Key tester thread started.")

    # 4. Start key status printer in a separate thread
    key_status_printer_thread = threading.Thread(
        target=run_key_status_printer_periodically, daemon=True
    )
    key_status_printer_thread.start()
    print("Key status printer thread started.")

    # 5. Start log cleaner in a separate thread
    log_cleaner_thread = threading.Thread(
        target=run_log_cleaner_periodically, daemon=True
    )
    log_cleaner_thread.start()
    print("Log cleaner thread started.")

    # 6. Start the Flask proxy service
    print("Starting proxy service...")
    # In a real deployment, use a production-ready WSGI server
    app.run(debug=config.DEBUG_MODE, port=config.APP_PORT, host=config.APP_HOST)
