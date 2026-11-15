from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from risk_app.workflow import assign_cases, normalize_email


SUBJECT_FIELDS = ["SubjectId", "name", "email"]
LEGACY_CASE_EXPORT_FIELDS = [
    "case_number",
    "component_answer",
    "explanation_answer",
    "llm_summary",
    "final_summary",
    "summary_modified",
    "llm_provider",
    "llm_model",
    "confirmed_at",
]
LEGACY_ANSWER_FIELDS = ["SubjectId", "StartDate", "EndDate", "Finished"] + [
    f"case_{position}_{field}"
    for position in (1, 2)
    for field in LEGACY_CASE_EXPORT_FIELDS
]
QUESTION_EXPORT_FIELDS = [
    "question_number",
    "question_type",
    "case_number",
    "component_answer",
    "explanation_answer",
    "provided_answer",
    "assessment_answer",
    "correction_answer",
    "llm_summary",
    "final_summary",
    "summary_modified",
    "llm_provider",
    "llm_model",
    "submitted_at",
    "confirmed_at",
]
ANSWER_FIELDS = ["SubjectId", "StartDate", "EndDate", "Finished"] + [
    f"question_{position}_{field}"
    for position in (1, 2)
    for field in QUESTION_EXPORT_FIELDS
]
RESPONSE_KEY_RE = re.compile(r"[0-9a-f]{64}")
SUBJECT_ID_RE = re.compile(r"[0-9]{8}")


class StorageError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def valid_subject_id(value: str) -> bool:
    return isinstance(value, str) and SUBJECT_ID_RE.fullmatch(value) is not None


