from __future__ import annotations

from dataclasses import dataclass


APP_TITLE = "Choice under Risk Assignment"

# ---------------------------------------------------------------------------
# CASES: source Word document cases 2-5, with source case 1 removed and the
# remaining cases renumbered 1-4 as requested.
# ---------------------------------------------------------------------------
CASES: dict[int, str] = {
    1: (
        "Many subjects exhibit, on the one hand, a preference for a sure €500 "
        "over a bet yielding €1000 with probability 50% and nothing otherwise, "
        "whilst, on the other hand, buying a lottery ticket."
    ),
    2: (
        "Many subjects exhibit, on the one hand, a preference for a bet yielding "
        "a loss of €1000 with probability 50% and nothing otherwise over a sure "
        "loss of €500, whilst, on the other hand, buying car insurance."
    ),
    3: (
        "A proven empirical finding is that investors tend to sell winning stocks "
        "(\"realise gains\") too soon and sell losing stocks (\"realise losses\") "
        "too late. This tendency persists even if one controls for subsequent stock "
        "performance and if there is a tax advantage from holding winning stocks "
        "for longer."
    ),
    4: (
        "The following is a common empirical pattern:\n\n"
        "- The certainty equivalent of a bet yielding €100 with probability 5% is around €14\n"
        "- The certainty equivalent of a bet yielding €100 with probability 50% is around €36\n"
        "- The certainty equivalent of a bet yielding €100 with probability 95% is around €78\n"
        "- The certainty equivalent of a bet yielding -€100 (i.e. a loss of €100) "
        "with probability 5% is around -€8\n"
        "- The certainty equivalent of a bet yielding -€100 (i.e. a loss of €100) "
        "with probability 50% is around -€42\n"
        "- The certainty equivalent of a bet yielding -€100 (i.e. a loss of €100) "
        "with probability 95% is around -€84."
    ),
}

# ---------------------------------------------------------------------------
# QUESTION TEXT: copied from the active Qualtrics questions QID2 and QID594.
# ---------------------------------------------------------------------------
ASSIGNMENT_CONTEXT = (
    "In this assignment, you will be asked to consider two cases from the file "
    "provided.\n\nThroughout this assignment, suppose that decision makers can be "
    "represented by Prospect Theory with a single (reference-dependent) utility "
    "function and a single probability weighting function. Each of the cases can "
    "be explained by a specific property or properties of one or both of the "
    "Prospect Theory components."
)

COMPONENT_QUESTION = (
    "i. Which of the Prospect Theory components – utility function, probability "
    "weighting function or both – plays a central role in explaining it?"
)

EXPLANATION_QUESTION = (
    "ii. Explain fully how the component or components identified in your previous "
    "answer can accommodate the behavior, identifying the specific property or "
    "properties of this component or components which are relevant. (If you think "
    "that no component specific to Prospect Theory is required to explain the "
    "behaviour, i.e. it can be accommodated by Expected Utility, then explain why.)"
)

FULL_CASE_QUESTION = f"{COMPONENT_QUESTION}\n\n{EXPLANATION_QUESTION}"


def format_full_student_answer(component_answer: str, explanation_answer: str) -> str:
    return f"i. {component_answer.strip()}\n\nii. {explanation_answer.strip()}"

# ---------------------------------------------------------------------------
# RESPONSE OPTIONS: copied from the active Qualtrics question QID2.
# ---------------------------------------------------------------------------
COMPONENT_OPTIONS = (
    "Utility function",
    "Probability weighting function",
    "Both",
    "Neither",
)

EMAIL_QUESTION = "Please enter your HEC e-mail address"
NAME_QUESTION = "Please enter your surname"
CODE_QUESTION = "Please enter your participant code"

SUMMARY_REVIEW_TEXT = (
    "Here is a bullet-point summary of your explanation. Please check that it "
    "captures what you intended. You can confirm it or modify the bullet points "
    "before continuing."
)


@dataclass(frozen=True)
class CaseItem:
    case_number: int


def build_case_items(assigned_cases: list[int]) -> list[CaseItem]:
    return [CaseItem(case_number) for case_number in assigned_cases]

