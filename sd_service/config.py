"""
sd_service 配置 —— 仅生图相关
"""

# Forge 实例列表 (多 GPU 时添加多个)
FORGE_INSTANCES = [
    {"url": "http://127.0.0.1:7860", "device_id": 0},
    # {"url": "http://127.0.0.1:7861", "device_id": 1},
]

# 默认 checkpoint (空字符串 = 使用 Forge 当前加载的模型)
# 示例: "waiIllustriousSDXL_v170.safetensors"
CHECKPOINT_NAME = ""

# 默认生图参数
DEFAULT_PARAMS = {
    "width": 960,
    "height": 1280,
    "steps": 20,
    "cfg_scale": 7,
    "sampler_name": "DPM++ 2M Karras",
    "seed": -1,
}
