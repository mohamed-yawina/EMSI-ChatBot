
import json
import os
import subprocess
import sys
import logging
import time


# =====================================================
# CONFIGURATION
# =====================================================

logger = logging.getLogger("emsi-chatbot.worker")

MAX_CPU_THREADS = 2
SEARCH_TIMEOUT = 120


# =====================================================
# RECHERCHE RAG ISOLÉE
# =====================================================

def _search_documents_subprocess(
    question: str,
    limit: int = 3
) -> list:

    question = question.strip()

    if not question:
        return []

    limit = max(1, min(limit, 10))

    # Limiter les ressources utilisées par BGE-M3.
    env = os.environ.copy()

    env["OMP_NUM_THREADS"] = str(MAX_CPU_THREADS)
    env["MKL_NUM_THREADS"] = str(MAX_CPU_THREADS)
    env["OPENBLAS_NUM_THREADS"] = str(MAX_CPU_THREADS)
    env["NUMEXPR_NUM_THREADS"] = str(MAX_CPU_THREADS)

    env["TOKENIZERS_PARALLELISM"] = "false"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # Keep BGE-M3 on CPU on the subprocess fallback as well as the persistent path.
    env["EMSI_AI_DEVICE"] = "cpu"

    # Lancer BGE-M3 dans un processus indépendant.
    command = [
        sys.executable,
        "-m",
        "app.rag.search_worker",
        question,
        str(limit)
    ]

    start = time.perf_counter()

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=False,
            timeout=SEARCH_TIMEOUT,
            env=env,
            check=False
        )

    except subprocess.TimeoutExpired as exc:
        logger.error(
            "Timeout BGE-M3 après %s secondes",
            SEARCH_TIMEOUT
        )

        raise RuntimeError(
            "La recherche BGE-M3 a dépassé "
            f"le délai de {SEARCH_TIMEOUT} secondes."
        ) from exc

    except OSError as exc:
        logger.error(
            "Impossible de démarrer BGE-M3 : %s",
            exc
        )

        raise RuntimeError(
            f"Impossible de démarrer BGE-M3 : {exc}"
        ) from exc

    total_duration = time.perf_counter() - start

    # =================================================
    # JOURNAUX DU PROCESSUS ISOLÉ
    # =================================================

    worker_logs = result.stderr.decode(
        "utf-8",
        errors="replace"
    ).strip()

    for line in worker_logs.splitlines():
        if "[PERF]" in line:
            logger.info(line)

    logger.info(
        "[PERF] Processus isolé total : %.2fs",
        total_duration
    )

    # =================================================
    # VÉRIFICATION DU PROCESSUS
    # =================================================

    if result.returncode != 0:

        logger.error(
            "Erreur du processus BGE-M3 : %s",
            worker_logs[-1500:]
        )

        raise RuntimeError(
            "Erreur recherche RAG : "
            + (
                worker_logs[-1500:]
                or f"Code {result.returncode}"
            )
        )

    # =================================================
    # DÉCODAGE DES RÉSULTATS JSON
    # =================================================

    try:
        output = result.stdout.decode("utf-8")
        documents = json.loads(output)

    except (
        UnicodeDecodeError,
        json.JSONDecodeError
    ) as exc:

        logger.error(
            "Réponse JSON invalide du processus BGE-M3"
        )

        raise RuntimeError(
            "Le processus BGE-M3 a retourné "
            "une réponse JSON invalide."
        ) from exc

    if not isinstance(documents, list):
        raise RuntimeError(
            "Format de résultats RAG invalide : "
            "une liste était attendue."
        )

    logger.info(
        "[PERF] %s documents récupérés",
        len(documents)
    )

    return documents

# =====================================================
# RECHERCHE PERSISTANTE CPU AVEC REPLI ISOLE
# =====================================================

import ctypes
import gc
import sys
import threading
from contextlib import contextmanager

PERSISTENT_MIN_RAM_MB = 4096
_persistent_lock = threading.Lock()
_persistent_state = "cold"


def should_use_persistent(available_ram_mb, minimum_ram_mb=PERSISTENT_MIN_RAM_MB):
    """Décision pure, testable sans charger de modèle."""
    return (
        isinstance(available_ram_mb, (int, float))
        and available_ram_mb >= minimum_ram_mb
    )


