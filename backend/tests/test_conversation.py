import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.conversation import (
    MAX_HISTORY_MESSAGES,
    build_retrieval_query,
    find_explicit_campus_names,
    has_campus_offering_evidence,
    is_campus_enumeration_question,
    is_follow_up,
    normalize_history,
    select_relevant_documents,
)


def test_history_is_limited_to_five_exchange_messages_and_char_budget():
    history = []
    for index in range(7):
        history.extend([
            {"role": "user", "content": f"Question {index}"},
            {"role": "assistant", "content": f"Réponse {index}"},
        ])
    normalized = normalize_history(history)
    assert len(normalized) == MAX_HISTORY_MESSAGES == 10
    assert normalized[0]["content"] == "Question 2"
    assert normalized[-1]["content"] == "Réponse 6"
    assert sum(len(turn["content"]) for turn in normalized) <= 4000


def test_follow_up_query_uses_previous_user_topic_but_not_assistant_claims():
    history = [
        {"role": "user", "content": "Quels sont les campus EMSI ?"},
        {"role": "assistant", "content": "Rabat, Casablanca et un fait non vérifié."},
    ]
    assert is_follow_up("Et celui de Rabat ?")
    query = build_retrieval_query("Et celui de Rabat ?", history)
    assert query == "Informations sur le campus EMSI de Rabat dans la brochure"
    assert "fait non vérifié" not in query


def test_standalone_question_does_not_expand_from_history():
    history = [{"role": "user", "content": "Quels sont les campus EMSI ?"}]
    assert build_retrieval_query("Quelle est la procédure d'inscription ?", history) == (
        "Quelle est la procédure d'inscription ?"
    )
    assert build_retrieval_query("Quels campus EMSI ?", history) == (
        "Noms et villes des campus EMSI explicitement mentionnés dans la brochure : "
        "Quels campus EMSI ?"
    )


def test_campus_list_query_and_name_extraction_require_explicit_passage_names():
    question = "Quels sont les campus EMSI mentionnés dans la brochure ?"
    assert is_campus_enumeration_question(question)
    assert build_retrieval_query(question, []) == (
        "Noms et villes des campus EMSI explicitement mentionnés dans la brochure : "
        + question
    )
    assert find_explicit_campus_names(
        "TANGER CASABLANCA RABAT MARRAKECH FES UN RÉSEAU DE 19 CAMPUS"
    ) == ["Tanger", "Casablanca", "Rabat", "Marrakech", "Fès"]
    assert find_explicit_campus_names("L'EMSI dispose d'un réseau de 19 campus.") == []
    assert not is_campus_enumeration_question("Quels sont les sites de Rabat et leurs adresses ?")
    assert build_retrieval_query("Quels sont les sites de Rabat et leurs adresses ?", []) == (
        "Quels sont les sites de Rabat et leurs adresses ?"
    )


def test_follow_up_references_celui_y_and_la_bas_resolve_to_rabat():
    after_campus_answer = [
        {"role": "user", "content": "Quels sont les campus EMSI ?"},
        {"role": "assistant", "content": "Le campus EMSI de Rabat est mentionné."},
    ]
    assert build_retrieval_query("Et celui de Rabat ?", after_campus_answer) == (
        "Informations sur le campus EMSI de Rabat dans la brochure"
    )
    assert build_retrieval_query("Quelles formations y sont proposées ?", after_campus_answer) == (
        "Formations proposées spécifiquement sur le campus EMSI de Rabat"
    )
    assert build_retrieval_query("Et là-bas ?", after_campus_answer) == (
        "Informations sur le campus EMSI de Rabat dans la brochure"
    )


def test_campus_reference_survives_follow_up_answer_without_campus_word():
    history = [
        {"role": "user", "content": "Quels sont les campus EMSI ?"},
        {"role": "assistant", "content": "Rabat, Casablanca, Marrakech, Casa Anfa, Fès et Tanger."},
        {"role": "user", "content": "Et celui de Rabat ?"},
        {"role": "assistant", "content": "L'association chronologique n'est pas vérifiable."},
    ]
    assert build_retrieval_query("Quelles formations y sont proposées ?", history) == (
        "Formations proposées spécifiquement sur le campus EMSI de Rabat"
    )


