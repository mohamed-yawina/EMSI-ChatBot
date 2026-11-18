import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main
from app.rag import isolated_clip, isolated_retriever
from app.rag.image_utils import build_image_result, build_image_url


def test_image_path_and_metadata_are_validated(tmp_path):
    root = tmp_path
    processed = root / "data" / "processed"
    image_dir = processed / "Brochure-EMSI" / "images"
    image_dir.mkdir(parents=True)
    image_file = image_dir / "page_7_image_1.jpeg"
    image_file.write_bytes(b"simulated image bytes")
    relative_path = str(image_file.relative_to(root))

    assert build_image_url(relative_path, root, processed) == "/images/Brochure-EMSI/images/page_7_image_1.jpeg"
    result = build_image_result(
        {"id": "image_7", "path": relative_path, "source": "Brochure-EMSI.pdf", "page": 7},
        0.92344,
        "qdrant-id",
        root,
        processed,
    )
    assert result == {
        "id": "image_7",
        "url": "/images/Brochure-EMSI/images/page_7_image_1.jpeg",
        "filename": "page_7_image_1.jpeg",
        "source": "Brochure-EMSI.pdf",
        "page": 7,
        "score": 0.9234,
    }
    assert build_image_url(str(root / "outside.jpeg"), root, processed) is None
    assert build_image_result({"path": relative_path, "source": "", "page": 7}, 0.9, "id", root, processed) is None
    assert build_image_result({"path": relative_path, "source": "Brochure.pdf", "page": 0}, 0.9, "id", root, processed) is None


def test_image_collection_metadata_references_existing_assets():
    project_root = Path(__file__).resolve().parents[2]
    metadata_path = project_root / "data" / "processed" / "Brochure-EMSI" / "image_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert len(metadata) == 147
    for item in metadata:
        assert item["source"] == "Brochure-EMSI.pdf"
        assert isinstance(item["page"], int) and item["page"] > 0
        assert (project_root / Path(item["path"].replace("\\", "/"))).is_file()


def test_clip_worker_is_prepared_on_cpu_and_returns_simulated_images(monkeypatch):
    monkeypatch.setattr(isolated_retriever, "prepare_for_clip", Mock(return_value=True))
    fake_result = Mock(returncode=0, stdout='{"images":[{"url":"/images/x.jpeg","source":"Brochure-EMSI.pdf","page":7}]}', stderr="")
    run = Mock(return_value=fake_result)
    monkeypatch.setattr(isolated_clip.subprocess, "run", run)

    images = isolated_clip.search_images_isolated("campus", limit=2)

    assert images == [{"url": "/images/x.jpeg", "source": "Brochure-EMSI.pdf", "page": 7}]
    isolated_retriever.prepare_for_clip.assert_called_once_with()
    env = run.call_args.kwargs["env"]
    assert env["EMSI_AI_DEVICE"] == "cpu"
    assert env["OMP_NUM_THREADS"] == "2"


def test_clip_is_skipped_when_ram_is_low_or_release_is_unconfirmed(monkeypatch):
    monkeypatch.setattr(isolated_retriever, "prepare_for_clip", Mock(return_value=False))
    run = Mock()
    monkeypatch.setattr(isolated_clip.subprocess, "run", run)
    with pytest.raises(isolated_clip.ClipSearchDeferred):
        isolated_clip.search_images_isolated("campus")
    run.assert_not_called()


def test_prepare_for_clip_requires_confirmed_release_then_ram():
    events = []
    with (
        patch.object(isolated_retriever, "release_persistent_model", side_effect=lambda: events.append("release") or True),
        patch.object(isolated_retriever, "_available_ram_mb", side_effect=lambda: events.append("ram") or 4096),
    ):
        assert isolated_retriever.prepare_for_clip() is True
    assert events == ["release", "ram"]

    with (
        patch.object(isolated_retriever, "release_persistent_model", return_value=False),
        patch.object(isolated_retriever, "_available_ram_mb") as available_ram,
    ):
        assert isolated_retriever.prepare_for_clip() is False
        available_ram.assert_not_called()

    with (
        patch.object(isolated_retriever, "release_persistent_model", return_value=True),
        patch.object(isolated_retriever, "_available_ram_mb", return_value=1024),
    ):
        assert isolated_retriever.prepare_for_clip() is False


def test_release_requires_empty_bge_cache():
    fake_retriever = types.ModuleType("app.rag.retriever")
    fake_get_model = Mock()
    fake_get_model.cache_clear = Mock()
    fake_get_model.cache_info = Mock(return_value=types.SimpleNamespace(currsize=0))
    fake_retriever.get_embedding_model = fake_get_model
    with patch.dict(sys.modules, {"app.rag.retriever": fake_retriever}):
        assert isolated_retriever.release_persistent_model() is True
    fake_get_model.cache_clear.assert_called_once_with()


def test_chat_includes_only_simulated_indexed_images_and_default_is_empty(monkeypatch):
    main.get_cached_rag_answer.cache_clear()
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", Mock(return_value=[]))
    image_results = [{
        "id": "qdrant-image-1", "url": "/images/Brochure-EMSI/images/page_7_image_1.jpeg",
        "filename": "page_7_image_1.jpeg", "source": "Brochure-EMSI.pdf", "page": 7, "score": 0.91,
    }]
    image_search = Mock(return_value=image_results)
    monkeypatch.setattr(main, "get_cached_images", image_search)
    client = TestClient(main.app)
    try:
        no_images = client.post("/api/chat", json={"question": "Salut", "use_llm": False})
        assert no_images.status_code == 200
        assert no_images.json()["images"] == []
        image_search.assert_not_called()

        with_images = client.post("/api/chat", json={
            "question": "Montre les campus", "use_llm": False, "include_images": True,
        })
        assert with_images.status_code == 200
        body = with_images.json()
        assert set(body) == {"answer", "sources", "images"}
        assert body["images"] == image_results
        assert body["sources"] == []
        image_search.assert_called_once_with("Montre les campus")
    finally:
        main.get_cached_rag_answer.cache_clear()


def test_ram_deferred_clip_keeps_text_response_and_returns_empty_images(monkeypatch):
    main.get_cached_rag_answer.cache_clear()
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", Mock(return_value=[]))
    monkeypatch.setattr(
        main,
        "get_cached_images",
        Mock(side_effect=isolated_clip.ClipSearchDeferred("low RAM")),
    )
    try:
        response = TestClient(main.app).post("/api/chat", json={
            "question": "Montre des campus", "use_llm": False, "include_images": True,
        })
    finally:
        main.get_cached_rag_answer.cache_clear()
    assert response.status_code == 200
    assert response.json()["answer"] == (
        "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
    )
    assert response.json()["images"] == []


def test_static_route_serves_existing_image():
    project_root = Path(__file__).resolve().parents[2]
    metadata = json.loads((project_root / "data/processed/Brochure-EMSI/image_metadata.json").read_text(encoding="utf-8"))
    url = build_image_url(metadata[0]["path"])
    response = TestClient(main.app).get(url)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


@pytest.mark.parametrize("failure", ["exit", "invalid-json"])
def test_clip_worker_errors_are_clear(monkeypatch, failure):
    monkeypatch.setattr(isolated_retriever, "prepare_for_clip", Mock(return_value=True))
    result = Mock(returncode=1 if failure == "exit" else 0,
                  stdout="not json" if failure == "invalid-json" else "",
                  stderr="simulated failure")
    monkeypatch.setattr(isolated_clip.subprocess, "run", Mock(return_value=result))
    with pytest.raises(RuntimeError):
        isolated_clip.search_images_isolated("campus")
