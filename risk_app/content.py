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
# QUESTION 2: exact assessment/correction wording and supplied responses from
# the current Qualtrics QSF (QID8/QID7 and QID597/QID596/QID595/QID328).
# Source case 1 is omitted, so source cases 2-5 map to app cases 1-4.
# ---------------------------------------------------------------------------
ASSESSMENT_QUESTION = (
    "How well do you think that this response answers the question concerning "
    "the case?"
)

ASSESSMENT_OPTIONS = (
    "Totally right: it would get full marks",
    "There is something along the right lines in the response, but requires "
    "some addition or modification",
    "Wrong",
)

CORRECTION_QUESTION = (
    "Explain your answer, specifying, if relevant, what needs to be added, "
    "corrected or changed to obtain a perfect response."
)

PROVIDED_ANSWERS: dict[int, str] = {
    1: (
        "i. Probability weighting function.\n\n"
        "ii. Subjects exhibit risk aversion when choosing a sure €500 over a "
        "50% chance of winning €1000. This preference is explained by the "
        "probability weighting function, which suggests that individuals "
        "overweight small probabilities and underweight moderate to high "
        "probabilities. In this case, the 50% probability of winning €1000 is "
        "psychologically perceived as riskier than the sure gain of €500, leading "
        "to risk-averse behavior.\n\n"
        "Despite the apparent risk aversion in the first scenario, individuals "
        "might buy lottery tickets. The probability weighting function also "
        "explains this apparent inconsistency. Lottery tickets typically involve "
        "small costs, and the low probability of winning a large sum is "
        "overweighted, making the potential gain more psychologically significant "
        "than the probable loss of the ticket price. The excitement of the small "
        "probability of winning a substantial amount can override the rational "
        "evaluation of expected value.\n\n"
        "The probability weighting function in Prospect Theory, with its "
        "characteristic overweighting of small probabilities, explains the "
        "preference for a sure gain in a moderate-risk scenario. However, the same "
        "function, coupled with the context of small costs and potential large "
        "gains, elucidates the decision to buy lottery tickets despite the "
        "unfavorable expected value. The nonlinear weighting of probabilities "
        "captures the psychological nuances influencing these seemingly "
        "contradictory choices."
    ),
    2: (
        "i. Probability weighting function.\n\n"
        "ii. The preference for a 50% chance of losing €1000 over a sure loss of "
        "€500 is explained by the probability weighting function. Prospect Theory "
        "suggests that individuals tend to overweight small probabilities and "
        "underweight moderate to high probabilities. In this case, the 50% chance "
        "of a larger loss is psychologically perceived as less severe due to the "
        "overweighting of small probabilities.\n\n"
        "On the other hand, individuals often buy car insurance, which might seem "
        "contradictory given the risk-seeking behavior observed earlier. However, "
        "the decision to purchase insurance can be explained by the context of "
        "small, regular premiums and the potential for significant losses. The "
        "small probability of a large loss (such as a car accident) is "
        "overweighted, making the potential loss more psychologically significant "
        "than the certain, smaller premium payments.\n\n"
        "The probability weighting function in Prospect Theory, with its tendency "
        "to overweight small probabilities, explains the preference for a risky "
        "bet when framed as a potential loss. However, when considering the "
        "decision to buy insurance, the same probability weighting function, "
        "coupled with the context of small, regular costs and the potential for "
        "significant losses, elucidates the decision to insure against unfavorable "
        "events. The nonlinear weighting of probabilities captures the "
        "psychological nuances influencing these seemingly contradictory choices."
    ),
    3: (
        "i. Both.\n\n"
        "ii. The tendency to sell winning stocks too soon can be explained by the "
        "utility function, which exhibits diminishing sensitivity to gains. As a "
        "stock's value increases, the marginal utility of additional gains "
        "diminishes. Investors, influenced by Prospect Theory, may decide to "
        "\"realize gains\" by selling winning stocks early to secure the perceived "
        "gains, driven by a desire for the psychological comfort of locking in "
        "profits.\n\n"
        "The inclination to sell losing stocks too late is also explained by the "
        "utility function, particularly the phenomenon of loss aversion. Prospect "
        "Theory suggests that individuals are more sensitive to losses than gains. "
        "Investors might delay selling losing stocks, hoping for a rebound, driven "
        "by the reluctance to accept a realized loss. This behavior is a "
        "manifestation of loss aversion, as the pain of realizing a loss is "
        "psychologically more impactful than the potential for future gains.\n\n"
        "The probability weighting function contributes to this behavior by "
        "influencing risk perception. Investors may overweight the probability of "
        "a losing stock rebounding, leading them to hold onto losing positions in "
        "the hope of recovering losses. This overweighting of small probabilities "
        "can delay the decision to sell, especially when the stock has experienced "
        "a decline.\n\n"
        "The combination of the utility function's diminishing sensitivity to "
        "gains and loss aversion, along with the probability weighting function's "
        "influence on risk perception, explains the empirical finding of investors "
        "selling winning stocks too soon and selling losing stocks too late. "
        "Prospect Theory provides a behavioral framework that captures the "
        "psychological biases influencing these selling decisions, even when "
        "controlling for subsequent stock performance and tax considerations."
    ),
    4: (
        "i. Probability weighting function.\n\n"
        "ii. The observed pattern in certainty equivalents aligns with the "
        "probability weighting function, a core component of Prospect Theory that "
        "reflects how individuals subjectively evaluate and weigh probabilities.\n\n"
        "Certainty equivalents for low-probability gains (e.g., 5%) are higher than "
        "the corresponding expected values, indicating an overweighting of small "
        "probabilities. In these cases, individuals seem to value the small chance "
        "of a large gain more than traditional expected utility theory would "
        "suggest.\n\n"
        "Certainty equivalents for moderate-probability gains (e.g., 50%) are lower "
        "than the corresponding expected values, reflecting an underweighting of "
        "moderate probabilities. Prospect Theory implies that individuals may be "
        "risk-averse in this range, leading to a preference for less risky "
        "alternatives.\n\n"
        "For losses, certainty equivalents show a similar pattern. The increasing "
        "negative values indicate loss aversion – individuals are more sensitive "
        "to losses than equivalent gains. The diminishing sensitivity to losses "
        "also implies that the reduction in certainty equivalent is less than the "
        "proportional increase in loss probability.\n\n"
        "The empirical pattern of certainty equivalents for different probability "
        "bets aligns with Prospect Theory's probability weighting function. The "
        "overweighting of small probabilities for gains and underweighting of "
        "moderate probabilities, combined with diminishing sensitivity to losses "
        "and loss aversion, offers a behavioral explanation for the observed "
        "values. This pattern reflects how individuals subjectively assess and "
        "respond to the probabilities associated with potential gains and losses, "
        "deviating from the predictions of classical expected utility theory."
    ),
}


def full_review_question(case_number: int) -> str:
    return (
        f"{FULL_CASE_QUESTION}\n\n"
        "The following response to the questions has been provided:\n\n"
        f"{PROVIDED_ANSWERS[case_number]}\n\n"
        f"{ASSESSMENT_QUESTION}\n\n{CORRECTION_QUESTION}"
    )


def format_full_review_answer(assessment_answer: str, correction_answer: str) -> str:
    return (
        f"Assessment: {assessment_answer.strip()}\n\n"
        f"Explanation and correction: {correction_answer.strip()}"
    )

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
NAME_QUESTION = "Please enter your full name"
CODE_QUESTION = "Please enter your participant code"

SUMMARY_REVIEW_TEXT = (
    "Here is a bullet-point summary of your explanation. Please check that it "
    "captures what you intended. You can confirm it or modify the bullet points "
    "before continuing."
)


@dataclass(frozen=True)
class CaseItem:
    case_number: int
    question_number: int
    question_type: str


def build_case_items(assigned_cases: list[int]) -> list[CaseItem]:
    return [
        CaseItem(
            case_number=case_number,
            question_number=position,
            question_type="original" if position == 1 else "review",
        )
        for position, case_number in enumerate(assigned_cases, start=1)
    ]

