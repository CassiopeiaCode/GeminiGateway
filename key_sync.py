import random
import time
from datetime import datetime
import config
import database
from key_reader import read_and_format_api_keys


def read_keys():
    """Reads keys from the directory specified in the config."""
    return read_and_format_api_keys(config.KEYS_DIRECTORY)


def sync_keys_to_db():
    """
    Reads keys from the source directory, syncs them with the `api_keys` table,
    and then ensures the `key_model_status` table is aligned with `config.SUPPORTED_MODELS`.
    """
    # Sync `api_keys` table first
    sync_api_keys_table()

    # Now, sync `key_model_status` based on `SUPPORTED_MODELS`
    sync_key_model_status_table()


def sync_api_keys_table():
    """Ensures the api_keys table is in sync with the key files."""
    conn = database.get_db_connection()
    if conn is None:
        return

    try:
        keys_from_files = set(read_keys())
        
        with conn:
            # Get keys from DB
            cursor = conn.execute("SELECT id, key_value FROM api_keys")
            keys_in_db = {row['key_value']: row['id'] for row in cursor.fetchall()}
            db_key_values = set(keys_in_db.keys())

            # Add new keys to DB
            new_keys = keys_from_files - db_key_values
            if new_keys:
                conn.executemany("INSERT INTO api_keys (key_value) VALUES (?)", [(k,) for k in new_keys])
                print(f"Added {len(new_keys)} new keys to DB.")

            # Remove old keys from DB
            keys_to_remove = db_key_values - keys_from_files
            if keys_to_remove:
                ids_to_remove = [keys_in_db[val] for val in keys_to_remove]
                conn.executemany("DELETE FROM api_keys WHERE id = ?", [(id,) for id in ids_to_remove])
                print(f"Removed {len(keys_to_remove)} obsolete keys from DB.")

    except Exception as e:
        print(f"API key sync failed: {e}")
    finally:
        if conn:
            conn.close()


def sync_key_model_status_table():
    """
    Adds or removes records in `key_model_status` to match the `SUPPORTED_MODELS` list.
    """
    conn = database.get_db_connection()
    if conn is None:
        return

    try:
        current_supported_models = set(config.SUPPORTED_MODELS)
        
        with conn:
            # Get all key IDs from the api_keys table
            cursor = conn.execute("SELECT id FROM api_keys")
            all_key_ids = {row['id'] for row in cursor.fetchall()}

            # Get all existing key-model pairs from the database
            cursor = conn.execute("SELECT key_id, model_name FROM key_model_status")
            existing_db_pairs = {(row['key_id'], row['model_name']) for row in cursor.fetchall()}

            # 1. Add missing key-model pairs
            pairs_to_add = []
            for key_id in all_key_ids:
                for model_name in current_supported_models:
                    if (key_id, model_name) not in existing_db_pairs:
                        pairs_to_add.append((key_id, model_name, datetime.now().isoformat()))
            
            if pairs_to_add:
                conn.executemany(
                    "INSERT INTO key_model_status (key_id, model_name, next_test_time) VALUES (?, ?, ?)",
                    pairs_to_add
                )
                print(f"Added {len(pairs_to_add)} new key-model status records.")

            # 2. Delete obsolete key-model pairs
            pairs_to_delete = []
            for key_id, model_name in existing_db_pairs:
                if model_name not in current_supported_models:
                    pairs_to_delete.append((key_id, model_name))
            
            if pairs_to_delete:
                conn.executemany("DELETE FROM key_model_status WHERE key_id = ? AND model_name = ?", pairs_to_delete)
                print(f"Deleted {len(pairs_to_delete)} obsolete key-model status records.")

        print("Key-model status synchronization completed.")
    except Exception as e:
        print(f"Key-model status sync failed: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    # Example usage: Run sync periodically
    while True:
        sync_keys_to_db()
        time.sleep(config.KEY_SYNC_INTERVAL_SECONDS)
