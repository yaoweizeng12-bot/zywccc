# SD Tools

手机端 Stable Diffusion 生图工具集。

## 结构

```
sd_service/      通用生图核心库 (可复制到其他项目)
sd-web/          移动网页 (FastAPI + 手机端 UI)
```

## 快速开始

1. 启动 SD Forge (绘世启动器)
2. 双击桌面 `SD_Web.bat`
3. 手机浏览器访问 `http://电脑IP:8000`

## 依赖

- SD Forge (aki v1.0)
- Python 3.11+ (fastapi, uvicorn, aiohttp, openai)
- DeepSeek API key (或其他 OpenAI 兼容 LLM)

## 配置

编辑 `sd-web/config.py`，设置 `AUTH_TOKEN` 和 LLM 参数。
生图参数编辑 `sd_service/config.py`。
