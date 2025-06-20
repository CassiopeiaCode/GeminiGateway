import sqlite3
import random
from datetime import datetime, timedelta
import config

DB_FILE = config.DATABASE_FILE


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Database connection failed: {e}")
        return None


def calculate_next_test_time(status_code):
    """Calculates the next test time based on the HTTP status code."""
    now = datetime.now()
    if status_code == 200:
        return now + timedelta(hours=config.TEST_INTERVAL_200_STATUS_HOURS)
    elif status_code == 403:
        return now + timedelta(days=config.TEST_INTERVAL_403_STATUS_DAYS)
    elif 400 <= status_code < 500:
        return now + timedelta(days=config.TEST_INTERVAL_4XX_STATUS_DAYS)
    elif 500 <= status_code < 600:
        return now + timedelta(minutes=config.TEST_INTERVAL_5XX_STATUS_MINUTES)
    else:
        return now + timedelta(days=1)  # Default for other errors


def initialize_database():
    """Initializes the database by creating the necessary tables if they don't exist."""
    conn = get_db_connection()
    if conn is None:
        return

    try:
        with conn:
            # Create api_keys table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_value TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create key_model_status table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS key_model_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_id INTEGER NOT NULL,
                    model_name TEXT NOT NULL,
                    last_tested TIMESTAMP,
                    next_test_time TIMESTAMP NOT NULL,
                    status_code INTEGER,
                    test_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (key_id, model_name),
                    FOREIGN KEY (key_id) REFERENCES api_keys(id) ON DELETE CASCADE
                );
            """)

            # Create request_logs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_id INTEGER REFERENCES api_keys(id),
                    model_name TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    request_path TEXT NOT NULL,
                    response_time_ms INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create banned_ips table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS banned_ips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT UNIQUE NOT NULL,
                    timestamp DATETIME NOT NULL
                );
            """)
        print("Database tables initialized successfully.")
    except sqlite3.Error as e:
        print(f"Database initialization failed: {e}")
    finally:
        if conn:
            conn.close()


def get_available_key_from_db(model_name):
    """
    Retrieves an available API key for the specified model from the database.
    Prioritizes keys with status 200, then untested keys.
    """
    conn = get_db_connection()
    if conn is None:
        return None

    try:
        now = datetime.now().isoformat()
        # First, try to get a key with status 200
        cursor = conn.execute(
            """
            SELECT ak.id, ak.key_value
            FROM api_keys ak
            JOIN key_model_status kms ON ak.id = kms.key_id
            WHERE kms.model_name = ? AND kms.status_code = 200
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (model_name,),
        )
        key = cursor.fetchone()
        if key:
            return {"id": key["id"], "key_value": key["key_value"]}

        # If no 200 key, try to get an random key
        print("No available key with status 200 found. Looking for random keys...")
        cursor = conn.execute(
            """
            SELECT ak.id, ak.key_value
            FROM api_keys ak
            JOIN key_model_status kms ON ak.id = kms.key_id
            WHERE kms.model_name = ?
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (model_name,),
        )
        key = cursor.fetchone()
        if key:
            return {"id": key["id"], "key_value": key["key_value"]}

        return None  # No suitable key found
    except sqlite3.Error as e:
        print(f"Failed to get available key: {e}")
        return None
    finally:
        if conn:
            conn.close()


