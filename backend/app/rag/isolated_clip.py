
import json
import logging
import os
import subprocess
import sys


CLIP_TIMEOUT = 180
logger = logging.getLogger("emsi-chatbot.clip")


class ClipSearchDeferred(RuntimeError):
    """CLIP was skipped because releasing BGE or safe RAM could not be confirmed."""


def search_images_isolated(
    question: str,
    limit: int = 3,
    mode: str = "generic",
):
    question = question.strip()

    if not question:
        return []

    from app.rag.isolated_retriever import prepare_for_clip
    if not prepare_for_clip():
        raise ClipSearchDeferred("CLIP différé : libération mémoire ou RAM insuffisante.")

    payload = {
        "question": question,
        "limit": max(1, min(int(limit), 10)),
        "mode": mode,
    }

    env = os.environ.copy()

    env["OMP_NUM_THREADS"] = "2"
    env["MKL_NUM_THREADS"] = "2"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "2"
    env["NUMEXPR_NUM_THREADS"] = "2"
    env["EMSI_AI_DEVICE"] = "cpu"

    command = [
        sys.executable,
        "-m",
        "app.rag.clip_worker"
    ]

    try:
        result = subprocess.run(
            command,
            input=json.dumps(
                payload,
                ensure_ascii=False
            ),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=CLIP_TIMEOUT,
            env=env,
            check=False
        )

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "La recherche CLIP a dépassé "
            "le délai autorisé."
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            "Échec du processus CLIP : "
            + result.stderr[-1500:]
        )

    if result.stderr.strip():
        logger.info("Diagnostics du worker CLIP : %s", result.stderr.strip()[-6000:])

    try:
        response = json.loads(
            result.stdout.strip()
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Réponse JSON invalide du processus CLIP : "
            + result.stdout[-500:]
        ) from exc

    images = response.get("images", [])

    if not isinstance(images, list):
        raise RuntimeError(
            "Format de réponse CLIP invalide."
        )

    return images
