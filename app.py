from __future__ import annotations

import html

import streamlit as st

from risk_app.content import (
    APP_TITLE,
    ASSIGNMENT_CONTEXT,
    CASES,
    COMPONENT_OPTIONS,
    COMPONENT_QUESTION,
    EMAIL_QUESTION,
    EXPLANATION_QUESTION,
    FULL_CASE_QUESTION,
    NAME_QUESTION,
    SUMMARY_REVIEW_TEXT,
    build_case_items,
    format_full_student_answer,
)
from risk_app.llm import SummaryClient
from risk_app.storage import Participant, StorageError, configured_repository
from risk_app.styles import QUALTRICS_CSS
from risk_app.workflow import normalize_email, valid_email


st.set_page_config(page_title=APP_TITLE, page_icon="📘", layout="centered")
st.markdown(QUALTRICS_CSS, unsafe_allow_html=True)


@st.cache_resource
def repository():
    return configured_repository()


@st.cache_resource
def summary_client() -> SummaryClient:
    return SummaryClient()


def initialize_state() -> None:
    defaults = {
        "phase": "email",
        "email": "",
        "subject_id": "",
        "participant_name": "",
        "pending_component_answer": "",
        "pending_explanation_answer": "",
        "pending_summary": "",
        "pending_provider": "",
        "pending_model": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def shell(meta: str = "") -> None:
    safe_meta = html.escape(meta)
    st.markdown(
        f"""
        <div class="survey-shell">
            <div class="survey-brand">HEC PARIS</div>
            <div class="survey-title">{APP_TITLE}</div>
            <div class="survey-meta">{safe_meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def set_participant(participant: Participant) -> None:
    st.session_state.subject_id = participant.subject_id
    st.session_state.participant_name = participant.name
    st.session_state.email = participant.email


def render_email() -> None:
    shell("Enter your e-mail address to begin or resume")
    with st.form("email_form"):
        email = st.text_input(EMAIL_QUESTION, value=st.session_state.email)
        submitted = st.form_submit_button("Next")
    st.markdown(
        '<div class="privacy-note">Returning participants are identified by e-mail and resume from their last confirmed answer.</div>',
        unsafe_allow_html=True,
    )
    if not submitted:
        return
    if not valid_email(email):
        st.error("Please enter a valid e-mail address.")
        return
    normalized = normalize_email(email)
    try:
        participant = repository().find_participant_by_email(normalized)
    except StorageError as error:
        st.error(str(error))
        return
    st.session_state.email = normalized
    if participant:
        set_participant(participant)
        st.session_state.phase = "question"
    else:
        st.session_state.phase = "details"
    st.rerun()


def render_details() -> None:
    shell("New participant details")
    st.info(f"E-mail: {st.session_state.email}")
    with st.form("details_form"):
        name = st.text_input(NAME_QUESTION)
        submitted = st.form_submit_button("Start assignment")
    if not submitted:
        return
    if not name.strip():
        st.error("Please enter your surname.")
        return
    try:
        participant = repository().create_participant(
            email=st.session_state.email,
            name=name,
        )
    except (ValueError, StorageError) as error:
        st.error(str(error))
        return
    set_participant(participant)
    st.session_state.phase = "question"
    st.rerun()


def current_context():
    progress = repository().get_progress(st.session_state.subject_id)
    items = build_case_items(progress.assigned_cases)
    return progress, items


def render_case(case_number: int) -> None:
    case_html = html.escape(CASES[case_number]).replace("\n", "<br>")
    st.markdown(
        f'<div class="case-card"><div class="case-label">Case {case_number}</div>{case_html}</div>',
        unsafe_allow_html=True,
    )


def render_question() -> None:
    progress, items = current_context()
    if progress.completed or progress.item_index >= len(items):
        st.session_state.phase = "complete"
        st.rerun()
    item = items[progress.item_index]
    ordinal = progress.assigned_cases.index(item.case_number) + 1
    shell(f"Case {ordinal} of 2")
    if progress.item_index == 0:
        st.markdown(ASSIGNMENT_CONTEXT)
    st.markdown(f"**First, consider case {item.case_number}.**")
    render_case(item.case_number)
    with st.form(f"question_form_{progress.item_index}"):
        component_answer = st.radio(COMPONENT_QUESTION, COMPONENT_OPTIONS, index=None)
        explanation_answer = st.text_area(EXPLANATION_QUESTION, height=220, max_chars=4000)
        st.caption("The explanation should ideally be no more than around 250–300 words.")
        submitted = st.form_submit_button("Review answers")
    if not submitted:
        return
    if not component_answer:
        st.error("Please answer question i before continuing.")
        return
    if not explanation_answer.strip():
        st.error("Please answer question ii before continuing.")
        return
    with st.spinner("Preparing a concise summary of your explanation…"):
        try:
            full_student_answer = format_full_student_answer(
                component_answer,
                explanation_answer,
            )
            result = summary_client().summarize(
                case_text=CASES[item.case_number],
                question_text=FULL_CASE_QUESTION,
                student_answer=full_student_answer,
            )
        except Exception as error:
            st.error(f"The summary could not be prepared. Please try again. Technical detail: {error}")
            return
    st.session_state.pending_component_answer = component_answer
    st.session_state.pending_explanation_answer = explanation_answer.strip()
    st.session_state.pending_summary = result.text
    st.session_state.pending_provider = result.provider
    st.session_state.pending_model = result.model
    st.session_state.phase = "review"
    st.rerun()


def render_review() -> None:
    progress, items = current_context()
    if progress.item_index >= len(items):
        st.session_state.phase = "complete"
        st.rerun()
    item = items[progress.item_index]
    shell(f"Review · Case {item.case_number}")
    render_case(item.case_number)
    st.markdown(f"**i. Selected component**\n\n{st.session_state.pending_component_answer}")
    st.markdown(f"**ii. Your explanation**\n\n{st.session_state.pending_explanation_answer}")
    st.markdown(SUMMARY_REVIEW_TEXT)
    safe_summary = html.escape(st.session_state.pending_summary).replace("\n", "<br>")
    st.markdown(
        f'<div class="summary-panel">{safe_summary}</div>',
        unsafe_allow_html=True,
    )
    decision = st.radio(
        "Does this summary capture your answer?",
        ("Confirm", "Modify"),
        horizontal=True,
        key=f"review_decision_{progress.item_index}",
    )
    if decision == "Modify":
        edited = st.text_area(
            "Edit the bullet points",
            value=st.session_state.pending_summary,
            height=180,
            key=f"review_edit_{progress.item_index}",
        )
    else:
        edited = st.session_state.pending_summary
    submitted = st.button("Confirm and continue", key=f"review_submit_{progress.item_index}")
    if not submitted:
        return
    final_summary = edited.strip() if decision == "Modify" else st.session_state.pending_summary.strip()
    if not final_summary:
        st.error("The confirmed summary cannot be empty.")
        return
    next_index = progress.item_index + 1
    completed = next_index >= len(items)
    try:
        repository().save_confirmed_response(
            subject_id=st.session_state.subject_id,
            case_number=item.case_number,
            component_answer=st.session_state.pending_component_answer,
            explanation_answer=st.session_state.pending_explanation_answer,
            llm_summary=st.session_state.pending_summary,
            final_summary=final_summary,
            llm_provider=st.session_state.pending_provider,
            llm_model=st.session_state.pending_model,
            next_item_index=next_index,
            completed=completed,
        )
    except StorageError as error:
        st.error(str(error))
        st.info("Your entry remains on this page so you can retry the save.")
        return
    for key in (
        "pending_component_answer",
        "pending_explanation_answer",
        "pending_summary",
        "pending_provider",
        "pending_model",
    ):
        st.session_state[key] = ""
    st.session_state.phase = "complete" if completed else "question"
    st.rerun()


def render_complete() -> None:
    shell("Submission complete")
    try:
        repository().finalize_completed(st.session_state.subject_id)
    except StorageError as error:
        st.info("Your completed response is saved as JSON, but the final CSV still needs to be updated.")
        st.error(str(error))
        if st.button("Retry finalising"):
            st.rerun()
        return
    st.success("Thank you. Your answers have been saved.")
    st.write(f"Subject ID: **{st.session_state.subject_id}**")
    st.caption("You may close this page.")


def main() -> None:
    initialize_state()
    phase = st.session_state.phase
    try:
        if phase == "email":
            render_email()
        elif phase == "details":
            render_details()
        elif phase == "question":
            render_question()
        elif phase == "review":
            render_review()
        elif phase == "complete":
            render_complete()
        else:
            st.session_state.phase = "email"
            st.rerun()
    except StorageError as error:
        st.error(str(error))
        st.info("Dropbox may be temporarily unavailable. Your last confirmed step remains saved.")
        if st.button("Retry connection"):
            st.rerun()


if __name__ == "__main__":
    main()

