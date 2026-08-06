from sqlagent.surveyor.graph import _skill_md, domains_node, semantics_node


COLUMNS = {
    "films": [
        {"column_name": "film_id", "data_type": "integer", "is_nullable": "NO", "ordinal_position": 1},
        {"column_name": "title", "data_type": "text", "is_nullable": "NO", "ordinal_position": 2},
    ],
    "rentals": [
        {"column_name": "rental_id", "data_type": "integer", "is_nullable": "NO", "ordinal_position": 1},
        {"column_name": "film_id", "data_type": "integer", "is_nullable": "NO", "ordinal_position": 2},
    ],
}


class FakeSemanticsLLM:
    def chat_json(self, system, user, schema=None):
        if "document a PostgreSQL database" in system:
            return {
                "films": {"description": "Movie catalog.", "grain": "one row per film"},
                "rentals": {"description": "Rental events.", "grain": "one row per rental"},
                "unknown_table": {"description": "must be ignored"},
            }
        return {"catalog": ["films"], "rental_ops": ["rentals", "not_a_table"]}


def test_semantics_fallback_is_neutral_and_pk_derived() -> None:
    state = {"columns": COLUMNS, "primary_keys": {"films": ["film_id"]}}

    result = semantics_node(state, llm=None)

    assert result["llm_used"] is False
    assert result["semantics"]["films"]["grain"] == "one row per film_id"
    assert "warehouse" not in result["semantics"]["films"]["description"].lower()
    assert "orders" not in result["semantics"]["rentals"]["description"].lower()


def test_semantics_uses_llm_and_ignores_unknown_tables() -> None:
    state = {"columns": COLUMNS, "primary_keys": {}, "profiles": {}}

    result = semantics_node(state, llm=FakeSemanticsLLM())

    assert result["llm_used"] is True
    assert result["semantics"]["films"]["description"] == "Movie catalog."
    assert "unknown_table" not in result["semantics"]


def test_domains_fallback_groups_everything() -> None:
    result = domains_node({"columns": COLUMNS}, llm=None)

    assert result["domains"] == {"all": ["films", "rentals"]}


def test_domains_llm_groups_and_validates_tables() -> None:
    state = {"columns": COLUMNS, "semantics": {table: {"description": ""} for table in COLUMNS}}

    result = domains_node(state, llm=FakeSemanticsLLM())

    assert result["domains"] == {"catalog": ["films"], "rental_ops": ["rentals"]}


def test_skill_md_lists_dangerous_join_rules_generically() -> None:
    content = _skill_md("dvdrental", [{"left": "film.film_id", "right": "inventory.film_id", "reason": "one-to-many fanout", "required_action": "preaggregate inventory"}])

    assert "# dvdrental skill" in content
    assert "preaggregate inventory" in content
    assert "warehouse" not in content.lower()
    assert "orders" not in content.lower()
