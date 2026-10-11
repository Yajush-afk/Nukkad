import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from nukkad.ollama import ModelFailure
from nukkad.storage import Store, identity, now


class Busy(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


@dataclass
class Result:
    payload: dict
    records: list[tuple[str, str, dict]] = field(default_factory=list)
    expected: list[tuple[str, str, dict]] = field(default_factory=list)


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

    def submit(
        self,
        title: str,
        action: Callable[[Callable[[str], None]], Result],
        *,
        context=None,
        coalesce_key=None,
        force=False,
    ) -> dict:
        with self.lock:
            if coalesce_key:
                matching = [
                    job for job in self.store.list("job") if job.get("coalesce_key") == coalesce_key
                ]
                previous = max(matching, key=lambda job: job["created_at"], default=None)
                if previous and (not force or previous["status"] in {"queued", "running"}):
                    return previous
            if self.active:
                raise Busy("Another local task is running; wait or cancel it first")
            job = {
                "id": identity(),
                "title": title,
                "status": "queued",
                "message": "Waiting for local worker",
                "created_at": now(),
                **(context or {}),
                **({"coalesce_key": coalesce_key} if coalesce_key else {}),
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
                        ],
                        expected=result.expected,
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
                    failure = (
                        {"failure_category": error.category, "diagnostics": error.diagnostics}
                        if isinstance(error, ModelFailure)
                        else {}
                    )
                    if isinstance(error, ModelFailure):
                        message = f"Local AI could not finish ({error.category}); existing saved work is unchanged. Review the model or use the manual option."
                    self.store.put(
                        "job",
                        key,
                        {
                            **job,
                            "status": "failed",
                            "message": message,
                            "finished_at": now(),
                            **failure,
                        },
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
        self.executor.shutdown(wait=True, cancel_futures=True)


def visit_job_context(experience, place_id):
    return {
        "task": "visit_memory",
        "experience_id": experience["id"],
        "place_id": place_id,
        "source_revision": experience["revision"],
    }


def visit_generation(store, experience):
    jobs = [
        job
        for job in store.list("job")
        if job.get("task") == "visit_memory" and job.get("experience_id") == experience["id"]
    ]
    job = max(jobs, key=lambda job: job["created_at"], default=None)
    if not job:
        return None
    return {
        key: value
        for key, value in {
            "id": job["id"],
            "status": job["status"]
            if job.get("source_revision") == experience["revision"]
            else "stale",
            "message": job["message"],
            "source_revision": job.get("source_revision"),
            "failure_category": job.get("failure_category"),
            "result": job.get("result"),
        }.items()
        if value is not None
    }
