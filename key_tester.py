import time
import random
from datetime import datetime, timedelta
import requests
import json
from database import get_db_connection, update_key_status_in_db
from config import (
    SUPPORTED_MODELS,
    KEY_TESTER_BATCH_LIMIT,
    KEY_TESTER_DEFAULT_TEST_URL,
    KEY_TESTER_INTERVAL_SECONDS,
    TEST_INTERVAL_200_STATUS_HOURS,
    TEST_INTERVAL_403_STATUS_DAYS,
    TEST_INTERVAL_4XX_STATUS_DAYS,
    TEST_INTERVAL_5XX_STATUS_MINUTES,
    PROXY,
)


def test_key(key_value, model_name):
    """
    测试单个API密钥对指定模型的可用性。
    """
    url = KEY_TESTER_DEFAULT_TEST_URL.format(model_name=model_name)
    headers = {"x-goog-api-key": key_value, "Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": "Hello, world!"}]}]}
    request_kwargs = {
        "headers": headers,
        "data": json.dumps(payload),
    }
    if isinstance(PROXY, str):
        request_kwargs["proxies"] = {"http": PROXY, "https": PROXY}

    try:
        response = requests.post(url, **request_kwargs)
        return response.status_code
    except Exception as e:
        print(f"测试密钥时发生错误 {key_value[:5]}... 模型 {model_name}: {e}")
        return None


def run_key_tester():
    """
    遍历所有密钥，并独立测试每个密钥支持的每个模型。
    """
    conn = get_db_connection()
    if conn is None:
        print("无法连接到数据库。")
        return

    try:
        # 1. 获取所有唯一的密钥
        all_keys = conn.execute("SELECT id, key_value FROM api_keys").fetchall()

        if not all_keys:
            print("数据库中没有找到API密钥。")
            return

        print(f"开始测试 {len(all_keys)} 个密钥...")

        # 2. 遍历每个密钥
        for key in all_keys:
            key_id = key["id"]
            key_value = key["key_value"]

            # 3. 遍历该密钥支持的所有模型
            for model_name in SUPPORTED_MODELS:
                # 4. 独立判断每个模型是否需要测试
                model_status = conn.execute(
                    """
                    SELECT last_tested, next_test_time
                    FROM key_model_status
                    WHERE key_id = ? AND model_name = ?
                """,
                    (key_id, model_name),
                ).fetchone()

                # 如果没有状态记录，或者 next_test_time 已到，则需要测试
                needs_test = False
                if model_status is None:
                    needs_test = True
                else:
                    next_test_time_str = model_status["next_test_time"]
                    if (
                        next_test_time_str is None
                        or datetime.fromisoformat(next_test_time_str) <= datetime.now()
                    ):
                        needs_test = True

                if needs_test:
                    # print(
                    #     f"  正在测试密钥 {key_value[:5]}... 在模型 {model_name} 上的状态..."
                    # )
                    status_code = test_key(key_value, model_name)
                    if status_code is not None:
                        update_key_status_in_db(
                            key_id, model_name, status_code, source="key_tester"
                        )
                        # print(f"    -> 测试完成，状态码: {status_code}")
                    else:
                        ...
                        # print(f"    -> 测试失败。")
                # else:
                #     print(f"  密钥 {key_value[:5]}... 在模型 {model_name} 上无需测试，下次测试时间: {model_status['next_test_time']}")

    except Exception as e:
        print(f"密钥测试器运行时发生错误: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    # Example usage: Run key tester periodically
    while True:
        run_key_tester()
        time.sleep(KEY_TESTER_INTERVAL_SECONDS)
