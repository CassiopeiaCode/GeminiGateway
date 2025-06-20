# -*- coding: utf-8 -*-
# 文件: config.py
# 描述: 集中存储所有可变配置项，便于管理和修改。

# --- 应用基础设置 ---
APP_HOST = "0.0.0.0"  # Flask 应用绑定的主机地址, "0.0.0.0" 表示监听所有网络接口
APP_PORT = 55200  # Flask 应用监听的端口号
DEBUG_MODE = False  # 是否开启 Flask 的调试模式，生产环境应设为 False

# --- 认证与安全 ---
# 用于认证的密钥，提供此密钥的请求将绕过速率限制和熔断机制
# 生产环境中，强烈建议从环境变量读取，而不是硬编码在代码里
AUTH_KEY = "your-secure-auth-key-here"

# --- API 密钥管理 ---
KEYS_DIRECTORY = "keys/"  # 存放 API 密钥文件的目录，程序会读取此目录下所有文件
DATABASE_FILE = "api_proxy.db"  # SQLite 数据库文件名，用于存储密钥状态和日志
# 本代理服务支持的 Gemini 模型列表
SUPPORTED_MODELS = [
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-flash-preview-05-20",
    "gemini-2.5-flash-lite-preview-06-17",
    "gemini-2.0-flash-preview-image-generation",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemma-3n-e4b-it",
    "gemma-3-1b-it",
    "gemma-3-4b-it",
    "gemma-3-12b-it",
    "gemma-3-27b-it",
]


# --- 代理核心逻辑设置 ---
MAX_RETRIES = 5  # 当一个请求失败时，最多尝试切换多少个不同的密钥进行重试
DEFAULT_UPSTREAM_URL = (
    "https://generativelanguage.googleapis.com"  # 默认的上游 Google API 地址
)
# (可选) 如果您使用自定义的 AI 网关，请设置此 URL，否则请保持为 None
AI_GATEWAY_URL = None

# --- 熔断机制配置 ---
# 当状态为 200 的可用密钥数量低于此值时，将完全开启熔断，大概率拒绝所有新请求
KEY_AVAILABILITY_THRESHOLD_LOW = 30
# 当状态为 200 的可用密钥数量高于此值时，将关闭熔断，接受所有新请求
KEY_AVAILABILITY_THRESHOLD_HIGH = 50
# 当可用密钥数在 LOW 和 HIGH 之间时，用于计算拒绝概率的公式
# successful_key_count 是当前可用密钥数
KEY_REJECTION_PROBABILITY_FORMULA = "(-0.05 * successful_key_count) + 2.5"

# --- 后台任务调度间隔 (单位: 秒) ---
KEY_SYNC_INTERVAL_SECONDS = 300  # 从文件同步密钥到数据库的间隔
KEY_TESTER_INTERVAL_SECONDS = 300  # 运行密钥测试器的间隔
KEY_STATUS_PRINTER_INTERVAL_SECONDS = 1800  # 将密钥状态报告写入文件的间隔
LOG_CLEANER_INTERVAL_SECONDS = 3600  # 清理旧日志的间隔

# --- 密钥健康检查配置 ---
# 密钥测试返回 200 (成功) 后，多少小时后再次测试
TEST_INTERVAL_200_STATUS_HOURS = 12
# 密钥测试返回 403 (权限问题) 后，多少天后再次测试
TEST_INTERVAL_403_STATUS_DAYS = 10
# 密钥测试返回其他 4xx (客户端错误) 后，多少天后再次测试
TEST_INTERVAL_4XX_STATUS_DAYS = 1
# 密钥测试返回 5xx (服务端错误) 后，多少分钟后再次测试
TEST_INTERVAL_5XX_STATUS_MINUTES = 10
# 密钥测试器单次运行时处理的最大密钥数量 (当前实现会测试所有需要测试的密钥)
KEY_TESTER_BATCH_LIMIT = 100
# 用于测试密钥有效性的 API 端点
KEY_TESTER_DEFAULT_TEST_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

# --- 状态文件设置 ---
STATUS_FILE_PATH = "./status.txt"  # 状态报告文件的路径
MAX_STATUS_FILE_SIZE_MB = 1  # 状态报告文件的最大体积(MB)，超过后会自动清空

# --- IP 速率限制设置 (仅对未使用 AUTH_KEY 的请求生效) ---
# 单个 IP 每分钟允许的最大请求数
RATE_LIMITER_TPM_LIMIT = 40
# 单个 IP 每小时请求数超过此值，将被永久封禁
RATE_LIMITER_BAN_LIMIT = 3600
# 临时封禁的时长 (秒)，当前未使用，因为封禁是永久的
RATE_LIMITER_BAN_DURATION_SECONDS = 3600

# --- 网络代理设置 ---
# 为所有出站请求（到 Google API）配置的代理
# 示例: "socks5://127.0.0.1:1080"
# 如果不需要代理，请设置为 None
PROXY = None
