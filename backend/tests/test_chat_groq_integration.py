import logging
import sys
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.main import app, get_cached_rag_answer
from app.rag import isolated_retriever
from app.services import groq_service


DOCUMENTS = [
    {
        "source": "Brochure EMSI",
        "page": 4,
        "score": 0.91,
        "content": "Le campus EMSI de Casablanca propose plusieurs formations.",
    },
    {
        "source": "Brochure EMSI",
        "page": 8,
        "score": 0.84,
        "content": "Le campus de Rabat accueille également des étudiants.",
    },
]


def setup_test(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "integration-test-secret")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    get_cached_rag_answer.cache_clear()
    monkeypatch.setattr(
        isolated_retriever,
        "search_documents_isolated",
        Mock(return_value=DOCUMENTS),
    )
    return TestClient(app)


def teardown_test():
    get_cached_rag_answer.cache_clear()


def test_api_chat_uses_retrieved_documents_and_groq(monkeypatch):
    client = setup_test(monkeypatch)
    response_from_groq = Mock(status_code=200)
    response_from_groq.json.return_value = {
        "choices": [{"message": {"content": "Les campus cités sont Casablanca [[REF:A]] et Rabat [[REF:B]]."}}]
    }
    groq_post = Mock(return_value=response_from_groq)
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)

    try:
        response = client.post(
            "/api/chat",
            json={
                "question": "  Quels campus sont cités ?  ",
                "use_llm": True,
                "include_images": False,
            },
        )
    finally:
        teardown_test()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "explicitement retrouvés" in response.content.decode("utf-8")
    body = response.json()
    assert set(body) == {"answer", "sources", "images"}
    assert body["answer"] == (
        "Les noms de campus explicitement retrouvés dans les passages consultés sont : "
        "Casablanca (Brochure EMSI, page 4); Rabat (Brochure EMSI, page 8)."
    )
    assert body["sources"] == [
        {"source": "Brochure EMSI", "page": 4, "score": 0.91},
        {"source": "Brochure EMSI", "page": 8, "score": 0.84},
    ]
    assert body["images"] == []

    isolated_retriever.search_documents_isolated.assert_called_once_with(
        "Noms et villes des campus EMSI explicitement mentionnés dans la brochure : "
        "Quels campus sont cités ?",
        limit=8,
    )
    groq_post.assert_called_once()
    _, request = groq_post.call_args
    assert request["json"]["model"] == "openai/gpt-oss-20b"
    assert request["json"]["messages"][1]["content"] == "Quels campus sont cités ?"
    context = request["json"]["messages"][0]["content"]
    assert "Le campus EMSI de Casablanca propose plusieurs formations." in context
    assert "Le campus de Rabat accueille également des étudiants." in context
    assert "Page PDF réelle : 4" in context and "Page PDF réelle : 8" in context
    assert "[PASSAGE A]" in context and "[PASSAGE B]" in context