def update_key_status_in_db(key_id, model_name, status_code, source='unknown'):
    """Updates the status of a key for a specific model in the database."""
    conn = get_db_connection()
    if conn is None:
        return

    now = datetime.now()
    now_iso = now.isoformat()

    try:
        with conn:
            if status_code == 200:
                # 成功时，按正常逻辑更新
                next_test_time = calculate_next_test_time(status_code)
                next_test_iso = next_test_time.isoformat()
            else:
                # 失败时，根据来源应用不同的重试逻辑
                if source == 'proxy_service':
                    # 代理服务失败时，检查当前的重试间隔
                    cursor = conn.execute(
                        "SELECT next_test_time FROM key_model_status WHERE key_id = ? AND model_name = ?",
                        (key_id, model_name),
                    )
                    current_status = cursor.fetchone()
                    
                    if current_status and current_status["next_test_time"]:
                        current_next_test_time = datetime.fromisoformat(current_status["next_test_time"])
                        retry_interval_seconds = (current_next_test_time - now).total_seconds()

                        if retry_interval_seconds > 300: # 5 minutes
                            # 如果间隔大于5分钟，则设置为5分钟后重试
                            next_test_time = now + timedelta(minutes=5)
                        else:
                            # 否则，保持原来的时间
                            next_test_time = current_next_test_time
                    else:
                        # 如果没有记录，则按常规计算
                        next_test_time = calculate_next_test_time(status_code)
                else:
                    # 对于其他来源（如 key_tester），保持原有的错误处理逻辑
                    next_test_time = calculate_next_test_time(status_code)
                
                next_test_iso = next_test_time.isoformat()

            conn.execute(
                """
                UPDATE key_model_status
                SET status_code = ?, test_count = test_count + 1, last_tested = ?, next_test_time = ?, updated_at = ?
                WHERE key_id = ? AND model_name = ?
                """,
                (status_code, now_iso, next_test_iso, now_iso, key_id, model_name),
            )
    except sqlite3.Error as e:
        print(f"Failed to update key {key_id} status for model '{model_name}': {e}")
    finally:
        if conn:
            conn.close()


def log_request_details(
    key_id, model_name, status_code, request_path, response_time_ms
):
    """Logs details of each request to the request_logs table."""
    conn = get_db_connection()
    if conn is None:
        return

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO request_logs (key_id, model_name, status_code, request_path, response_time_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key_id, model_name, status_code, request_path, response_time_ms),
            )
    except sqlite3.Error as e:
        print(f"Failed to log request: {e}")
    finally:
        if conn:
            conn.close()


def get_successful_key_count(model_name):
    """Counts the total number of keys with status code 200 for a specific model."""
    conn = get_db_connection()
    if conn is None:
        return 0

    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM key_model_status WHERE model_name = ? AND status_code = 200",
            (model_name,),
        )
        count = cursor.fetchone()[0]
        return count
    except sqlite3.Error as e:
        print(
            f"Error getting successful key count for model '{model_name}' from DB: {e}"
        )
        return 0
    finally:
        if conn:
            conn.close()


def get_all_key_stats():
    """Retrieves statistics for all keys and models.
    Returns a tuple of (valid_count, invalid_count, untested_count)"""
    conn = get_db_connection()
    if conn is None:
        return (0, 0, 0)

    try:
        # Get count of available keys (status 200)
        cursor = conn.execute(
            "SELECT COUNT(DISTINCT key_id) FROM key_model_status WHERE status_code = 200"
        )
        valid_count = cursor.fetchone()[0]

        # Get count of unavailable keys (status not 200 and not NULL)
        cursor = conn.execute(
            "SELECT COUNT(DISTINCT key_id) FROM key_model_status WHERE status_code != 200"
        )
        invalid_count = cursor.fetchone()[0]

        # Get count of untested keys (status is NULL)
        cursor = conn.execute(
            "SELECT COUNT(DISTINCT key_id) FROM key_model_status WHERE status_code IS NULL"
        )
        untested_count = cursor.fetchone()[0]

        return (valid_count, invalid_count, untested_count)
    except sqlite3.Error as e:
        print(f"Error getting all key stats: {e}")
        return (0, 0, 0)
    finally:
        if conn:
            conn.close()


def get_all_key_model_statuses():
    """
    Retrieves the status of all models for each key.
    """
    conn = get_db_connection()
    if conn is None:
        return []

    try:
        cursor = conn.execute("""
            SELECT
                ak.key_value,
                kms.model_name,
                kms.status_code,
                kms.last_tested,
                kms.next_test_time
            FROM api_keys ak
            JOIN key_model_status kms ON ak.id = kms.key_id
            ORDER BY ak.key_value, kms.model_name
        """)
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Error getting all key model statuses: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_recent_requests_count():
    """Gets the count of requests in the last 24 hours."""
    conn = get_db_connection()
    if conn is None:
        return 0

    try:
        twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM request_logs WHERE created_at >= ?",
            (twenty_four_hours_ago.isoformat(),),
        )
        count = cursor.fetchone()[0]
        return count
    except sqlite3.Error as e:
        print(f"Error getting recent requests count: {e}")
        return 0
    finally:
        if conn:
            conn.close()


