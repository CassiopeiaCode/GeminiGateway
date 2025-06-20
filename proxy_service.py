import os
import traceback
import requests
import random
from flask import Flask, request, jsonify, make_response, Response, stream_with_context
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from datetime import datetime, timedelta
import config  # 导入配置文件
from database import (
    get_successful_key_count,
    update_key_status_in_db,
    log_request_details,
    get_available_key_from_db,
)
from rate_limiter import rate_limiter

app = Flask(__name__)

# 从config.py导入配置
AUTH_KEY = config.AUTH_KEY
MAX_RETRIES = config.MAX_RETRIES
SUPPORTED_MODELS = config.SUPPORTED_MODELS
AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", config.AI_GATEWAY_URL)
DEFAULT_UPSTREAM_URL = config.DEFAULT_UPSTREAM_URL
KEY_AVAILABILITY_THRESHOLD_LOW = config.KEY_AVAILABILITY_THRESHOLD_LOW
KEY_AVAILABILITY_THRESHOLD_HIGH = config.KEY_AVAILABILITY_THRESHOLD_HIGH


# Custom exception for SSE pre-check failure
class SSEPrecheckError(Exception):
    pass


def _validate_path(subpath):
    """
    Validates the request path format, extracts the model name,
    and checks if the model is supported.
    Returns (is_valid, error_message, status_code, model_name).
    """
    if not subpath.startswith("v1beta/models/"):
        return False, "Not Found", 404, None

    # Handle paths like "v1beta/models/gemini-pro:generateContent"
    path_parts = subpath.split(":")
    model_part = path_parts[0]

    model_name_parts = model_part.split("/")
    if len(model_name_parts) < 3:
        return False, "Invalid path format", 404, None

    model_name = model_name_parts[-1]

    if model_name not in SUPPORTED_MODELS:
        return False, f"Model '{model_name}' not supported", 404, None

    return True, None, None, model_name


def _authenticate_request():
    """验证客户端API密钥。"""
    if AUTH_KEY:
        client_key = request.args.get("key")
        header_key = request.headers.get("x-goog-api-key")
        if client_key != AUTH_KEY and header_key != AUTH_KEY:
            return False
    return True


def _check_key_availability(model):
    """检查针对特定模型的可用密钥数量并根据策略决定是否拒绝请求。"""
    successful_key_count = get_successful_key_count(model)
    reject_request = False
    if successful_key_count < KEY_AVAILABILITY_THRESHOLD_LOW:
        reject_request = True
    elif (
        KEY_AVAILABILITY_THRESHOLD_LOW
        <= successful_key_count
        < KEY_AVAILABILITY_THRESHOLD_HIGH
    ):
        # This uses the formula from the config, but it's safer to keep the logic here
        probability_of_rejection = eval(
            config.KEY_REJECTION_PROBABILITY_FORMULA,
            {"successful_key_count": successful_key_count},
        )
        if random.random() < probability_of_rejection:
            reject_request = True

    if reject_request:
        print(
            f"Request rejected due to key availability for model {model}. Count: {successful_key_count}"
        )
        return False, "当前没有可用的gemini key", 500
    return True, None, None


def _build_upstream_url(subpath):
    """根据配置构建上游API的URL。"""
    upstream_url = ""

    if AI_GATEWAY_URL:
        model_path = subpath.split("/")[-1]
        upstream_url = f"{AI_GATEWAY_URL}/google-ai-studio/v1beta/models/{model_path}"
    else:
        upstream_url = f"{DEFAULT_UPSTREAM_URL}/{subpath}"

    parsed_url = urlparse(request.url)
    query_params = parse_qs(parsed_url.query)
    query_params.pop("key", None)

    if query_params:
        upstream_url += "?" + urlencode(query_params, doseq=True)

    return upstream_url


def _handle_sse_stream(response, response_headers):
    """处理Server-Sent Events (SSE) 流式响应，包括预检。"""

    def generate():
        buffer = b""
        event_count = 0
        precheck_done = False
        buffered_events_list = []

        response_iterator = response.iter_content(chunk_size=8192)

        for chunk in response_iterator:
            buffer += chunk
            if not precheck_done:
                while b"\r\n\r\n" in buffer and not precheck_done:
                    event_end_index = buffer.find(b"\r\n\r\n") + 4
                    event = buffer[:event_end_index]
                    buffer = buffer[event_end_index:]
                    buffered_events_list.append(event)
                    event_count += 1
                    if event_count == 2:
                        precheck_done = True
                        break
                if precheck_done:
                    break

        if event_count < 2:
            raise SSEPrecheckError(
                f"SSE pre-check failed: Insufficient events received. {b''.join(buffered_events_list).decode('utf-8',errors='ignore')}--{buffer.decode('utf-8',errors='ignore')}"
            )

        for event in buffered_events_list:
            yield event

        if buffer:
            yield buffer

        for chunk in response_iterator:
            yield chunk

    response_headers = {
        k: v for k, v in response_headers.items() if k.lower() != "transfer-encoding"
    }
    return Response(stream_with_context(generate()), headers=response_headers)


