import unittest

from app.rag.ranking_policy import (
    campus_list_bonus,
    is_exhaustive_program_question,
    program_catalog_bonus,
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

    def test_exhaustive_program_query_promotes_curriculum_catalog_structure(self):
        query = "Quelles sont les filières proposées par l'EMSI ?"
        catalog = (
            "Diplôme d'ingénieur. Ingénierie Informatique & Réseaux. "
            "2 années préparatoires pour IIR, IAII, GI, GESI. "
            "3 années cycle d'ingénieur. Génie Industriel. "
            "3 années cycle d'ingénieur. Génie Civil."
        )
        unrelated = "La vie associative et les activités sportives de l'école."

        assert is_exhaustive_program_question(query)
        assert program_catalog_bonus(query, catalog) == 0.18
        assert program_catalog_bonus(query, unrelated) == 0.0
        assert program_catalog_bonus("Comment fonctionne l'admission ?", catalog) == 0.0

    def test_general_program_list_question_variants_trigger_exhaustive_retrieval(self):
        for question in (
            "Quelles sont toutes les filières de l'EMSI ?",
            "Quelles formations sont proposées ?",
            "Liste les filières disponibles.",
            "Quels sont les cursus de l'EMSI ?",
            "Quelles sont les formations proposees par l'EMSI ?",
        ):
            assert is_exhaustive_program_question(question), question

    def test_specific_program_question_variants_do_not_trigger_exhaustive_retrieval(self):
        for question in (
            "Quelle est la durée de la filière Génie Civil ?",
            "Quels sont les débouchés du Génie Industriel ?",
            "Quels sont les débouchés des formations en Génie Industriel ?",
            "Quelles sont les conditions d'admission en IIR ?",
            "Présente-moi la filière Génie Financier.",
            "Quelle est la duree de la filiere Genie Civil ?",
        ):
            assert not is_exhaustive_program_question(question), question

    def test_specific_program_question_does_not_trigger_exhaustive_retrieval(self):
        assert not is_exhaustive_program_question(
            "Quelle est la durée de la filière Génie Civil ?"
        )

    def test_specific_program_duration_gets_targeted_catalog_retrieval(self):
        from app.rag.ranking_policy import (
            is_program_duration_question,
            program_duration_catalog_bonus,
        )

        question = "Quelle est la durée de la formation en Génie Civil ?"
        catalog = (
            "2 années préparatoires pour GC. "
            "3 années cycle d'ingénieur Génie Civil, Bâtiments & Travaux Publics. "
            "Options en bâtiment durable."
        )
        unrelated = "La brochure décrit les activités étudiantes et sportives."

        assert is_program_duration_question(question)
        assert not is_exhaustive_program_question(question)
        assert program_duration_catalog_bonus(question, catalog) == 0.18
        assert program_duration_catalog_bonus(question, unrelated) == 0.0


if __name__ == "__main__":
    unittest.main()
