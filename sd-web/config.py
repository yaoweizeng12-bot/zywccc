"""
SD Mobile Web 配置 —— 仅 Web 相关
生图相关配置在 sd_service/config.py
"""

import os
import secrets

# ---- 鉴权 ----
# 格式: "用户名:密码,用户名2:密码2"。用户名只允许字母、数字、_ 和 -。
# 兼容旧配置：未设置 SD_WEB_USERS 时，owner 密码沿用 SD_WEB_TOKEN。
_legacy_password = os.getenv("SD_WEB_TOKEN", "sd-web-token-change-me")
_users_raw = os.getenv("SD_WEB_USERS", f"owner:{_legacy_password}")
USERS = dict(item.split(":", 1) for item in _users_raw.split(",") if ":" in item)
SESSION_SECRET = os.getenv("SD_WEB_SESSION_SECRET", secrets.token_hex(32))
SESSION_MAX_AGE = int(os.getenv("SD_WEB_SESSION_MAX_AGE", "604800"))

# ---- LLM (OpenAI 兼容接口) ----
LLM_API_KEY = os.getenv("SD_WEB_LLM_KEY", "sk-your-key-here")
LLM_BASE_URL = os.getenv("SD_WEB_LLM_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("SD_WEB_LLM_MODEL", "deepseek-chat")

# ---- 输出 ----
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# ---- 服务 ----
HOST = "0.0.0.0"
PORT = 8000

# ---- 队列 ----
QUEUE_SIZE = 20
MAX_USER_TASKS = int(os.getenv("SD_WEB_MAX_USER_TASKS", "3"))

# 16GB/24GB GPU 混合队列按较小显卡设置。默认约等于 1024x1536。
MAX_IMAGE_PIXELS = int(os.getenv("SD_WEB_MAX_PIXELS", "1572864"))
MAX_IMAGE_SIDE = int(os.getenv("SD_WEB_MAX_SIDE", "1536"))
