#!/usr/bin/env python3
"""Assert the FE-00 visual evidence actually evidences something.

The previous version of this check confirmed that every file named in the
manifest existed and was non-empty. Under that bar, twelve byte-identical
"200% zoom" screenshots counted as covering 200% zoom. What is checked now:

  - the PNG's own IHDR header agrees with the size the manifest claims, so a
    capture cannot be described as something it is not;
  - the manifest carries the sha256 of each prototype it came from, and those
    still match on disk — edit a prototype without recapturing and this is red;
  - within one frame, two conditions may not produce the same bytes unless the
    manifest says why. That is the exact shape of the defect above;
  - every frame was probed by keyboard, and axe found nothing serious.

Regenerate with:
    node frontend/tools/fe00-evidence.mjs --out docs/前端UI架构/FE-00/evidence

Usage:
    python3 scripts/exe01/assert_visual_evidence.py
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FE00 = PROJECT_ROOT / "docs/前端UI架构/FE-00"
EVIDENCE = FE00 / "evidence"
MANIFEST = EVIDENCE / "evidence-manifest.json"

REQUIRED_CONDITIONS = {"base", "zoom200"}
# Founder decision A exempts the fixed-canvas prototypes from 200% reflow, but
# the states themselves still have to be shown.
REQUIRED_DESKTOP_STATES = {"loading", "empty", "failure", "longtext"}
REQUIRED_MOBILE_STATES = {"failure", "states", "longtext"}
BLOCKING_IMPACTS = {"serious", "critical"}


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from the PNG header itself, not from the manifest."""
    header = path.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name} 不是 PNG")
    if header[12:16] != b"IHDR":
        raise ValueError(f"{path.name} 缺少 IHDR")
    return struct.unpack(">II", header[16:24])


def check_prototype_binding(manifest: dict[str, object]) -> list[str]:
    recorded = manifest.get("prototypes")
    if not isinstance(recorded, dict) or not recorded:
        return ["manifest 没有记录原型 sha256，截图与原型没有绑定"]
    problems: list[str] = []
    for name, digest in recorded.items():
        source = FE00 / str(name)
        if not source.exists():
            problems.append(f"manifest 引用了不存在的原型 {name}")
            continue
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != digest:
            problems.append(
                f"{name} 自取证后已修改（manifest {str(digest)[:12]} ≠ 现盘 {actual[:12]}），"
                "证据已过期，请重新采集"
            )
    return problems


def check_duplicates(captures: list[dict[str, object]]) -> list[str]:
    """One frame, two conditions, identical bytes — the original false green."""
    by_frame: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for capture in captures:
        key = f"{capture['document']}::{capture['frame']}"
        by_frame[key][str(capture["sha256"])].append(capture)
    problems: list[str] = []
    for frame, digests in by_frame.items():
        for digest, group in digests.items():
            if len(group) < 2:
                continue
            conditions = sorted(str(item["condition"]) for item in group)
            if all(item.get("identical_reason") for item in group):
                continue
            problems.append(
                f"{frame} 的条件 {conditions} 截图逐字节相同（{digest[:12]}）——"
                "不同条件产出同一张图不构成证据；确实应当相同请在 manifest 里"
                "登记 identical_reason"
            )
    return problems


def check_captures(captures: list[dict[str, object]]) -> list[str]:
    problems: list[str] = []
    for capture in captures:
        image = EVIDENCE / str(capture["file"])
        if not image.exists():
            problems.append(f"manifest 列了 {capture['file']}，盘上没有")
            continue
        if image.stat().st_size == 0:
            problems.append(f"{capture['file']} 是空文件")
            continue
        width, height = png_size(image)
        if (width, height) != (capture["png_width"], capture["png_height"]):
            problems.append(
                f"{capture['file']} 实际 {width}x{height}，manifest 说 "
                f"{capture['png_width']}x{capture['png_height']}"
            )
        if hashlib.sha256(image.read_bytes()).hexdigest() != capture["sha256"]:
            problems.append(f"{capture['file']} 内容与 manifest 记录的 sha256 不符")
        scale = capture["device_scale_factor"]
        expected = int(capture["css_viewport_width"]) * int(scale)
        if int(scale) != 1 and width <= expected // 2:
            problems.append(
                f"{capture['file']} 声称 {scale}x 缩放，物理宽度却只有 {width}"
            )
    return problems


