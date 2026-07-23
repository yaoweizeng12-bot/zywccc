"""
任务队列 + Worker 调度 —— 通用, 不关心上层调用方是谁
支持多实例并发, 每个 worker 独立追踪自己的任务
"""

import asyncio
import time
import uuid
import os

import aiohttp

from .forge_client import build_payload, call_forge, save_image, save_meta


class GenerationTask:
    def __init__(self, params: dict, owner_id: str):
        self.id = str(uuid.uuid4())[:8]
        self.params = params
        self.owner_id = owner_id
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
                 queue_size: int = 20, max_user_tasks: int = 3):
        self.forge_instances = forge_instances
        self.output_dir = output_dir
        self.queue: asyncio.Queue[GenerationTask] = asyncio.Queue(queue_size)
        self.active_tasks: dict[str, GenerationTask] = {}
        self.max_user_tasks = max_user_tasks

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

    async def stop(self):
        """停止 worker，供 Web 服务优雅关闭。"""
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def submit(self, params: dict, owner_id: str) -> str:
        """提交任务, 返回 task_id"""
        if self.queue.qsize() >= self.queue.maxsize:
            raise RuntimeError(f"队列已满 (最多 {self.queue.maxsize})")
        self._prune_tasks()
        outstanding = sum(
            t.owner_id == owner_id and t.status in {"queued", "running"}
            for t in self.active_tasks.values()
        )
        if outstanding >= self.max_user_tasks:
            raise RuntimeError(f"每位用户最多同时保留 {self.max_user_tasks} 个任务")
        task = GenerationTask(params, owner_id)
        await self.queue.put(task)
        self.active_tasks[task.id] = task
        return task.id

    def get_task(self, task_id: str, owner_id: str) -> GenerationTask | None:
        task = self.active_tasks.get(task_id)
        return task if task and task.owner_id == owner_id else None

    async def cancel(self, owner_id: str, task_id: str | None = None) -> int:
        """取消该用户的指定任务，未指定时取消该用户的全部未完成任务。"""
        targets = [
            task for task in self.active_tasks.values()
            if task.owner_id == owner_id
            and task.status in {"queued", "running"}
            and (task_id is None or task.id == task_id)
        ]
        for task in targets:
            self._cancelled_ids.add(task.id)
            if task.status == "queued":
                task.status = "cancelled"
                task.done_event.set()

        if task_id:
            # 找到运行该任务的实例, 只中断那个
            target_url = None
            for url, task in self.running_tasks.items():
                if task.id == task_id and task.owner_id == owner_id:
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
            # 只中断该用户正在运行任务所在的实例
            async with aiohttp.ClientSession() as s:
                urls = [url for url, task in self.running_tasks.items() if task.owner_id == owner_id]
                for url in urls:
                    try:
                        await s.post(
                            f"{url.rstrip('/')}/sdapi/v1/interrupt",
                            timeout=5,
                        )
                    except Exception:
                        pass
        return len(targets)

    def queue_status(self, owner_id: str) -> dict:
        running = [
            {"task_id": t.id, "instance": url}
            for url, t in self.running_tasks.items() if t.owner_id == owner_id
        ]
        return {
            "queue_length": sum(
                t.owner_id == owner_id and t.status == "queued"
                for t in self.active_tasks.values()
            ),
            "running": running,
        }

    async def _worker(self, instance: dict):
        """单个 worker, 绑定一个 Forge 实例, 循环消费队列"""
        forge_url = instance["url"].rstrip("/")

        async with aiohttp.ClientSession() as session:
            while True:
                task = await self.queue.get()
                if task.status == "cancelled" or task.id in self._cancelled_ids:
                    task.status = "cancelled"
                    task.done_event.set()
                    self._cancelled_ids.discard(task.id)
                    self.queue.task_done()
                    continue
                self.running_tasks[forge_url] = task
                task.status = "running"

                try:
                    payload = build_payload(task.params)
                    data = await call_forge(forge_url, payload, session)

                    if task.id in self._cancelled_ids:
                        task.status = "cancelled"
                    else:
                        user_output_dir = os.path.join(self.output_dir, task.owner_id)
                        os.makedirs(user_output_dir, exist_ok=True)
                        filename, filepath = save_image(
                            data["images"][0], user_output_dir, task.id,
                        )
                        meta = save_meta(filepath, payload, data)

                        task.image_path = f"{task.owner_id}/{filename}"
                        task.result_params = meta
                        task.status = "done"
                        task.progress = 1.0

                except asyncio.CancelledError:
                    task.status = "cancelled"
                    raise
                except Exception as e:
                    task.status = "failed"
                    task.error = str(e)
                finally:
                    task.done_event.set()
                    self.running_tasks.pop(forge_url, None)
                    self._cancelled_ids.discard(task.id)
                    self.queue.task_done()

    def _prune_tasks(self):
        """完成任务保留 24 小时，避免内存无限增长。"""
        cutoff = time.time() - 86400
        expired = [
            task_id for task_id, task in self.active_tasks.items()
            if task.status in {"done", "failed", "cancelled"}
            and task.created_at < cutoff
        ]
        for task_id in expired:
            self.active_tasks.pop(task_id, None)
