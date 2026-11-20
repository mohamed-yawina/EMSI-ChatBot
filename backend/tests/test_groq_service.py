import os
import re
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.groq_service import GroqAPIError, build_context_with_references, build_prompt, generate_answer, resolve_answer_references


DOCS = [{"source": "Brochure EMSI", "page": 4, "content": "Campus à Casablanca."}]


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"})
@patch("app.services.groq_service.httpx.post")
def test_sends_only_question_and_retrieved_context(mock_post, caplog):
    response = Mock(status_code=200)
    response.json.return_value = {
        "choices": [{"message": {"content": "Casablanca [[REF:A]]."}, "finish_reason": "stop"}]
    }
    mock_post.return_value = response

    assert generate_answer("Où ?", DOCS) == "Casablanca (Brochure EMSI, page 4)."
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["model"] == "openai/gpt-oss-20b"
    assert kwargs["json"]["temperature"] == 0.5
    assert kwargs["json"]["max_completion_tokens"] == 1024
    assert kwargs["json"]["reasoning_effort"] == "low"
    assert "Campus à Casablanca." in kwargs["json"]["messages"][0]["content"]
    assert "Page PDF réelle : 4" in kwargs["json"]["messages"][0]["content"]
    assert "[PASSAGE A]" in kwargs["json"]["messages"][0]["content"]
    assert kwargs["json"]["messages"][1]["content"] == "Où ?"
    assert kwargs["timeout"].connect == 5.0
    assert kwargs["timeout"].read == 60.0
    assert "test-key" not in caplog.text


