from progettare.engine.criteria import Criterion, parse_criteria


def test_plain_acceptance_header_with_dash_bullets() -> None:
    body = (
        "Some context first.\n"
        "\n"
        "Acceptance:\n"
        "- The harness is read only\n"
        "- Every call goes through nare\n"
    )

    criteria = parse_criteria(body)

    assert criteria == (
        Criterion(id="c1", text="The harness is read only"),
        Criterion(id="c2", text="Every call goes through nare"),
    )


def test_heading_form() -> None:
    body = "## Acceptance\n- One thing\n- Another thing\n"

    criteria = parse_criteria(body)

    assert criteria == (
        Criterion(id="c1", text="One thing"),
        Criterion(id="c2", text="Another thing"),
    )


def test_bold_acceptance_criteria_form() -> None:
    body = "**Acceptance criteria:**\n- First\n- Second\n"

    criteria = parse_criteria(body)

    assert criteria == (
        Criterion(id="c1", text="First"),
        Criterion(id="c2", text="Second"),
    )


def test_star_bullets() -> None:
    body = "Acceptance:\n* First\n* Second\n"

    criteria = parse_criteria(body)

    assert criteria == (
        Criterion(id="c1", text="First"),
        Criterion(id="c2", text="Second"),
    )


def test_blank_lines_inside_the_section() -> None:
    body = "Acceptance:\n- First\n\n- Second\n"

    criteria = parse_criteria(body)

    assert criteria == (
        Criterion(id="c1", text="First"),
        Criterion(id="c2", text="Second"),
    )


def test_section_ends_at_next_heading() -> None:
    body = "Acceptance:\n- Kept\n\n## Later\n- Not kept\n"

    criteria = parse_criteria(body)

    assert criteria == (Criterion(id="c1", text="Kept"),)


def test_section_ends_at_non_bullet_line() -> None:
    body = "Acceptance:\n- Kept\nSome closing note.\n- Not kept\n"

    criteria = parse_criteria(body)

    assert criteria == (Criterion(id="c1", text="Kept"),)


def test_order_is_stable_across_calls() -> None:
    body = "Acceptance:\n- Second goes second\n- First goes first\n"

    first = parse_criteria(body)
    second = parse_criteria(body)

    assert first == second
    assert first == (
        Criterion(id="c1", text="Second goes second"),
        Criterion(id="c2", text="First goes first"),
    )


def test_ids_run_from_c1_to_cn() -> None:
    body = "Acceptance:\n- One\n- Two\n- Three\n"

    criteria = parse_criteria(body)

    assert [criterion.id for criterion in criteria] == ["c1", "c2", "c3"]


def test_no_header_returns_empty_tuple() -> None:
    body = "Some prose.\n- A stray bullet\nMore prose.\n"

    assert parse_criteria(body) == ()


def test_header_with_no_bullets_returns_empty_tuple() -> None:
    body = "Acceptance:\nSome prose instead of bullets.\n"

    assert parse_criteria(body) == ()


def test_header_with_trailing_text_is_not_a_header() -> None:
    body = "Acceptance criteria for the intake stage:\n- One\n"

    assert parse_criteria(body) == ()


def test_header_is_case_insensitive() -> None:
    body = "acceptance criteria:\n- One\n"

    criteria = parse_criteria(body)

    assert criteria == (Criterion(id="c1", text="One"),)
