from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class LiteralReferenceMatch:
    start: int
    end: int
    exact_text: str
    identities: frozenset[str]


@dataclass(frozen=True)
class LiteralReferenceResolution:
    resolved_identities: frozenset[str]
    ambiguous_aliases: tuple[str, ...]
    near_aliases: tuple[str, ...]
    matches: tuple[LiteralReferenceMatch, ...]

    @property
    def is_complete(self) -> bool:
        return bool(self.resolved_identities) and not self.ambiguous_aliases and not self.near_aliases


def alias_index(
    records: Sequence[tuple[str, Sequence[str]]],
) -> dict[str, frozenset[str]]:
    """Build one literal, case-folded alias index without normalizing identity."""

    aliases: dict[str, set[str]] = {}
    for identity, labels in records:
        for label in labels:
            if label:
                aliases.setdefault(label.casefold(), set()).add(identity)
    return {label: frozenset(identities) for label, identities in aliases.items()}


def resolve_literal_mentions(
    text: str,
    aliases: Mapping[str, frozenset[str]],
) -> LiteralReferenceResolution:
    """Resolve only complete literal mentions and expose near/ambiguous attempts.

    Case folding is comparison-only.  The function never applies compatibility
    normalization, SKU grammar, prefix completion, substring authorization or
    similarity.  Longest non-overlapping aliases win; the returned identities
    remain the caller's original database values.
    """

    candidates: list[LiteralReferenceMatch] = []
    near_candidates: list[tuple[int, int, str]] = []
    for folded_alias, identities in aliases.items():
        for start, end in _casefold_spans(text, folded_alias):
            exact = text[start:end]
            if _has_literal_boundaries(text, start, end):
                candidates.append(LiteralReferenceMatch(start, end, exact, identities))
            else:
                near_candidates.append((start, end, exact))

    selected: list[LiteralReferenceMatch] = []
    occupied: set[int] = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (-(item.end - item.start), item.start, item.end),
    ):
        span = set(range(candidate.start, candidate.end))
        if span & occupied:
            continue
        selected.append(candidate)
        occupied.update(span)
    selected.sort(key=lambda item: (item.start, item.end))

    ambiguous = tuple(
        dict.fromkeys(match.exact_text for match in selected if len(match.identities) != 1)
    )
    near_aliases = tuple(
        dict.fromkeys(
            exact
            for start, end, exact in near_candidates
            if not any(match.start <= start and end <= match.end for match in selected)
        )
    )
    resolved = frozenset(
        next(iter(match.identities))
        for match in selected
        if len(match.identities) == 1
    )
    return LiteralReferenceResolution(
        resolved_identities=resolved,
        ambiguous_aliases=ambiguous,
        near_aliases=near_aliases,
        matches=tuple(selected),
    )


def has_partial_reference_list(
    text: str,
    matches: Sequence[LiteralReferenceMatch],
) -> bool:
    """Detect a mixed explicit list that resolved only one side.

    Only punctuation lists, whitespace-delimited conjunctions, or a conjunction
    directly adjoining a resolved alias count as an explicit product list.  A
    conjunction elsewhere in ordinary prose does not mint product identity and
    does not turn the whole sentence into a product list.
    """

    if not matches:
        return False
    match_ranges = tuple((match.start, match.end) for match in matches)
    clause_start = 0
    for clause_end in (*_clause_boundaries(text), len(text)):
        clause_matches = tuple(
            match
            for match in matches
            if clause_start <= match.start and match.end <= clause_end
        )
        if clause_matches and _clause_has_partial_list(
            text,
            clause_start,
            clause_end,
            clause_matches,
            match_ranges,
        ):
            return True
        clause_start = clause_end + 1
    return False


def _clause_has_partial_list(
    text: str,
    clause_start: int,
    clause_end: int,
    clause_matches: Sequence[LiteralReferenceMatch],
    all_ranges: Sequence[tuple[int, int]],
) -> bool:
    connectors: list[int] = []
    for index in range(clause_start, clause_end):
        character = text[index]
        if character not in {"、", "与", "和", "及"}:
            continue
        if any(start <= index < end for start, end in all_ranges):
            continue
        left_space = index > clause_start and text[index - 1].isspace()
        right_space = index + 1 < clause_end and text[index + 1].isspace()
        adjoining_match = any(
            match.end == index or match.start == index + 1
            for match in clause_matches
        )
        if character == "、" or (left_space and right_space) or adjoining_match:
            connectors.append(index)
    if not connectors:
        return False

    boundaries = (clause_start, *(index + 1 for index in connectors), clause_end + 1)
    for start, stop in pairwise(boundaries):
        segment_stop = stop - 1 if stop - 1 in connectors else stop
        segment = text[start:segment_stop].strip()
        if not segment:
            return True
        if not any(start <= match.start and match.end <= segment_stop for match in clause_matches):
            return True
    return False


def _casefold_spans(text: str, folded_alias: str) -> tuple[tuple[int, int], ...]:
    if not folded_alias:
        return ()
    spans: list[tuple[int, int]] = []
    for start in range(len(text)):
        folded = ""
        for end in range(start + 1, len(text) + 1):
            folded += text[end - 1].casefold()
            if folded == folded_alias:
                spans.append((start, end))
                break
            if len(folded) >= len(folded_alias) or not folded_alias.startswith(folded):
                break
    return tuple(spans)


def _has_literal_boundaries(text: str, start: int, end: int) -> bool:
    return _is_identity_boundary(text[start - 1] if start else None) and _is_identity_boundary(
        text[end] if end < len(text) else None
    )


def _is_identity_boundary(character: str | None) -> bool:
    if character is None:
        return True
    if character in {"、", "与", "和", "及"}:
        return True
    if character in {"-", "_"}:
        return False
    return not character.isalnum()


def _clause_boundaries(text: str) -> tuple[int, ...]:
    return tuple(
        index
        for index, character in enumerate(text)
        if character in {"，", ",", "。", "；", ";", "!", "！", "?", "？", "\n"}
    )
