import json
import os
from pathlib import Path
import sys

from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.unavailable_answer import (
    has_explicit_admission_criteria,
    unavailable_answer,
)
from app.services.groq_service import generate_answer
from unittest.mock import Mock, patch


def test_admission_absence_is_specific_and_does_not_invent_requirements():
    answer = unavailable_answer("Quelles sont les conditions d'admission à l'EMSI ?")

    assert "Je n'ai pas trouvé les conditions d'admission" in answer
    assert "diplômes requis" in answer
    assert "modalités de sélection" in answer
    assert "documents à fournir" in answer
    assert "contacter le service des admissions de l'EMSI" in answer
    assert "filières et les formations présentées dans la brochure" in answer
    assert "baccalauréat requis" not in answer


def test_other_missing_information_uses_a_question_specific_fallback():
    fees_answer = unavailable_answer("Quels sont les frais de scolarité ?")
    director_answer = unavailable_answer("Quel est le nom du directeur général ?")

    assert "Je n'ai pas trouvé les frais de scolarité" in fees_answer
    assert fees_answer != director_answer


def test_admission_testimonial_and_apply_call_are_not_eligibility_evidence():
    assert not has_explicit_admission_criteria([
        {"content": "J'ai rejoint l'EMSI par admission directe."},
        {"content": "CANDIDATEZ ICI. Deux années préparatoires pour IIR."},
        {"content": "Conditions d'admission : détails communiqués sur demande."},
    ])


def test_explicit_baccalaureate_criterion_is_recognized():
    for criterion in (
        "Les candidats doivent être titulaires du baccalauréat.",
        "Être titulaire du baccalauréat est une condition d'accès.",
        "Diplôme requis : licence.",
        "L'admission est soumise à un concours.",
    ):
        assert has_explicit_admission_criteria([{"content": criterion}]), criterion


def test_fastapi_json_response_preserves_french_unicode_characters():
    expected = "é è ê à ç œ"
    response = JSONResponse(content={"answer": expected})

    assert json.loads(response.body.decode("utf-8")) == {"answer": expected}


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "mock-model"})
@patch("app.services.groq_service.httpx.post")
def test_cited_groq_answer_is_not_replaced_by_admission_fallback(mock_post):
    response = Mock(status_code=200)
    response.json.return_value = {
        "choices": [{
            "message": {"content": "Le passage indique le diplôme requis [[REF:A]]."},
            "finish_reason": "stop",
        }]
    }
    mock_post.return_value = response
    documents = [{
        "source": "Brochure-EMSI.pdf",
        "page": 12,
        "content": "Le passage indique le diplôme requis.",
    }]

    answer = generate_answer(
        "Quelles sont les conditions d'admission ?", documents
    )

    assert answer == (
        "Le passage indique le diplôme requis (Brochure-EMSI.pdf, page 12)."
    )