def test_campus_list_enumerates_source_names_and_separates_total_with_cache(monkeypatch):
    client = setup_test(monkeypatch)
    documents = [
        {
            "source": "Brochure-EMSI.pdf",
            "page": 2,
            "score": 0.90,
            "content": (
                "TANGER CASABLANCA RABAT MARRAKECH FES "
                "UN RÉSEAU DE 19 CAMPUS, TOUJOURS PLUS PROCHE DE VOUS"
            ),
        },
        {
            "source": "Brochure-EMSI.pdf",
            "page": 5,
            "score": 0.88,
            "content": (
                "2025 ouverture nouveau campus à CASA ANFA. "
                "La brochure annonce un réseau de 19 campus au Maroc."
            ),
        },
    ]
    search = Mock(return_value=documents)
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", search)
    groq_response = Mock(status_code=200)
    groq_response.json.return_value = {
        "choices": [{
            "message": {"content": "La brochure annonce 19 campus [[REF:B]]."},
            "finish_reason": "stop",
        }]
    }
    groq_post = Mock(return_value=groq_response)
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)
    question = "Quels sont les campus EMSI mentionnés dans la brochure ?"

    try:
        first = client.post("/api/chat", json={
            "question": question,
            "use_llm": True,
            "include_images": False,
        })
        repeated = client.post("/api/chat", json={
            "question": question,
            "use_llm": True,
            "include_images": False,
        })
        cache_info = get_cached_rag_answer.cache_info()
    finally:
        teardown_test()

    expected_answer = (
        "Les noms de campus explicitement retrouvés dans les passages consultés sont : "
        "Tanger, Casablanca, Rabat, Marrakech, Fès (Brochure-EMSI.pdf, page 2); "
        "Casa Anfa (Brochure-EMSI.pdf, page 5). "
        "La brochure annonce séparément 19 campus au total ; les passages consultés "
        "ne confirment pas que les noms retrouvés constituent la liste complète. "
        "(Brochure-EMSI.pdf, page 2)"
    )
    assert first.status_code == repeated.status_code == 200
    assert first.json()["answer"] == repeated.json()["answer"] == expected_answer
    assert first.json()["sources"] == repeated.json()["sources"] == [
        {"source": "Brochure-EMSI.pdf", "page": 2, "score": 0.90},
        {"source": "Brochure-EMSI.pdf", "page": 5, "score": 0.88},
    ]
    assert search.call_count == 1
    search.assert_called_once_with(
        "Noms et villes des campus EMSI explicitement mentionnés dans la brochure : "
        + question,
        limit=8,
    )
    assert groq_post.call_count == 1
    assert cache_info.hits == 1
    assert cache_info.misses == 1


def test_rabat_site_follow_up_keeps_branch_names_addresses_and_page_39(monkeypatch):
    client = setup_test(monkeypatch)
    rabat_document = {
        "source": "Brochure-EMSI.pdf",
        "page": 39,
        "score": 0.92,
        "content": (
            "Rabat Agdal 1, Imm 52 Av. Omar Ben Khattab; Agdal 2, angle Oqbah; "
            "Souissi, angle rues Zerhoun, Ejoukak et Ait Brahim Souissi; "
            "Centre 1, 49 rue Patrice Lumumba; Centre 2, rue Moulay Abdalhafid, Hassan; "
            "Bouregreg, 13 bis rue Abdelmoumen; Hassan, angle Av. Abou Inane et "
            "rue Haj Mohamed Rifai."
        ),
    }
    monkeypatch.setattr(
        isolated_retriever,
        "search_documents_isolated",
        Mock(return_value=[rabat_document]),
    )
    groq_response = Mock(status_code=200)
    groq_response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    "Les sept sites EMSI de Rabat sont : Agdal 1, Imm 52, avenue Omar "
                    "Ben Khattab; Agdal 2, angle Oqbah; Souissi, angle rues Zerhoun, "
                    "Ejoukak et Ait Brahim; Centre 1, 49 rue Patrice Lumumba; "
                    "Centre 2, rue Moulay Abdalhafid; Bouregreg, 13 bis rue Abdelmoumen; "
                    "Hassan, angle avenue Abou Inane et rue Haj Mohamed Rifai [[REF:A]]."
                )
            },
            "finish_reason": "stop",
        }]
    }
    groq_post = Mock(return_value=groq_response)
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)
    history = [
        {"role": "user", "content": "Quels sont les campus EMSI ?"},
        {"role": "assistant", "content": "Rabat fait partie des villes mentionnées."},
    ]

    try:
        response = client.post("/api/chat", json={
            "question": "Quels sont les sites de Rabat et leurs adresses ?",
            "use_llm": True,
            "include_images": False,
            "history": history,
        })
    finally:
        teardown_test()

    assert response.status_code == 200
    assert response.json()["answer"] == (
        "Les sept sites EMSI de Rabat sont : Agdal 1, Imm 52, avenue Omar Ben Khattab; "
        "Agdal 2, angle Oqbah; Souissi, angle rues Zerhoun, Ejoukak et Ait Brahim; "
        "Centre 1, 49 rue Patrice Lumumba; Centre 2, rue Moulay Abdalhafid; "
        "Bouregreg, 13 bis rue Abdelmoumen; Hassan, angle avenue Abou Inane et "
        "rue Haj Mohamed Rifai (Brochure-EMSI.pdf, page 39)."
    )
    assert response.json()["sources"] == [
        {"source": "Brochure-EMSI.pdf", "page": 39, "score": 0.92}
    ]
    isolated_retriever.search_documents_isolated.assert_called_once_with(
        "Informations sur le campus EMSI de Rabat dans la brochure",
        limit=8,
    )
    groq_post.assert_called_once()