def test_prompt_requires_cited_program_lists_without_claiming_unproven_completeness():
    prompt = build_prompt(
        "Quelles sont toutes les filières EMSI ?",
        "[PASSAGE A] Génie Civil [[REF:A]]",
    )
    assert "énumère les intitulés explicitement présents" in prompt
    assert "Ne présente pas les passages récupérés comme une liste complète" in prompt
    assert "distingue les filières des options" in prompt


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"})
@patch("app.services.groq_service.httpx.post")
def test_exhaustive_program_context_separates_titles_prerequisites_and_options(mock_post):
    documents = [
        {
            "source": "Brochure-EMSI.pdf",
            "page": 9,
            "content": (
                "INTITULÉ : Architecture des systèmes (AS)\n"
                "INTITULÉ : Réseaux et sécurité (RS)\n"
                "PRÉREQUIS : 2 années préparatoires pour AS, RS\n"
                "CYCLE : 3 années d'ingénieur pour les deux cursus\n"
                "OPTIONS : Cloud et cybersécurité"
            ),
        },
        {
            "source": "Brochure-EMSI.pdf",
            "page": 10,
            "content": (
                "INTITULÉ : Génie civil et infrastructures (GCI)\n"
                "PRÉREQUIS : 2 années préparatoires pour GCI\n"
                "OPTIONS : Construction durable"
            ),
        },
    ]
    response = Mock(status_code=200)
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    "- Architecture des systèmes [[REF:A]]\n"
                    "- Réseaux et sécurité [[REF:A]]\n"
                    "- Génie civil et infrastructures [[REF:B]]"
                )
            },
            "finish_reason": "stop",
        }]
    }
    mock_post.return_value = response

    answer = generate_answer("Quelles sont toutes les filières du document ?", documents)

    assert "Architecture des systèmes (Brochure-EMSI.pdf, page 9)" in answer
    assert "Réseaux et sécurité (Brochure-EMSI.pdf, page 9)" in answer
    assert "Génie civil et infrastructures (Brochure-EMSI.pdf, page 10)" in answer
    system_prompt = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "un intitulé indépendant par puce" in system_prompt
    assert "ne devient pas une parenthèse ni une liste d'alias du titre voisin" in system_prompt
    assert "Sépare les noms de programmes des durées, années préparatoires, prérequis et options" in system_prompt
    assert "INTITULÉ : Architecture des systèmes (AS)\nINTITULÉ : Réseaux et sécurité (RS)" in system_prompt
    assert "2 années préparatoires pour AS, RS" in system_prompt
    assert "OPTIONS : Cloud et cybersécurité" in system_prompt
    assert mock_post.call_args.kwargs["json"]["max_completion_tokens"] == 1024


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"})
@patch("app.services.groq_service.httpx.post")
def test_structured_catalog_repairs_incomplete_duplicate_program_list(mock_post):
    catalog = (
        "GÉNIE CIVIL, BÂTIMENTS & TRAVAUX PUBLICS (GC) GÉNIE FINANCIER (GF) "
        "3 années Cycle d’ingénieur Ingénierie Informatique & Réseaux "
        "2 ANNÉES PRÉPARATOIRES POUR IIR, IAII, GI, GESI "
        "2 ANNÉES PRÉPARATOIRES POUR GC 2 ANNÉES PRÉPARATOIRES POUR GF "
        "3 années Cycle d’ingénieur Ingénierie des Automatismes & Informatique Industrielle "
        "3 années Cycle d’ingénieur Génie Industriel "
        "3 années Cycle d’ingénieur Génie Électrique & Systèmes Intelligents "
        "3 années Cycle d’ingénieur Génie Civil, Bâtiments & Travaux Publics "
        "3 années Cycle d’ingénieur Génie Financier Option 1 Actuariat et Finance. "
        "INGÉNIERIE INFORMATIQUE & RÉSEAUX (IIR) "
        "INGÉNIERIE DES AUTOMATISMES & INFORMATIQUE INDUSTRIELLE (IAII) "
        "GÉNIE INDUSTRIEL (GI) GÉNIE ÉLECTRIQUE & SYSTÈMES INTELLIGENTS (GESI)"
    )
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {
        "content": (
            "- Ingénierie Informatique & Réseaux (IIR, IAII, GI, GESI) [[REF:A]]; "
            "- Génie Industriel [[REF:A]]; - Génie Civil & BTP [[REF:A]]; "
            "- Génie Civil, Bâtiments & Travaux Publics [[REF:A]]; "
            "- Génie Financier [[REF:A]]"
        )
    }, "finish_reason": "stop"}]}
    mock_post.return_value = response
    documents = [{
        "source": "Brochure-EMSI.pdf", "page": 9,
        "content": catalog, "chunk_index": 0,
    }]

    answer = generate_answer("Quelles sont toutes les filières proposées par l'EMSI ?", documents)

    expected = (
        "Ingénierie Informatique & Réseaux",
        "Ingénierie des Automatismes & Informatique Industrielle",
        "Génie Industriel",
        "Génie Électrique & Systèmes Intelligents",
        "Génie Civil, Bâtiments & Travaux Publics",
        "Génie Financier",
    )
    for title in expected:
        assert title in answer
    assert answer.count("Génie Civil") == 1
    assert all(acronym in answer for acronym in ("IIR", "IAII", "GI", "GESI", "GC", "GF"))
    assert answer.count("Brochure-EMSI.pdf, page 9") >= len(expected)


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"})
@patch("app.services.groq_service.httpx.post")
def test_linked_program_durations_are_added_with_verified_citation(mock_post):
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {
        "content": "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
    }, "finish_reason": "stop"}]}
    mock_post.return_value = response
    documents = [{
        "source": "Brochure-EMSI.pdf", "page": 9, "chunk_index": 0,
        "content": (
            "GÉNIE CIVIL, BÂTIMENTS & TRAVAUX PUBLICS (GC). "
            "2 années préparatoires pour GC. "
            "3 années Cycle d’ingénieur Génie Civil, Bâtiments & Travaux Publics."
        ),
    }]

    answer = generate_answer(
        "Quelle est la durée de la formation en Génie Civil ?", documents
    )

    assert "2 années préparatoires" in answer
    assert "3 années de cycle ingénieur" in answer
    assert "5 années au total" in answer
    assert "Brochure-EMSI.pdf, page 9" in answer


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"})
@patch("app.services.groq_service.httpx.post")
def test_unlinked_program_durations_are_not_added(mock_post):
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {
        "content": "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
    }, "finish_reason": "stop"}]}
    mock_post.return_value = response
    documents = [{
        "source": "Brochure-EMSI.pdf", "page": 9,
        "content": (
            "2 années préparatoires pour IIR. "
            "3 années Cycle d’ingénieur Génie Civil, Bâtiments & Travaux Publics (GC)."
        ),
    }]

    answer = generate_answer(
        "Quelle est la durée de la formation en Génie Civil ?", documents
    )

    assert answer == "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."


@pytest.mark.parametrize("status,expected", [(401, "Authentification"), (429, "Quota")])
@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "mock-model"})
@patch("app.services.groq_service.httpx.post")
def test_http_auth_and_quota_errors(mock_post, status, expected):
    mock_post.return_value = Mock(status_code=status)
    with pytest.raises(GroqAPIError, match=re.escape(expected)):
        generate_answer("Question", DOCS)


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("timeout", "Délai d'attente"),
        ("server", "Erreur HTTP Groq (500)"),
    ],
)
@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"})
@patch("app.services.groq_service.httpx.post")
def test_timeout_and_http_failures_are_clear(mock_post, failure, expected):
    if failure == "timeout":
        import httpx
        mock_post.side_effect = httpx.ReadTimeout("simulated timeout")
    else:
        mock_post.return_value = Mock(status_code=500)
    with pytest.raises(GroqAPIError, match=re.escape(expected)):
        generate_answer("Question", DOCS)


