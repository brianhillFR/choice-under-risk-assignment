from __future__ import annotations

import csv
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from dropbox.exceptions import ApiError
from dropbox.files import (
    DownloadError,
    FileMetadata,
    LookupError,
    UploadError,
    UploadWriteFailed,
    WriteConflictError,
    WriteError,
)

from risk_app.dropbox_storage import DropboxRepository, StaleResponse
from risk_app.storage import StorageError
from tools import dropbox_oauth


def conflict() -> ApiError:
    return ApiError(
        "request",
        UploadError.path(
            UploadWriteFailed(reason=WriteError.conflict(WriteConflictError.file))
        ),
        None,
        None,
    )


class FakeDropbox:
    def __init__(self) -> None:
        self.files: dict[str, tuple[FileMetadata, bytes]] = {}
        self.counter = 0
        self.fail_csv = False
        self.conflict_once: set[str] = set()

    def files_upload(self, content: bytes, path: str, mode, **kwargs):
        if self.fail_csv and path.endswith("answers.csv"):
            raise ConnectionError("simulated Dropbox outage")
        current = self.files.get(path)
        if mode.is_add() and current:
            raise conflict()
        if path in self.conflict_once:
            self.conflict_once.remove(path)
            raise conflict()
        if mode.is_update() and (
            not current or current[0].rev != mode.get_update()
        ):
            raise conflict()
        self.counter += 1
        metadata = FileMetadata(
            name=path.rsplit("/", 1)[-1],
            id="id:test",
            rev=format(self.counter, "010x"),
            size=len(content),
            client_modified=datetime.now(),
            server_modified=datetime.now(),
            path_lower=path,
        )
        self.files[path] = metadata, content
        return metadata

    def files_download(self, path: str):
        if path not in self.files:
            raise ApiError(
                "request",
                DownloadError.path(LookupError.not_found),
                None,
                None,
            )
        metadata, content = self.files[path]
        return metadata, SimpleNamespace(content=content, close=lambda: None)


class DropboxRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeDropbox()
        self.repo = DropboxRepository(self.client)
        self.participant = self.repo.create_participant(
            email="Student@hec.edu",
            name="Student",
        )

    def _save_case(self, position: int, *, completed: bool) -> None:
        progress = self.repo.get_progress(self.participant.subject_id)
        case_number = progress.assigned_cases[position]
        self.repo.save_confirmed_response(
            subject_id=self.participant.subject_id,
            case_number=case_number,
            component_answer="Both" if position == 0 else "Neither",
            explanation_answer=f"Explanation for saved case {position + 1}.",
            llm_summary=f"- Summary for saved case {position + 1}.",
            final_summary=f"- Summary for saved case {position + 1}.",
            llm_provider="demo",
            llm_model="demo",
            next_item_index=position + 1,
            completed=completed,
        )

    def test_registration_resume_and_completion_only_csv(self) -> None:
        subject_path = "/choice_under_risk_assignment/subjects.csv"
        self.assertIn(subject_path, self.client.files)
        subject_text = self.client.files[subject_path][1].decode("utf-8-sig")
        self.assertIn("student@hec.edu", subject_text)

        response_paths = [path for path in self.client.files if "/responses/" in path]
        self.assertEqual(len(response_paths), 1)
        response_text = self.client.files[response_paths[0]][1].decode("utf-8")
        self.assertNotIn("student@hec.edu", response_text)
        self.assertNotIn('"name"', response_text)

        restarted = DropboxRepository(self.client)
        found = restarted.find_participant_by_email("student@hec.edu")
        self.assertEqual(found, self.participant)

        self._save_case(0, completed=False)
        self.assertNotIn(
            "/choice_under_risk_assignment/answers.csv", self.client.files
        )
        self._save_case(1, completed=True)

        answers = self.client.files[
            "/choice_under_risk_assignment/answers.csv"
        ][1].decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(answers)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["SubjectId"], self.participant.subject_id)
        self.assertNotIn("name", rows[0])
        self.assertNotIn("email", rows[0])
        self.assertTrue(self.repo.get_response_state(self.participant.subject_id)["csv_synced"])

    def test_failed_final_csv_retries_without_duplicate(self) -> None:
        self._save_case(0, completed=False)
        self.client.fail_csv = True
        with self.assertRaises(StorageError):
            self._save_case(1, completed=True)
        state = self.repo.get_response_state(self.participant.subject_id)
        self.assertEqual(state["stage"], "complete")
        self.assertFalse(state["csv_synced"])

        self.client.fail_csv = False
        self.repo.finalize_completed(self.participant.subject_id)
        self.repo.finalize_completed(self.participant.subject_id)
        answers = self.client.files[
            "/choice_under_risk_assignment/answers.csv"
        ][1].decode("utf-8-sig")
        self.assertEqual(len(list(csv.DictReader(io.StringIO(answers)))), 1)

    def test_revision_conflict_does_not_advance_response(self) -> None:
        response_path = next(path for path in self.client.files if "/responses/" in path)
        self.client.conflict_once.add(response_path)
        with self.assertRaises(StaleResponse):
            self._save_case(0, completed=False)
        state = self.repo.get_response_state(self.participant.subject_id)
        self.assertEqual(state["item_index"], 0)
        self.assertEqual(state["answers"], [])

    def test_identity_and_path_validation_fail_closed(self) -> None:
        with self.assertRaises(StorageError):
            DropboxRepository(self.client, root="/")
        with self.assertRaises(StorageError):
            DropboxRepository(self.client, csv_name="../answers.csv")


class DropboxOAuthTests(unittest.TestCase):
    def test_working_hill_flow_requests_scopes_and_accepts_pasted_code(self) -> None:
        output = io.StringIO()
        with (
            patch.object(dropbox_oauth, "input", side_effect=["app-key", "auth-code"]) as entered,
            patch.object(dropbox_oauth, "getpass", return_value="app-secret"),
            patch.object(dropbox_oauth, "DropboxOAuth2FlowNoRedirect") as flow_class,
            redirect_stdout(output),
        ):
            flow = flow_class.return_value
            flow.start.return_value = "https://dropbox.example/authorize"
            flow.finish.return_value = SimpleNamespace(refresh_token="test-refresh-token")
            dropbox_oauth.main()

        flow_class.assert_called_once_with(
            "app-key",
            "app-secret",
            token_access_type="offline",
            scope=[
                "files.content.read",
                "files.content.write",
                "files.metadata.read",
            ],
        )
        self.assertEqual(entered.call_args_list[1].args[0], "\nPaste the authorization code: ")
        flow.finish.assert_called_once_with("auth-code")
        self.assertIn('DROPBOX_REFRESH_TOKEN = "test-refresh-token"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