def _available_ram_mb():
    """Return safe available memory on Windows and Linux containers.

    Linux uses the effective cgroup limit (when configured), bounded by host
    MemAvailable. Unknown limits are ignored instead of interpreted as free RAM.
    """
    if os.name != "nt":
        candidates = []

        def read_integer(path):
            try:
                with open(path, encoding="ascii") as source:
                    value = source.read().strip()
                return int(value) if value and value != "max" else None
            except (OSError, ValueError):
                return None

        # cgroup v2, used by current Docker Desktop Linux containers.
        limit = read_integer("/sys/fs/cgroup/memory.max")
        current = read_integer("/sys/fs/cgroup/memory.current")
        if limit is not None and current is not None and limit < (1 << 60):
            candidates.append(max(0, limit - current) // (1024 * 1024))

        # cgroup v1 fallback.
        limit = read_integer("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        current = read_integer("/sys/fs/cgroup/memory/memory.usage_in_bytes")
        if limit is not None and current is not None and limit < (1 << 60):
            candidates.append(max(0, limit - current) // (1024 * 1024))

        try:
            with open("/proc/meminfo", encoding="ascii") as meminfo:
                for line in meminfo:
                    if line.startswith("MemAvailable:"):
                        candidates.append(int(line.split()[1]) // 1024)
                        break
        except (OSError, ValueError, IndexError):
            pass

        return min(candidates) if candidates else None

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(status)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return int(status.ullAvailPhys / (1024 * 1024))
    except (AttributeError, OSError):
        return None


@contextmanager
def _force_cpu_device():
    """Force le chargement initial du modèle sur CPU sans altérer l'environnement appelant."""
    previous = os.environ.get("EMSI_AI_DEVICE")
    os.environ["EMSI_AI_DEVICE"] = "cpu"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("EMSI_AI_DEVICE", None)
        else:
            os.environ["EMSI_AI_DEVICE"] = previous


def _release_persistent_model():
    retriever = sys.modules.get("app.rag.retriever")
    if retriever is None:
        gc.collect()
        return True
    get_model = getattr(retriever, "get_embedding_model", None)
    if get_model is None or not hasattr(get_model, "cache_clear"):
        gc.collect()
        return False
    get_model.cache_clear()
    gc.collect()
    cache_info = getattr(get_model, "cache_info", None)
    if cache_info is None:
        return False
    try:
        return cache_info().currsize == 0
    except (AttributeError, TypeError):
        return False


def release_persistent_model():
    """Clear and confirm the cached BGE-M3 object is released."""
    global _persistent_state
    with _persistent_lock:
        released = _release_persistent_model()
        if _persistent_state != "disabled":
            _persistent_state = "cold"
        return released


def prepare_for_clip() -> bool:
    """Require a cleared BGE cache and the existing safe RAM floor before CLIP."""
    release_started = time.perf_counter()
    released = release_persistent_model()
    logger.info(
        "[CLIP_PERF] stage=release_bge seconds=%.3f confirmed=%s",
        time.perf_counter() - release_started,
        released,
    )
    if not released:
        logger.warning("CLIP désactivé : libération du cache BGE-M3 non confirmée.")
        return False
    memory_started = time.perf_counter()
    available_ram = _available_ram_mb()
    logger.info(
        "[CLIP_PERF] stage=ram_gate seconds=%.3f available_mb=%s threshold_mb=%s",
        time.perf_counter() - memory_started,
        available_ram,
        PERSISTENT_MIN_RAM_MB,
    )
    if not should_use_persistent(available_ram):
        logger.warning(
            "CLIP différé : RAM disponible=%s Mio; seuil de sécurité=%s Mio.",
            available_ram,
            PERSISTENT_MIN_RAM_MB,
        )
        return False
    return True


def search_documents_isolated(question: str, limit: int = 3) -> list:
    """Réutilise BGE-M3 sur CPU si la RAM le permet, sinon utilise le worker isolé historique."""
    global _persistent_state
    fallback_due_to_ram = False

    question = question.strip()
    if not question:
        return []
    limit = max(1, min(limit, 10))

    # CLIP may stay warm in its dedicated process. Reap that process before
    # BGE-M3 can be imported or loaded, preserving strict model exclusivity.
    from app.rag.isolated_clip import stop_clip_worker
    stop_clip_worker()

    with _persistent_lock:
        if _persistent_state != "disabled":
            if _persistent_state == "cold":
                available_ram = _available_ram_mb()
                if not should_use_persistent(available_ram):
                    logger.warning(
                        "BGE-M3 persistant différé : RAM disponible=%s Mio; "
                        "seuil=%s Mio. Utilisation du worker isolé pour cette requête.",
                        available_ram,
                        PERSISTENT_MIN_RAM_MB,
                    )
                    fallback_due_to_ram = True
                else:
                    logger.info(
                        "Initialisation BGE-M3 persistante sur CPU (%s Mio libres)",
                        available_ram,
                    )

            if not fallback_due_to_ram:
                try:
                    start_total = time.perf_counter()
                    with _force_cpu_device():
                        start_import = time.perf_counter()
                        from app.rag.retriever import search_documents
                        logger.info(
                            "[PERF] Import Python/PyTorch persistant: %.2fs",
                            time.perf_counter() - start_import,
                        )
                        documents = search_documents(question, limit=limit)

                    _persistent_state = "ready"
                    logger.info(
                        "[PERF] Recherche persistante totale: %.2fs",
                        time.perf_counter() - start_total,
                    )
                    return documents

                except Exception:
                    logger.exception(
                        "Recherche BGE-M3 persistante indisponible; repli vers le worker isolé."
                    )
                    _persistent_state = "disabled"
                    _release_persistent_model()

    return _search_documents_subprocess(question, limit)
