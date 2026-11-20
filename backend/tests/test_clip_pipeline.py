import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main
from app.rag import isolated_clip, isolated_retriever
from app.rag import clip_worker
from app.rag.image_utils import build_image_result, build_image_url
from app.rag.image_intent import ImageIntent, image_matches_person_evidence, resolve_image_intent
from app.rag.image_evidence import (
    image_candidate_decision,
    image_candidate_evidence,
    page_context,
    select_diverse_images,
)


def _write_test_image(path):
    image = Image.new("RGB", (400, 400))
    seed = 17
    pixels = []
    for _ in range(400 * 400):
        seed = (1664525 * seed + 1013904223) % (2 ** 32)
        red = (seed >> 16) & 255
        seed = (1664525 * seed + 1013904223) % (2 ** 32)
        green = (seed >> 16) & 255
        seed = (1664525 * seed + 1013904223) % (2 ** 32)
        blue = (seed >> 16) & 255
        pixels.append((red, green, blue))
    image.putdata(pixels)
    image.save(path, format="PNG")
    image.close()


def test_image_path_and_metadata_are_validated(tmp_path):
    root = tmp_path
    processed = root / "data" / "processed"
    image_dir = processed / "Brochure-EMSI" / "images"
    image_dir.mkdir(parents=True)
    image_file = image_dir / "page_7_image_1.png"
    _write_test_image(image_file)
    relative_path = str(image_file.relative_to(root))

    assert build_image_url(relative_path, root, processed) == "/images/Brochure-EMSI/images/page_7_image_1.png"
    result = build_image_result(
        {"id": "image_7", "path": relative_path, "source": "Brochure-EMSI.pdf", "page": 7},
        0.92344,
        "qdrant-id",
        root,
        processed,
    )
    assert result == {
        "id": "image_7",
        "url": "/images/Brochure-EMSI/images/page_7_image_1.png",
        "filename": "page_7_image_1.png",
        "source": "Brochure-EMSI.pdf",
        "page": 7,
        "score": 0.9234,
        "width": 400,
        "height": 400,
        "aspect_ratio": 1.0,
    }
    assert build_image_url(str(root / "outside.jpeg"), root, processed) is None
    assert build_image_result({"path": relative_path, "source": "", "page": 7}, 0.9, "id", root, processed) is None
    assert build_image_result({"path": relative_path, "source": "Brochure.pdf", "page": 0}, 0.9, "id", root, processed) is None
    tiny_file = image_dir / "tiny.png"
    tiny_file.write_bytes(b"x" * 500)
    assert build_image_result(
        {"path": str(tiny_file.relative_to(root)), "source": "Brochure-EMSI.pdf", "page": 7},
        0.9, "tiny", root, processed,
    ) is None
    unverified_caption = build_image_result(
        {"path": relative_path, "source": "Brochure-EMSI.pdf", "page": 7,
         "caption": "Photo du campus EMSI"},
        0.9, "unverified-caption", root, processed,
    )
    assert "caption" not in unverified_caption
    verified_caption = build_image_result(
        {"path": relative_path, "source": "Brochure-EMSI.pdf", "page": 7,
         "caption": "Campus EMSI de Rabat", "caption_verified": True},
        0.9, "verified-caption", root, processed,
    )
    assert verified_caption["caption"] == "Campus EMSI de Rabat"
    assert verified_caption["caption_verified"] is True


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

    images = isolated_clip.search_images_isolated("campus", limit=2, mode="campus")

    assert images == [{"url": "/images/x.jpeg", "source": "Brochure-EMSI.pdf", "page": 7}]
    isolated_retriever.prepare_for_clip.assert_called_once_with()
    env = run.call_args.kwargs["env"]
    assert env["EMSI_AI_DEVICE"] == "cpu"
    assert env["OMP_NUM_THREADS"] == "2"
    payload = json.loads(run.call_args.kwargs["input"])
    assert payload["mode"] == "campus"


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
    from app.rag import image_evidence
    monkeypatch.setattr(
        image_evidence,
        "image_candidate_decision",
        lambda image, intent, documents: (True, "Texte extrait de la page de l’image.", "mocked positive"),
    )
    client = TestClient(main.app)
    try:
        no_images = client.post("/api/chat", json={"question": "Salut", "use_llm": False})
        assert no_images.status_code == 200
        assert no_images.json()["images"] == []
        image_search.assert_not_called()

        with_images = client.post("/api/chat", json={
            "question": "Montre-moi une photo du campus EMSI de Rabat", "use_llm": False, "include_images": True,
        })
        assert with_images.status_code == 200
        body = with_images.json()
        assert set(body) == {"answer", "sources", "images"}
        assert len(body["images"]) == 1
        assert body["images"][0]["url"] == image_results[0]["url"]
        assert "context" not in body["images"][0]
        assert body["sources"][0]["source"] == "Brochure-EMSI.pdf"
        assert body["sources"][0]["page"] == 7
        image_search.assert_called_once_with("montre-moi une photo du campus emsi de rabat", "campus")

        text_only_with_toggle = client.post("/api/chat", json={
            "question": "Quels campus EMSI ?", "use_llm": False,
            "include_images": True,
        })
        assert text_only_with_toggle.status_code == 200
        assert text_only_with_toggle.json()["images"] == []
        image_search.assert_called_once()
    finally:
        main.get_cached_rag_answer.cache_clear()


