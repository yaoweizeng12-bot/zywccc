"""
SD Mobile Web - FastAPI 后端
依赖 sd_service 提供生图能力
"""

import json
import os
import sys

# 让 sd_service 可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI

from sd_service.config import FORGE_INSTANCES
from sd_service.task_queue import TaskManager

from config import (
    AUTH_TOKEN,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    OUTPUT_DIR,
    HOST,
    PORT,
    QUEUE_SIZE,
)

# ---- 初始化 ----
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="SD Web", docs_url=None, redoc_url=None)

llm = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

task_mgr = TaskManager(FORGE_INSTANCES, OUTPUT_DIR, QUEUE_SIZE)


@app.on_event("startup")
async def startup():
    await task_mgr.start()


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
async def enhance_prompt(req: dict, _=None):
    """自然语言 -> SD 提示词 (LLM, 可选调用)"""
    text = req.get("text", "").strip()
    if not text:
        raise HTTPException(400, "text 不能为空")

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
async def generate(req: dict, _=None):
    """提交生成任务"""
    try:
        task_id = await task_mgr.submit(req)
        return {
            "task_id": task_id,
            "queue_position": task_mgr.queue_status["queue_length"],
        }
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.get("/api/task/{task_id}")
async def get_task(task_id: str, _=None):
    """查询任务状态"""
    task = task_mgr.get_task(task_id)
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
async def wait_task(task_id: str, _=None):
    """长轮询等待任务完成"""
    import asyncio

    task = task_mgr.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    try:
        await asyncio.wait_for(task.done_event.wait(), timeout=300)
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
async def cancel(req: dict = {}, _=None):
    """取消生成, 可选指定 task_id"""
    await task_mgr.cancel(req.get("task_id"))
    return {"ok": True}


@app.get("/api/queue-status")
async def queue_status(_=None):
    """队列状态"""
    return task_mgr.queue_status


@app.get("/api/history")
async def history(limit: int = 20, _=None):
    """最近 N 张生成记录"""
    files = sorted(
        [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".png")],
        key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)),
        reverse=True,
    )[:limit]

    items = []
    for fn in files:
        json_fn = fn.replace(".png", ".json")
        json_path = os.path.join(OUTPUT_DIR, json_fn)
        params = {}
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                params = json.load(f)
        items.append({
            "image_url": f"/outputs/{fn}",
            "thumbnail_url": f"/outputs/{fn}",
            "params": params,
        })
    return items


# ---- 鉴权中间件 ----
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method != "OPTIONS":
        auth_header = request.headers.get("Authorization", "")
        if auth_header.removeprefix("Bearer ") != AUTH_TOKEN:
            return JSONResponse({"detail": "未授权"}, status_code=401)
    return await call_next(request)


# ---- 静态文件 ----
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


# ---- 入口 ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
