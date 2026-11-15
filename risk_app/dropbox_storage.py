from __future__ import annotations

import csv
import io
import json
import re
import secrets
from copy import deepcopy
from functools import lru_cache

from risk_app.storage import (
    ANSWER_FIELDS,
    SUBJECT_FIELDS,
    JsonCsvRepository,
    Participant,
    Progress,
    StorageError,
    email_key,
    setting,
    utc_now,
    valid_subject_id,
)
from risk_app.workflow import assign_cases, normalize_email


RESPONSE_KEY_RE = re.compile(r"[0-9a-f]{64}")


class StaleResponse(StorageError):
    """Dropbox rejected a conditional write because another request won."""


def path_error(error: Exception, tag: str) -> bool:
    """Classify Dropbox SDK tagged errors without masking network failures."""
    union = getattr(error, "error", None)
    if not getattr(union, "is_path", lambda: False)():
        return False
    path = union.get_path()
    path = getattr(path, "reason", path)
    return getattr(path, "is_" + tag, lambda: False)()


@lru_cache(maxsize=1)
def _client(app_key: str, app_secret: str, refresh_token: str):
    import dropbox

    return dropbox.Dropbox(
        app_key=app_key,
        app_secret=app_secret,
        oauth2_refresh_token=refresh_token,
        timeout=20,
        max_retries_on_error=2,
        max_retries_on_rate_limit=1,
    )


def configured_dropbox_repository():
    names = ("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN")
    values = [str(setting(name, "")).strip() for name in names]
    if not all(values):
        raise StorageError(
            "Set DROPBOX_APP_KEY, DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN "
            "in Streamlit secrets."
        )
    return DropboxRepository(
        _client(*values),
        root=str(setting("DROPBOX_ROOT_PATH", "/choice_under_risk_assignment")),
        csv_name=str(setting("DROPBOX_CSV_NAME", "answers.csv")),
        subject_csv_name=str(setting("DROPBOX_SUBJECT_CSV_NAME", "subjects.csv")),
    )


