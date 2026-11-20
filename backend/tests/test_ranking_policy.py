import unittest

from app.rag.ranking_policy import (
    campus_list_bonus,
    repair_common_mojibake,
    should_apply_program_topic_bonus,
)


class ProgramTopicBonusPolicyTests(unittest.TestCase):
    def test_common_brochure_mojibake_is_repaired_without_changing_valid_text(self):
        corrupted = "Pourquoi choisir la fili\u00c3\u00a8re G\u00c3\u00a9nie Industriel ?"
        self.assertEqual(
            repair_common_mojibake(corrupted),
            "Pourquoi choisir la fili\u00e8re G\u00e9nie Industriel ?",
        )
        valid = "Une \u00e9cole d\u2019ing\u00e9nieurs \u00e0 Rabat"
        self.assertEqual(repair_common_mojibake(valid), valid)

    def test_repaired_program_text_keeps_program_bonus_eligibility(self):
        corrupted = "Pourquoi choisir la fili\u00c3\u00a8re G\u00c3\u00a9nie Industriel ?"
        self.assertTrue(
            should_apply_program_topic_bonus(
                "Quelles fili\u00e8res sont propos\u00e9es?", corrupted
            )
        )

    def test_hybrid_lexical_match_sees_accented_program_terms_in_corrupted_payload(self):
        from app.rag.retriever import keyword_score

        score = keyword_score(
            "Quelles fili\u00e8res sont propos\u00e9es?",
            ("Pourquoi choisir la fili\u00c3\u00a8re G\u00c3\u00a9nie Industriel ?"),
        )
        self.assertEqual(score, 1.0)

    def test_historical_filiere_announcement_does_not_receive_bonus(self):
        question = "Quelles filiÃ¨res sont proposÃ©es?"
        historical = "2016 dÃ©marrage de la filiÃ¨re gÃ©nie financier; 2024 adhÃ©sion au rÃ©seau CDIO"
        self.assertFalse(should_apply_program_topic_bonus(question, historical))

    def test_current_curriculum_description_keeps_bonus_eligibility(self):
        question = "Quelles formations sont proposÃ©es?"
        current = "Structure du cursus: formation progressive et modules d ingÃ©nierie"
        self.assertTrue(should_apply_program_topic_bonus(question, current))

    def test_unrelated_question_gets_no_program_bonus(self):
        self.assertFalse(
            should_apply_program_topic_bonus(
                "Quels sont les campus?",
                "Formation d ingÃ©nieur proposÃ©e depuis 1986",
            )
        )

    def test_campus_enumeration_rewards_named_passage_not_total_count(self):
        question = "Noms et villes des campus EMSI explicitement mentionnÃ©s"
        names_passage = (
            "TANGER CASABLANCA RABAT MARRAKECH FES, un rÃ©seau de 19 campus."
        )
        total_only_passage = "L'EMSI accueille des Ã©tudiants sur 19 campus."

        assert campus_list_bonus(question, names_passage) == 0.18
        assert campus_list_bonus(question, total_only_passage) == 0.0
        assert campus_list_bonus("Quelles formations propose l'EMSI ?", names_passage) == 0.0


if __name__ == "__main__":
    unittest.main()
