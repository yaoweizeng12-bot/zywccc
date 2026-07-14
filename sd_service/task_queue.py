"""
任务队列 + Worker 调度 —— 通用, 不关心上层调用方是谁
支持多实例并发, 每个 worker 独立追踪自己的任务
"""

import asyncio
import time
import uuid

import aiohttp

from .forge_client import build_payload, call_forge, save_image, save_meta


class GenerationTask:
    def __init__(self, params: dict):
        self.id = str(uuid.uuid4())[:8]
        self.params = params
        self.status = "queued"     # queued | running | done | failed | cancelled
        self.progress = 0.0
        self.image_path: str | None = None
        self.result_params: dict | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self.done_event = asyncio.Event()


class TaskManager:
    """管理生图队列和 worker 池, 多实例安全"""

    def __init__(self, forge_instances: list[dict], output_dir: str,
                 queue_size: int = 20):
        self.forge_instances = forge_instances
        self.output_dir = output_dir
        self.queue: asyncio.Queue[GenerationTask] = asyncio.Queue(queue_size)
        self.active_tasks: dict[str, GenerationTask] = {}

        # 每个实例独立追踪当前任务 (forge_url -> task)
        self.running_tasks: dict[str, GenerationTask] = {}
        # 被请求取消的 task_id 集合
        self._cancelled_ids: set[str] = set()

        self._workers: list[asyncio.Task] = []

    async def start(self):
        """启动所有 worker"""
        for inst in self.forge_instances:
            w = asyncio.create_task(self._worker(inst))
            self._workers.append(w)
            print(f"[TaskManager] Worker 启动, Forge: {inst['url']} "
                  f"(GPU {inst['device_id']})")

    async def submit(self, params: dict) -> str:
        """提交任务, 返回 task_id"""
        if self.queue.qsize() >= self.queue.maxsize:
            raise RuntimeError(f"队列已满 (最多 {self.queue.maxsize})")
        task = GenerationTask(params)
        await self.queue.put(task)
        self.active_tasks[task.id] = task
        return task.id

    def get_task(self, task_id: str) -> GenerationTask | None:
        return self.active_tasks.get(task_id)

    async def cancel(self, task_id: str | None = None):
        """取消任务。指定 task_id 只取消该任务; 不指定则取消所有正在运行的任务"""
        if task_id:
            # 找到运行该任务的实例, 只中断那个
            target_url = None
            for url, task in self.running_tasks.items():
                if task.id == task_id:
                    self._cancelled_ids.add(task_id)
                    target_url = url
                    break
            if target_url:
                async with aiohttp.ClientSession() as s:
                    try:
                        await s.post(
                            f"{target_url}/sdapi/v1/interrupt", timeout=5,
                        )
                    except Exception:
                        pass
        else:
            # 取消全部运行中的任务
            for url, task in list(self.running_tasks.items()):
                self._cancelled_ids.add(task.id)
            async with aiohttp.ClientSession() as s:
                for inst in self.forge_instances:
                    try:
                        await s.post(
                            f"{inst['url'].rstrip('/')}/sdapi/v1/interrupt",
                            timeout=5,
                        )
                    except Exception:
                        pass

    @property
    def queue_status(self) -> dict:
        running = [
            {"task_id": t.id, "instance": url}
            for url, t in self.running_tasks.items()
        ]
        return {
            "queue_length": self.queue.qsize(),
            "running": running,
        }

    async def _worker(self, instance: dict):
        """单个 worker, 绑定一个 Forge 实例, 循环消费队列"""
        forge_url = instance["url"].rstrip("/")

        async with aiohttp.ClientSession() as session:
            while True:
                task = await self.queue.get()
                self.running_tasks[forge_url] = task
                task.status = "running"

                try:
                    payload = build_payload(task.params)
                    data = await call_forge(forge_url, payload, session)

                    if task.id in self._cancelled_ids:
                        task.status = "cancelled"
                    else:
                        filename, filepath = save_image(
                            data["images"][0], self.output_dir, task.id,
                        )
                        meta = save_meta(filepath, payload, data)

                        task.image_path = filename
                        task.result_params = meta
                        task.status = "done"
                        task.progress = 1.0

                except asyncio.CancelledError:
                    task.status = "cancelled"
                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)
                finally:
                    task.done_event.set()
                    self.running_tasks.pop(forge_url, None)
                    self._cancelled_ids.discard(task.id)
                    self.queue.task_done()
