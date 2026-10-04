from progettare.engine.clarifications import Clarification, extract_clarifications
from progettare.engine.issue_fetch import Comment


def test_three_question_lines_pair_in_order_with_three_answers() -> None:
    comment = Comment(
        author="octo",
        created_at="2026-10-01T10:00:00Z",
        body="Q: One?\nQ: Two?\nQ: Three?\nA: first\nA: second\nA: third\n",
    )

    clarifications = extract_clarifications((comment,))

    assert clarifications == (
        Clarification(
            question="One?",
            answer="first",
            source="comment by octo on 2026-10-01T10:00:00Z",
        ),
        Clarification(
            question="Two?",
            answer="second",
            source="comment by octo on 2026-10-01T10:00:00Z",
        ),
        Clarification(
            question="Three?",
            answer="third",
            source="comment by octo on 2026-10-01T10:00:00Z",
        ),
    )


def test_question_comment_pairs_with_later_answer_comment() -> None:
    first = Comment(author="octo", created_at="2026-10-01T10:00:00Z", body="Q: One?\n")
    second = Comment(
        author="octo", created_at="2026-10-02T10:00:00Z", body="A: first\n"
    )

    clarifications = extract_clarifications((first, second))

    assert clarifications == (
        Clarification(
            question="One?",
            answer="first",
            source="comment by octo on 2026-10-01T10:00:00Z",
        ),
    )


def test_one_answer_between_two_questions_leaves_the_second_unanswered() -> None:
    first = Comment(
        author="octo",
        created_at="2026-10-01T10:00:00Z",
        body="Q: One?\nQ: Two?\n",
    )
    second = Comment(
        author="octo", created_at="2026-10-02T10:00:00Z", body="A: first\n"
    )

    clarifications = extract_clarifications((first, second))

    assert clarifications == (
        Clarification(
            question="One?",
            answer="first",
            source="comment by octo on 2026-10-01T10:00:00Z",
        ),
        Clarification(
            question="Two?",
            answer=None,
            source="comment by octo on 2026-10-01T10:00:00Z",
        ),
    )


def test_blockquote_and_bold_prefixes_are_stripped() -> None:
    comment = Comment(
        author="octo",
        created_at="2026-10-01T10:00:00Z",
        body="> **Q: What about the run dir?\n> A: it defaults to run\n",
    )

    clarifications = extract_clarifications((comment,))

    assert clarifications == (
        Clarification(
            question="What about the run dir?",
            answer="it defaults to run",
            source="comment by octo on 2026-10-01T10:00:00Z",
        ),
    )


def test_long_form_question_and_answer_markers() -> None:
    comment = Comment(
        author="octo",
        created_at="2026-10-01T10:00:00Z",
        body="Question: Why now?\nAnswer: Because.\n",
    )

    clarifications = extract_clarifications((comment,))

    assert clarifications == (
        Clarification(
            question="Why now?",
            answer="Because.",
            source="comment by octo on 2026-10-01T10:00:00Z",
        ),
    )


def test_comment_without_markers_produces_nothing() -> None:
    comment = Comment(
        author="octo",
        created_at="2026-10-01T10:00:00Z",
        body="Just a plain remark.\n",
    )

    assert extract_clarifications((comment,)) == ()


def test_answers_without_pending_questions_produce_nothing() -> None:
    comment = Comment(
        author="octo", created_at="2026-10-01T10:00:00Z", body="A: first\n"
    )

    assert extract_clarifications((comment,)) == ()


def test_empty_comments_tuple_gives_empty_tuple() -> None:
    assert extract_clarifications(()) == ()
