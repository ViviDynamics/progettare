from progettare.engine.criteria import (
    Conflict,
    Criterion,
    find_conflicts,
    parse_criteria,
)


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


def test_identical_text_across_ids_is_a_duplicate() -> None:
    criteria = (
        Criterion(id="c1", text="Ship the harness"),
        Criterion(id="c2", text="Ship the harness"),
    )

    conflicts = find_conflicts(criteria)

    assert conflicts == (
        Conflict(
            kind="duplicate",
            first_id="c1",
            second_id="c2",
            detail="ship the harness",
        ),
    )


def test_near_duplicate_with_different_casing_and_whitespace() -> None:
    criteria = (
        Criterion(id="c1", text="Ship the harness"),
        Criterion(id="c2", text="  ship   THE\tharness "),
    )

    conflicts = find_conflicts(criteria)

    assert conflicts == (
        Conflict(
            kind="duplicate",
            first_id="c1",
            second_id="c2",
            detail="ship the harness",
        ),
    )


def test_different_text_is_not_a_conflict() -> None:
    criteria = (
        Criterion(id="c1", text="Ship the harness"),
        Criterion(id="c2", text="Sink the harness"),
    )

    assert find_conflicts(criteria) == ()


def test_setting_conflict_via_colon_and_equals_forms() -> None:
    criteria = (
        Criterion(id="c1", text="max_questions: 12"),
        Criterion(id="c2", text="max_questions=8"),
    )

    conflicts = find_conflicts(criteria)

    assert conflicts == (
        Conflict(
            kind="setting",
            first_id="c1",
            second_id="c2",
            detail="max_questions: '12' vs '8'",
        ),
    )


def test_same_key_same_value_is_not_a_conflict() -> None:
    criteria = (
        Criterion(id="c1", text="max_questions: 12"),
        Criterion(id="c2", text="max_questions=12"),
    )

    assert find_conflicts(criteria) == ()


def test_setting_keys_compare_casefolded() -> None:
    criteria = (
        Criterion(id="c1", text="Max_Questions: 12"),
        Criterion(id="c2", text="max_questions=8"),
    )

    conflicts = find_conflicts(criteria)

    assert conflicts == (
        Conflict(
            kind="setting",
            first_id="c1",
            second_id="c2",
            detail="max_questions: '12' vs '8'",
        ),
    )


def test_multiple_keys_per_criterion() -> None:
    criteria = (
        Criterion(id="c1", text="max_questions: 12 size: large"),
        Criterion(id="c2", text="size: small"),
    )

    conflicts = find_conflicts(criteria)

    assert conflicts == (
        Conflict(
            kind="setting",
            first_id="c1",
            second_id="c2",
            detail="size: 'large' vs 'small'",
        ),
    )


def test_two_differing_keys_yield_one_conflict_naming_the_first_key() -> None:
    criteria = (
        Criterion(id="c1", text="max_questions: 12 size: large"),
        Criterion(id="c2", text="max_questions: 8 size: small"),
    )

    conflicts = find_conflicts(criteria)

    assert conflicts == (
        Conflict(
            kind="setting",
            first_id="c1",
            second_id="c2",
            detail="max_questions: '12' vs '8'",
        ),
    )


def test_clean_list_and_empty_input_return_empty_tuple() -> None:
    clean = (
        Criterion(id="c1", text="Ship the harness"),
        Criterion(id="c2", text="max_questions: 12"),
    )

    assert find_conflicts(clean) == ()
    assert find_conflicts(()) == ()


def test_duplicates_come_before_setting_conflicts() -> None:
    criteria = (
        Criterion(id="c1", text="max_questions: 12"),
        Criterion(id="c2", text="Same words here"),
        Criterion(id="c3", text="max_questions: 8"),
        Criterion(id="c4", text="Same words here"),
    )

    conflicts = find_conflicts(criteria)

    assert conflicts == (
        Conflict(
            kind="duplicate",
            first_id="c2",
            second_id="c4",
            detail="same words here",
        ),
        Conflict(
            kind="setting",
            first_id="c1",
            second_id="c3",
            detail="max_questions: '12' vs '8'",
        ),
    )


def test_duplicate_detail_truncates_to_sixty_characters() -> None:
    long_text = "x" * 70
    criteria = (
        Criterion(id="c1", text=long_text),
        Criterion(id="c2", text=long_text),
    )

    conflicts = find_conflicts(criteria)

    assert conflicts[0].detail == "x" * 60 + "..."
