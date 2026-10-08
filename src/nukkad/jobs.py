import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from nukkad.storage import Store, identity, now


class Busy(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


@dataclass
class Result:
    payload: dict
    records: list[tuple[str, str, dict]] = field(default_factory=list)


class Jobs:
    """One worker; cancellation and publication share the same lock."""

    def __init__(self, store: Store):
        self.store = store
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nukkad")
        self.active: str | None = None
        for job in store.list("job"):
            if job["status"] in {"queued", "running"}:
                store.put(
                    "job",
                    job["id"],
                    {
                        **job,
                        "status": "interrupted",
                        "message": "Application stopped; start a new request",
                        "finished_at": now(),
                    },
                )

    def submit(self, title: str, action: Callable[[Callable[[str], None]], Result]) -> dict:
        with self.lock:
            if self.active:
                raise Busy("Another local task is running; wait or cancel it first")
            job = {
                "id": identity(),
                "title": title,
                "status": "queued",
                "message": "Waiting for local worker",
                "created_at": now(),
            }
            self.store.put("job", job["id"], job)
            self.active = job["id"]
            self.executor.submit(self._run, job["id"], action)
            return job

    def _run(self, key: str, action):
        def stage(message: str):
            with self.lock:
                job = self.store.get("job", key)
                if job["status"] == "cancelled":
                    raise Cancelled("Task cancelled")
                self.store.put("job", key, {**job, "status": "running", "message": message})

        try:
            stage("Starting")
            result = action(stage)
            with self.lock:
                job = self.store.get("job", key)
                if job["status"] != "cancelled":
                    self.store.atomic(
                        [
                            *result.records,
                            (
                                "job",
                                key,
                                {
                                    **job,
                                    "status": "complete",
                                    "message": "Ready",
                                    "result": result.payload,
                                    "finished_at": now(),
                                },
                            ),
                        ]
                    )
        except Exception as error:
            with self.lock:
                job = self.store.get("job", key)
                if job["status"] != "cancelled":
                    message = (
                        str(error)
                        if isinstance(error, (ValueError, Busy, Cancelled))
                        else f"Local task failed ({type(error).__name__}); your saved data is unchanged"
                    )
                    self.store.put(
                        "job",
                        key,
                        {**job, "status": "failed", "message": message, "finished_at": now()},
                    )
        finally:
            with self.lock:
                self.active = None

    def cancel(self, key: str) -> dict:
        with self.lock:
            job = self.store.get("job", key)
            if job is None:
                raise ValueError("Unknown task")
            if job["status"] in {"queued", "running"}:
                job = {
                    **job,
                    "status": "cancelled",
                    "message": "Cancelled; waiting for current work to stop",
                    "finished_at": now(),
                }
                self.store.put("job", key, job)
            return job

    def close(self):
        with self.lock:
            if self.active:
                self.cancel(self.active)
        self.executor.shutdown(wait=False, cancel_futures=True)
