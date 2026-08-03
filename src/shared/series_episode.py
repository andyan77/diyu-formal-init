from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from src.shared.errors import DomainError
from src.shared.types import SeriesContext

SERIES_EPISODE_CONTRACT_VERSION = "series-episode-contract-v1"


@dataclass(frozen=True)
class SeriesEpisodeContractV1:
    contract_version: str
    prior_episode_facts: tuple[str, ...]
    prior_judgments: tuple[str, ...]
    current_episode_job: str
    required_new_judgment: str
    series_position: int
    topic_origin: str


def build_series_episode_contract(
    context: SeriesContext | None,
    *,
    topic_origin: str,
    current_episode_job: str,
) -> SeriesEpisodeContractV1 | None:
    if context is None:
        return None
    contract = SeriesEpisodeContractV1(
        contract_version=SERIES_EPISODE_CONTRACT_VERSION,
        prior_episode_facts=tuple(
            dict.fromkeys(
                fact
                for entry in context.prior_entries
                for fact in entry.prior_facts
            )
        ),
        prior_judgments=tuple(
            entry.prior_judgment or _legacy_outline_judgment(entry.outline)
            for entry in context.prior_entries
        ),
        current_episode_job=current_episode_job.strip(),
        required_new_judgment=("在冻结前情上形成一个此前没有表达过、并且完成本篇任务的新判断"),
        series_position=context.target_position,
        topic_origin=topic_origin,
    )
    assert_series_episode_contract(contract)
    return contract


def _legacy_outline_judgment(outline: str) -> str:
    """Read one bounded legacy judgment without treating a whole artifact as it."""

    first_line = next(
        (line.strip() for line in outline.splitlines() if line.strip()),
        "",
    )
    if not first_line:
        raise DomainError("系列前情缺少可冻结的判断")
    return first_line


def series_episode_contract_document(
    contract: SeriesEpisodeContractV1,
) -> dict[str, object]:
    return {
        "contract_version": contract.contract_version,
        "prior_episode_facts": list(contract.prior_episode_facts),
        "prior_judgments": list(contract.prior_judgments),
        "current_episode_job": contract.current_episode_job,
        "required_new_judgment": contract.required_new_judgment,
        "series_position": contract.series_position,
        "topic_origin": contract.topic_origin,
    }


def series_episode_contract_digest(contract: SeriesEpisodeContractV1) -> str:
    return hashlib.sha256(
        json.dumps(
            series_episode_contract_document(contract),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def series_episode_contract_from_document(
    value: object,
) -> SeriesEpisodeContractV1:
    if not isinstance(value, Mapping):
        raise DomainError("内容任务冻结的系列任务无效")
    try:
        prior_facts = value["prior_episode_facts"]
        prior_judgments = value["prior_judgments"]
        if not isinstance(prior_facts, list) or not isinstance(prior_judgments, list):
            raise TypeError
        contract = SeriesEpisodeContractV1(
            contract_version=str(value["contract_version"]),
            prior_episode_facts=tuple(str(item) for item in prior_facts),
            prior_judgments=tuple(str(item) for item in prior_judgments),
            current_episode_job=str(value["current_episode_job"]),
            required_new_judgment=str(value["required_new_judgment"]),
            series_position=int(value["series_position"]),
            topic_origin=str(value["topic_origin"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("内容任务冻结的系列任务无效") from exc
    assert_series_episode_contract(contract)
    return contract


def assert_series_episode_contract(contract: SeriesEpisodeContractV1) -> None:
    if (
        contract.contract_version != SERIES_EPISODE_CONTRACT_VERSION
        or not contract.current_episode_job
        or not contract.required_new_judgment
        or contract.series_position < 1
        or contract.topic_origin not in {"explicit_user", "system_selected"}
        or (contract.series_position > 1 and not contract.prior_judgments)
    ):
        raise DomainError("内容任务冻结的系列任务无效")