@patch.dict(os.environ, {"GROQ_API_KEY": "", "GROQ_MODEL": "mock-model"})
@patch("app.services.groq_service.httpx.post")
def test_missing_key_does_not_make_request(mock_post):
    with pytest.raises(GroqAPIError, match="GROQ_API_KEY"):
        generate_answer("Question", DOCS)
    mock_post.assert_not_called()


def test_empty_documents_need_no_api_key():
    assert generate_answer("Question", []) == (
        "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
    )


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"})
@patch("app.services.groq_service.httpx.post")
def test_token_limit_is_distinguished_and_diagnosed(mock_post, caplog):
    response = Mock(status_code=200)
    response.json.return_value = {
        "choices": [{
            "message": {"content": None, "reasoning": "private reasoning must not be logged"},
            "finish_reason": "length",
        }],
        "usage": {
            "prompt_tokens": 300,
            "completion_tokens": 1024,
            "completion_tokens_details": {"reasoning_tokens": 1024},
        },
    }
    mock_post.return_value = response

    with pytest.raises(GroqAPIError, match="max_completion_tokens"):
        generate_answer("Question", DOCS)

    assert "finish_reason=length" in caplog.text
    assert "reasoning_tokens=1024" in caplog.text
    assert "private reasoning" not in caplog.text
    assert "test-key" not in caplog.text


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"})
@patch("app.services.groq_service.httpx.post")
def test_empty_content_without_token_limit_is_distinguished(mock_post, caplog):
    response = Mock(status_code=200)
    response.json.return_value = {
        "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 300, "completion_tokens": 12},
    }
    mock_post.return_value = response

    with pytest.raises(GroqAPIError, match="contenu vide sans atteindre"):
        generate_answer("Question", DOCS)

    assert "Contenu Groq vide" in caplog.text
    assert "finish_reason=stop" in caplog.text


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "openai/gpt-oss-20b"})
@patch("app.services.groq_service.httpx.post")
def test_complete_campus_list_passages_reach_groq(mock_post):
    documents = [
        {
            "source": "Brochure EMSI",
            "page": 5,
            "content": "2025 ouverture nouveau campus à Casa Anfa; 2023 ouverture EMSI Fès; 2019 ouverture EMSI Tanger.",
        },
        {
            "source": "Brochure EMSI",
            "page": 5,
            "content": "Texte de présentation institutionnelle.",
        },
        {
            "source": "Brochure EMSI",
            "page": 6,
            "content": "Présentation du réseau Honoris United Universities.",
        },
        {
            "source": "Brochure EMSI",
            "page": 4,
            "content": "1996 ouverture EMSI Rabat; 1986 création EMSI Casablanca; 2004 ouverture EMSI Marrakech.",
        },
    ]
    response = Mock(status_code=200)
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": "Les lieux explicitement cités sont Rabat [[REF:D]], Casablanca [[REF:D]], Marrakech [[REF:D]], Casa Anfa [[REF:A]], Fès [[REF:A]] et Tanger [[REF:A]]."
            }
        }]
    }
    mock_post.return_value = response

    answer = generate_answer(
        "Quels campus EMSI sont mentionnés dans la brochure ?", documents
    )

    for city in ("Rabat", "Casablanca", "Marrakech", "Casa Anfa", "Fès", "Tanger"):
        assert city in answer
    assert "(Brochure EMSI, page 4)" in answer and "(Brochure EMSI, page 5)" in answer
    system_prompt = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "Page PDF réelle : 4" in system_prompt and "Page PDF réelle : 5" in system_prompt
    assert "EMSI Rabat" in system_prompt
    assert "EMSI Casablanca" in system_prompt
    assert "EMSI Marrakech" in system_prompt
    assert "Casa Anfa" in system_prompt and "EMSI Fès" in system_prompt
    assert "EMSI Tanger" in system_prompt
    assert "chaque élément distinct explicitement" in system_prompt


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "mock-model"})
@patch("app.services.groq_service.httpx.post")
def test_campus_total_alone_is_not_returned_as_a_name_list(mock_post):
    response = Mock(status_code=200)
    response.json.return_value = {
        "choices": [{
            "message": {"content": "La brochure mentionne 19 campus [[REF:A]]."},
            "finish_reason": "stop",
        }]
    }
    mock_post.return_value = response
    documents = [{
        "source": "Brochure-EMSI.pdf",
        "page": 5,
        "content": "Présents dans tout le territoire avec 19 campus.",
    }]

    answer = generate_answer("Quels sont les campus EMSI ?", documents)

    assert answer == (
        "La brochure annonce 19 campus au total, mais les passages consultés "
        "ne donnent pas leurs noms. (Brochure-EMSI.pdf, page 5)"
    )
    assert "Casa Anfa" not in answer
    assert "Tanger" not in answer
    prompt = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "Un nombre total de campus ne remplace jamais la liste" in prompt