def _execute_proxy_request(subpath, key_value):
    """执行代理请求并返回原始requests响应。"""
    upstream_url = _build_upstream_url(subpath)
    print(f"upstreamUrl: {upstream_url}")

    new_headers = dict(request.headers)
    new_headers["x-goog-api-key"] = key_value
    new_headers["host"] = "generativelanguage.googleapis.com"

    request_kwargs = {
        "method": request.method,
        "url": upstream_url,
        "headers": new_headers,
        "data": request.data,
        "stream": True,
    }
    if isinstance(config.PROXY, str):
        request_kwargs["proxies"] = {"http": config.PROXY, "https": config.PROXY}

    response = requests.request(**request_kwargs)
    return response


def _stream_response(response, response_headers, status_code):
    """根据响应类型（SSE或普通）流式传输响应。"""
    if "text/event-stream" in response.headers.get("Content-Type", ""):
        return _handle_sse_stream(response, response_headers)
    else:
        full_content = b"".join(response.iter_content(chunk_size=8192))
        return Response(
            full_content,
            headers=response_headers,
            status=status_code,
        )


@app.route("/<path:subpath>", methods=["POST"])
def handle_request(subpath):
    # 1. Authentication & Rate Limiting for unauthorized access
    if not _authenticate_request():
        client_ip = request.remote_addr
        if not rate_limiter.check_rate_limit(client_ip):
            print(f"IP {client_ip} hit rate limit.")
            return make_response(jsonify(error="Too Many Requests"), 429)

    # 2. Path validation and model name extraction
    is_valid, error_message, status_code, model_name = _validate_path(subpath)
    if not is_valid:
        return make_response(jsonify(error=error_message), status_code)

    # 3. Key availability check (only for unauthorized access)
    if not _authenticate_request():
        is_available, error_message, status_code = _check_key_availability(model_name)
        if not is_available:
            return make_response(jsonify(error=error_message), status_code)

    used_key_ids = set()

    for retry_count in range(MAX_RETRIES):
        key = get_available_key_from_db(model_name)
        if key is None:
            if retry_count == 0:
                # Log failure only on the first attempt to find a key
                log_request_details(None, model_name, 503, request.path, 0)
            print(
                f"No available keys for model '{model_name}', retrying... ({retry_count + 1}/{MAX_RETRIES})"
            )
            continue

        key_id, key_value = key["id"], key["key_value"]

        if key_id in used_key_ids:
            print(f"Key {key_id} already used in this sequence, getting another.")
            continue
        used_key_ids.add(key_id)

        start_time = datetime.now()
        try:
            response = _execute_proxy_request(subpath, key_value)
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)
            status_code = response.status_code

            update_key_status_in_db(key_id, model_name, status_code, source='proxy_service')
            log_request_details(
                key_id, model_name, status_code, request.path, response_time_ms
            )

            response_headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower()
                not in ["transfer-encoding", "content-encoding", "content-length"]
            }

            if response.ok:
                return _stream_response(response, response_headers, status_code)
            else:
                print(
                    f"Upstream failed with status {status_code}. Retrying... ({retry_count + 1}/{MAX_RETRIES})"
                )
                print(
                    f"raw  response: {response.content.decode(errors='ignore')[:1000]}"
                )  # Log first 1000 chars
                continue  # Retry with a new key

        except (requests.exceptions.RequestException, SSEPrecheckError) as e:
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)
            print(f"Request/SSE error for key {key_id}: {e}")
            update_key_status_in_db(key_id, model_name, 500, source='proxy_service')  # Mark key as faulty
            log_request_details(key_id, model_name, 500, request.path, response_time_ms)
            continue  # Retry with a new key

        except Exception as e:
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)
            print(
                f"An unexpected error occurred for key {key_id}: {e}\n{traceback.format_exc()}"
            )
            update_key_status_in_db(key_id, model_name, 500, source='proxy_service')  # Mark key as faulty
            log_request_details(key_id, model_name, 500, request.path, response_time_ms)
            continue  # Retry with a new key

    # If all retries fail
    return make_response(
        jsonify(
            error=f"Service temporarily unavailable for model '{model_name}' after {MAX_RETRIES} retries."
        ),
        503,
    )


if __name__ == "__main__":
    app.run(debug=True, port=52948)
