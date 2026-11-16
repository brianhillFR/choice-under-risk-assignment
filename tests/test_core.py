from __future__ import annotations

import csv
import json
import tempfile
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
    FULL_CASE_QUESTION,
    PROVIDED_ANSWERS,
    REVIEW_CASE_INTRO,
    REVIEW_QUESTIONS_INTRO,
    REVIEW_RESPONSE_INTRO,
    build_case_items,
    format_full_review_answer,
    format_full_student_answer,
    full_review_question,
)
from risk_app.llm import SummaryClient, build_prompt
from risk_app.storage import JsonCsvRepository, valid_subject_id
from risk_app.workflow import assign_cases, valid_code, valid_email


class WorkflowTests(unittest.TestCase):
    def test_four_renumbered_cases_and_two_case_assignment(self) -> None:
        self.assertEqual(sorted(CASES), [1, 2, 3, 4])
        assigned = assign_cases("TEST-2048")
        self.assertEqual(len(assigned), 2)
        self.assertEqual(len(set(assigned)), 2)
        self.assertEqual(assigned, assign_cases("TEST-2048"))

    def test_case_sequence(self) -> None:
        items = build_case_items([2, 4])
        self.assertEqual([item.case_number for item in items], [2, 4])
        self.assertEqual([item.question_number for item in items], [1, 2])
        self.assertEqual([item.question_type for item in items], ["original", "review"])
        self.assertEqual(COMPONENT_OPTIONS, (
            "Utility function", "Probability weighting function", "Both", "Neither"
        ))

    def test_validation(self) -> None:
        self.assertTrue(valid_email("student@hec.edu"))
        self.assertFalse(valid_email("not-an-email"))
        self.assertTrue(valid_code("ABCD-1234"))
        self.assertFalse(valid_code("x"))


class SummaryTests(unittest.TestCase):
    def test_demo_summary_is_bulleted(self) -> None:
        full_answer = format_full_student_answer(
            "Utility function",
            "The utility function explains the pattern because outcomes are reference-dependent.",
        )
        result = SummaryClient(mode="demo").summarize(
            case_text=CASES[1],
            question_text=FULL_CASE_QUESTION,
            student_answer=full_answer,
        )
        self.assertTrue(result.text.startswith("- "))
        self.assertEqual(result.provider, "demo")

    def test_llm_prompt_contains_full_question_and_full_student_answer(self) -> None:
        full_answer = format_full_student_answer(
            "Both",
            "The utility function explains one part. Probability weighting explains the other.",
        )
        prompt = build_prompt(
            case_text=CASES[2],
            question_text=FULL_CASE_QUESTION,
            student_answer=full_answer,
        )
        self.assertIn(COMPONENT_QUESTION, prompt)
        self.assertIn(EXPLANATION_QUESTION, prompt)
        self.assertIn("i. Both", prompt)
        self.assertIn(
            "ii. The utility function explains one part. Probability weighting explains the other.",
            prompt,
        )

    def test_review_prompt_contains_provided_response_and_full_student_answer(self) -> None:
        student_answer = format_full_review_answer(
            ASSESSMENT_OPTIONS[1],
            "The response should replace its account of the 50% probability.",
        )
        prompt = build_prompt(
            case_text=CASES[2],
            question_text=full_review_question(2),
            student_answer=student_answer,
        )
        self.assertIn(ASSESSMENT_QUESTION, prompt)
        self.assertIn(CORRECTION_QUESTION, prompt)
        self.assertIn(PROVIDED_ANSWERS[2], prompt)
        self.assertIn(REVIEW_CASE_INTRO.format(case_number=2), prompt)
        self.assertIn(REVIEW_QUESTIONS_INTRO, prompt)
        self.assertIn(REVIEW_RESPONSE_INTRO, prompt)
        self.assertLess(prompt.index(REVIEW_QUESTIONS_INTRO), prompt.index(PROVIDED_ANSWERS[2]))
        self.assertIn(f"Assessment: {ASSESSMENT_OPTIONS[1]}", prompt)
        self.assertIn("Explanation and correction: The response should replace", prompt)