def test_ram_deferred_clip_keeps_text_response_and_returns_empty_images(monkeypatch):
    main.get_cached_rag_answer.cache_clear()
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", Mock(return_value=[{
        "content": "Le campus EMSI presente une vue du site.",
        "source": "Brochure-EMSI.pdf", "page": 7, "score": 0.9,
    }]))
    monkeypatch.setattr(
        main,
        "get_cached_images",
        Mock(side_effect=isolated_clip.ClipSearchDeferred("low RAM")),
    )
    try:
        response = TestClient(main.app).post("/api/chat", json={
            "question": "Montre-moi une photo du campus EMSI", "use_llm": False, "include_images": True,
        })
    finally:
        main.get_cached_rag_answer.cache_clear()
    assert "Le campus EMSI presente une vue du site." in response.json()["answer"]
    assert response.json()["images"] == []


def test_image_search_requires_explicit_image_intent_and_resolves_sa_photo():
    assert resolve_image_intent("Quels sont les campus EMSI ?").requested is False
    history = [{"role": "user", "content": "Montre le directeur general de l EMSI"}]
    intent = resolve_image_intent("Donne-moi sa photo", history)
    assert intent.requested is True
    assert "directeur general" in intent.query
    assert intent.person_target == "directeur general"
    assert resolve_image_intent("Montre-moi une photo d'un campus EMSI").mode == "campus"
    assert resolve_image_intent("Montre-moi des images de la brochure EMSI").mode == "brochure"
    assert resolve_image_intent("Montre-moi une image d'un laboratoire EMSI").mode == "laboratory"
    assert resolve_image_intent("Montre-moi une image de la cérémonie de remise des diplômes").mode == "event"
    assert resolve_image_intent("Montre-moi un événement EMSI").mode == "event"


    assert resolve_image_intent(
        "Montre-moi une image de la remise des diplomes avec le directeur EMSI"
    ).mode == "event"
    person = resolve_image_intent("Montre-moi une photo de Fatima")
    assert person.mode == "person"
    assert person.person_target == "fatima"


