"""
SD Mobile Web 配置 —— 仅 Web 相关
生图相关配置在 sd_service/config.py
"""

import os

# ---- 鉴权 ----
AUTH_TOKEN = os.getenv("SD_WEB_TOKEN", "sd-web-token-change-me")

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
