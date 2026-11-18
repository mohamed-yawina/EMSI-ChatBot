import unittest

from app.rag.ranking_policy import (
    campus_list_bonus,
    should_apply_program_topic_bonus,
)


class ProgramTopicBonusPolicyTests(unittest.TestCase):
    def test_historical_filiere_announcement_does_not_receive_bonus(self):
        question = "Quelles filières sont proposées?"
        historical = "2016 démarrage de la filière génie financier; 2024 adhésion au réseau CDIO"
        self.assertFalse(should_apply_program_topic_bonus(question, historical))

    def test_current_curriculum_description_keeps_bonus_eligibility(self):
        question = "Quelles formations sont proposées?"
        current = "Structure du cursus: formation progressive et modules d ingénierie"
        self.assertTrue(should_apply_program_topic_bonus(question, current))

    def test_unrelated_question_gets_no_program_bonus(self):
        self.assertFalse(
            should_apply_program_topic_bonus(
                "Quels sont les campus?",
                "Formation d ingénieur proposée depuis 1986",
            )
        )

    def test_campus_enumeration_rewards_named_passage_not_total_count(self):
        question = "Noms et villes des campus EMSI explicitement mentionnés"
        names_passage = (
            "TANGER CASABLANCA RABAT MARRAKECH FES, un réseau de 19 campus."
        )
        total_only_passage = "L'EMSI accueille des étudiants sur 19 campus."

        assert campus_list_bonus(question, names_passage) == 0.18
        assert campus_list_bonus(question, total_only_passage) == 0.0
        assert campus_list_bonus("Quelles formations propose l'EMSI ?", names_passage) == 0.0


if __name__ == "__main__":
    unittest.main()