def test_image_page_context_and_clip_floor_are_used_without_text_retrieval_match(monkeypatch):
    monkeypatch.setenv("EMSI_CLIP_MIN_SCORE", "0.20")
    context = page_context("Brochure-EMSI.pdf", 6, "campus EMSI")
    assert "campus" in context.lower()
    intent = ImageIntent(requested=True, query="images de la brochure EMSI", mode="brochure")
    weak_candidate = {
        "source": "Brochure-EMSI.pdf", "page": 6, "score": 0.10,
        "url": "/images/Brochure-EMSI/images/page_6_image_1.jpeg",
    }
    assert image_candidate_evidence(weak_candidate, intent, [])[0] is True
    strong_candidate = {**weak_candidate, "score": 0.40}
    relevant, excerpt = image_candidate_evidence(strong_candidate, intent, [])
    assert relevant is True
    assert excerpt


def test_targeted_image_requires_visual_contrast_not_page_words_alone(monkeypatch):
    monkeypatch.setattr(
        "app.rag.image_evidence.page_context",
        lambda source, page, query: "Le campus EMSI et ses infrastructures sont présentés.",
    )
    intent = ImageIntent(True, "photo campus EMSI", mode="campus")
    candidate = {"source": "Brochure-EMSI.pdf", "page": 4, "score": 0.31}
    assert image_candidate_decision(candidate, intent, [])[2] == "contrast_scores_missing"
    assert image_candidate_decision({**candidate, "visual_margin": -0.01}, intent, [])[2] == "confounder_prompt_scored_at_least_as_high"
    assert image_candidate_decision({**candidate, "visual_margin": 0.02}, intent, [])[0] is True


def test_generic_clip_search_scores_confounders_and_can_retain_relevant_candidate(monkeypatch):
    monkeypatch.setattr(
        clip_worker,
        "encode_questions",
        lambda prompts, device: [[1.0], *[[0.0] for _ in prompts[1:]]],
    )
    monkeypatch.setattr(
        clip_worker,
        "build_image_result",
        lambda payload, score, result_id: {
            "id": str(result_id),
            "source": "Brochure-EMSI.pdf",
            "page": 11,
            "url": "/images/Brochure-EMSI/images/page_11_image_1.jpg",
            "score": round(float(score), 4),
        },
    )

    class FakeQdrantClient:
        def __init__(self, **_kwargs):
            self.query_number = 0

        def query_points(self, **_kwargs):
            score = 0.52 if self.query_number == 0 else 0.18
            self.query_number += 1
            return Mock(points=[Mock(
                id="asset-1",
                payload={"page": 11, "source": "Brochure-EMSI.pdf", "path": "unused"},
                score=score,
            )])

    monkeypatch.setattr(clip_worker, "QdrantClient", FakeQdrantClient)
    results = clip_worker.search_images("Montre une photo en informatique", mode="generic")

    assert len(clip_worker.NEGATIVE_PROMPTS["generic"]) == 2
    assert len(results) == 1
    assert results[0]["visual_margin"] == 0.34
    intent = ImageIntent(True, "photo informatique", mode="generic")
    monkeypatch.setattr(
        "app.rag.image_evidence.page_context",
        lambda source, page, query: "La formation présente des équipements informatiques.",
    )
    accepted, _, reason = image_candidate_decision(results[0], intent, [])
    assert accepted is True
    assert reason == "positive_contrast_and_topical_page_context"


def test_laboratory_rejects_image_when_graduation_contrast_wins(monkeypatch):
    monkeypatch.setattr(
        "app.rag.image_evidence.page_context",
        lambda source, page, query: "Le laboratoire de recherche EMSI est équipé.",
    )
    intent = ImageIntent(True, "image laboratoire EMSI", mode="laboratory")
    candidate = {
        "source": "Brochure-EMSI.pdf", "page": 30, "score": 0.38,
        "visual_margin": -0.04,
    }
    accepted, _, reason = image_candidate_decision(candidate, intent, [])
    assert accepted is False
    assert reason == "confounder_prompt_scored_at_least_as_high"


