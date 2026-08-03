from __future__ import annotations

from src.shared.product_references import (
    alias_index,
    has_partial_reference_list,
    resolve_literal_mentions,
)


def _aliases() -> dict[str, frozenset[str]]:
    return alias_index(
        (
            ("abc-123", ("abc-123", "小写编号商品")),
            ("ABC123", ("ABC123", "无连字符商品")),
            ("123456", ("123456", "纯数字商品")),
            ("款号一", ("款号一", "中文编号商品")),
            ("GD-UP-01", ("GD-UP-01", "基础上装")),
        )
    )


def test_literal_product_mentions_return_database_identity_without_rewriting() -> None:
    aliases = _aliases()
    for text, expected in (
        ("请围绕 abc-123 写一条", "abc-123"),
        ("请围绕 abc123 写一条", "ABC123"),
        ("请围绕 123456 写一条", "123456"),
        ("请围绕 款号一 写一条", "款号一"),
        ("请围绕 gd-up-01 写一条", "GD-UP-01"),
        ("请围绕 中文编号商品 写一条", "款号一"),
    ):
        resolution = resolve_literal_mentions(text, aliases)
        assert resolution.is_complete
        assert resolution.resolved_identities == {expected}


def test_near_identifiers_do_not_mint_product_identity() -> None:
    aliases = _aliases()
    for text in (
        "请围绕 abc-1234 写一条",
        "请围绕 Xabc-123 写一条",
        "请围绕 ABC123X 写一条",
        "请围绕 小写编号商品升级款 写一条",
        "请围绕 升级款小写编号商品 写一条",
    ):
        resolution = resolve_literal_mentions(text, aliases)
        assert not resolution.is_complete
        assert resolution.near_aliases


def test_mixed_reference_list_fails_all_or_none() -> None:
    aliases = _aliases()
    for text in (
        "请围绕 abc-123、完全未知商品 写一条",
        "请围绕 完全未知商品、abc-123 写一条",
        "请围绕 abc-123 和 完全未知商品 写一条",
        "请围绕 abc-123与完全未知商品 写一条",
    ):
        resolution = resolve_literal_mentions(text, aliases)
        assert resolution.resolved_identities == {"abc-123"}
        assert has_partial_reference_list(text, resolution.matches)


def test_complete_reference_list_resolves_every_literal_alias() -> None:
    aliases = _aliases()
    for text in (
        "请围绕 abc-123、ABC123 写一条",
        "请围绕 abc-123与中文编号商品 写一条",
        "请围绕 款号一及GD-UP-01 写一条",
    ):
        resolution = resolve_literal_mentions(text, aliases)
        assert not resolution.near_aliases
        assert not resolution.ambiguous_aliases
        assert not has_partial_reference_list(text, resolution.matches)
        assert len(resolution.resolved_identities) == 2


def test_duplicate_full_name_is_ambiguous() -> None:
    aliases = alias_index(
        (
            ("one", ("ONE", "重复名称")),
            ("two", ("TWO", "重复名称")),
        )
    )
    resolution = resolve_literal_mentions("请围绕 重复名称 写一条", aliases)
    assert resolution.ambiguous_aliases == ("重复名称",)
    assert not resolution.is_complete
