from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_app.content import (
    ASSESSMENT_OPTIONS,
    ASSESSMENT_QUESTION,
    CASES,
    COMPONENT_OPTIONS,
    COMPONENT_QUESTION,
    CORRECTION_QUESTION,
    EXPLANATION_QUESTION,
    PROVIDED_ANSWERS,
)


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

    def test_review_wording_matches_qsf_and_reference_assignment(self) -> None:
        self.assertEqual(
            ASSESSMENT_QUESTION,
            "How well do you think that this response answers the question concerning the case?",
        )
        self.assertEqual(
            ASSESSMENT_OPTIONS,
            (
                "Totally right: it would get full marks",
                "There is something along the right lines in the response, but requires some addition or modification",
                "Wrong",
            ),
        )
        self.assertEqual(
            CORRECTION_QUESTION,
            "Explain your answer, specifying, if relevant, what needs to be added, corrected or changed to obtain a perfect response.",
        )
        self.assertEqual(sorted(PROVIDED_ANSWERS), [1, 2, 3, 4])
        self.assertTrue(all(answer.startswith("i. ") for answer in PROVIDED_ANSWERS.values()))


if __name__ == "__main__":
    unittest.main()