def test_brochure_request_samples_diverse_pages_without_a_concept_floor():
    intent = ImageIntent(True, "images de la brochure EMSI", mode="brochure")
    candidates = [
        {"source": "Brochure-EMSI.pdf", "page": 2, "url": "/images/a.jpg", "score": 0.13},
        {"source": "Brochure-EMSI.pdf", "page": 2, "url": "/images/b.jpg", "score": 0.12},
        {"source": "Brochure-EMSI.pdf", "page": 9, "url": "/images/c.jpg", "score": 0.11},
    ]
    assert image_candidate_evidence(candidates[0], intent, [])[0] is True
    selected = select_diverse_images(candidates, limit=3)
    assert [item["url"] for item in selected] == ["/images/a.jpg", "/images/c.jpg"]


def test_api_returns_a_diverse_brochure_image_sample_with_page_sources(monkeypatch):
    candidates = [
        {"id": "a", "source": "Brochure-EMSI.pdf", "page": 2, "url": "/images/a.jpg", "score": 0.14},
        {"id": "b", "source": "Brochure-EMSI.pdf", "page": 2, "url": "/images/b.jpg", "score": 0.13},
        {"id": "c", "source": "Brochure-EMSI.pdf", "page": 9, "url": "/images/c.jpg", "score": 0.12},
    ]
    monkeypatch.setattr(main, "_compute_rag_answer", Mock(return_value=("", [], [])))
    monkeypatch.setattr(main, "get_cached_images", Mock(return_value=candidates))
    response = TestClient(main.app).post("/api/chat", json={
        "question": "Montre-moi des images présentes dans la brochure EMSI",
        "use_llm": False, "include_images": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert [image["url"] for image in body["images"]] == ["/images/a.jpg", "/images/c.jpg"]
    assert [source["page"] for source in body["sources"]] == [2, 9]
    assert "visuels extraits" in body["answer"]


def test_api_rejects_lab_result_when_visual_scores_favor_graduation(monkeypatch):
    candidate = {
        "id": "lab-or-graduation", "source": "Brochure-EMSI.pdf", "page": 30,
        "url": "/images/ambiguous.jpg", "score": 0.38, "visual_margin": -0.04,
    }
    monkeypatch.setattr(main, "_compute_rag_answer", Mock(return_value=("", [], [])))
    monkeypatch.setattr(main, "get_cached_images", Mock(return_value=[candidate]))
    monkeypatch.setattr(
        "app.rag.image_evidence.page_context",
        lambda source, page, query: "Le laboratoire de recherche EMSI est décrit sur cette page.",
    )
    response = TestClient(main.app).post("/api/chat", json={
        "question": "Montre-moi une image d'un laboratoire EMSI",
        "use_llm": False, "include_images": True,
    })
    assert response.status_code == 200
    assert response.json()["images"] == []
    assert "laboratoire EMSI" in response.json()["answer"]


def test_person_image_requires_same_page_text_and_identifying_caption():
    document = {
        "content": "Le directeur general de l EMSI presente le campus.",
        "source": "Brochure-EMSI.pdf", "page": 12,
    }
    image = {
        "source": "Brochure-EMSI.pdf", "page": 12,
        "caption": "Portrait du directeur general de l EMSI",
        "caption_verified": True,
    }
    assert image_matches_person_evidence(image, [document], "directeur general")
    assert not image_matches_person_evidence(
        {**image, "caption": "Portrait d'un homme"}, [document], "directeur general"
    )
    assert not image_matches_person_evidence(
        image, [{**document, "page": 13}], "directeur general"
    )
    assert not image_matches_person_evidence(
        {**image, "caption_verified": False}, [document], "directeur general"
    )


def test_image_answers_are_brief_and_do_not_turn_clip_similarity_into_fact():
    campus = main._answer_for_images("campus", [{"page": 2}])
    assert "aucune légende ne confirme" in campus
    assert "page 2" in campus
    assert "photo de campus vérifiée" not in campus.lower()

    laboratory = main._answer_for_images("laboratory", [{"page": 32}, {"page": 22}])
    assert "ne sont pas légendées individuellement" in laboratory
    assert "32, 22" in laboratory

    brochure = main._answer_for_images("brochure", [{"page": 9}, {"page": 38}, {"page": 8}])
    assert brochure == "Voici quelques visuels extraits de la brochure EMSI, avec leurs pages : 9, 38, 8."


def test_only_verified_campus_caption_allows_verified_campus_wording():
    answer = main._answer_for_images("campus", [{
        "page": 4,
        "caption": "Campus EMSI de Rabat",
        "caption_verified": True,
    }])
    assert "La légende identifie" in answer
    verified_photo = main._answer_for_images("campus", [{
        "page": 4,
        "caption": "Photographie du campus EMSI de Rabat",
        "caption_verified": True,
    }])
    assert "Voici une photo explicitement légendée" in verified_photo
    unverified = main._answer_for_images("campus", [{
        "page": 4, "caption": "Campus EMSI de Rabat", "caption_verified": False,
    }])
    assert "aucune légende ne confirme" in unverified


def test_chat_does_not_label_unverified_person_photo_from_clip_similarity(monkeypatch):
    main.get_cached_rag_answer.cache_clear()
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", Mock(return_value=[{
        "content": "Le directeur general de l EMSI presente le campus.",
        "source": "Brochure-EMSI.pdf", "page": 12, "score": 0.9,
    }]))
    monkeypatch.setattr(main, "get_cached_images", Mock(return_value=[{
        "url": "/images/portrait.jpg", "source": "Brochure-EMSI.pdf",
        "page": 12, "score": 0.99,
    }]))
    response = TestClient(main.app).post("/api/chat", json={
        "question": "Donne-moi la photo du directeur general de l EMSI",
        "use_llm": False, "include_images": True,
    })
    main.get_cached_rag_answer.cache_clear()
    assert response.status_code == 200
    assert response.json()["images"] == []
    assert "photo explicitement" in response.json()["answer"]