def test_api_chat_groq_auth_error_does_not_expose_key(monkeypatch, caplog):
    client = setup_test(monkeypatch)
    groq_post = Mock(return_value=Mock(status_code=401))
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)

    try:
        with caplog.at_level(logging.INFO):
            response = client.post(
                "/api/chat",
                json={
                    "question": "Quels campus sont cités ?",
                    "use_llm": True,
                    "include_images": False,
                },
            )
    finally:
        teardown_test()

    assert response.status_code == 503
    assert "Authentification Groq refusée" in response.json()["detail"]
    assert "integration-test-secret" not in response.text
    assert "integration-test-secret" not in caplog.text
    groq_post.assert_called_once()


def test_qdrant_retriever_failure_returns_sanitized_api_error(monkeypatch):
    client = setup_test(monkeypatch)
    internal_detail = "simulated Qdrant connection failure"
    monkeypatch.setattr(
        isolated_retriever,
        "search_documents_isolated",
        Mock(side_effect=RuntimeError(internal_detail)),
    )

    try:
        response = client.post(
            "/api/chat",
            json={"question": "Question de démonstration", "use_llm": False},
        )
    finally:
        teardown_test()

    assert response.status_code == 500
    assert response.json() == {"detail": "Erreur interne pendant le traitement RAG."}
    assert internal_detail not in response.text


def test_api_chat_omits_uncited_and_unverified_sources(monkeypatch):
    client = setup_test(monkeypatch)
    response_from_groq = Mock(status_code=200)
    response_from_groq.json.return_value = {
        "choices": [{"message": {"content": "Rabat (page 2), selon la brochure."}}]
    }
    monkeypatch.setattr(groq_service.httpx, "post", Mock(return_value=response_from_groq))
    try:
        response = client.post("/api/chat", json={
            "question": "Où se trouvent les campus ?", "use_llm": True, "include_images": False,
        })
    finally:
        teardown_test()
    assert response.status_code == 200
    body = response.json()
    assert "non vérifiée" in body["answer"]
    assert body["sources"] == []
    assert body["images"] == []


def test_follow_up_uses_request_history_only_for_retrieval_and_prompt(monkeypatch):
    client = setup_test(monkeypatch)
    response_from_groq = Mock(status_code=200)
    response_from_groq.json.return_value = {
        "choices": [{"message": {"content": "Le campus de Rabat [[REF:B]]."}, "finish_reason": "stop"}]
    }
    groq_post = Mock(return_value=response_from_groq)
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)

    histories = [
        [
            {"role": "user", "content": "Quels sont les campus EMSI ?"},
            {"role": "assistant", "content": "Casablanca, Rabat et Marrakech."},
        ],
        [
            {"role": "user", "content": "Quelles formations existe-t-il ?"},
            {"role": "assistant", "content": "Formations non vérifiées."},
        ],
    ]
    try:
        answers = [client.post("/api/chat", json={
            "question": "Et celui de Rabat ?",
            "use_llm": True,
            "include_images": False,
            "history": history,
        }) for history in histories]
        assert get_cached_rag_answer.cache_info().misses == 0
    finally:
        teardown_test()

    assert all(response.status_code == 200 for response in answers)
    assert all(response.json()["answer"] == "Le campus de Rabat (Brochure EMSI, page 8)." for response in answers)
    assert all(response.json()["sources"] == [
        {"source": "Brochure EMSI", "page": 8, "score": 0.84}
    ] for response in answers)
    calls = isolated_retriever.search_documents_isolated.call_args_list
    assert calls[0].args == ("Informations sur le campus EMSI de Rabat dans la brochure",)
    assert calls[1].args == ("Informations sur le campus EMSI de Rabat dans la brochure",)
    prompts = [call.kwargs["json"]["messages"][0]["content"] for call in groq_post.call_args_list]
    assert all(call.kwargs["json"]["messages"][1]["content"] == "Et celui de Rabat ?" for call in groq_post.call_args_list)
    assert "Casablanca, Rabat et Marrakech." in prompts[0]
    assert "Formations non vérifiées." in prompts[1]
    assert all("PAS UNE SOURCE DOCUMENTAIRE" in prompt for prompt in prompts)


