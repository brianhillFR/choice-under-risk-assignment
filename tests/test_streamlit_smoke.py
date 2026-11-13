from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest


class StreamlitSmokeTest(unittest.TestCase):
    def test_email_page_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = os.environ.get("RISK_APP_DATA_DIR")
            os.environ["RISK_APP_DATA_DIR"] = directory
            st.cache_resource.clear()
            try:
                app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"))
                app.run(timeout=20)
                self.assertFalse(app.exception)
                self.assertIn("Please enter your HEC e-mail address", [item.label for item in app.text_input])
                self.assertIn("Next", [item.label for item in app.button])
            finally:
                if previous is None:
                    os.environ.pop("RISK_APP_DATA_DIR", None)
                else:
                    os.environ["RISK_APP_DATA_DIR"] = previous

    def test_new_participant_can_confirm_first_answer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous_data = os.environ.get("RISK_APP_DATA_DIR")
            previous_mode = os.environ.get("LLM_MODE")
            os.environ["RISK_APP_DATA_DIR"] = directory
            os.environ["LLM_MODE"] = "demo"
            st.cache_resource.clear()
            try:
                app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"))
                app.run(timeout=20)
                app.text_input[0].set_value("new.student@hec.edu")
                app.button[0].click()
                app.run(timeout=20)

                labels = [item.label for item in app.text_input]
                app.text_input[labels.index("Please enter your surname")].set_value("Student")
                app.button[0].click()
                app.run(timeout=20)

                self.assertEqual(app.radio[0].options, [
                    "Utility function", "Probability weighting function", "Both", "Neither"
                ])
                self.assertIn("ii. Explain fully", app.text_area[0].label)
                app.radio[0].set_value("Both")
                app.text_area[0].set_value("Both components help explain the behavior in this case.")
                app.button[0].click()
                app.run(timeout=20)

                self.assertIn("Confirm", app.radio[0].options)
                app.button[0].click()
                app.run(timeout=20)

                self.assertEqual(app.radio[0].options, [
                    "Utility function", "Probability weighting function", "Both", "Neither"
                ])
                self.assertIn("ii. Explain fully", app.text_area[0].label)
                response_paths = list((Path(directory) / "responses").glob("*.json"))
                self.assertEqual(len(response_paths), 1)
                response = response_paths[0].read_text(encoding="utf-8")
                self.assertIn('"item_index": 1', response)
                self.assertNotIn("new.student@hec.edu", response)
                self.assertFalse((Path(directory) / "answers.csv").exists())
            finally:
                if previous_data is None:
                    os.environ.pop("RISK_APP_DATA_DIR", None)
                else:
                    os.environ["RISK_APP_DATA_DIR"] = previous_data
                if previous_mode is None:
                    os.environ.pop("LLM_MODE", None)
                else:
                    os.environ["LLM_MODE"] = previous_mode

    def test_summary_can_be_modified_before_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous_data = os.environ.get("RISK_APP_DATA_DIR")
            previous_mode = os.environ.get("LLM_MODE")
            os.environ["RISK_APP_DATA_DIR"] = directory
            os.environ["LLM_MODE"] = "demo"
            st.cache_resource.clear()
            try:
                app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"))
                app.run(timeout=20)
                app.text_input[0].set_value("modify.test@hec.edu")
                app.button[0].click()
                app.run(timeout=20)
                labels = [item.label for item in app.text_input]
                app.text_input[labels.index("Please enter your surname")].set_value("Modifier")
                app.button[0].click()
                app.run(timeout=20)
                app.radio[0].set_value("Neither")
                app.text_area[0].set_value(
                    "Expected Utility can accommodate the behavior without a special component."
                )
                app.button[0].click()
                app.run(timeout=20)

                app.radio[0].set_value("Modify")
                app.run(timeout=20)
                self.assertEqual(app.text_area[0].label, "Edit the bullet points")
                app.text_area[0].set_value("- My corrected summary")
                app.button[0].click()
                app.run(timeout=20)

                response_path = next((Path(directory) / "responses").glob("*.json"))
                response = response_path.read_text(encoding="utf-8")
                self.assertIn("My corrected summary", response)
                self.assertIn('"summary_modified": true', response)
                self.assertIn('"llm_provider": "demo"', response)
            finally:
                if previous_data is None:
                    os.environ.pop("RISK_APP_DATA_DIR", None)
                else:
                    os.environ["RISK_APP_DATA_DIR"] = previous_data
                if previous_mode is None:
                    os.environ.pop("LLM_MODE", None)
                else:
                    os.environ["LLM_MODE"] = previous_mode


if __name__ == "__main__":
    unittest.main()

