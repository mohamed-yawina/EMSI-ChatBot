import sys
import os
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag import retriever
from app.rag.ranking_policy import repair_common_mojibake


QUESTION = "Quelles sont toutes les filières proposées par l'EMSI selon la brochure ?"
CATALOG_TEXT = (
    "Diplôme d'ingénieur. Ingénierie Informatique & Réseaux. "
    "2 années préparatoires pour IIR, IAII, GI, GESI. "
    "2 années préparatoires pour GC. 2 années préparatoires pour GF. "
    "3 années cycle d'ingénieur Ingénierie des Automatismes & Informatique Industrielle. "
    "3 années cycle d'ingénieur Génie Industriel. "
    "3 années cycle d'ingénieur Génie Électrique & Systèmes Intelligents. "
    "3 années cycle d'ingénieur Génie Civil, Bâtiments & Travaux Publics. "
    "3 années cycle d'ingénieur Génie Financier."
)


class _Vector:
    def tolist(self):
        return [0.1, 0.2]


def _point(point_id, payload, score=None):
    return SimpleNamespace(id=point_id, payload=payload, score=score)


def test_local_extraction_page_nine_contains_all_program_names_and_gc_duration():
    project_root = Path(__file__).resolve().parents[2]
    chunks_path = (
        project_root / "data" / "processed" / "Brochure-EMSI" / "chunks.json"
    )
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    page_nine = [
        repair_common_mojibake(item["content"])
        for item in chunks
        if item.get("source") == "Brochure-EMSI.pdf" and item.get("page") == 9
    ]
    page_nine_text = " ".join(page_nine)

    assert len(page_nine) == 2
    for program_name in (
        "Ingénierie Informatique & Réseaux",
        "Ingénierie des Automatismes & Informatique Industrielle",
        "Génie Industriel",
        "Génie Électrique & Systèmes Intelligents",
        "Génie Civil, Bâtiments & Travaux Publics",
        "Génie Financier",
    ):
        assert program_name in page_nine_text
    assert "2 ANNÉES PRÉPARATOIRES POUR GC" in page_nine_text
    assert "3 années Cycle d’ingénieur Génie Civil" in page_nine_text


def _install_fake_search(monkeypatch, scroll_points):
    class _Model:
        def encode(self, *_args, **_kwargs):
            return _Vector()

    client = Mock()
    client.query_points.return_value.points = [
        _point(
            "detail-18",
            {
                "source": "Brochure-EMSI.pdf", "page": 18,
                "chunk_index": 0, "content": "Pourquoi choisir Génie Civil & BTP ?",
            },
            score=0.95,
        )
    ]
    client.scroll.return_value = (scroll_points, None)
    monkeypatch.setattr(retriever, "get_embedding_model", lambda: _Model())
    monkeypatch.setattr(retriever, "get_compute_device", lambda: "cpu")
    monkeypatch.setattr(retriever, "QdrantClient", Mock(return_value=client))
    return client


def test_exhaustive_retrieval_recovers_catalog_chunk_from_existing_qdrant_payloads(monkeypatch):
    catalog = _point(
        "b70accbb-6adc-5040-bcb2-7a12bb0d834e",
        {
            "source": "Brochure-EMSI.pdf", "page": 9,
            "chunk_index": 0, "content": CATALOG_TEXT,
        },
    )
    client = _install_fake_search(monkeypatch, [catalog])

    documents = retriever.search_documents(QUESTION, limit=10)

    assert any(
        item["id"] == catalog.id and item["page"] == 9
        and item["chunk_index"] == 0 and item["catalog_evidence"]
        for item in documents
    )
    client.scroll.assert_called_once_with(
        collection_name="emsi_text", limit=256,
        with_payload=True, with_vectors=False,
    )
    from app.rag.conversation import select_relevant_documents
    from app.services.groq_service import build_context_with_references

    selected = select_relevant_documents(
        documents, limit=8, preserve_catalog_evidence=True
    )
    context, references = build_context_with_references(
        selected, max_documents=8, max_chars_per_document=1200
    )
    for program_name in (
        "Ingénierie Informatique & Réseaux",
        "Ingénierie des Automatismes & Informatique Industrielle",
        "Génie Industriel",
        "Génie Électrique & Systèmes Intelligents",
        "Génie Civil, Bâtiments & Travaux Publics",
        "Génie Financier",
    ):
        assert program_name in context
    assert any(reference["page"] == 9 for reference in references.values())


def test_non_exhaustive_search_does_not_scan_qdrant_payloads(monkeypatch):
    client = _install_fake_search(monkeypatch, [])

    documents = retriever.search_documents(
        "Comment est organisée la vie étudiante ?", limit=8
    )

    assert len(documents) == 1
    client.scroll.assert_not_called()


def test_specific_duration_search_supplements_matching_catalog_chunks(monkeypatch):
    catalog_chunks = [
        _point("catalog-c0", {
            "source": "Brochure-EMSI.pdf", "page": 9, "chunk_index": 0,
            "content": (
                "Génie Civil, Bâtiments & Travaux Publics (GC). "
                "2 années préparatoires pour GC. "
                "3 années cycle d'ingénieur Génie Civil, Bâtiments & Travaux Publics. "
                "Options : Construction durable."
            ),
        }),
        _point("catalog-c1", {
            "source": "Brochure-EMSI.pdf", "page": 9, "chunk_index": 1,
            "content": (
                "3 années cycle d'ingénieur Génie Civil, Bâtiments & Travaux Publics. "
                "Options : Gestion de projets."
            ),
        }),
    ]
    client = _install_fake_search(monkeypatch, catalog_chunks)

    documents = retriever.search_documents(
        "Quelle est la durée de la formation en Génie Civil ?", limit=8
    )

    assert client.scroll.call_count == 1
    retained = [item for item in documents if item.get("page") == 9]
    assert retained
    assert all(item["catalog_evidence"] for item in retained)
    assert all(item["duration_catalog_bonus"] == 0.18 for item in retained)


@pytest.mark.skipif(
    os.getenv("EMSI_RUN_QDRANT_RAG_INTEGRATION") != "1",
    reason="Opt-in: nécessite Qdrant et une recherche BGE-M3 soumise au garde-fou RAM.",
)
def test_live_qdrant_rag_context_contains_all_page_nine_programs():
    from app.main import _compute_rag_answer
    from app.services.groq_service import build_context_with_references

    _answer, sources, selected = _compute_rag_answer(
        QUESTION, False, QUESTION, return_evidence=True
    )
    context, references = build_context_with_references(
        selected, max_documents=8, max_chars_per_document=1200
    )

    assert any(
        document.get("page") == 9 and document.get("catalog_evidence")
        for document in selected
    )
    for program_name in (
        "Ingénierie Informatique & Réseaux",
        "Ingénierie des Automatismes & Informatique Industrielle",
        "Génie Industriel",
        "Génie Électrique & Systèmes Intelligents",
        "Génie Civil, Bâtiments & Travaux Publics",
        "Génie Financier",
    ):
        assert program_name in context
    assert any(source["page"] == 9 for source in sources)
    assert any(reference["page"] == 9 for reference in references.values())