def test_three_turn_campus_follow_up_keeps_scope_and_does_not_invent_local_offerings(monkeypatch, caplog):
    client = setup_test(monkeypatch)
    original_compute = main._compute_rag_answer
    monkeypatch.setattr(
        main,
        "_compute_rag_answer",
        Mock(return_value=("RÉPONSE GÉNÉRALE EN CACHE OBSOLÈTE", [])),
    )
    get_cached_rag_answer("Quelles formations y sont proposées ?", True)
    monkeypatch.setattr(main, "_compute_rag_answer", original_compute)

    campus_docs = [{
        "source": "Brochure EMSI", "page": 39, "score": 0.91,
        "content": "Les campus EMSI comprennent Rabat, Casablanca, Marrakech, Casa Anfa, Fès et Tanger.",
    }]
    rabat_docs = [
        {
            "source": "Brochure EMSI", "page": 5, "score": 0.90,
            "content": "2025 ouverture Casa Anfa; 2023 ouverture EMSI Fès; 2019 ouverture EMSI Tanger.",
        },
        {
            "source": "Brochure EMSI", "page": 39, "score": 0.83,
            "content": "Le campus EMSI de Rabat accueille des étudiants.",
        },
    ]
    general_program_docs = [
        {
            "source": "Brochure EMSI", "page": 20, "score": 0.93,
            "content": "L'EMSI propose plusieurs formations en génie informatique et industriel.",
        },
        {
            "source": "Brochure EMSI", "page": 39, "score": 0.82,
            "content": "Le campus EMSI de Rabat accueille des étudiants.",
        },
    ]
    search = Mock(side_effect=[campus_docs, rabat_docs, general_program_docs])
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", search)
    groq_answers = [
        "Rabat, Casablanca, Marrakech, Casa Anfa, Fès et Tanger [[REF:A]].",
        "Le campus EMSI de Rabat est mentionné dans la brochure [[REF:B]].",
        "L'EMSI propose Génie Industriel, Génie Électrique, Génie Civil et Génie Financier [[REF:A]].",
    ]
    def fake_groq_response(*args, **kwargs):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": groq_answers.pop(0)}, "finish_reason": "stop"}]
        }
        return response
    groq_post = Mock(side_effect=fake_groq_response)
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)

    history = []
    turns = [
        ("Quels sont les campus EMSI mentionnés dans la brochure ?",),
        ("Et celui de Rabat ?",),
        ("Quelles formations y sont proposées ?",),
    ]
    responses = []
    try:
        with caplog.at_level(logging.INFO):
            for (question,) in turns:
                response = client.post("/api/chat", json={
                    "question": question,
                    "use_llm": True,
                    "include_images": False,
                    "history": history,
                })
                responses.append(response)
                if response.status_code == 200:
                    history.extend([
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": response.json()["answer"]},
                    ])
            cache_info_after_requests = get_cached_rag_answer.cache_info()
    finally:
        teardown_test()

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert responses[0].json()["answer"] == (
        "Les noms de campus explicitement retrouvés dans les passages consultés sont : "
        "Rabat, Casablanca, Marrakech, Casa Anfa, Fès, Tanger (Brochure EMSI, page 39)."
    )
    assert responses[1].json()["answer"] == (
        "Le campus EMSI de Rabat est mentionné dans la brochure (Brochure EMSI, page 39)."
    )
    assert "dates et événements" not in responses[1].json()["answer"]
    assert responses[1].json()["sources"] == [
        {"source": "Brochure EMSI", "page": 39, "score": 0.83}
    ]
    assert responses[2].json()["answer"] == (
        "Les passages consultés mentionnent des formations EMSI, mais ne permettent pas de confirmer "
        "lesquelles sont spécifiquement proposées sur le campus EMSI de Rabat. "
        "(Brochure EMSI, page 20)."
    )
    assert responses[2].json()["sources"] == [
        {"source": "Brochure EMSI", "page": 20, "score": 0.93}
    ]
    assert [call.args[0] for call in search.call_args_list] == [
        "Noms et villes des campus EMSI explicitement mentionnés dans la brochure : "
        "Quels sont les campus EMSI mentionnés dans la brochure ?",
        "Informations sur le campus EMSI de Rabat dans la brochure",
        "Formations proposées spécifiquement sur le campus EMSI de Rabat",
    ]
    assert groq_post.call_count == 2
    assert groq_answers == [
        "L'EMSI propose Génie Industriel, Génie Électrique, Génie Civil et Génie Financier [[REF:A]]."
    ]
    assert cache_info_after_requests.misses == 2
    assert cache_info_after_requests.hits == 0
    assert "cache_policy=bypass-history" in caplog.text
    assert "campus_offering_target=Rabat" in caplog.text
    assert "preuves_locales=0" in caplog.text
    assert "passages_generaux=1" in caplog.text
    assert "groq_bypassed=true" in caplog.text
    assert "RÉPONSE GÉNÉRALE EN CACHE OBSOLÈTE" not in responses[2].json()["answer"]
    assert "Génie Industriel" not in responses[2].json()["answer"]
    assert "Quelles formations y sont proposées ?" not in caplog.text
    second_prompt = groq_post.call_args_list[1].kwargs["json"]["messages"][0]["content"]
    assert "HISTORIQUE CONVERSATIONNEL" in second_prompt
    assert "QUESTION :\nEt celui de Rabat ?" in second_prompt