def test_passage_ordinal_is_not_pdf_page_and_bad_refs_are_rejected():
    context, references = build_context_with_references([
        {"source": "Brochure-EMSI.pdf", "page": 39, "content": "Rabat."},
        {"source": "Brochure-EMSI.pdf", "page": 4, "content": "Casablanca."},
    ])
    assert "[PASSAGE A]" in context and "Page PDF réelle : 39" in context
    assert "[PASSAGE B]" in context and "Page PDF réelle : 4" in context
    answer = resolve_answer_references("Rabat [[REF:A]], Casablanca [[REF:B]].", references)
    assert answer == "Rabat (Brochure-EMSI.pdf, page 39), Casablanca (Brochure-EMSI.pdf, page 4)."
    assert "non vérifiée" in resolve_answer_references("Rabat (page 2).", references)
    assert "non vérifiée" in resolve_answer_references("Rabat [[REF:Z]].", references)


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "mock-model"})
@patch("app.services.groq_service.httpx.post")
def test_ambiguous_timeline_year_is_withheld(mock_post):
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {
        "content": "Casa Anfa a ouvert en 2023 [[REF:A]]."
    }, "finish_reason": "stop"}]}
    mock_post.return_value = response
    docs = [{"source": "Brochure-EMSI.pdf", "page": 5,
             "content": "2025 ouverture Casa Anfa; 2023 ouverture EMSI Fès; 2019 ouverture EMSI Tanger."}]
    answer = generate_answer("Quand Casa Anfa a ouvert ?", docs)
    assert "2023" not in answer
    assert "n'est pas vérifiable" in answer


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "mock-model"})
@patch("app.services.groq_service.httpx.post")
def test_campus_answer_is_not_replaced_by_timeline_warning(mock_post):
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {
        "content": "Le campus EMSI de Rabat est mentionné dans la brochure [[REF:A]]."
    }, "finish_reason": "stop"}]}
    mock_post.return_value = response
    docs = [{"source": "Brochure-EMSI.pdf", "page": 5,
             "content": "2025 ouverture Casa Anfa; 2023 ouverture EMSI Fès; 2019 ouverture EMSI Tanger."}]
    answer = generate_answer("Et celui de Rabat ?", docs)
    assert "campus EMSI de Rabat" in answer
    assert "page 5" in answer
    assert "dates et événements" not in answer


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "mock-model"})
@patch("app.services.groq_service.httpx.post")
def test_unassociated_year_list_does_not_trigger_event_warning(mock_post):
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {
        "content": "La brochure mentionne Rabat et les années 2019 et 2023 [[REF:A]]."
    }, "finish_reason": "stop"}]}
    mock_post.return_value = response
    docs = [{"source": "Brochure-EMSI.pdf", "page": 5,
             "content": "2025 ouverture Casa Anfa; 2023 ouverture EMSI Fès; 2019 ouverture EMSI Tanger."}]
    answer = generate_answer("Quels lieux et années sont écrits ?", docs)
    assert "Rabat" in answer
    assert "2019" in answer and "2023" in answer
    assert "dates et événements" not in answer


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "mock-model"})
@patch("app.services.groq_service.httpx.post")
def test_unknown_answer_does_not_gain_a_citation(mock_post):
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {
        "content": "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
    }, "finish_reason": "stop"}]}
    mock_post.return_value = response
    answer = generate_answer("Quel est le nom du directeur ?", DOCS)
    assert answer == "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "mock-model"})
@patch("app.services.groq_service.httpx.post")
def test_uncited_claim_is_replaced_with_unverified_response(mock_post):
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {
        "content": "Le campus est à Casablanca."
    }, "finish_reason": "stop"}]}
    mock_post.return_value = response
    answer = generate_answer("Où est le campus ?", DOCS)
    assert answer == "Les documents consultés ne permettent pas de vérifier cette réponse (référence non vérifiée)."


def test_conversation_history_is_context_not_documentary_evidence():
    prompt = build_prompt(
        "Et celui de Rabat ?",
        "[PASSAGE A] Source PDF : Brochure EMSI\nPage PDF réelle : 8\nTexte : Campus de Rabat.",
        [
            {"role": "user", "content": "Quels sont les campus EMSI ?"},
            {"role": "assistant", "content": "Casablanca et Rabat [[REF:A]]."},
        ],
    )
    assert "HISTORIQUE CONVERSATIONNEL" in prompt
    assert "PAS UNE SOURCE DOCUMENTAIRE" in prompt
    assert "sans demander son histoire ni une date" in prompt
    assert "QUESTION :\nEt celui de Rabat ?" in prompt
    assert "[[REF:A]]" in prompt
    assert "Je n'ai pas trouvé cette information dans les documents EMSI disponibles." in prompt
