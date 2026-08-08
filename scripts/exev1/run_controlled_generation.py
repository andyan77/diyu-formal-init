#!/usr/bin/env python3
"""EXE-V1 · 受控真实生成（B 层 / S4 生产验证运行）。

**这个脚本会往生产写入真实内容并调用真实模型。** 因此它自带硬上限，
且只接受从文件传入的显式 scope——不做任何账号发现、不遍历租户。

运行位置：**生产容器内部**（用已部署镜像 + `/etc/diyu/app.env`）。
执行侧全程不接触任何凭据值：Settings 从容器环境自读。

硬边界（代码强制，不是口头约定）：
  · `--limit` 上限 3（B 层）/ 30（S4），超过即拒绝启动；
  · 只对传入的**单一** tenant/account/user 生成；
  · 不发布、不新增用户、不改画像/资料/权限——本脚本根本不调用那些接口；
  · 任一条生成抛异常即停止后续（两败即停由调用方按刹车条款处置）。

输出：
  stdout   只含安全字段的逐条结论 + 汇总（零正文、零画像、零 task UUID）
  --detail-out  逐条详单（含 task id 与正文）——**只能写进私有证据根**
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

ABSOLUTE_MAXIMUM = 30


def _load_scope(path: Path) -> dict[str, UUID]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {key: UUID(str(document[key])) for key in ("tenant_id", "brand_id", "account_id", "user_id")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="受控真实生成", allow_abbrev=False)
    parser.add_argument("--scope-file", type=Path, required=True)
    parser.add_argument("--seeds-file", type=Path, required=True, help="每行一个题目")
    parser.add_argument("--limit", type=int, required=True, help="本次生成条数上限")
    parser.add_argument("--detail-out", type=Path, required=True)
    parser.add_argument("--target", default="douyin_video")
    arguments = parser.parse_args(argv)

    if not 1 <= arguments.limit <= ABSOLUTE_MAXIMUM:
        print(f"FAIL --limit 必须在 1..{ABSOLUTE_MAXIMUM} 之间，收到 {arguments.limit}", file=sys.stderr)
        return 2

    from src.composition.bootstrap import build_content_service
    from src.gateway.api.settings import Settings
    from src.shared.content_snapshot import frozen_task_value_assembly
    from src.shared.types import TrustedScope

    settings = Settings.model_validate({})
    if settings.generator_mode != "deepseek":
        print(f"FAIL 期望真实模型，但 generator_mode = {settings.generator_mode}", file=sys.stderr)
        return 2

    identifiers = _load_scope(arguments.scope_file)
    scope = TrustedScope(**identifiers)  # type: ignore[arg-type]
    seeds = [line.strip() for line in arguments.seeds_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    seeds = seeds[: arguments.limit]

    service = build_content_service(settings)
    details: list[dict[str, Any]] = []
    stopped_early: str | None = None

    for index, seed in enumerate(seeds, start=1):
        try:
            created = service.create_from_weak_seed(scope, seed, target=arguments.target)
        except Exception as error:  # noqa: BLE001 —— 生产运行：一条失败必须可见且立即止步
            stopped_early = f"第 {index} 条抛出 {type(error).__name__}: {error}"
            break

        task_id = created.get("task_id") or created.get("id")
        snapshot = service._repository.load_content_context_snapshot(  # noqa: SLF001
            scope, UUID(str(task_id))
        ) if task_id else None
        assembly = frozen_task_value_assembly(snapshot) if isinstance(snapshot, dict) else None
        details.append(
            {
                "index": index,
                "task_id": str(task_id),
                "seed": seed,
                "payoff_origin": assembly.payoff_origin if assembly else None,
                "brand_relevance_path": assembly.brand_relevance_path if assembly else None,
                "payoff_degraded": assembly.payoff_degraded if assembly else None,
                "payoff_degradation_reason": assembly.payoff_degradation_reason if assembly else None,
                "ruleset_version": assembly.ruleset_version if assembly else None,
                "audience_payoff": assembly.audience_payoff if assembly else None,
                "raw_result_keys": sorted(created.keys()),
            }
        )
        safe_path = details[-1]["brand_relevance_path"] or "-"
        print(
            f"#{index:02d} origin={details[-1]['payoff_origin']} "
            f"path={safe_path} 降级={details[-1]['payoff_degraded']}"
        )

    arguments.detail_out.parent.mkdir(parents=True, exist_ok=True)
    arguments.detail_out.write_text(
        json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )

    print()
    print(f"生成条数 = {len(details)} / 上限 {arguments.limit}")
    if stopped_early:
        print(f"提前停止：{stopped_early}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
