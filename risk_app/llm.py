from __future__ import annotations

import os
import re
from dataclasses import dataclass


SYSTEM_INSTRUCTIONS = """You are participating in a choice-under-risk
homework exercise. You are an expert on the subject. Your role is to summarize 
the student's own explanation for confirmation. Your only task is to paraphrase in a 
concise and bullet-point form the student's explanation, removing any elements of 
the writing style, and boiling the student's previous response down to the concepts
involved and the points made.

Preserve the student's intended meaning. Do not
grade, correct, criticize, praise, add missing theory, or provide feedback. Likewise, 
make your output as matter-of-fact as possible, with no highlighting of any elements
of the responses or judgements about the correctness, importance or relevance of them.
Do not, in particular, reorganise the points made by the student, omit any or add any that 
were absent.

For each case, you will receive:
- The case shown to the student.
- The full two-part question shown to the student.
- The student's full two-part answer, including their selected component and explanation.

Return only a concise Markdown bullet list of all and only the arguments and considerations
actually present in the explanation. Use 1-6
bullets. Each bullet must begin with '- '"""



def normalize_bullets(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if line:
            lines.append(f"- {line}")
    return "\n".join(lines[:6])


def demo_summary(student_answer: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", student_answer.strip())
    points = [sentence.strip(" -*•\t") for sentence in sentences if sentence.strip(" -*•\t")]
    if not points:
        return "- No substantive answer was supplied."
    return "\n".join(f"- {point}" for point in points[:6])


def build_prompt(*, case_text: str, question_text: str, student_answer: str) -> str:
    return (
        f"CASE SHOWN TO STUDENT\n{case_text}\n\n"
        f"FULL QUESTION SHOWN TO STUDENT\n{question_text}\n\n"
        f"STUDENT'S FULL ANSWER\n{student_answer}"
    )


@dataclass(frozen=True)
class SummaryResult:
    text: str
    provider: str
    model: str


class SummaryClient:
    def __init__(self, mode: str | None = None, model: str | None = None) -> None:
        self.mode = (mode or os.getenv("LLM_MODE", "demo")).strip().casefold()
        self.model = (model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")).strip()
        self.api_key_secret = os.getenv("OPENAI_API_KEY_SECRET", "KEY_OPENAI").strip()
        self.max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "800"))
        self.timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45"))
        self.generation_lease_seconds = int(
            os.getenv("OPENAI_GENERATION_LEASE_SECONDS", "120")
        )

    def _api_key(self) -> str:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if key:
            return key
        try:
            import streamlit as st

            key = str(st.secrets.get(self.api_key_secret, "")).strip()
        except (FileNotFoundError, KeyError, AttributeError):
            key = ""
        if not key:
            raise RuntimeError(
                "No OpenAI API key was found. Set OPENAI_API_KEY or the "
                f"Streamlit secret {self.api_key_secret}."
            )
        return key

    def summarize(
        self,
        *,
        case_text: str,
        question_text: str,
        student_answer: str,
    ) -> SummaryResult:
        if self.mode == "demo":
            return SummaryResult(demo_summary(student_answer), "demo", "demo")
        if self.mode != "openai":
            raise ValueError("LLM_MODE must be either 'demo' or 'openai'.")

        from openai import OpenAI

        prompt = build_prompt(
            case_text=case_text,
            question_text=question_text,
            student_answer=student_answer,
        )
        response = OpenAI(
            api_key=self._api_key(),
            timeout=self.timeout_seconds,
        ).responses.create(
            model=self.model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=prompt,
            max_output_tokens=self.max_output_tokens,
            store=False,
        )
        summary = normalize_bullets(response.output_text)
        if not summary:
            raise RuntimeError("The model returned an empty summary.")
        return SummaryResult(summary, "openai", self.model)