def test_chat_discards_clip_candidate_from_unrelated_page(monkeypatch):
    main.get_cached_rag_answer.cache_clear()
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", Mock(return_value=[{
        "content": "Le campus EMSI de Rabat accueille les ÃƒÂ©tudiants.",
        "source": "Brochure-EMSI.pdf", "page": 7, "score": 0.9,
    }]))
    monkeypatch.setattr(main, "get_cached_images", Mock(return_value=[{
        "url": "/images/unrelated.jpg", "source": "Brochure-EMSI.pdf",
        "page": 8, "score": 0.99,
    }]))
    response = TestClient(main.app).post("/api/chat", json={
        "question": "Montre-moi une photo du campus EMSI de Rabat",
        "use_llm": False, "include_images": True,
    })
    main.get_cached_rag_answer.cache_clear()
    assert response.status_code == 200
    assert response.json()["images"] == []


def test_static_route_serves_existing_image():
    project_root = Path(__file__).resolve().parents[2]
    metadata = json.loads((project_root / "data/processed/Brochure-EMSI/image_metadata.json").read_text(encoding="utf-8"))
    url = build_image_url(metadata[0]["path"])
    response = TestClient(main.app).get(url)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_image_route_does_not_expose_non_image_processed_files():
    client = TestClient(main.app)
    response = client.get("/images/Brochure-EMSI/chunks.json")
    assert response.status_code == 404


@pytest.mark.parametrize("failure", ["exit", "invalid-json"])
def test_clip_worker_errors_are_clear(monkeypatch, failure):
    monkeypatch.setattr(isolated_retriever, "prepare_for_clip", Mock(return_value=True))
    result = Mock(returncode=1 if failure == "exit" else 0,
                  stdout="not json" if failure == "invalid-json" else "",
                  stderr="simulated failure")
    monkeypatch.setattr(isolated_clip.subprocess, "run", Mock(return_value=result))
    with pytest.raises(RuntimeError):
        isolated_clip.search_images_isolated("campus")
