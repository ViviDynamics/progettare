"""Clarifying question extraction from issue comments."""

import re
from dataclasses import dataclass, replace

from progettare.engine.issue_fetch import Comment

_QUESTION_RE = re.compile(r"^q(?:uestion)?:(.*)$", re.IGNORECASE)
_ANSWER_RE = re.compile(r"^a(?:nswer)?:(.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class Clarification:
    question: str
    answer: str | None
    source: str


def extract_clarifications(comments: tuple[Comment, ...]) -> tuple[Clarification, ...]:
    clarifications: list[Clarification] = []
    for comment in comments:
        source = f"comment by {comment.author} on {comment.created_at}"
        questions, answers = _question_and_answer_lines(comment.body)
        paired = min(len(questions), len(answers))
        for index in range(paired):
            clarifications.append(
                Clarification(
                    question=questions[index], answer=answers[index], source=source
                )
            )
        for answer in answers[paired:]:
            _fill_earliest_unanswered(clarifications, answer)
        for question in questions[paired:]:
            clarifications.append(
                Clarification(question=question, answer=None, source=source)
            )
    return tuple(clarifications)


def _question_and_answer_lines(body: str) -> tuple[list[str], list[str]]:
    questions: list[str] = []
    answers: list[str] = []
    for line in body.splitlines():
        text = _strip_prefixes(line)
        question = _QUESTION_RE.match(text)
        answer = _ANSWER_RE.match(text)
        if question is not None:
            questions.append(question.group(1).strip())
        elif answer is not None:
            answers.append(answer.group(1).strip())
    return questions, answers


def _strip_prefixes(line: str) -> str:
    text = line.strip()
    while text.startswith(">") or text.startswith("**"):
        if text.startswith(">"):
            text = text[1:].lstrip()
        else:
            text = text[2:].lstrip()
    return text


def _fill_earliest_unanswered(clarifications: list[Clarification], answer: str) -> None:
    for index, clarification in enumerate(clarifications):
        if clarification.answer is None:
            clarifications[index] = replace(clarification, answer=answer)
            return