def test_follow_up_after_topic_change_does_not_reuse_stale_campus():
    history = [
        {"role": "user", "content": "Quels campus EMSI ?"},
        {"role": "assistant", "content": "Le campus EMSI de Rabat."},
        {"role": "user", "content": "Quels sont les frais d'inscription ?"},
        {"role": "assistant", "content": "La brochure décrit la procédure d'inscription."},
    ]
    assert build_retrieval_query("Quelles formations y sont proposées ?", history) == (
        "Quels sont les frais d'inscription — Quelles formations y sont proposées ?"
    )


def test_relevance_filter_drops_weak_ranked_tail_and_preserves_metadata():
    docs = [
        {"source": "Brochure-EMSI.pdf", "page": 4, "score": 0.8, "content": "Rabat"},
        {"source": "Brochure-EMSI.pdf", "page": 5, "score": 0.6, "content": "Casablanca"},
        {"source": "Brochure-EMSI.pdf", "page": 30, "score": 0.2, "content": "hors sujet"},
    ]
    selected = select_relevant_documents(docs, limit=4)
    assert [doc["page"] for doc in selected] == [4, 5]
    assert selected[0]["source"] == "Brochure-EMSI.pdf"
    assert select_relevant_documents([{"score": 0.19}], limit=4) == []


def test_exhaustive_list_preserves_relevant_catalog_passage_below_relative_cutoff():
    detailed_page = {"page": 16, "score": 0.90, "content": "Détails d'une filière."}
    catalog_page = {
        "page": 9, "chunk_index": 0, "score": 0.26,
        "catalog_evidence": True, "content": "Structure des cursus et intitulés des filières.",
    }
    documents = [detailed_page, catalog_page]

    assert select_relevant_documents(documents, limit=4) == [detailed_page]
    selected = select_relevant_documents(
        documents, limit=4, preserve_catalog_evidence=True
    )
    assert detailed_page in selected
    assert catalog_page in selected
    below_minimum = {**catalog_page, "score": 0.19}
    assert select_relevant_documents(
        [detailed_page, below_minimum],
        limit=4,
        preserve_catalog_evidence=True,
    ) == [detailed_page]


def test_general_program_list_is_not_evidence_for_rabat_offerings():
    general_programs = {
        "content": "L'EMSI propose plusieurs formations en génie informatique et industriel."
    }
    disconnected_mentions = {
        "content": (
            "Le campus EMSI de Rabat accueille des étudiants. "
            "L'EMSI propose plusieurs formations en génie informatique."
        )
    }
    explicit_local_programs = {
        "content": "Le campus EMSI de Rabat propose des formations en génie informatique."
    }
    assert not has_campus_offering_evidence([general_programs], "Rabat")
    assert not has_campus_offering_evidence([disconnected_mentions], "Rabat")
    assert has_campus_offering_evidence([explicit_local_programs], "Rabat")

    for location in ("Casa Anfa", "Casablanca", "Marrakech", "Rabat", "Fès", "Tanger"):
        document = {
            "content": f"Le campus EMSI de {location} propose la formation Génie Civil."
        }
        assert has_campus_offering_evidence([document], location)

    reverse_form = {
        "content": "Les formations en Génie Civil sont proposées au campus EMSI de Casablanca."
    }
    fronted_form = {
        "content": "Au campus de Fès, la filière Génie Civil est dispensée."
    }
    disconnected_clause = {
        "content": (
            "Le campus EMSI de Rabat accueille les étudiants, "
            "et l'EMSI propose des formations en Génie Civil."
        )
    }
    assert has_campus_offering_evidence([reverse_form], "Casablanca")
    assert has_campus_offering_evidence([fronted_form], "Fès")
    assert not has_campus_offering_evidence([disconnected_clause], "Rabat")
