"""RAM-exclusive, reusable CLIP worker with a bounded idle lifetime."""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time


CLIP_TIMEOUT = 180
CLIP_IDLE_SECONDS = 120
logger = logging.getLogger("emsi-chatbot.clip")

_worker_lock = threading.RLock()
_worker_process: subprocess.Popen | None = None
_worker_responses: queue.Queue[str | None] | None = None
_worker_reader: threading.Thread | None = None
_idle_timer: threading.Timer | None = None
_worker_generation = 0


class ClipSearchDeferred(RuntimeError):
    """CLIP was skipped because releasing BGE or safe RAM could not be confirmed."""


def _read_worker_stdout(process: subprocess.Popen, responses: queue.Queue):
    try:
        assert process.stdout is not None
        for line in process.stdout:
            responses.put(line)
    finally:
        responses.put(None)


def _cancel_idle_timer_locked():
    global _idle_timer, _worker_generation
    _worker_generation += 1
    if _idle_timer is not None:
        _idle_timer.cancel()
        _idle_timer = None


def _stop_worker_locked(graceful: bool = True):
    global _worker_process, _worker_responses, _worker_reader
    process = _worker_process
    reader = _worker_reader
    if process is None:
        return

    _cancel_idle_timer_locked()
    if process.poll() is None:
        if graceful and process.stdin is not None:
            try:
                process.stdin.write(json.dumps({"command": "shutdown"}) + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                graceful = False
        try:
            process.wait(timeout=5 if graceful else 0.2)
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
                process.wait(timeout=3)

    if reader is not None and reader is not threading.current_thread():
        reader.join(timeout=1)

    for stream in (process.stdin, process.stdout):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass

    _worker_process = None
    _worker_responses = None
    _worker_reader = None
    logger.info("[CLIP_PERF] worker_stopped graceful=%s", graceful)


def stop_clip_worker():
    """Stop CLIP and wait for process exit before any BGE-M3 load."""
    with _worker_lock:
        _stop_worker_locked()


def _expire_worker(process: subprocess.Popen, generation: int):
    with _worker_lock:
        if _worker_process is process and _worker_generation == generation:
            logger.info("[CLIP_PERF] idle_expiration_seconds=%s", CLIP_IDLE_SECONDS)
            _stop_worker_locked()


def _schedule_idle_expiration_locked(process: subprocess.Popen):
    global _idle_timer
    _cancel_idle_timer_locked()
    generation = _worker_generation
    timer = threading.Timer(CLIP_IDLE_SECONDS, _expire_worker, args=(process, generation))
    timer.daemon = True
    _idle_timer = timer
    timer.start()


def _worker_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "2",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "OPENBLAS_NUM_THREADS": "2",
        "NUMEXPR_NUM_THREADS": "2",
        "EMSI_AI_DEVICE": "cpu",
    })
    return env


def _start_worker_locked():
    global _worker_process, _worker_responses, _worker_reader
    if _worker_process is not None and _worker_process.poll() is None:
        logger.info("[CLIP_PERF] worker_reused pid=%s", _worker_process.pid)
        return _worker_process

    _stop_worker_locked(graceful=False)
    command = [sys.executable, "-m", "app.rag.clip_worker"]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=_worker_environment(),
    )
    responses: queue.Queue[str | None] = queue.Queue()
    reader = threading.Thread(
        target=_read_worker_stdout,
        args=(process, responses),
        name="emsi-clip-stdout",
        daemon=True,
    )
    _worker_process = process
    _worker_responses = responses
    _worker_reader = reader
    reader.start()
    logger.info("[CLIP_PERF] worker_started pid=%s", process.pid)
    return process


def _run_worker_locked(payload: dict) -> list[dict]:
    process = _start_worker_locked()
    responses = _worker_responses
    if process.stdin is None or responses is None:
        _stop_worker_locked(graceful=False)
        raise RuntimeError("Le worker CLIP n'a pas démarré correctement.")

    worker_started = time.perf_counter()
    try:
        process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        process.stdin.flush()
        response_line = responses.get(timeout=CLIP_TIMEOUT)
    except queue.Empty as exc:
        logger.error("[CLIP_PERF] worker_request_timeout_seconds=%.3f", time.perf_counter() - worker_started)
        _stop_worker_locked(graceful=False)
        raise RuntimeError("La recherche CLIP a dépassé le délai autorisé.") from exc
    except (BrokenPipeError, OSError) as exc:
        _stop_worker_locked(graceful=False)
        raise RuntimeError("Le processus CLIP s'est arrêté pendant la recherche.") from exc

    if response_line is None:
        _stop_worker_locked(graceful=False)
        raise RuntimeError("Le processus CLIP s'est arrêté sans réponse.")

    try:
        response = json.loads(response_line)
    except json.JSONDecodeError as exc:
        _stop_worker_locked(graceful=False)
        raise RuntimeError("Réponse JSON invalide du processus CLIP.") from exc

    if response.get("error"):
        _stop_worker_locked(graceful=False)
        raise RuntimeError("Le worker CLIP a échoué; consultez les diagnostics serveur.")

    images = response.get("images", [])
    if not isinstance(images, list):
        _stop_worker_locked(graceful=False)
        raise RuntimeError("Format de réponse CLIP invalide.")

    _schedule_idle_expiration_locked(process)
    logger.info("[CLIP_PERF] worker_request_seconds=%.3f retained=%d", time.perf_counter() - worker_started, len(images))
    return images


def search_images_isolated(
    question: str,
    limit: int = 3,
    mode: str = "generic",
):
    question = question.strip()
    if not question:
        return []

    payload = {
        "question": question,
        "limit": max(1, min(int(limit), 10)),
        "mode": mode,
    }

    with _worker_lock:
        from app.rag.isolated_retriever import prepare_for_clip
        if not prepare_for_clip():
            # A warm CLIP process may itself leave too little safe RAM. Stop it
            # before returning control so future BGE searches start cleanly.
            _stop_worker_locked()
            raise ClipSearchDeferred("CLIP différé : libération mémoire ou RAM insuffisante.")
        _cancel_idle_timer_locked()
        return _run_worker_locked(payload)


atexit.register(stop_clip_worker)