def test_explicit_campus_offering_is_quoted_with_verified_citation(monkeypatch):
    client = setup_test(monkeypatch)
    local_document = {
        "source": "Brochure-EMSI.pdf", "page": 24, "score": 0.91,
        "content": "Le campus EMSI de Rabat propose la formation Génie Civil.",
    }
    monkeypatch.setattr(
        isolated_retriever, "search_documents_isolated", Mock(return_value=[local_document])
    )
    groq_post = Mock()
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)
    history = [
        {"role": "user", "content": "Quels sont les campus EMSI ?"},
        {"role": "assistant", "content": "Rabat et Casablanca."},
        {"role": "user", "content": "Et celui de Rabat ?"},
        {"role": "assistant", "content": "Le campus EMSI de Rabat est mentionné dans la brochure."},
    ]

    try:
        response = client.post("/api/chat", json={
            "question": "Quelles formations y sont proposées ?",
            "use_llm": True, "include_images": False, "history": history,
        })
    finally:
        teardown_test()

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == (
        "Pour le campus EMSI de Rabat, la brochure indique : "
        "« Le campus EMSI de Rabat propose la formation Génie Civil. » "
        "(Brochure-EMSI.pdf, page 24)."
    )
    assert body["sources"] == [
        {"source": "Brochure-EMSI.pdf", "page": 24, "score": 0.91}
    ]
    assert "Génie Industriel" not in body["answer"]
    groq_post.assert_not_called()


