"""
SD Mobile Web - FastAPI 后端
依赖 sd_service 提供生图能力
"""

import json
import os
import sys
import hashlib
import hmac
import secrets
import time
from typing import Literal

# 让 sd_service 可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from sd_service.config import FORGE_INSTANCES
from sd_service.task_queue import TaskManager

from config import (
    USERS,
    SESSION_SECRET,
    SESSION_MAX_AGE,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    OUTPUT_DIR,
    HOST,
    PORT,
    QUEUE_SIZE,
    MAX_USER_TASKS,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_SIDE,
)

# ---- 初始化 ----
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="SD Web", docs_url=None, redoc_url=None)

llm = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

task_mgr = TaskManager(FORGE_INSTANCES, OUTPUT_DIR, QUEUE_SIZE, MAX_USER_TASKS)


@app.on_event("startup")
async def startup():
    await task_mgr.start()


@app.on_event("shutdown")
async def shutdown():
    await task_mgr.stop()


def user_storage_id(username: str) -> str:
    return hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]


def make_session(username: str) -> str:
    expires = int(time.time()) + SESSION_MAX_AGE
    value = f"{username}.{expires}"
    signature = hmac.new(SESSION_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{signature}"


def read_session(token: str | None) -> str | None:
    if not token:
        return None
    try:
        username, expires_text, signature = token.rsplit(".", 2)
        value = f"{username}.{expires_text}"
        expected = hmac.new(SESSION_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or int(expires_text) < time.time():
            return None
        return username if username in USERS else None
    except (ValueError, TypeError):
        return None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class EnhanceRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    negative_prompt: str = Field(default="", max_length=8000)
    width: int = Field(default=960, ge=256, le=MAX_IMAGE_SIDE)
    height: int = Field(default=1280, ge=256, le=MAX_IMAGE_SIDE)
    steps: int = Field(default=20, ge=1, le=60)
    cfg_scale: float = Field(default=7, ge=1, le=20)
    sampler_name: Literal[
        "DPM++ 2M Karras", "Euler a", "Euler", "DPM++ 2M SDE Karras",
        "DPM++ 2M", "DDIM",
    ] = "DPM++ 2M Karras"
    seed: int = Field(default=-1, ge=-1, le=2**32 - 1)

    class Config:
        extra = "forbid"


class CancelRequest(BaseModel):
    task_id: str | None = Field(default=None, max_length=36)


@app.post("/api/login")
async def login(req: LoginRequest, response: Response):
    password = USERS.get(req.username)
    if password is None or not secrets.compare_digest(password, req.password):
        raise HTTPException(401, "用户名或密码错误")
    response.set_cookie(
        "sd_session", make_session(req.username), max_age=SESSION_MAX_AGE,
        httponly=True, samesite="strict", secure=False, path="/",
    )
    return {"ok": True, "username": req.username}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie("sd_session", path="/")
    return {"ok": True}


@app.get("/api/me")
async def me(request: Request):
    return {"username": request.state.username}


# ---- LLM 增强 ----
ENHANCE_SYSTEM = """你是一个 Stable Diffusion 提示词翻译专家。
用户会用自然语言描述想要的画面, 你需要:
1. 翻译成 SDXL 标准的英文标签, 用逗号分隔, 按重要性排序
2. 自动补充品质词: masterpiece, best quality, amazing quality
3. 生成对应的负面提示词

输出必须是纯粹的 JSON:
{"prompt": "...", "negative_prompt": "..."}

规则:
- prompt 用 danbooru 风格标签, 逗号分隔, 不加换行
- 主体在前, 然后是场景/动作, 然后是风格, 最后是品质词
- negative_prompt 包含常见低质量标签: worst quality, low quality, bad anatomy, extra fingers, missing fingers, blurry, watermark, text, signature
- 根据用户描述的场景, 补充相关负面词
- 不要输出任何 JSON 以外的内容"""


# ---- API 路由 ----

@app.post("/api/enhance-prompt")
async def enhance_prompt(req: EnhanceRequest):
    """自然语言 -> SD 提示词 (LLM, 可选调用)"""
    text = req.text.strip()
    if not text:
        raise HTTPException(422, "描述不能为空")

    try:
        resp = await llm.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": ENHANCE_SYSTEM},
                {"role": "user", "content": text},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content.strip()
        result = json.loads(content)
        return {
            "prompt": result.get("prompt", ""),
            "negative_prompt": result.get("negative_prompt", ""),
        }
    except json.JSONDecodeError:
        raise HTTPException(500, "LLM 返回格式异常, 请重试")
    except Exception as e:
        raise HTTPException(500, f"增强失败: {str(e)}")


@app.post("/api/generate")
async def generate(req: GenerateRequest, request: Request):
    """提交生成任务"""
    try:
        if not req.prompt.strip():
            raise HTTPException(422, "提示词不能为空")
        if req.width % 8 or req.height % 8:
            raise HTTPException(422, "宽高必须是 8 的倍数")
        if req.width * req.height > MAX_IMAGE_PIXELS:
            raise HTTPException(422, f"总像素不能超过 {MAX_IMAGE_PIXELS:,}")
        owner_id = user_storage_id(request.state.username)
        params = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        task_id = await task_mgr.submit(params, owner_id)
        return {
            "task_id": task_id,
            "queue_position": task_mgr.queue_status(owner_id)["queue_length"],
        }
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.get("/api/task/{task_id}")
async def get_task(task_id: str, request: Request):
    """查询任务状态"""
    task = task_mgr.get_task(task_id, user_storage_id(request.state.username))
    if not task:
        raise HTTPException(404, "任务不存在")

    result = {
        "task_id": task.id,
        "status": task.status,
        "progress": task.progress,
        "error": task.error,
    }
    if task.status == "done":
        result["image_url"] = f"/outputs/{task.image_path}"
        result["params"] = task.result_params
    return result


@app.get("/api/task/{task_id}/wait")
async def wait_task(task_id: str, request: Request):
    """长轮询等待任务完成"""
    import asyncio

    task = task_mgr.get_task(task_id, user_storage_id(request.state.username))
    if not task:
        raise HTTPException(404, "任务不存在")

    try:
        await asyncio.wait_for(task.done_event.wait(), timeout=610)
    except asyncio.TimeoutError:
        raise HTTPException(504, "生成超时")

    if task.status == "failed":
        raise HTTPException(500, task.error or "未知错误")
    if task.status == "cancelled":
        raise HTTPException(499, "任务已取消")

    return {
        "task_id": task.id,
        "status": task.status,
        "image_url": f"/outputs/{task.image_path}",
        "params": task.result_params,
    }


@app.post("/api/cancel")
async def cancel(req: CancelRequest, request: Request):
    """取消生成, 可选指定 task_id"""
    count = await task_mgr.cancel(user_storage_id(request.state.username), req.task_id)
    return {"ok": count > 0, "cancelled": count}


@app.get("/api/queue-status")
async def queue_status(request: Request):
    """队列状态"""
    return task_mgr.queue_status(user_storage_id(request.state.username))


@app.get("/api/history")
async def history(request: Request, limit: int = 20):
    """最近 N 张生成记录"""
    limit = max(1, min(limit, 50))
    owner_id = user_storage_id(request.state.username)
    user_dir = os.path.join(OUTPUT_DIR, owner_id)
    os.makedirs(user_dir, exist_ok=True)
    files = sorted(
        [f for f in os.listdir(user_dir) if f.endswith(".png")],
        key=lambda x: os.path.getmtime(os.path.join(user_dir, x)),
        reverse=True,
    )[:limit]

    items = []
    for fn in files:
        json_fn = fn.replace(".png", ".json")
        json_path = os.path.join(user_dir, json_fn)
        params = {}
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                params = json.load(f)
        items.append({
            "image_url": f"/outputs/{owner_id}/{fn}",
            "thumbnail_url": f"/outputs/{owner_id}/{fn}",
            "params": params,
        })
    return items


# ---- 鉴权中间件 ----
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    protected = request.url.path.startswith("/api/") or request.url.path.startswith("/outputs/")
    public_api = request.url.path == "/api/login"
    if protected and not public_api and request.method != "OPTIONS":
        username = read_session(request.cookies.get("sd_session"))
        if not username:
            return JSONResponse({"detail": "未授权"}, status_code=401)
        request.state.username = username
        if request.url.path.startswith("/outputs/"):
            requested_owner = request.url.path.split("/", 3)[2]
            if requested_owner != user_storage_id(username):
                return JSONResponse({"detail": "无权访问该图片"}, status_code=403)
    return await call_next(request)


# ---- 静态文件 ----
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


# ---- 入口 ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
