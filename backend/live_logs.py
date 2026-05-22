"""
服务器管家 - 运行日志缓冲（强一致显示）

使用后端内存缓存 + 前端轮询拉取，避免 evaluate_js 推送在部分环境下丢失/失效。
每次脚本运行生成一个 run_id，并按 seq 递增记录日志行。
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Dict, List, Tuple, Optional


class _RunLog:
    __slots__ = ("created_at", "updated_at", "seq", "lines", "done", "success", "message", "meta")

    def __init__(self, meta=None):
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.seq = 0
        self.lines: List[Tuple[int, str]] = []
        self.done: bool = False
        self.success: Optional[bool] = None
        self.message: str = ""
        self.meta: dict = meta or {}


_lock = threading.RLock()
_runs: Dict[str, _RunLog] = {}

# 只保留最近 N 条日志行（每个 run）
MAX_LINES_PER_RUN = 5000
# 只保留最近 N 个运行（避免内存增长）
MAX_RUNS = 50


def create_run(meta=None) -> str:
    """创建一个新的运行日志流，返回 run_id。"""
    run_id = uuid.uuid4().hex
    with _lock:
        _runs[run_id] = _RunLog(meta=meta)
        _gc_if_needed()
    return run_id


def append(run_id: str, text: str) -> None:
    """追加一行日志。text 可包含 \\n，但前端按行拼接即可。"""
    if not run_id:
        return
    line = str(text)
    if not line.endswith("\n"):
        line += "\n"
    with _lock:
        run = _runs.get(run_id)
        if not run:
            return
        run.seq += 1
        run.updated_at = time.time()
        run.lines.append((run.seq, line))
        if len(run.lines) > MAX_LINES_PER_RUN:
            run.lines = run.lines[-MAX_LINES_PER_RUN:]


def finish(run_id: str, success: bool, message: str = "") -> None:
    with _lock:
        run = _runs.get(run_id)
        if not run:
            return
        run.done = True
        run.success = bool(success)
        run.message = str(message or "")
        run.updated_at = time.time()


def fetch(run_id: str, since_seq: int = 0, limit: int = 200) -> dict:
    """拉取 since_seq 之后的日志。返回: {lines, next_seq, done, success, message}"""
    try:
        since_seq = int(since_seq or 0)
    except Exception:
        since_seq = 0
    try:
        limit = int(limit or 200)
    except Exception:
        limit = 200
    limit = max(1, min(2000, limit))

    with _lock:
        run = _runs.get(run_id)
        if not run:
            return {"success": False, "message": "run_id 不存在或已过期"}

        out: List[str] = []
        next_seq = since_seq
        for seq, line in run.lines:
            if seq <= since_seq:
                continue
            out.append(line)
            next_seq = seq
            if len(out) >= limit:
                break

        return {
            "success": True,
            "data": {
                "lines": out,
                "next_seq": next_seq,
                "done": run.done,
                "success_flag": run.success,
                "message": run.message,
                "meta": run.meta,
            },
        }


def list_runs(limit: int = 20) -> dict:
    """列出最近运行任务，供前端自动发现托盘启动的任务。"""
    try:
        limit = int(limit or 20)
    except Exception:
        limit = 20
    limit = max(1, min(100, limit))
    with _lock:
        items = sorted(_runs.items(), key=lambda kv: kv[1].created_at, reverse=True)[:limit]
        return {
            "success": True,
            "data": [
                {
                    "run_id": rid,
                    "created_at": run.created_at,
                    "updated_at": run.updated_at,
                    "done": run.done,
                    "success_flag": run.success,
                    "message": run.message,
                    "seq": run.seq,
                    "meta": run.meta,
                }
                for rid, run in items
            ],
        }


def _gc_if_needed():
    # 超过 MAX_RUNS 时按创建时间清理最旧的
    if len(_runs) <= MAX_RUNS:
        return
    items = sorted(_runs.items(), key=lambda kv: kv[1].created_at)
    overflow = len(_runs) - MAX_RUNS
    for i in range(overflow):
        _runs.pop(items[i][0], None)

