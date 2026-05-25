from collections.abc import Callable
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import asyncio

from os import getenv


class ThreadedDateFileHandler(logging.Handler):
    """
    Writes logs into:

    logs/YYYY/MM/DD/HH/<thread_id>.log

    Example:
    logs/2026/05/14/11/abc123.log

    Directories are created lazily only when logs are written.
    """

    def __init__(
        self,
        base_dir=getenv("LOGS_DIR"),
        max_bytes=10_000_000,  # 10 MB
        backup_count=5,
        encoding="utf-8",
    ):
        super().__init__()

        self.base_dir = Path(base_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.encoding = encoding

        # cache: filepath -> handler
        self.handlers_cache = {}

    def _build_path(self, thread_id: str) -> Path:
        now = datetime.now()

        return (
            self.base_dir
            / now.strftime("%Y")
            / now.strftime("%m")
            / now.strftime("%d")
            / now.strftime("%H")
            / f"{thread_id}.log"
        )

    def _get_handler(self, thread_id: str):
        path = self._build_path(thread_id)

        cache_key = str(path)

        if cache_key not in self.handlers_cache:
            # created only when first log arrives
            path.parent.mkdir(parents=True, exist_ok=True)

            handler = RotatingFileHandler(
                filename=path,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding=self.encoding,
            )

            if self.formatter:
                handler.setFormatter(self.formatter)

            self.handlers_cache[cache_key] = handler

        return self.handlers_cache[cache_key]

    def emit(self, record):
        try:
            thread_id = getattr(record, "thread_id", "default")

            handler = self._get_handler(thread_id)

            handler.emit(record)

        except Exception:
            self.handleError(record)

    def close(self):
        for handler in self.handlers_cache.values():
            handler.close()

        self.handlers_cache.clear()

        super().close()


logger = logging.getLogger("langgraph")
logger.setLevel(logging.INFO)

handler = ThreadedDateFileHandler(
    max_bytes=10_000_000,
    backup_count=5,
)

handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s - %(message)s"))

logger.addHandler(handler)


def add_logger(node: Callable) -> Callable:
    @wraps(node)
    async def wrapper(*args, **kwargs):
        await asyncio.to_thread(
            logger.info,
            "Entering node %s",
            node.__name__,
            extra={"thread_id": kwargs.get("config")["metadata"]["thread_id"]},
        )

        await asyncio.to_thread(
            logger.info,
            "Node state: %s",
            {
                k: v
                for (k, v) in args[0].items()
                if k not in ["messages", "project_structure"]
            },
            extra={"thread_id": kwargs.get("config")["metadata"]["thread_id"]},
        )

        result = await node(*args, **kwargs)

        await asyncio.to_thread(
            logger.info,
            "Node result: %s",
            result,
            extra={"thread_id": kwargs.get("config")["metadata"]["thread_id"]},
        )

        return result

    return wrapper


def add_tool_logger(node: Callable) -> Callable:
    @wraps(node)
    async def wrapper(self, *args, **kwargs):
        await asyncio.to_thread(
            logger.info,
            "Entering node %s",
            node.__name__,
            extra={"thread_id": args[1]["metadata"]["thread_id"]},
        )

        await asyncio.to_thread(
            logger.info,
            "Node state: %s",
            {
                k: v
                for (k, v) in args[0].items()
                if k not in ["messages", "project_structure"]
            },
            extra={"thread_id": args[1]["metadata"]["thread_id"]},
        )

        result = await node(self, *args, **kwargs)

        await asyncio.to_thread(
            logger.info,
            "Node result: %s",
            result,
            extra={"thread_id": args[1]["metadata"]["thread_id"]},
        )

        return result

    return wrapper
