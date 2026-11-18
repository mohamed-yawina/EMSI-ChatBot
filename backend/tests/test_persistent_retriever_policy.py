import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

from app.rag import isolated_retriever
from app.rag.isolated_retriever import _force_cpu_device, should_use_persistent


class PersistentRetrieverPolicyTests(unittest.TestCase):
    def setUp(self):
        self.previous_state = isolated_retriever._persistent_state
        isolated_retriever._persistent_state = "cold"

    def tearDown(self):
        isolated_retriever._persistent_state = self.previous_state

    def test_ram_threshold(self):
        self.assertTrue(should_use_persistent(4096))
        self.assertFalse(should_use_persistent(4095))
        self.assertFalse(should_use_persistent(None))

    def test_cpu_override_is_restored(self):
        original = os.environ.get("EMSI_AI_DEVICE")
        os.environ["EMSI_AI_DEVICE"] = "cuda"
        try:
            with _force_cpu_device():
                self.assertEqual(os.environ["EMSI_AI_DEVICE"], "cpu")
            self.assertEqual(os.environ["EMSI_AI_DEVICE"], "cuda")
        finally:
            if original is None:
                os.environ.pop("EMSI_AI_DEVICE", None)
            else:
                os.environ["EMSI_AI_DEVICE"] = original

    def test_low_ram_fallback_rechecks_before_disabling_persistent_mode(self):
        fallback_result = [{"page": 1}]
        persistent_result = [{"page": 2}]
        fake_retriever = types.ModuleType("app.rag.retriever")
        fake_retriever.search_documents = Mock(return_value=persistent_result)

        with (
            patch.object(
                isolated_retriever,
                "_available_ram_mb",
                side_effect=[1024, 8192],
            ),
            patch.object(
                isolated_retriever,
                "_search_documents_subprocess",
                return_value=fallback_result,
            ) as fallback,
            patch.dict(sys.modules, {"app.rag.retriever": fake_retriever}),
        ):
            self.assertEqual(
                isolated_retriever.search_documents_isolated("question"),
                fallback_result,
            )
            self.assertEqual(isolated_retriever._persistent_state, "cold")
            self.assertEqual(
                isolated_retriever.search_documents_isolated("question"),
                persistent_result,
            )

        fallback.assert_called_once_with("question", 3)
        fake_retriever.search_documents.assert_called_once_with("question", limit=3)
        self.assertEqual(isolated_retriever._persistent_state, "ready")

    def test_release_persistent_model_clears_cache_and_rechecks_ram_next_time(self):
        fake_retriever = types.ModuleType("app.rag.retriever")
        fake_retriever.get_embedding_model = Mock()
        fake_retriever.get_embedding_model.cache_clear = Mock()
        isolated_retriever._persistent_state = "ready"

        with patch.dict(sys.modules, {"app.rag.retriever": fake_retriever}):
            isolated_retriever.release_persistent_model()

        fake_retriever.get_embedding_model.cache_clear.assert_called_once_with()
        self.assertEqual(isolated_retriever._persistent_state, "cold")


if __name__ == "__main__":
    unittest.main()
