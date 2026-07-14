"""
Forge API 封装 —— 纯函数, 不依赖任何 Web 框架
"""

import base64
import json
import os
from datetime import datetime

import aiohttp

from .config import CHECKPOINT_NAME, DEFAULT_PARAMS


def build_payload(params: dict) -> dict:
    """合并用户参数和默认值, 返回 Forge API 请求体"""
    p = {**DEFAULT_PARAMS, **params}
    payload = {
        "prompt": p["prompt"],
        "negative_prompt": p.get("negative_prompt", ""),
        "width": p.get("width", 960),
        "height": p.get("height", 1280),
        "steps": p.get("steps", 20),
        "cfg_scale": p.get("cfg_scale", 7),
        "sampler_name": p.get("sampler_name", "DPM++ 2M Karras"),
        "seed": p.get("seed", -1),
        "batch_size": 1,
    }

    # 显式指定 checkpoint, 不依赖 Forge UI 当前加载的模型
    checkpoint = p.get("checkpoint", CHECKPOINT_NAME)
    if checkpoint:
        payload["override_settings"] = {"sd_model_checkpoint": checkpoint}

    return payload


async def call_forge(forge_url: str, payload: dict,
                     session: aiohttp.ClientSession | None = None) -> dict:
    """调用 Forge txt2img API, 返回原始 JSON 响应"""
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()

    try:
        async with session.post(
            f"{forge_url.rstrip('/')}/sdapi/v1/txt2img",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=600),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Forge {forge_url} 返回 {resp.status}: {text}")
            return await resp.json()
    finally:
        if own_session:
            await session.close()


def save_image(image_b64: str, output_dir: str, task_id: str = "") -> tuple[str, str]:
    """解码 base64 并保存为 PNG, 返回 (filename, filepath)"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{task_id}.png" if task_id else f"{timestamp}.png"
    filepath = os.path.join(output_dir, filename)

    img_bytes = base64.b64decode(image_b64)
    with open(filepath, "wb") as f:
        f.write(img_bytes)

    return filename, filepath


def save_meta(filepath: str, payload: dict, forge_response: dict) -> dict:
    """保存生成参数到同名 .json 文件, 返回 meta 字典"""
    info = forge_response.get("info", {})
    if isinstance(info, str):
        try:
            info = json.loads(info)
        except (json.JSONDecodeError, TypeError):
            info = {}

    meta = {
        "prompt": payload["prompt"],
        "negative_prompt": payload["negative_prompt"],
        "width": payload["width"],
        "height": payload["height"],
        "steps": payload["steps"],
        "cfg_scale": payload["cfg_scale"],
        "sampler_name": payload["sampler_name"],
        "seed": info.get("seed", -1),
        "checkpoint": payload.get("override_settings", {}).get("sd_model_checkpoint", ""),
    }

    json_path = filepath.replace(".png", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return meta
