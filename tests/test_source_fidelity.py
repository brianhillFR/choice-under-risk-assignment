from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_app.content import CASES, COMPONENT_OPTIONS, COMPONENT_QUESTION, EXPLANATION_QUESTION


ROOT = Path(__file__).parents[1]


class SourceFidelityTests(unittest.TestCase):
    def test_cases_match_source_word_document_after_removal_and_renumbering(self) -> None:
        source = json.loads((ROOT / "references" / "word_content.json").read_text(encoding="utf-8"))
        paragraphs = {item["index"]: item["text"] for item in source["paragraphs"]}
        expected = {
            1: paragraphs[28],
            2: paragraphs[30],
            3: paragraphs[32],
            4: paragraphs[34] + "\n\n" + "\n".join(f"- {paragraphs[index]}" for index in range(35, 41)),
        }
        self.assertEqual(CASES, expected)

    def test_questions_and_options_match_active_qualtrics_questions(self) -> None:
        source = json.loads((ROOT / "references" / "qualtrics_active.json").read_text(encoding="utf-8"))
        questions = {item["qid"]: item for item in source["active_questions"]}
        self.assertIn(COMPONENT_QUESTION, questions["QID2"]["question_text"])
        self.assertEqual(EXPLANATION_QUESTION, questions["QID594"]["question_text"])
        choice_order = [str(value) for value in questions["QID2"]["choice_order"]]
        source_options = tuple(questions["QID2"]["choices"][key] for key in choice_order)
        self.assertEqual(COMPONENT_OPTIONS, source_options)


if __name__ == "__main__":
    unittest.main()

