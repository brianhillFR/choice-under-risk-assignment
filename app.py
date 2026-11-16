from __future__ import annotations

import html

import streamlit as st

from risk_app.content import (
    APP_TITLE,
    ASSESSMENT_OPTIONS,
    ASSESSMENT_QUESTION,
    ASSIGNMENT_CONTEXT,
    CASES,
    COMPONENT_OPTIONS,
    COMPONENT_QUESTION,
    CORRECTION_QUESTION,
    EMAIL_QUESTION,
    EXPLANATION_QUESTION,
    FULL_CASE_QUESTION,
    NAME_QUESTION,
    PROVIDED_ANSWERS,
    REVIEW_CASE_INTRO,
    REVIEW_QUESTIONS_INTRO,
    REVIEW_RESPONSE_INTRO,
    SUMMARY_REVIEW_TEXT,
    build_case_items,
    format_full_student_answer,
    format_full_review_answer,
    full_review_question,
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


def resume_phase() -> str:
    progress = repository().get_progress(st.session_state.subject_id)
    if progress.completed:
        return "complete"
    if progress.stage == "summary_review":
        return "review"
    return "question"


def render_email() -> None:
    shell("Enter your e-mail address to begin or resume")
    with st.form("email_form"):
        email = st.text_input(EMAIL_QUESTION, value=st.session_state.email)
        submitted = st.form_submit_button("Next")
    st.markdown(
        '<div class="privacy-note">Returning participants are identified by e-mail and resume from their last saved step.</div>',
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
        st.session_state.phase = resume_phase()
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
        st.error("Please enter your full name.")
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
    st.session_state.phase = resume_phase()
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


def render_provided_answer(case_number: int) -> None:
    safe_answer = html.escape(PROVIDED_ANSWERS[case_number]).replace("\n", "<br>")
    st.markdown(
        '<div class="provided-answer"><div class="provided-answer-label">'
        f'Provided response</div>{safe_answer}</div>',
        unsafe_allow_html=True,
    )


def submit_for_summary(item, **answer_fields: str) -> bool:
    try:
        repository().save_pending_response(
            subject_id=st.session_state.subject_id,
            case_number=item.case_number,
            question_type=item.question_type,
            **answer_fields,
        )
    except StorageError as error:
        st.error(str(error))
        return False
    st.session_state.phase = "review"
    st.rerun()
    return True


def render_original_question(item) -> None:
    if item.question_number == 1:
        st.markdown(ASSIGNMENT_CONTEXT)
    st.markdown(f"**First, consider case {item.case_number}.**")
    render_case(item.case_number)
    with st.form(f"question_form_{item.question_number}"):
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
    submit_for_summary(
        item,
        component_answer=component_answer,
        explanation_answer=explanation_answer,
    )


def render_correction_question(item) -> None:
    st.markdown(
        f"**{REVIEW_CASE_INTRO.format(case_number=item.case_number)}**"
    )
    render_case(item.case_number)
    st.markdown(f"**{REVIEW_QUESTIONS_INTRO}**")
    st.markdown(FULL_CASE_QUESTION)
    st.markdown(REVIEW_RESPONSE_INTRO)
    render_provided_answer(item.case_number)
    with st.form(f"question_form_{item.question_number}"):
        assessment_answer = st.radio(
            ASSESSMENT_QUESTION,
            ASSESSMENT_OPTIONS,
            index=None,
        )
        correction_answer = st.text_area(
            CORRECTION_QUESTION,
            height=220,
            max_chars=4000,
        )
        st.caption("The explanation should ideally be no more than around 250–300 words.")
        submitted = st.form_submit_button("Review answers")
    if not submitted:
        return
    if not assessment_answer:
        st.error("Please assess the provided response before continuing.")
        return
    if not correction_answer.strip():
        st.error("Please explain your assessment before continuing.")
        return
    submit_for_summary(
        item,
        provided_answer=PROVIDED_ANSWERS[item.case_number],
        assessment_answer=assessment_answer,
        correction_answer=correction_answer,
    )


def render_question() -> None:
    progress, items = current_context()
    if progress.completed or progress.item_index >= len(items):
        st.session_state.phase = "complete"
        st.rerun()
    item = items[progress.item_index]
    shell(f"Question {item.question_number} of 2")
    if item.question_type == "original":
        render_original_question(item)
    else:
        render_correction_question(item)


def ensure_saved_summary(item, pending: dict[str, object]) -> dict[str, object] | None:
    if pending.get("llm_summary"):
        return pending
    if item.question_type == "original":
        question_text = FULL_CASE_QUESTION
        student_answer = format_full_student_answer(
            str(pending.get("component_answer", "")),
            str(pending.get("explanation_answer", "")),
        )
    else:
        question_text = full_review_question(item.case_number)
        student_answer = format_full_review_answer(
            str(pending.get("assessment_answer", "")),
            str(pending.get("correction_answer", "")),
        )
    with st.spinner("Preparing a concise summary of your explanation…"):
        try:
            result = summary_client().summarize(
                case_text=CASES[item.case_number],
                question_text=question_text,
                student_answer=student_answer,
            )
            repository().save_generated_summary(
                subject_id=st.session_state.subject_id,
                case_number=item.case_number,
                llm_summary=result.text,
                llm_provider=result.provider,
                llm_model=result.model,
            )
        except Exception as error:
            st.error(
                "Your answer is saved, but the summary could not be prepared. "
                f"Please retry. Technical detail: {error}"
            )
            if st.button("Retry summary"):
                st.rerun()
            return None
    return repository().get_progress(st.session_state.subject_id).pending_answer


def render_review() -> None:
    progress, items = current_context()
    if progress.item_index >= len(items):
        st.session_state.phase = "complete"
        st.rerun()
    item = items[progress.item_index]
    if not isinstance(progress.pending_answer, dict):
        st.session_state.phase = "question"
        st.rerun()
    pending = ensure_saved_summary(item, progress.pending_answer)
    if pending is None:
        return
    shell(f"Question {item.question_number} of 2 · Summary review")
    render_case(item.case_number)
    if item.question_type == "original":
        st.markdown(f"**i. Selected component**\n\n{pending['component_answer']}")
        st.markdown(f"**ii. Your explanation**\n\n{pending['explanation_answer']}")
    else:
        render_provided_answer(item.case_number)
        st.markdown(f"**Your assessment**\n\n{pending['assessment_answer']}")
        st.markdown(f"**Your explanation and correction**\n\n{pending['correction_answer']}")
    st.markdown(SUMMARY_REVIEW_TEXT)
    summary = str(pending["llm_summary"])
    safe_summary = html.escape(summary).replace("\n", "<br>")
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
            value=summary,
            height=180,
            key=f"review_edit_{progress.item_index}",
        )
    else:
        edited = summary
    submitted = st.button("Confirm and continue", key=f"review_submit_{progress.item_index}")
    if not submitted:
        return
    final_summary = edited.strip() if decision == "Modify" else summary.strip()
    if not final_summary:
        st.error("The confirmed summary cannot be empty.")
        return
    try:
        repository().confirm_pending_response(
            subject_id=st.session_state.subject_id,
            final_summary=final_summary,
        )
    except StorageError as error:
        st.error(str(error))
        st.info("Your entry remains on this page so you can retry the save.")
        return
    st.session_state.phase = resume_phase()
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
        st.info("Dropbox may be temporarily unavailable. Your last saved step remains available.")
        if st.button("Retry connection"):
            st.rerun()


if __name__ == "__main__":
    main()

