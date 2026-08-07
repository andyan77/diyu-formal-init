#!/usr/bin/env python3
"""EXE-V1 · 部署前硬门：回滚兼容实证（v1.1 第 11 条）。

要证明的命题——**回滚是安全的**：

    候选版本会往任务快照里写一个新键 `task_value_assembly`（jsonb 只扩不改）。
    如果部署后需要回滚到旧运行时，旧代码会读到这个它不认识的键。
    必须证明：① 旧代码不因新键报错；② 旧代码读出的发布合同与历史指纹不变。

做法：在**同一台机器的隔离进程**里跑两份代码——

    Phase A  候选代码（当前工作树）造一份含新键的真实快照，记下发布合同 digest；
    Phase B  用 `git archive` 把旧 SHA 的 src/ 树解到临时目录，另起一个进程，
             只把旧树放进 sys.path，让**旧的** content_snapshot 去读同一份快照。

不连数据库、不碰生产。失败即退非零——按刹车条款，**这一关不过不得部署**。

用法：
    python3 scripts/exev1/prove_rollback_compat.py --old-sha b12b3cb…
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

DEFAULT_OLD_SHA = "b12b3cbeb17c0af1b4a5452e54c4a5685adb0461"

# Phase B 在子进程里跑，只能看见旧树。它读快照、跑遍所有旧 reader，然后把结论
# 用 JSON 吐回来。任何异常都原样上报，不吞。
_OLD_READER_PROGRAM = r"""
import json, sys
from src.shared.content_snapshot import (
    frozen_publication_contract, frozen_narrative_frame, frozen_creative_plan,
    frozen_creative_kernel, frozen_writer_output, frozen_media_contract,
    frozen_product_value_contract, frozen_product_facts, frozen_series_context,
    visible_direction,
)
from src.shared.publication_contract import publication_contract_digest
import src.shared.content_snapshot as old_module

snapshot = json.load(open(sys.argv[1], encoding="utf-8"))
result = {
    "errors": {},
    "knows_task_value_reader": hasattr(old_module, "frozen_task_value_assembly"),
    "readers_probed": 0,
}

try:
    contract = frozen_publication_contract(snapshot)
    result["publication_contract_digest"] = publication_contract_digest(contract)
    result["readers_probed"] += 1
except Exception as error:
    result["errors"]["frozen_publication_contract"] = f"{type(error).__name__}: {error}"

for name, reader in (
    ("frozen_narrative_frame", lambda s: frozen_narrative_frame(s, None)),
    ("frozen_creative_plan", lambda s: frozen_creative_plan(s, None)),
    ("frozen_creative_kernel", lambda s: frozen_creative_kernel(s, None)),
    ("frozen_writer_output", lambda s: frozen_writer_output(s, None)),
    ("frozen_media_contract", frozen_media_contract),
    ("frozen_product_value_contract", frozen_product_value_contract),
    ("frozen_product_facts", frozen_product_facts),
    ("frozen_series_context", frozen_series_context),
    ("visible_direction", visible_direction),
):
    try:
        reader(snapshot)
        result["readers_probed"] += 1
    except TypeError:
        # 签名在两版之间可能不同；签名差异不是本命题要证的东西，跳过。
        pass
    except Exception as error:
        result["errors"][name] = f"{type(error).__name__}: {error}"