def get_model_aggregated_stats():
    """
    Aggregates key stats by model and gets recent request counts.
    """
    conn = get_db_connection()
    if conn is None:
        return []

    stats = {}

    try:
        # Get available/unavailable key counts per model
        cursor = conn.execute("""
            SELECT
                model_name,
                SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as available_keys,
                SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as unavailable_keys
            FROM key_model_status
            GROUP BY model_name
        """)
        rows = cursor.fetchall()
        for row in rows:
            stats[row["model_name"]] = {
                "available_keys": row["available_keys"] or 0,
                "unavailable_keys": row["unavailable_keys"] or 0,
                "requests_last_30_mins": 0,
            }

        # Get request counts for the last 30 minutes per model
        thirty_minutes_ago = (datetime.now() - timedelta(minutes=30)).isoformat()
        cursor = conn.execute(
            """
            SELECT
                model_name,
                COUNT(*) as request_count
            FROM request_logs
            WHERE created_at >= ?
            GROUP BY model_name
        """,
            (thirty_minutes_ago,),
        )
        rows = cursor.fetchall()
        for row in rows:
            if row["model_name"] in stats:
                stats[row["model_name"]]["requests_last_30_mins"] = row["request_count"]

        # Convert dict to list of dicts for the final output
        result = [{"model_name": model, **data} for model, data in stats.items()]
        return result

    except sqlite3.Error as e:
        print(f"Error getting model aggregated stats: {e}")
        return []
    finally:
        if conn:
            conn.close()


def cleanup_old_logs():
    """Deletes request logs older than a specified number of days."""
    conn = get_db_connection()
    if conn is None:
        return

    try:
        threshold_date = (
            datetime.now() - timedelta(days=config.LOG_CLEANER_INTERVAL_SECONDS / 86400)
        ).isoformat()
        with conn:
            cursor = conn.execute(
                "DELETE FROM request_logs WHERE created_at < ?", (threshold_date,)
            )
            print(
                f"Deleted {cursor.rowcount} logs older than {config.LOG_CLEANER_INTERVAL_SECONDS / 86400} days."
            )
    except sqlite3.Error as e:
        print(f"Error cleaning up old logs: {e}")
    finally:
        if conn:
            conn.close()


def add_banned_ip(ip_address):
    """Adds a banned IP address to the database."""
    conn = get_db_connection()
    if conn is None:
        return

    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO banned_ips (ip_address, timestamp) VALUES (?, ?)",
                (ip_address, datetime.now()),
            )
    except sqlite3.Error as e:
        print(f"Failed to add banned IP {ip_address}: {e}")
    finally:
        if conn:
            conn.close()


def remove_banned_ip(ip_address):
    """Removes a banned IP address from the database."""
    conn = get_db_connection()
    if conn is None:
        return

    try:
        with conn:
            conn.execute("DELETE FROM banned_ips WHERE ip_address = ?", (ip_address,))
    except sqlite3.Error as e:
        print(f"Failed to remove banned IP {ip_address}: {e}")
    finally:
        if conn:
            conn.close()


def get_all_banned_ips():
    """Retrieves all banned IPs from the database."""
    conn = get_db_connection()
    if conn is None:
        return set()

    try:
        cursor = conn.execute("SELECT ip_address, timestamp FROM banned_ips")
        # Return a dictionary of {ip: timestamp}
        return {
            row["ip_address"]: datetime.fromisoformat(row["timestamp"])
            for row in cursor.fetchall()
        }
    except sqlite3.Error as e:
        print(f"Failed to get all banned IPs: {e}")
        return {}
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    initialize_database()
    print("Database setup complete.")