class StorageTests(unittest.TestCase):
    def test_json_is_authoritative_and_csv_is_created_only_at_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = JsonCsvRepository(directory)
            participant = repo.create_participant(
                email="Student@hec.edu",
                name="Student",
            )
            self.assertTrue(valid_subject_id(participant.subject_id))
            found = repo.find_participant_by_email("student@hec.edu")
            self.assertIsNotNone(found)
            self.assertEqual(found.subject_id, participant.subject_id)

            with (Path(directory) / "subjects.csv").open(encoding="utf-8-sig") as handle:
                identity_rows = list(csv.DictReader(handle))
            self.assertEqual(identity_rows, [{
                "SubjectId": participant.subject_id,
                "name": "Student",
                "email": "student@hec.edu",
            }])

            response_paths = list((Path(directory) / "responses").glob("*.json"))
            self.assertEqual(len(response_paths), 1)
            state = json.loads(response_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(state["subject_id"], participant.subject_id)
            self.assertNotIn("name", json.dumps(state))
            self.assertNotIn("student@hec.edu", json.dumps(state))
            self.assertFalse((Path(directory) / "answers.csv").exists())

            first_case, second_case = state["assignment"]["assigned_cases"]

            repo.save_pending_response(
                subject_id=participant.subject_id,
                case_number=first_case,
                question_type="original",
                component_answer="Both",
                explanation_answer="Both components matter for this case.",
            )
            restarted = JsonCsvRepository(directory)
            pending = restarted.get_progress(participant.subject_id)
            self.assertEqual(pending.stage, "summary_review")
            self.assertEqual(pending.item_index, 0)
            self.assertEqual(pending.pending_answer["component_answer"], "Both")
            self.assertEqual(
                pending.pending_answer["explanation_answer"],
                "Both components matter for this case.",
            )
            self.assertFalse((Path(directory) / "answers.csv").exists())

            restarted.save_generated_summary(
                subject_id=participant.subject_id,
                case_number=first_case,
                llm_summary="- Both components matter for this case.",
                llm_provider="demo",
                llm_model="demo",
            )
            restarted_again = JsonCsvRepository(directory)
            self.assertEqual(
                restarted_again.get_progress(participant.subject_id).pending_answer["llm_summary"],
                "- Both components matter for this case.",
            )
            restarted_again.confirm_pending_response(
                subject_id=participant.subject_id,
                final_summary="- Both components matter.",
            )
            self.assertEqual(repo.get_progress(participant.subject_id).item_index, 1)
            self.assertFalse((Path(directory) / "answers.csv").exists())

            saved = repo.get_response_state(participant.subject_id)
            self.assertEqual(saved["answers"][0]["component_answer"], "Both")
            self.assertEqual(saved["answers"][0]["case_number"], first_case)

            repo.save_pending_response(
                subject_id=participant.subject_id,
                case_number=second_case,
                question_type="review",
                provided_answer=PROVIDED_ANSWERS[second_case],
                assessment_answer=ASSESSMENT_OPTIONS[1],
                correction_answer="The supplied response needs a more precise explanation.",
            )
            repo.save_generated_summary(
                subject_id=participant.subject_id,
                case_number=second_case,
                llm_summary="- Expected Utility explains this case.",
                llm_provider="demo",
                llm_model="demo",
            )
            repo.confirm_pending_response(
                subject_id=participant.subject_id,
                final_summary="- The supplied response needs a more precise explanation.",
            )
            with (Path(directory) / "answers.csv").open(encoding="utf-8-sig") as handle:
                answer_rows = list(csv.DictReader(handle))
            self.assertEqual(len(answer_rows), 1)
            self.assertEqual(answer_rows[0]["SubjectId"], participant.subject_id)
            self.assertEqual(answer_rows[0]["question_1_case_number"], str(first_case))
            self.assertEqual(answer_rows[0]["question_1_question_type"], "original")
            self.assertEqual(answer_rows[0]["question_2_case_number"], str(second_case))
            self.assertEqual(answer_rows[0]["question_2_question_type"], "review")
            self.assertEqual(
                answer_rows[0]["question_2_assessment_answer"], ASSESSMENT_OPTIONS[1]
            )
            self.assertIn(
                "more precise", answer_rows[0]["question_2_correction_answer"]
            )
            self.assertNotIn("name", answer_rows[0])
            self.assertNotIn("email", answer_rows[0])
            self.assertTrue(repo.get_response_state(participant.subject_id)["csv_synced"])

            repo.finalize_completed(participant.subject_id)
            with (Path(directory) / "answers.csv").open(encoding="utf-8-sig") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 1)


if __name__ == "__main__":
    unittest.main()