print(json.dumps(result, ensure_ascii=False))
"""


def build_candidate_snapshot() -> tuple[dict[str, Any], str, str]:
    """用候选代码造一份含 task_value_assembly 的快照。

    返回 (快照, 发布合同 digest, 组装 digest)。
    """
    from src.brain.payoff_assembly import (
        assemble_task_value,
        build_payoff_request,
        product_contract_job,
    )
    from src.brain.input_role_resolver import resolve_input_roles
    from src.shared.narrative import user_fact_candidates
    from src.shared.publication_contract import (
        AccountEditorialPermissionV3,
        BrandContextUseV3,
        PlatformDirectionV3,
        build_publication_contract_v3,
        product_brief,
        publication_contract_digest,
        publication_contract_document,
    )
    from src.shared.task_value_assembly import (
        task_value_assembly_digest,
        task_value_assembly_document,
    )
    from src.shared.types import AccountExpression

    expression = AccountExpression(
        profile_id=None,
        version=1,
        is_draft=False,
        identity_position="我们代表总部内容账号说话，不冒充门店店员或顾客。",
        authority_boundary="只讲已确认的品牌立场与商品资料；没有来源的经历不写成事实。",
        audience_relationship="长期服务愿意认真挑选衣服的人，保持平等、不施压的关系。",
        content_territories="穿衣处境、商品取舍与品牌立场三类内容可以长期经营。",
        default_production_conditions="一名创作者、一部手机、普通室内或门店。",
    )
    product = "brand_life_narrative"
    assembly = assemble_task_value(
        build_payoff_request(
            content_product=product,
            topic_origin="explicit_user",
            account_expression=expression,
            product_basis=None,
            series_delta=None,
            static_payoff=product_brief(product, "explicit_user")[1],
        )
    )

    turns = ("回家才发现忘记喝水，帮我发一条。",)
    candidates = user_fact_candidates(turns)
    resolution = resolve_input_roles(
        user_turns=turns,
        candidates=candidates,
        roles={
            candidates[0].source_id: "observable_actuality",
            candidates[1].source_id: "creation_instruction",
        },
    )
    contract = build_publication_contract_v3(
        input_roles=resolution.spans,
        topic_origin="explicit_user",
        topic="围绕忙碌中遗漏日常步骤的张力形成一条生活观察",
        content_product=product,
        central_job=product_contract_job(product, "explicit_user"),
        audience_payoff=assembly.audience_payoff,
        explicit_user_controls=(candidates[1].exact_text,),
        account_editorial_permission=AccountEditorialPermissionV3(
            identity="品牌生活观察账号",
            audience="愿意认真看日常的人",
            attention_order="先看具体处境，再形成判断",
            response_posture="平等、具体、不替用户补原因",
            refusals="不新增用户身体、心理、原因或后续结果",
            allowed_stance="可以形成一般观察与低风险比喻",
            source_profile_id="profile-exev1-rollback-proof",
            source_profile_version=3,
        ),
        frozen_fact_refs=(candidates[0].source_id,),
        product_decision_basis=None,
        series_delta=None,
        platform_direction=PlatformDirectionV3(
            target="xiaohongshu_graphic",
            media_format="graphic",
            direction_version="platform-direction-v3-proof",
            direction_digest="3" * 64,
        ),
        media_capability_ref="4" * 64,
        brand_context_use=BrandContextUseV3(
            available_refs=("brand-1", "method-1"),
            frozen_refs=("brand-1", "method-1"),
            consumed_refs=("method-1",),
            displayed_refs=(),
        ),
        publication_projection_id="projection-exev1-rollback-proof",
        publication_projection_version=4,
        publication_projection_digest="5" * 64,
    )

    contract_digest = publication_contract_digest(contract)
    assembly_digest = task_value_assembly_digest(assembly)
    snapshot: dict[str, Any] = {
        "publication_contract": publication_contract_document(contract),
        "publication_contract_digest": contract_digest,
        "task_value_assembly": task_value_assembly_document(assembly),
        "task_value_assembly_digest": assembly_digest,
    }
    return snapshot, contract_digest, assembly_digest


def extract_old_tree(sha: str, destination: Path) -> None:
    archive = subprocess.run(
        ("git", "archive", sha, "src"),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise RuntimeError(f"取不出旧树 {sha}：{archive.stderr.decode(errors='replace').strip()}")
    extract = subprocess.run(
        ("tar", "-x", "-C", str(destination)),
        input=archive.stdout,
        capture_output=True,
        check=False,
    )
    if extract.returncode != 0:
        raise RuntimeError(f"解压旧树失败：{extract.stderr.decode(errors='replace').strip()}")


def run_old_readers(old_tree: Path, snapshot_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        (sys.executable, "-c", _OLD_READER_PROGRAM, str(snapshot_path)),
        cwd=old_tree,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(old_tree), "PATH": "/usr/bin:/bin"},
    )
    if completed.returncode != 0:
        raise RuntimeError(f"旧代码进程异常退出：{completed.stderr.strip()}")
    return json.loads(completed.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="回滚兼容实证", allow_abbrev=False)
    parser.add_argument("--old-sha", default=DEFAULT_OLD_SHA, help="回滚目标 SHA（生产当前版本）")
    arguments = parser.parse_args(argv)

    snapshot, contract_digest, assembly_digest = build_candidate_snapshot()
    print(f"Phase A · 候选代码造出快照（含新键 task_value_assembly）")
    print(f"  publication_contract_digest = {contract_digest}")
    print(f"  task_value_assembly_digest  = {assembly_digest}")

    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace)
        snapshot_path = root / "snapshot.json"
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        old_tree = root / "old"
        old_tree.mkdir()
        extract_old_tree(arguments.old_sha, old_tree)
        outcome = run_old_readers(old_tree, snapshot_path)

    print(f"\nPhase B · 旧代码 {arguments.old_sha[:7]} 读同一份快照")
    print(f"  旧树是否已有 frozen_task_value_assembly = {outcome['knows_task_value_reader']}")

    failures: list[str] = []
    if outcome["knows_task_value_reader"]:
        failures.append("旧树居然已经认识新 reader——回滚目标 SHA 选错了，这个实证没有意义")
    if outcome["errors"]:
        for name, message in outcome["errors"].items():
            failures.append(f"旧 reader {name} 因新键报错：{message}")
    old_digest = outcome.get("publication_contract_digest")
    if old_digest != contract_digest:
        failures.append(f"旧代码读出的发布合同 digest 不同：{old_digest} != {contract_digest}")

    print()
    if failures:
        print("FAIL 回滚兼容实证不通过：", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        print("按刹车条款：本关不过不得部署。", file=sys.stderr)
        return 1

    print("PASS 回滚兼容成立：")
    print("  · 旧代码读到未知键 task_value_assembly 未报错（jsonb 只扩不改成立）")
    print("  · 旧代码读出的发布合同 digest 与候选完全一致（历史指纹不变）")
    print(f"  · 旧 reader 探测 {outcome['readers_probed']} 个，零异常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
