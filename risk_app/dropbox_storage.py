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
            raise ValueError("Please enter your surname.")
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
        )

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
        from dropbox.files import WriteMode

        path, metadata, state = self._response_for_subject(subject_id)
        assigned = [int(value) for value in state["assignment"]["assigned_cases"]]
        current_index = int(state.get("item_index", 0))
        incoming = self._incoming_answer(
            case_number,
            component_answer,
            explanation_answer,
            llm_summary,
            final_summary,
            llm_provider,
            llm_model,
        )
        if current_index >= len(assigned):
            saved = next(
                (
                    answer
                    for answer in state.get("answers", [])
                    if int(answer.get("case_number", -1)) == int(case_number)
                ),
                None,
            )
            if saved is None or not JsonCsvRepository._same_answer(saved, incoming):
                raise StorageError("This completed response cannot be changed.")
            self._sync_completed_csv(path, metadata, state)
            return
        if assigned[current_index] != int(case_number):
            raise StorageError("The submitted case does not match the saved assignment.")
        if next_item_index != current_index + 1:
            raise StorageError("The submitted progress position is invalid.")
        should_complete = next_item_index >= len(assigned)
        if completed != should_complete:
            raise StorageError("The completion status does not match the saved assignment.")

        updated = deepcopy(state)
        confirmed = dict(incoming, confirmed_at=utc_now())
        answers = updated.setdefault("answers", [])
        if any(int(answer.get("case_number", -1)) == int(case_number) for answer in answers):
            raise StorageError("A confirmed answer for this case is already saved.")
        answers.append(confirmed)
        updated["item_index"] = next_item_index
        updated["updated_at"] = confirmed["confirmed_at"]
        updated["revision"] = int(state.get("revision", 0)) + 1
        if completed:
            updated["stage"] = "complete"
            updated["completed_at"] = confirmed["confirmed_at"]
            updated["csv_synced"] = False
        response_metadata = self._upload_json(
            path, updated, WriteMode.update(metadata.rev)
        )
        if completed:
            self._sync_completed_csv(path, response_metadata, updated)

    def _sync_completed_csv(self, path: str, response_metadata, state: dict[str, object]):
        from dropbox.files import WriteMode

        if state.get("stage") != "complete":
            raise StorageError("Only completed responses can enter answers.csv.")
        if state.get("csv_synced"):
            return
        new_row = JsonCsvRepository._export_row(state)
        for _ in range(5):
            metadata, header, rows = self._read_csv(self.answers_path)
            if header and header != ANSWER_FIELDS:
                raise StorageError(
                    "answers.csv has an unexpected layout. The completed JSON remains saved."
                )
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