def email_key(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Participant:
    subject_id: str
    name: str
    email: str


@dataclass(frozen=True)
class Progress:
    subject_id: str
    assigned_cases: list[int]
    item_index: int
    completed: bool
    stage: str
    pending_answer: dict[str, object] | None


class JsonCsvRepository:
    """Local version of the reference app's JSON-then-CSV persistence flow.

    A private JSON file is authoritative for each response and is updated after
    every confirmed case. Only completed responses are merged into answers.csv.
    The answer CSV is de-identified; subjects.csv is the separate identity log.
    """

    _lock = threading.RLock()

    def __init__(self, data_dir: str | Path | None = None) -> None:
        configured = data_dir or os.getenv("RISK_APP_DATA_DIR", "data")
        self.data_dir = Path(configured)
        self.responses_dir = self.data_dir / "responses"
        self.email_index_dir = self.data_dir / "_email_index"
        self.subjects_path = self.data_dir / "subjects.csv"
        self.answers_path = self.data_dir / "answers.csv"
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.email_index_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_csv(self.subjects_path, SUBJECT_FIELDS)

    @staticmethod
    def _ensure_csv(path: Path, fields: list[str]) -> None:
        if path.exists():
            return
        JsonCsvRepository._write_csv_atomic(path, fields, [])

    @staticmethod
    def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
        if not path.exists():
            return [], []
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)

    @staticmethod
    def _write_csv_atomic(
        path: Path, fields: list[str], rows: list[dict[str, object]]
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.stem}-", suffix=".csv", dir=path.parent
        )
        os.close(descriptor)
        temp_path = Path(temp_name)
        try:
            with temp_path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.stem}-", suffix=".json", dir=path.parent
        )
        os.close(descriptor)
        temp_path = Path(temp_name)
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(f"Could not read saved response {path.name}.") from error
        if not isinstance(payload, dict):
            raise StorageError(f"Saved response {path.name} is not a JSON object.")
        return payload

    def _subject_rows(self) -> list[dict[str, str]]:
        header, rows = self._read_csv(self.subjects_path)
        if header != SUBJECT_FIELDS:
            raise StorageError("subjects.csv must contain SubjectId, name and email columns.")
        ids = [row.get("SubjectId", "") for row in rows]
        emails = [normalize_email(row.get("email", "")) for row in rows]
        if any(not valid_subject_id(value) for value in ids) or len(ids) != len(set(ids)):
            raise StorageError("subjects.csv contains an invalid or duplicate SubjectId.")
        if any(not value for value in emails) or len(emails) != len(set(emails)):
            raise StorageError("subjects.csv contains an empty or duplicate email address.")
        return rows

    def _new_subject_id(self, rows: list[dict[str, str]]) -> str:
        existing = {row["SubjectId"] for row in rows}
        for _ in range(100):
            candidate = str(secrets.randbelow(90_000_000) + 10_000_000)
            if candidate not in existing:
                return candidate
        raise StorageError("Could not allocate a unique subject ID. Please retry.")

    def _response_path(self, response_key: str) -> Path:
        if RESPONSE_KEY_RE.fullmatch(response_key) is None:
            raise StorageError("The saved response reference is invalid.")
        return self.responses_dir / f"{response_key}.json"

    def _index_path(self, email: str) -> Path:
        return self.email_index_dir / f"{email_key(email)}.json"

    def _response_for_subject(self, subject_id: str) -> tuple[Path, dict[str, object]]:
        rows = self._subject_rows()
        subject = next((row for row in rows if row["SubjectId"] == subject_id), None)
        if subject is None:
            raise KeyError(f"No identity record for subject {subject_id}.")

        index_path = self._index_path(subject["email"])
        if index_path.exists():
            index = self._read_json(index_path)
            response_key = str(index.get("response_key", ""))
            path = self._response_path(response_key)
            if path.exists():
                state = self._read_json(path)
                if state.get("subject_id") == subject_id:
                    return path, state

        matches: list[tuple[Path, dict[str, object]]] = []
        for path in self.responses_dir.glob("*.json"):
            state = self._read_json(path)
            if state.get("subject_id") == subject_id:
                matches.append((path, state))
        if len(matches) != 1:
            raise StorageError("The saved response for this subject could not be identified uniquely.")
        path, state = matches[0]
        self._write_json_atomic(index_path, {"response_key": path.stem})
        return path, state

    def find_participant_by_email(self, email: str) -> Participant | None:
        target = normalize_email(email)
        with self._lock:
            matches = [
                row for row in self._subject_rows()
                if normalize_email(row["email"]) == target
            ]
            if not matches:
                return None
            if len(matches) != 1:
                raise StorageError("More than one identity record uses this email address.")
            row = matches[0]
            self._response_for_subject(row["SubjectId"])
            return Participant(row["SubjectId"], row["name"], row["email"])

    def find_participant_by_subject_id(self, subject_id: str) -> Participant | None:
        with self._lock:
            for row in self._subject_rows():
                if row["SubjectId"] == subject_id:
                    return Participant(row["SubjectId"], row["name"], row["email"])
        return None

    def create_participant(self, *, email: str, name: str) -> Participant:
        email = normalize_email(email)
        name = name.strip()
        if not name:
            raise ValueError("Please enter your full name.")
        with self._lock:
            rows = self._subject_rows()
            if any(normalize_email(row["email"]) == email for row in rows):
                raise ValueError("This e-mail address is already registered.")

            subject_id = self._new_subject_id(rows)
            response_key = secrets.token_hex(32)
            now = utc_now()
            state: dict[str, object] = {
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

            # The response JSON is created before either lookup points to it.
            self._write_json_atomic(self._response_path(response_key), state)
            rows.append({"SubjectId": subject_id, "name": name, "email": email})
            self._write_csv_atomic(self.subjects_path, SUBJECT_FIELDS, rows)
            self._write_json_atomic(
                self._index_path(email), {"response_key": response_key}
            )
            return Participant(subject_id, name, email)

    def get_progress(self, subject_id: str) -> Progress:
        with self._lock:
            _, state = self._response_for_subject(subject_id)
            assignment = state.get("assignment", {})
            assigned_cases = assignment.get("assigned_cases", []) if isinstance(assignment, dict) else []
            return Progress(
                subject_id=subject_id,
                assigned_cases=[int(value) for value in assigned_cases],
                item_index=int(state.get("item_index", 0)),
                completed=state.get("stage") == "complete",
                stage=str(state.get("stage", "question")),
                pending_answer=deepcopy(state.get("pending_answer")),
            )

    @staticmethod
    def _same_answer(saved: dict[str, object], incoming: dict[str, object]) -> bool:
        return all(saved.get(key) == value for key, value in incoming.items())

    @staticmethod
    def _pending_payload(
        *,
        question_number: int,
        question_type: str,
        case_number: int,
        component_answer: str = "",
        explanation_answer: str = "",
        provided_answer: str = "",
        assessment_answer: str = "",
        correction_answer: str = "",
    ) -> dict[str, object]:
        return {
            "question_number": int(question_number),
            "question_type": question_type,
            "case_number": int(case_number),
            "component_answer": component_answer.strip(),
            "explanation_answer": explanation_answer.strip(),
            "provided_answer": provided_answer.strip(),
            "assessment_answer": assessment_answer.strip(),
            "correction_answer": correction_answer.strip(),
        }

    @staticmethod
    def _validate_pending_position(
        state: dict[str, object], *, case_number: int, question_type: str
    ) -> tuple[list[int], int]:
        assigned = [int(value) for value in state["assignment"]["assigned_cases"]]
        current_index = int(state.get("item_index", 0))
        if state.get("stage") == "complete" or current_index >= len(assigned):
            raise StorageError("This completed response cannot be changed.")
        if assigned[current_index] != int(case_number):
            raise StorageError("The submitted case does not match the saved assignment.")
        expected_type = "original" if current_index == 0 else "review"
        if question_type != expected_type:
            raise StorageError("The submitted answer type does not match this question.")
        return assigned, current_index

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
        """Persist the student's full answer before any LLM request is made."""
        with self._lock:
            path, state = self._response_for_subject(subject_id)
            _, current_index = self._validate_pending_position(
                state, case_number=case_number, question_type=question_type
            )
            incoming = self._pending_payload(
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
            if isinstance(current, dict) and self._same_answer(current, incoming):
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
            self._write_json_atomic(path, updated)

    def save_generated_summary(
        self,
        *,
        subject_id: str,
        case_number: int,
        llm_summary: str,
        llm_provider: str,
        llm_model: str,
    ) -> None:
        """Persist the LLM result so a reconnect does not repeat the request."""
        llm_summary = llm_summary.strip()
        if not llm_summary:
            raise ValueError("The generated summary cannot be empty.")
        with self._lock:
            path, state = self._response_for_subject(subject_id)
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
            self._write_json_atomic(path, updated)

    def confirm_pending_response(
        self, *, subject_id: str, final_summary: str
    ) -> None:
        final_summary = final_summary.strip()
        if not final_summary:
            raise ValueError("The confirmed summary cannot be empty.")
        with self._lock:
            path, state = self._response_for_subject(subject_id)
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
            self._write_json_atomic(path, updated)
            if completed:
                self._sync_completed_csv(path, updated)

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
        # Compatibility wrapper for older callers. New UI code saves each of
        # these three durability boundaries explicitly.
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

    @staticmethod
    def _export_row(state: dict[str, object]) -> dict[str, object]:
        row: dict[str, object] = {
            "SubjectId": state["subject_id"],
            "StartDate": state.get("started_at", ""),
            "EndDate": state.get("completed_at", ""),
            "Finished": 1,
        }
        answers = state.get("answers", [])
        for position in (1, 2):
            answer = answers[position - 1] if len(answers) >= position else {}
            for field in QUESTION_EXPORT_FIELDS:
                value = answer.get(field, "")
                if isinstance(value, bool):
                    value = str(value).lower()
                row[f"question_{position}_{field}"] = value
        return row

    @staticmethod
    def _normalize_answer_rows(
        header: list[str], rows: list[dict[str, str]]
    ) -> list[dict[str, object]]:
        """Preserve completed rows written by the previous two-case schema."""
        if not header or header == ANSWER_FIELDS:
            return rows
        if header != LEGACY_ANSWER_FIELDS:
            raise StorageError(
                "answers.csv has an unexpected layout. The completed JSON remains saved."
            )
        migrated: list[dict[str, object]] = []
        for old in rows:
            new: dict[str, object] = {
                key: old.get(key, "")
                for key in ("SubjectId", "StartDate", "EndDate", "Finished")
            }
            for position in (1, 2):
                new[f"question_{position}_question_number"] = position
                new[f"question_{position}_question_type"] = "legacy_original"
                for field in LEGACY_CASE_EXPORT_FIELDS:
                    new[f"question_{position}_{field}"] = old.get(
                        f"case_{position}_{field}", ""
                    )
                for field in ("provided_answer", "assessment_answer", "correction_answer", "submitted_at"):
                    new[f"question_{position}_{field}"] = ""
            migrated.append(new)
        return migrated

    def _sync_completed_csv(self, path: Path, state: dict[str, object]) -> None:
        if state.get("stage") != "complete":
            raise StorageError("Only completed responses can enter answers.csv.")
        if state.get("csv_synced"):
            return
        if not valid_subject_id(str(state.get("subject_id", ""))):
            raise StorageError("The completed response has no valid SubjectId.")

        header, rows = self._read_csv(self.answers_path)
        rows = self._normalize_answer_rows(header, rows)
        new_row = self._export_row(state)
        matches = [
            index for index, row in enumerate(rows)
            if row.get("SubjectId") == state["subject_id"]
        ]
        if matches:
            rows[matches[0]] = {key: str(new_row.get(key, "")) for key in ANSWER_FIELDS}
            rows = [row for index, row in enumerate(rows) if index not in matches[1:]]
        else:
            rows.append(new_row)
        self._write_csv_atomic(self.answers_path, ANSWER_FIELDS, rows)

        # Mark the JSON only after the idempotent merge succeeds.
        synced = deepcopy(state)
        synced["csv_synced"] = True
        synced["revision"] = int(state.get("revision", 0)) + 1
        synced["updated_at"] = utc_now()
        self._write_json_atomic(path, synced)

    def finalize_completed(self, subject_id: str) -> None:
        """Retry the completion-only CSV merge after any interrupted final save."""
        with self._lock:
            path, state = self._response_for_subject(subject_id)
            self._sync_completed_csv(path, state)

    def get_response_state(self, subject_id: str) -> dict[str, object]:
        """Return a copy for verification and future storage-adapter tests."""
        with self._lock:
            _, state = self._response_for_subject(subject_id)
            return deepcopy(state)


# Backwards-compatible import name for any existing local scripts.
CsvRepository = JsonCsvRepository


def setting(name: str, default: str | None = None) -> str | None:
    """Read a deployment setting from the environment or Streamlit secrets."""
    if name in os.environ:
        return os.environ[name]
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except (ImportError, FileNotFoundError):
        return default


def configured_repository():
    """Select local development storage or persistent Dropbox storage."""
    backend = str(setting("STORAGE_BACKEND", "local")).strip().casefold()
    if backend in {"local", "json", "json-csv"}:
        return JsonCsvRepository(str(setting("RISK_APP_DATA_DIR", "data")))
    if backend == "dropbox":
        from risk_app.dropbox_storage import configured_dropbox_repository

        return configured_dropbox_repository()
    raise StorageError("STORAGE_BACKEND must be either 'local' or 'dropbox'.")