def test_only_campus_confirmed_courses_are_returned_from_partial_list(monkeypatch):
    client = setup_test(monkeypatch)
    documents = [
        {
            "source": "Brochure-EMSI.pdf", "page": 25, "score": 0.92,
            "content": "Sur le campus EMSI de Rabat, les filières Génie Civil et Génie Industriel sont proposées.",
        },
        {
            "source": "Brochure-EMSI.pdf", "page": 26, "score": 0.87,
            "content": "L'EMSI propose aussi les formations Génie Électrique et Génie Financier.",
        },
    ]
    monkeypatch.setattr(
        isolated_retriever, "search_documents_isolated", Mock(return_value=documents)
    )
    groq_post = Mock()
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)

    try:
        response = client.post("/api/chat", json={
            "question": "Quelles formations sont proposées à Rabat ?",
            "use_llm": True, "include_images": False,
        })
    finally:
        teardown_test()

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "Génie Civil et Génie Industriel" in answer
    assert "Génie Électrique" not in answer
    assert "Génie Financier" not in answer
    assert "(Brochure-EMSI.pdf, page 25)" in answer
    assert response.json()["sources"] == [
        {"source": "Brochure-EMSI.pdf", "page": 25, "score": 0.92}
    ]
    groq_post.assert_not_called()


def test_general_emsi_trainings_still_use_groq_after_campus_topic_change(monkeypatch):
    client = setup_test(monkeypatch)
    general_document = {
        "source": "Brochure-EMSI.pdf", "page": 26, "score": 0.94,
        "content": "L'EMSI propose les formations Génie Industriel, Génie Électrique, Génie Civil et Génie Financier.",
    }
    search = Mock(return_value=[general_document])
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", search)
    response_from_groq = Mock(status_code=200)
    response_from_groq.json.return_value = {"choices": [{"message": {
        "content": "L'EMSI propose Génie Industriel, Génie Électrique, Génie Civil et Génie Financier [[REF:A]]."
    }, "finish_reason": "stop"}]}
    groq_post = Mock(return_value=response_from_groq)
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)

    try:
        response = client.post("/api/chat", json={
            "question": "Quelles formations propose l'EMSI ?",
            "use_llm": True, "include_images": False,
            "history": [
                {"role": "user", "content": "Quelles formations propose le campus de Rabat ?"},
                {"role": "assistant", "content": "Le campus de Rabat propose des formations."},
            ],
        })
    finally:
        teardown_test()

    assert response.status_code == 200
    assert "Génie Industriel" in response.json()["answer"]
    assert "Génie Financier" in response.json()["answer"]
    assert response.json()["sources"] == [
        {"source": "Brochure-EMSI.pdf", "page": 26, "score": 0.94}
    ]
    search.assert_called_once_with("Quelles formations propose l'EMSI ?", limit=8)
    groq_post.assert_called_once()


def test_follow_up_switches_from_rabat_to_casablanca(monkeypatch):
    client = setup_test(monkeypatch)
    documents = [
        {
            "source": "Brochure-EMSI.pdf", "page": 24, "score": 0.92,
            "content": "Le campus EMSI de Rabat propose la formation Génie Civil.",
        },
        {
            "source": "Brochure-EMSI.pdf", "page": 31, "score": 0.90,
            "content": "Le campus EMSI de Casablanca propose la formation Génie Financier.",
        },
    ]
    search = Mock(return_value=documents)
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", search)
    groq_post = Mock()
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)
    history = [
        {"role": "user", "content": "Quelles formations propose le campus de Rabat ?"},
        {"role": "assistant", "content": "Génie Civil."},
    ]

    try:
        response = client.post("/api/chat", json={
            "question": "Et quelles formations à Casablanca ?",
            "use_llm": True, "include_images": False, "history": history,
        })
    finally:
        teardown_test()

    assert response.status_code == 200
    assert "campus EMSI de Casablanca" in response.json()["answer"]
    assert "Génie Financier" in response.json()["answer"]
    assert "Génie Civil" not in response.json()["answer"]
    assert response.json()["sources"] == [
        {"source": "Brochure-EMSI.pdf", "page": 31, "score": 0.90}
    ]
    search.assert_called_once_with(
        "Formations proposées spécifiquement sur le campus EMSI de Casablanca", limit=8
    )
    groq_post.assert_not_called()