class DropboxRepository:
    """Revision-safe Dropbox persistence with JSON as the authoritative record."""

    def __init__(
        self,
        client,
        root: str = "/choice_under_risk_assignment",
        csv_name: str = "answers.csv",
        subject_csv_name: str = "subjects.csv",
    ) -> None:
        root = "/" + root.strip("/")
        if root == "/" or any(part in {"", ".", ".."} for part in root[1:].split("/")):
            raise StorageError(
                "DROPBOX_ROOT_PATH must name a dedicated folder, such as "
                "/choice_under_risk_assignment."
            )
        if "/" in csv_name or "\\" in csv_name or not csv_name.endswith(".csv"):
            raise StorageError("DROPBOX_CSV_NAME must be a CSV filename.")
        if (
            "/" in subject_csv_name
            or "\\" in subject_csv_name
            or not subject_csv_name.endswith(".csv")
            or subject_csv_name == csv_name
        ):
            raise StorageError(
                "DROPBOX_SUBJECT_CSV_NAME must name a separate CSV file."
            )
        self.client = client
        self.root = root
        self.responses_root = root + "/responses"
        self.email_index_root = root + "/_email_index"
        self.answers_path = root + "/" + csv_name
        self.subjects_path = root + "/" + subject_csv_name

    def _read_json(self, path: str):
        try:
            metadata, response = self.client.files_download(path)
            try:
                payload = json.loads(response.content.decode("utf-8"))
            finally:
                response.close()
        except Exception as error:
            if path_error(error, "not_found"):
                return None
            raise StorageError("Could not read saved data from Dropbox. Please retry.") from error
        if not isinstance(payload, dict):
            raise StorageError("A saved Dropbox JSON file has an invalid format.")
        return metadata, payload

    def _read_csv(self, path: str):
        try:
            metadata, response = self.client.files_download(path)
            try:
                reader = csv.DictReader(
                    io.StringIO(response.content.decode("utf-8-sig"))
                )
                return metadata, list(reader.fieldnames or []), list(reader)
            finally:
                response.close()
        except Exception as error:
            if path_error(error, "not_found"):
                return None, [], []
            raise StorageError("Could not read a saved Dropbox CSV file. Please retry.") from error

    def _upload_bytes(self, path: str, payload: bytes, mode):
        try:
            return self.client.files_upload(
                payload,
                path,
                mode=mode,
                autorename=False,
                strict_conflict=True,
                mute=True,
            )
        except Exception as error:
            if path_error(error, "conflict"):
                raise StaleResponse(
                    "This response was updated in another tab. Reload to continue."
                ) from error
            raise StorageError(
                "Dropbox could not confirm the save. Please retry."
            ) from error

    def _upload_json(self, path: str, payload: dict[str, object], mode):
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return self._upload_bytes(path, encoded, mode)

    def _upload_csv(self, path: str, fields: list[str], rows, mode):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        return self._upload_bytes(path, output.getvalue().encode("utf-8-sig"), mode)

    @staticmethod
    def _validate_subject_rows(header: list[str], rows: list[dict[str, str]]) -> None:
        if header != SUBJECT_FIELDS:
            raise StorageError(
                "subjects.csv must contain SubjectId, name and email columns."
            )
        ids = [row.get("SubjectId", "") for row in rows]
        emails = [normalize_email(row.get("email", "")) for row in rows]
        if any(not valid_subject_id(value) for value in ids) or len(ids) != len(set(ids)):
            raise StorageError("subjects.csv contains an invalid or duplicate SubjectId.")
        if any(not value for value in emails) or len(emails) != len(set(emails)):
            raise StorageError("subjects.csv contains an empty or duplicate email address.")

    def _subject_identity(self, *, email: str | None = None, subject_id: str | None = None):
        metadata, header, rows = self._read_csv(self.subjects_path)
        if metadata is None:
            return None
        self._validate_subject_rows(header, rows)
        matches = [
            row
            for row in rows
            if (email is None or normalize_email(row["email"]) == normalize_email(email))
            and (subject_id is None or row["SubjectId"] == subject_id)
        ]
        if len(matches) > 1:
            raise StorageError("subjects.csv contains duplicate identity records.")
        return matches[0] if matches else None

    def _allocate_subject(self, name: str, email: str) -> tuple[dict[str, str], bool]:
        from dropbox.files import WriteMode

        email = normalize_email(email)
        for _ in range(5):
            metadata, header, rows = self._read_csv(self.subjects_path)
            if metadata is None:
                header, rows = list(SUBJECT_FIELDS), []
            self._validate_subject_rows(header, rows)
            matches = [row for row in rows if normalize_email(row["email"]) == email]
            if matches:
                return matches[0], False
            ids = {row["SubjectId"] for row in rows}
            subject_id = str(secrets.randbelow(90_000_000) + 10_000_000)
            while subject_id in ids:
                subject_id = str(secrets.randbelow(90_000_000) + 10_000_000)
            identity = {"SubjectId": subject_id, "name": name, "email": email}
            rows.append(identity)
            mode = WriteMode.update(metadata.rev) if metadata else WriteMode.add
            try:
                self._upload_csv(self.subjects_path, SUBJECT_FIELDS, rows, mode)
                return identity, True
            except StaleResponse:
                continue
        raise StorageError("Other registrations are updating subjects.csv. Please retry.")

    def _response_path(self, response_key: str) -> str:
        if RESPONSE_KEY_RE.fullmatch(response_key) is None:
            raise StorageError("The saved response reference is invalid.")
        return self.responses_root + "/" + response_key + ".json"

    def _index_path(self, email: str) -> str:
        return self.email_index_root + "/" + email_key(email) + ".json"

    @staticmethod
    def _new_state(subject_id: str) -> dict[str, object]:
        now = utc_now()
        return {
            "subject_id": subject_id,
            "response_id": "R_" + secrets.token_hex(12),
            "assignment": {"assigned_cases": assign_cases(subject_id)},
            "stage": "question",
            "revision": 0,
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
            "item_index": 0,
            "answers": [],
            "pending_answer": None,
            "csv_synced": False,
        }

    def _ensure_registration(self, identity: dict[str, str]):
        from dropbox.files import WriteMode

        index_path = self._index_path(identity["email"])
        indexed = self._read_json(index_path)
        if indexed is None:
            registration = {
                "subject_id": identity["SubjectId"],
                "response_key": secrets.token_hex(32),
            }
            try:
                index_metadata = self._upload_json(index_path, registration, WriteMode.add)
                indexed = index_metadata, registration
            except StaleResponse:
                indexed = self._read_json(index_path)
        if indexed is None:
            raise StorageError("Could not confirm the saved email lookup. Please retry.")
        _, registration = indexed
        if registration.get("subject_id") != identity["SubjectId"]:
            raise StorageError("The saved email lookup conflicts with subjects.csv.")
        response_key = str(registration.get("response_key", ""))
        path = self._response_path(response_key)
        saved = self._read_json(path)
        if saved is None:
            state = self._new_state(identity["SubjectId"])
            try:
                metadata = self._upload_json(path, state, WriteMode.add)
                saved = metadata, state
            except StaleResponse:
                saved = self._read_json(path)
        if saved is None or saved[1].get("subject_id") != identity["SubjectId"]:
            raise StorageError("The saved response for this email could not be recovered.")
        return path, saved[0], saved[1]

    def _response_for_subject(self, subject_id: str):
        identity = self._subject_identity(subject_id=subject_id)
        if identity is None:
            raise KeyError(f"No identity record for subject {subject_id}.")
        return self._ensure_registration(identity)

    def find_participant_by_email(self, email: str) -> Participant | None:
        identity = self._subject_identity(email=normalize_email(email))
        if identity is None:
            return None
        self._ensure_registration(identity)
        return Participant(identity["SubjectId"], identity["name"], identity["email"])

    def find_participant_by_subject_id(self, subject_id: str) -> Participant | None:
        identity = self._subject_identity(subject_id=subject_id)
        if identity is None:
            return None
        return Participant(identity["SubjectId"], identity["name"], identity["email"])

    def create_participant(self, *, email: str, name: str) -> Participant:
        name = name.strip()
        email = normalize_email(email)
        if not name:
            raise ValueError("Please enter your full name.")
        identity, created = self._allocate_subject(name, email)
        self._ensure_registration(identity)
        if not created:
            raise ValueError("This e-mail address is already registered.")
        return Participant(identity["SubjectId"], identity["name"], identity["email"])

    def get_progress(self, subject_id: str) -> Progress:
        _, _, state = self._response_for_subject(subject_id)
        assigned = [int(value) for value in state["assignment"]["assigned_cases"]]
        return Progress(
            subject_id=subject_id,
            assigned_cases=assigned,
            item_index=int(state.get("item_index", 0)),
            completed=state.get("stage") == "complete",
            stage=str(state.get("stage", "question")),
            pending_answer=deepcopy(state.get("pending_answer")),
        )

    def save_pending_response(
        self,
        *,
        subject_id: str,
        case_number: int,
        question_type: str,
        component_answer: str = "",
        explanation_answer: str = "",
        provided_answer: str = "",
        assessment_answer: str = "",
        correction_answer: str = "",
    ) -> None:
        from dropbox.files import WriteMode

        path, metadata, state = self._response_for_subject(subject_id)
        _, current_index = JsonCsvRepository._validate_pending_position(
            state, case_number=case_number, question_type=question_type
        )
        incoming = JsonCsvRepository._pending_payload(
            question_number=current_index + 1,
            question_type=question_type,
            case_number=case_number,
            component_answer=component_answer,
            explanation_answer=explanation_answer,
            provided_answer=provided_answer,
            assessment_answer=assessment_answer,
            correction_answer=correction_answer,
        )
        current = state.get("pending_answer")
        if isinstance(current, dict) and JsonCsvRepository._same_answer(current, incoming):
            return
        now = utc_now()
        updated = deepcopy(state)
        updated["pending_answer"] = dict(
            incoming,
            submitted_at=now,
            llm_summary="",
            llm_provider="",
            llm_model="",
        )
        updated["stage"] = "summary_review"
        updated["updated_at"] = now
        updated["revision"] = int(state.get("revision", 0)) + 1
        self._upload_json(path, updated, WriteMode.update(metadata.rev))

    def save_generated_summary(
        self,
        *,
        subject_id: str,
        case_number: int,
        llm_summary: str,
        llm_provider: str,
        llm_model: str,
    ) -> None:
        from dropbox.files import WriteMode

        llm_summary = llm_summary.strip()
        if not llm_summary:
            raise ValueError("The generated summary cannot be empty.")
        path, metadata, state = self._response_for_subject(subject_id)
        pending = state.get("pending_answer")
        if state.get("stage") != "summary_review" or not isinstance(pending, dict):
            raise StorageError("There is no submitted answer awaiting a summary.")
        if int(pending.get("case_number", -1)) != int(case_number):
            raise StorageError("The summary does not match the saved question.")
        if pending.get("llm_summary"):
            if (
                pending.get("llm_summary") == llm_summary
                and pending.get("llm_provider") == llm_provider
                and pending.get("llm_model") == llm_model
            ):
                return
            raise StorageError("A summary is already saved for this answer.")
        updated = deepcopy(state)
        updated_pending = updated["pending_answer"]
        updated_pending["llm_summary"] = llm_summary
        updated_pending["llm_provider"] = llm_provider
        updated_pending["llm_model"] = llm_model
        updated["updated_at"] = utc_now()
        updated["revision"] = int(state.get("revision", 0)) + 1
        self._upload_json(path, updated, WriteMode.update(metadata.rev))

    def confirm_pending_response(
        self, *, subject_id: str, final_summary: str
    ) -> None:
        from dropbox.files import WriteMode

        final_summary = final_summary.strip()
        if not final_summary:
            raise ValueError("The confirmed summary cannot be empty.")
        path, metadata, state = self._response_for_subject(subject_id)
        pending = state.get("pending_answer")
        if state.get("stage") != "summary_review" or not isinstance(pending, dict):
            raise StorageError("There is no submitted answer awaiting confirmation.")
        llm_summary = str(pending.get("llm_summary", "")).strip()
        if not llm_summary:
            raise StorageError("The generated summary has not yet been saved.")
        assigned = [int(value) for value in state["assignment"]["assigned_cases"]]
        current_index = int(state.get("item_index", 0))
        if int(pending.get("case_number", -1)) != assigned[current_index]:
            raise StorageError("The saved answer does not match the current question.")
        now = utc_now()
        confirmed = deepcopy(pending)
        confirmed["final_summary"] = final_summary
        confirmed["summary_modified"] = final_summary != llm_summary
        confirmed["confirmed_at"] = now
        updated = deepcopy(state)
        updated.setdefault("answers", []).append(confirmed)
        updated["pending_answer"] = None
        updated["item_index"] = current_index + 1
        updated["updated_at"] = now
        updated["revision"] = int(state.get("revision", 0)) + 1
        completed = updated["item_index"] >= len(assigned)
        updated["stage"] = "complete" if completed else "question"
        if completed:
            updated["completed_at"] = now
            updated["csv_synced"] = False
        response_metadata = self._upload_json(
            path, updated, WriteMode.update(metadata.rev)
        )
        if completed:
            self._sync_completed_csv(path, response_metadata, updated)

    @staticmethod
    def _incoming_answer(
        case_number: int,
        component_answer: str,
        explanation_answer: str,
        llm_summary: str,
        final_summary: str,
        llm_provider: str,
        llm_model: str,
    ) -> dict[str, object]:
        return {
            "case_number": int(case_number),
            "component_answer": component_answer,
            "explanation_answer": explanation_answer,
            "llm_summary": llm_summary,
            "final_summary": final_summary,
            "summary_modified": final_summary.strip() != llm_summary.strip(),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
        }

    def save_confirmed_response(
        self,
        *,
        subject_id: str,
        case_number: int,
        component_answer: str,
        explanation_answer: str,
        llm_summary: str,
        final_summary: str,
        llm_provider: str,
        llm_model: str,
        next_item_index: int,
        completed: bool,
    ) -> None:
        progress = self.get_progress(subject_id)
        if next_item_index != progress.item_index + 1:
            raise StorageError("The submitted progress position is invalid.")
        if completed != (next_item_index >= len(progress.assigned_cases)):
            raise StorageError("The completion status does not match the saved assignment.")
        self.save_pending_response(
            subject_id=subject_id,
            case_number=case_number,
            question_type="original" if progress.item_index == 0 else "review",
            component_answer=component_answer,
            explanation_answer=explanation_answer,
        )
        self.save_generated_summary(
            subject_id=subject_id,
            case_number=case_number,
            llm_summary=llm_summary,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        self.confirm_pending_response(
            subject_id=subject_id, final_summary=final_summary
        )

    def _sync_completed_csv(self, path: str, response_metadata, state: dict[str, object]):
        from dropbox.files import WriteMode

        if state.get("stage") != "complete":
            raise StorageError("Only completed responses can enter answers.csv.")
        if state.get("csv_synced"):
            return
        new_row = JsonCsvRepository._export_row(state)
        for _ in range(5):
            metadata, header, rows = self._read_csv(self.answers_path)
            rows = JsonCsvRepository._normalize_answer_rows(header, rows)
            matches = [
                index
                for index, row in enumerate(rows)
                if row.get("SubjectId") == state["subject_id"]
            ]
            if matches:
                rows[matches[0]] = {
                    key: str(new_row.get(key, "")) for key in ANSWER_FIELDS
                }
                rows = [
                    row for index, row in enumerate(rows) if index not in matches[1:]
                ]
            else:
                rows.append(new_row)
            mode = WriteMode.update(metadata.rev) if metadata else WriteMode.add
            try:
                self._upload_csv(self.answers_path, ANSWER_FIELDS, rows, mode)
                break
            except StaleResponse:
                continue
        else:
            raise StorageError(
                "Other submissions are updating answers.csv. The completed JSON is saved; "
                "retry finalising."
            )

        synced = deepcopy(state)
        synced["csv_synced"] = True
        synced["revision"] = int(state.get("revision", 0)) + 1
        synced["updated_at"] = utc_now()
        try:
            self._upload_json(path, synced, WriteMode.update(response_metadata.rev))
        except StaleResponse:
            current = self._read_json(path)
            if current is not None and current[1].get("csv_synced"):
                return
            raise StorageError(
                "The answer CSV is saved, but the response marker needs another retry."
            )

    def finalize_completed(self, subject_id: str) -> None:
        path, metadata, state = self._response_for_subject(subject_id)
        self._sync_completed_csv(path, metadata, state)

    def get_response_state(self, subject_id: str) -> dict[str, object]:
        _, _, state = self._response_for_subject(subject_id)
        return deepcopy(state)
