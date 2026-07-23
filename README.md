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

编辑 `sd-web/config.py`，设置账号和 LLM 参数。
生图参数编辑 `sd_service/config.py`。

推荐通过环境变量配置朋友账号，不要继续使用默认密码：

```powershell
$env:SD_WEB_USERS="owner:换成强密码,friend:朋友的独立密码"
$env:SD_WEB_SESSION_SECRET="换成一段足够长的随机字符串"
```

账号之间的任务、取消操作和历史图片互相隔离。默认每人最多同时保留 3 个任务，图片上限为
1,572,864 像素（1024×1536），可分别用 `SD_WEB_MAX_USER_TASKS` 和
`SD_WEB_MAX_PIXELS` 调整。
