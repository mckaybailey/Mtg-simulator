"""Running games in parallel on a pool of long-lived Forge JVMs.

Starting Forge costs several seconds, so each worker process is started once and fed jobs over
stdin (see ``bridge/ForgeBridge.java`` for the protocol). Forge keeps global state, including
its random number generator, so one JVM plays one game at a time and parallelism comes from
running several JVMs.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from . import forge as forge_mod
from .forge import ForgeError, ForgeInstall

STARTUP_TIMEOUT = 300  # seconds to wait for a JVM to load the card database
RESULT_GRACE = 60  # seconds beyond the in-game timeout before a silent worker is declared hung
MAX_START_FAILURES = 3


@dataclass
class Job:
    """One game. ``meta`` is carried through to the result untouched."""

    id: str
    seed: int
    decks: List[str]  # .dck paths in seat order
    timeout: int = 180
    game_format: str = "Constructed"
    monte_carlo: str = "off"
    log_path: str = ""
    profiles: List[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def line(self) -> str:
        parts = [
            f"id={self.id}", f"seed={self.seed}", f"timeout={self.timeout}",
            f"format={self.game_format}", f"mc={self.monte_carlo}", f"log={self.log_path}",
        ]
        parts += [f"deck={d}" for d in self.decks]
        parts += [f"profile={p}" for p in self.profiles]
        for part in parts:
            if "\t" in part or "\n" in part:
                raise ValueError(f"job field may not contain tabs or newlines: {part!r}")
        return "\t".join(parts)


class _Worker:
    """One Forge JVM plus a thread that turns its stdout into a queue of parsed messages."""

    _EOF = object()

    def __init__(self, cmd: List[str], cwd: Path, env: dict, stderr_path: Path):
        self._cmd, self._cwd, self._env, self._stderr_path = cmd, cwd, env, stderr_path
        self.proc: Optional[subprocess.Popen] = None
        self.info: dict = {}
        self._messages: "queue.Queue" = queue.Queue()
        self._stderr = None

    def start(self) -> None:
        self._stderr_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr = open(self._stderr_path, "ab")
        self.proc = subprocess.Popen(
            self._cmd, cwd=self._cwd, env=self._env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        threading.Thread(target=self._pump, args=(self.proc, self._messages), daemon=True).start()
        message = self._next(STARTUP_TIMEOUT)
        if not isinstance(message, dict) or message.get("type") != "ready":
            detail = message.get("error", "") if isinstance(message, dict) else ""
            self.stop()
            raise ForgeError(
                "A Forge worker failed to start" + (f": {detail.strip()[:600]}" if detail else "")
                + f" (see {self._stderr_path})."
            )
        self.info = message

    @classmethod
    def _pump(cls, proc: subprocess.Popen, out: "queue.Queue") -> None:
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    out.put(json.loads(line))
                except ValueError:
                    continue
        finally:
            out.put(cls._EOF)

    def _next(self, timeout: float):
        try:
            return self._messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def run(self, job: Job) -> dict:
        """Play one game. A worker that dies or goes silent yields a synthetic ``crash``/``hang`` result."""
        assert self.proc is not None and self.proc.stdin is not None
        try:
            self.proc.stdin.write(job.line() + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            return {"type": "result", "id": job.id, "status": "crash", "winner": -1,
                    "error": "worker process was not accepting jobs"}
        message = self._next(job.timeout + RESULT_GRACE)
        if message is None:
            self.stop(kill=True)
            return {"type": "result", "id": job.id, "status": "hang", "winner": -1,
                    "error": "no result within the time limit; worker was killed"}
        if message is self._EOF:
            code = self.proc.poll()
            return {"type": "result", "id": job.id, "status": "crash", "winner": -1,
                    "error": f"worker process exited (code {code}); see {self._stderr_path}"}
        return message

    def stop(self, kill: bool = False) -> None:
        proc, self.proc = self.proc, None
        if proc is not None:
            try:
                if not kill and proc.poll() is None and proc.stdin:
                    proc.stdin.write("quit\n")
                    proc.stdin.flush()
                    proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            # Close the pipes ourselves: left to the garbage collector, flushing stdin of a
            # process that has already exited prints a spurious "Exception ignored" at exit.
            for stream in (proc.stdin, proc.stdout):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None


def default_workers() -> int:
    import os

    return max(1, min(os.cpu_count() or 1, 8))


def run_jobs(
    install: ForgeInstall,
    jobs: List[Job],
    on_result: Callable[[Job, dict], None],
    workers: Optional[int] = None,
    heap: str = "2g",
    log_dir: Optional[Path] = None,
) -> dict:
    """Play every job, calling ``on_result(job, result)`` (serialised) as each game finishes.

    Returns information about the engine that played them (Forge and Java versions).
    """
    if not jobs:
        return {}
    classes = forge_mod.ensure_bridge(install)
    cmd = forge_mod.java_command(install, classes, heap=heap)
    env = forge_mod.java_env()
    log_dir = Path(log_dir) if log_dir else forge_mod.home_dir() / "logs"
    count = max(1, min(workers or default_workers(), len(jobs)))

    pending: "queue.Queue[Job]" = queue.Queue()
    for job in jobs:
        pending.put(job)

    lock = threading.Lock()
    stop = threading.Event()
    failures: List[BaseException] = []
    engine: dict = {}
    live: List[_Worker] = []

    def loop(index: int) -> None:
        worker: Optional[_Worker] = None
        start_failures = 0
        try:
            while not stop.is_set():
                try:
                    job = pending.get_nowait()
                except queue.Empty:
                    return
                while worker is None and not stop.is_set():
                    candidate = _Worker(cmd, install.workdir, env, log_dir / f"worker-{index}.log")
                    try:
                        candidate.start()
                    except ForgeError:
                        start_failures += 1
                        if start_failures >= MAX_START_FAILURES:
                            raise
                        time.sleep(1.0)
                        continue
                    worker = candidate
                    start_failures = 0
                    with lock:
                        live.append(worker)
                        engine.update({"forgeVersion": worker.info.get("forgeVersion"),
                                       "java": worker.info.get("java")})
                if worker is None:
                    return
                result = worker.run(job)
                if result.get("status") == "crash" and not job.meta.get("_retried"):
                    # The process may have died between games; that says nothing about this game,
                    # so give it one more try on a fresh worker before recording a crash.
                    job.meta["_retried"] = True
                    pending.put(job)
                    result = None
                if result is None or result.get("restart") or not worker.alive():
                    with lock:
                        if worker in live:
                            live.remove(worker)
                    worker.stop(kill=True)
                    worker = None
                if result is None:
                    continue
                with lock:
                    if not stop.is_set():
                        on_result(job, result)
        except BaseException as exc:  # surfaced to the caller below
            with lock:
                failures.append(exc)
            stop.set()
        finally:
            if worker is not None:
                worker.stop()

    threads = [threading.Thread(target=loop, args=(i,), daemon=True) for i in range(count)]
    for thread in threads:
        thread.start()
    try:
        while any(t.is_alive() for t in threads):
            for thread in threads:
                thread.join(timeout=0.2)
    except KeyboardInterrupt:
        stop.set()
        with lock:
            for worker in list(live):
                worker.stop(kill=True)
        raise
    if failures:
        raise failures[0]
    return engine