def test_new_conversation_does_not_reuse_previous_campus_context(monkeypatch):
    client = setup_test(monkeypatch)
    general_document = {
        "source": "Brochure-EMSI.pdf", "page": 26, "score": 0.94,
        "content": "L'EMSI propose la formation Génie Civil.",
    }
    search = Mock(return_value=[general_document])
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", search)
    response_from_groq = Mock(status_code=200)
    response_from_groq.json.return_value = {"choices": [{"message": {
        "content": "La brochure présente la formation Génie Civil [[REF:A]]."
    }, "finish_reason": "stop"}]}
    groq_post = Mock(return_value=response_from_groq)
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)

    try:
        response = client.post("/api/chat", json={
            "question": "Quelles formations y sont proposées ?",
            "use_llm": True, "include_images": False, "history": [],
        })
    finally:
        teardown_test()

    assert response.status_code == 200
    assert response.json()["answer"] == "La brochure présente la formation Génie Civil (Brochure-EMSI.pdf, page 26)."
    search.assert_called_once_with("Quelles formations y sont proposées ?", limit=8)
    groq_post.assert_called_once()


def test_rabat_and_course_terms_in_separate_passages_do_not_prove_local_availability(monkeypatch):
    client = setup_test(monkeypatch)
    unrelated_documents = [
        {
            "source": "Brochure-EMSI.pdf", "page": 32, "score": 0.90,
            "content": "Le campus EMSI de Rabat accueille des étudiants.",
        },
        {
            "source": "Brochure-EMSI.pdf", "page": 33, "score": 0.88,
            "content": "L'EMSI propose la formation Génie Civil.",
        },
    ]
    monkeypatch.setattr(
        isolated_retriever, "search_documents_isolated", Mock(return_value=unrelated_documents)
    )
    groq_post = Mock()
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)

    try:
        response = client.post("/api/chat", json={
            "question": "Quelles formations sont proposées à Rabat ?",
            "use_llm": True, "include_images": False,
        })
    finally:
        teardown_test()

    assert response.status_code == 200
    assert response.json()["answer"] == (
        "Les passages consultés mentionnent des formations EMSI, mais ne permettent pas de confirmer "
        "lesquelles sont spécifiquement proposées sur le campus EMSI de Rabat. "
        "(Brochure-EMSI.pdf, page 33)."
    )
    assert response.json()["sources"] == [
        {"source": "Brochure-EMSI.pdf", "page": 33, "score": 0.88}
    ]
    assert "Génie Civil" not in response.json()["answer"]
    groq_post.assert_not_called()


def test_no_relevant_course_passage_returns_out_of_scope_answer(monkeypatch):
    client = setup_test(monkeypatch)
    search = Mock(return_value=[])
    monkeypatch.setattr(isolated_retriever, "search_documents_isolated", search)
    groq_post = Mock()
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)

    try:
        response = client.post("/api/chat", json={
            "question": "Quelles formations sont proposées à Rabat ?",
            "use_llm": True, "include_images": False,
        })
    finally:
        teardown_test()

    assert response.status_code == 200
    assert response.json()["answer"] == (
        "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
    )
    assert response.json()["sources"] == []
    search.assert_called_once_with("Quelles formations sont proposées à Rabat ?", limit=8)
    groq_post.assert_not_called()


def test_low_relevance_context_returns_exact_out_of_scope_message(monkeypatch):
    client = setup_test(monkeypatch)
    low_score_documents = [{
        "source": "Brochure EMSI", "page": 4, "score": 0.10,
        "content": "Quelques éléments sans rapport avec la demande.",
    }]
    monkeypatch.setattr(
        isolated_retriever,
        "search_documents_isolated",
        Mock(return_value=low_score_documents),
    )
    groq_post = Mock()
    monkeypatch.setattr(groq_service.httpx, "post", groq_post)
    try:
        response = client.post("/api/chat", json={
            "question": "Quel est le temps prévu demain ?",
            "use_llm": True,
            "include_images": False,
        })
    finally:
        teardown_test()
    assert response.status_code == 200
    assert response.json()["answer"] == "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
    assert response.json()["sources"] == []
    groq_post.assert_not_called()