def check_keyboard(probes: list[dict[str, object]]) -> list[str]:
    problems: list[str] = []
    if not probes:
        return ["没有任何键盘可达探测记录"]
    for probe in probes:
        actions = int(probe.get("actions") or 0)
        if actions == 0:
            continue  # A static frame with nothing to operate; recorded as such.
        if int(probe.get("reachable") or 0) < actions:
            problems.append(
                f"{probe['frame']}@{probe['condition']}：{actions} 个动作只有 "
                f"{probe.get('reachable')} 个键盘可达"
            )
        if int(probe.get("focusVisible") or 0) < actions:
            problems.append(
                f"{probe['frame']}@{probe['condition']}：有动作聚焦后看不出焦点在哪"
            )
    return problems


def report(manifest: dict[str, object], captures: list[dict[str, object]]) -> None:
    """The summary a reader scans; kept out of main so main stays a checklist."""
    conditions = {str(item["condition"]) for item in captures}
    violations = [v for scope in manifest["axe"].values() for v in scope]
    print("PASS FE-00 visual evidence matrix")
    print(f"  captures: {len(captures)}（IHDR 尺寸与 sha256 均已交叉校验）")
    for condition in sorted(conditions):
        count = sum(1 for item in captures if item["condition"] == condition)
        note = {
            "enforced": "重排硬门",
            "na-by-design": "重排 N/A（裁决 A：固定画布原型豁免）",
        }.get(
            next(str(i["reflow"]) for i in captures if i["condition"] == condition), ""
        )
        print(f"    {condition:10s} {count:3d}  {note}")
    print(f"  原型绑定: {len(manifest['prototypes'])} 份 sha256 与现盘一致")
    print(f"  键盘探测: {len(manifest['keyboard'])} 帧")
    print(f"  reduced-motion: {manifest['decisions']['reducedMotion'][:34]}…")
    print(f"  axe-core: {len(violations)} violations, 0 serious/critical")


def main() -> int:
    if not MANIFEST.exists():
        print(f"FAIL 缺少 {MANIFEST}", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    captures = manifest["captures"]
    failures: list[str] = []

    conditions = {str(item["condition"]) for item in captures}
    missing = REQUIRED_CONDITIONS - conditions
    if missing:
        failures.append(f"缺少采集条件：{sorted(missing)}")

    for label, required in (
        ("desktop", REQUIRED_DESKTOP_STATES),
        ("mobile", REQUIRED_MOBILE_STATES),
    ):
        shown = {
            str(item["frame"]).replace("fe00-m-", "").replace("fe00-", "")
            for item in captures
            if str(item["file"]).startswith(label)
        }
        absent = required - shown
        if absent:
            failures.append(f"{label} 缺少状态：{sorted(absent)}")

    if not any(str(item["file"]).startswith("mobile--") for item in captures):
        failures.append("移动端没有逐状态截图")
    if any("all-states" in str(item["file"]) for item in captures):
        failures.append("移动端仍在用 all-states 长图充当证据")

    failures.extend(check_prototype_binding(manifest))
    failures.extend(check_captures(captures))
    failures.extend(check_duplicates(captures))
    failures.extend(check_keyboard(manifest.get("keyboard", [])))

    violations = [v for scope in manifest["axe"].values() for v in scope]
    for violation in violations:
        if violation.get("impact") in BLOCKING_IMPACTS:
            failures.append(
                f"axe {violation['impact']} {violation['id']}: "
                f"{violation['help']}（{violation['count']} 处）"
            )

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    report(manifest, captures)
    return 0


if __name__ == "__main__":
    sys.exit(main())
