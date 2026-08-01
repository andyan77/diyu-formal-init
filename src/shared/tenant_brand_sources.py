from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

SemanticKind = Literal[
    "brand_fact",
    "expression_constraint",
    "creative_method",
    "candidate_product_guidance",
    "template_only",
    "source_catalog_only",
]
EvidenceLevel = Literal["V", "P", "C", "R"]

TENANT_SOURCE_NAMESPACE = UUID("5a494392-942d-53f5-9e10-4f8d28b92931")
TENANT_SOURCE_CONTRACT_VERSION = "tenant-brand-source-v1"

_DOCUMENT_ID = re.compile(
    r"(?:文档编号|Document ID)[：:\s`*]+([^\n|`*]+)|"
    r"\b([A-Z]{1,12}(?:-[A-Z0-9]{1,18}){1,8})\b",
    re.IGNORECASE,
)
_DOCUMENT_VERSION = re.compile(
    r"(?:文档版本|版本)[：:\s`*]+(V?\d+(?:\.\d+)?)|\b(V\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)
_DOCUMENT_STATUS = re.compile(
    r"(?:原始状态|文档状态|状态)[：:\s`*]+([^\n|`*]+)",
    re.IGNORECASE,
)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_DIVIDER = re.compile(r"^\s*\|?\s*:?-{3,}")
_PRODUCT_HEADING = re.compile(r"^#{2,6}\s+(DIYU-CSPU-\d+)\s+(.+?)\s*$")

_TEMPLATE_DOCUMENTS = frozenset(
    {
        "DIYU-ACCOUNT-MATRIX-001",
        "DIYU-ORG-IP-ACCOUNT-MATRIX-001",
        "DIYU-TENANT-ORG-AUTH-001",
        "DIYU-STORE-FIXTURE-PROFILE-001",
        "DIYU-STORE-FIXTURE-COLLECTION-001",
        "DIYU-ASSET-BRAND-UNIFICATION-001",
    }
)
_CATALOG_DOCUMENTS = frozenset({"DIYU-ASSET-CATALOG-001"})
_PRODUCT_GUIDANCE_DOCUMENTS = frozenset(
    {
        "DIYU-CANDIDATE-PRODUCT-MASTER-001",
        "DIYU-PRODUCT-TRADEOFF-P2-001",
        "DIYU-PRODUCT-PRICE-CORRECTION-001",
        "DIYU-ASSET-PRODUCT-INFERENCE-001",
    }
)
_CREATIVE_METHOD_DOCUMENTS = frozenset(
    {
        "DIYU-DISPLAY-EXPRESSION-001",
        "DIYU-BRAND-VISUAL-001",
        "DIYU-ASSET-CALLING-001",
        "DIYU-ASSET-VISUAL-ANALYSIS-001",
    }
)
_EXPRESSION_DOCUMENTS = frozenset(
    {
        "DIYU-CONTENT-ROLE-001",
        "DIYU-CONTENT-GOVERNANCE-001",
        "DIYU-BRAND-VOICE-001",
        "DIYU-ACCOUNT-AUTHORITY-001",
    }
)
_BRAND_FACT_DOCUMENTS = frozenset(
    {
        "DIYU-BRAND-BASELINE-001",
        "DIYU-AUDIENCE-PROFILE-001",
    }
)


@dataclass(frozen=True)
class SourceSegmentDraft:
    segment_id: UUID
    segment_key: str
    heading_path: tuple[str, ...]
    source_locator: str
    exact_text: str
    semantic_kind: SemanticKind
    evidence_level: str
    applicability: str
    digest: str


@dataclass(frozen=True)
class ProductFieldDraft:
    field_name: str
    exact_text: str
    evidence_levels: tuple[EvidenceLevel, ...]
    allowed_in_product_fact: bool
    source_locator: str
    source_segment_id: UUID
    source_digest: str


@dataclass(frozen=True)
class ProductCandidateDraft:
    sku: str
    display_name: str
    fields: tuple[ProductFieldDraft, ...]

    @property
    def fact_fields(self) -> dict[str, str]:
        return {
            field.field_name: field.exact_text
            for field in self.fields
            if field.allowed_in_product_fact
        }


@dataclass(frozen=True)
class SourceDocumentDraft:
    document_id: UUID
    source_id: str
    embedded_title: str
    provenance_filename: str
    source_version: str
    original_status: str
    activation_status: str
    authorization_source: str
    raw_sha256: str
    normalized_sha256: str
    source_size: int
    source_mtime_ns: int
    normalized_content: str
    semantic_kind: SemanticKind
    segments: tuple[SourceSegmentDraft, ...]
    products: tuple[ProductCandidateDraft, ...]


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    if match is None:
        return ""
    return next((value.strip() for value in match.groups() if value), "")


def _embedded_title(lines: list[str], metadata: str) -> str:
    for line in lines:
        match = _HEADING.match(line)
        if match is not None:
            return match.group(2).strip()
    for label in ("文档名称", "文件名称", "标题"):
        match = re.search(rf"{label}[：:\s`*]+([^\n|`*]+)", metadata)
        if match is not None:
            return match.group(1).strip()
    # A small number of the frozen source files use an embedded numbered-file
    # heading instead of Markdown heading syntax.  It is still document-owned
    # metadata, not a filename inference.
    for line in lines[:20]:
        match = re.match(r"^文件[一二三四五六七八九十]+[：:]\s*(.+?)\s*$", line.strip())
        if match is not None:
            return match.group(1).strip()
    return ""


def _is_document_metadata(exact_text: str) -> bool:
    first_line = exact_text.strip().splitlines()[0].strip().strip("|").strip()
    first_cell = re.split(r"[|：:]", first_line, maxsplit=1)[0].strip(" *_`")
    return first_cell in {
        "文档编号",
        "Document ID",
        "文档版本",
        "版本",
        "原始状态",
        "文档状态",
        "状态",
    }


def classify_source_segment(
    source_id: str,
    heading_path: tuple[str, ...],
    exact_text: str = "",
) -> SemanticKind:
    """Return the consumer-facing semantic kind from immutable source structure.

    The stored source text remains byte-for-byte provenance.  Headings that
    describe the product's own content taxonomy are operating constraints,
    not institutional facts that may be inserted verbatim into an artifact.
    Keeping this decision here lets a current consumer safely project records
    imported by an older parser without rewriting their immutable rows.
    """

    if exact_text and _is_document_metadata(exact_text):
        return "source_catalog_only"
    if source_id in _TEMPLATE_DOCUMENTS:
        return "template_only"
    if source_id in _CATALOG_DOCUMENTS:
        return "source_catalog_only"
    if source_id in _PRODUCT_GUIDANCE_DOCUMENTS:
        return "candidate_product_guidance"
    if source_id in _CREATIVE_METHOD_DOCUMENTS:
        return "creative_method"
    if source_id in _EXPRESSION_DOCUMENTS:
        return "expression_constraint"
    if source_id in _BRAND_FACT_DOCUMENTS:
        # These documents contain explicit gaps and candidate/example sections.
        # The heading, not free prose or a model, decides whether the segment can
        # be licensed as an immutable brand fact.
        joined = "/".join(heading_path)
        if any(
            marker in joined
            for marker in (
                "待补",
                "评审",
                "示例",
                "候选",
                "不是什么",
                "内容产品",
            )
        ):
            return "expression_constraint"
        return "brand_fact"
    return "expression_constraint"


def _segment_blocks(source_id: str, source_version: str, lines: list[str]) -> tuple[SourceSegmentDraft, ...]:
    headings: list[str] = []
    blocks: list[tuple[int, int, tuple[str, ...], str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        heading = _HEADING.match(line)
        if heading is not None:
            level = len(heading.group(1))
            headings = headings[: level - 1]
            headings.append(heading.group(2).strip())
            index += 1
            continue
        if not line.strip():
            index += 1
            continue
        if (
            line.lstrip().startswith("|")
            and index + 1 < len(lines)
            and _TABLE_DIVIDER.match(lines[index + 1])
        ):
            index += 2
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                text = lines[index].strip()
                blocks.append((index + 1, index + 1, tuple(headings), text))
                index += 1
            continue
        start = index
        paragraph = [line]
        index += 1
        while index < len(lines):
            if not lines[index].strip() or _HEADING.match(lines[index]):
                break
            if lines[index].lstrip().startswith("|"):
                break
            if lines[index].lstrip().startswith(("- ", "* ", "> ")):
                break
            paragraph.append(lines[index])
            index += 1
        text = "\n".join(paragraph).strip()
        if text:
            blocks.append((start + 1, start + len(paragraph), tuple(headings), text))

    drafts: list[SourceSegmentDraft] = []
    for start, end, heading_path, exact_text in blocks:
        digest = sha256(exact_text.encode("utf-8")).hexdigest()
        locator = f"line:{start}" if start == end else f"line:{start}-{end}"
        key = f"{source_id}:{source_version}:{locator}:{digest[:16]}"
        kind = classify_source_segment(source_id, heading_path, exact_text)
        evidence = {
            "brand_fact": "brand_user_authorized",
            "expression_constraint": "brand_user_authorized_constraint",
            "creative_method": "method_only",
            "candidate_product_guidance": "candidate_only",
            "template_only": "template_only",
            "source_catalog_only": "catalog_only",
        }[kind]
        drafts.append(
            SourceSegmentDraft(
                segment_id=uuid5(TENANT_SOURCE_NAMESPACE, key),
                segment_key=key,
                heading_path=heading_path,
                source_locator=locator,
                exact_text=exact_text,
                semantic_kind=kind,
                evidence_level=evidence,
                applicability=f"{source_id}:{'/'.join(heading_path[-2:])}",
                digest=digest,
            )
        )
    return tuple(drafts)


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _levels(value: str) -> tuple[EvidenceLevel, ...]:
    found = tuple(
        level
        for level in ("V", "P", "C", "R")
        if re.search(rf"(?:^|[/、,，\s]){level}(?:级)?(?:$|[/、,，\s])", value)
    )
    return found  # type: ignore[return-value]


def _product_candidates(
    lines: list[str],
    segments: tuple[SourceSegmentDraft, ...],
) -> tuple[ProductCandidateDraft, ...]:
    segment_by_locator = {segment.source_locator: segment for segment in segments}
    products: list[ProductCandidateDraft] = []
    current_sku = ""
    current_name = ""
    fields: list[ProductFieldDraft] = []

    def finish() -> None:
        if current_sku:
            products.append(ProductCandidateDraft(current_sku, current_name, tuple(fields)))

    index = 0
    while index < len(lines):
        product_heading = _PRODUCT_HEADING.match(lines[index])
        if product_heading is not None:
            finish()
            current_sku = product_heading.group(1)
            current_name = product_heading.group(2).strip()
            fields = []
            index += 1
            continue
        if (
            current_sku
            and index + 1 < len(lines)
            and lines[index].lstrip().startswith("|")
            and "字段" in lines[index]
            and _TABLE_DIVIDER.match(lines[index + 1])
        ):
            index += 2
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                cells = _table_cells(lines[index])
                if len(cells) >= 3:
                    evidence_levels = _levels(cells[-1])
                    if evidence_levels:
                        locator = f"line:{index + 1}"
                        segment = segment_by_locator.get(locator)
                        if segment is None:
                            raise ValueError(f"商品字段缺少稳定 segment：{locator}")
                        fields.append(
                            ProductFieldDraft(
                                field_name=cells[0],
                                exact_text=cells[1],
                                evidence_levels=evidence_levels,
                                allowed_in_product_fact=evidence_levels == ("V",),
                                source_locator=locator,
                                source_segment_id=segment.segment_id,
                                source_digest=segment.digest,
                            )
                        )
                index += 1
            continue
        index += 1
    finish()
    return tuple(products)


def parse_source_document(path: Path) -> SourceDocumentDraft:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines()
    metadata = "\n".join(lines[:100])
    source_id = _first_match(_DOCUMENT_ID, metadata)
    source_version = _first_match(_DOCUMENT_VERSION, metadata)
    original_status = _first_match(_DOCUMENT_STATUS, metadata)
    title = _embedded_title(lines, metadata)
    if not source_id or not source_version or not original_status or not title:
        missing = [
            label
            for label, value in (
                ("文档编号", source_id),
                ("内嵌标题", title),
                ("版本", source_version),
                ("原始状态", original_status),
            )
            if not value
        ]
        raise ValueError(f"{path.name} 缺少可验证元数据：{'、'.join(missing)}")
    document_id = uuid5(TENANT_SOURCE_NAMESPACE, source_id)
    segments = _segment_blocks(source_id, source_version, lines)
    if not segments:
        raise ValueError(f"{path.name} 没有可导入的稳定语义段")
    activation_status = (
        "template_only"
        if source_id
        in {"DIYU-STORE-FIXTURE-PROFILE-001", "DIYU-STORE-FIXTURE-COLLECTION-001"}
        else "brand_user_authorized"
    )
    stat = path.stat()
    return SourceDocumentDraft(
        document_id=document_id,
        source_id=source_id,
        embedded_title=title,
        provenance_filename=path.name,
        source_version=source_version,
        original_status=original_status,
        activation_status=activation_status,
        authorization_source="TENANT-01 user-authorized import",
        raw_sha256=sha256(raw).hexdigest(),
        normalized_sha256=sha256(normalized.encode("utf-8")).hexdigest(),
        source_size=stat.st_size,
        source_mtime_ns=stat.st_mtime_ns,
        normalized_content=normalized,
        semantic_kind=classify_source_segment(source_id, ()),
        segments=segments,
        products=(
            _product_candidates(lines, segments)
            if source_id == "DIYU-CANDIDATE-PRODUCT-MASTER-001"
            else ()
        ),
    )


def freeze_source_batch(root: Path) -> tuple[SourceDocumentDraft, ...]:
    documents = tuple(parse_source_document(path) for path in sorted(root.glob("*.md")))
    if len(documents) != 21:
        raise ValueError(f"TENANT-01 必须一次冻结 21 份 Markdown，当前为 {len(documents)} 份")
    source_ids = [document.source_id for document in documents]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("源目录中存在重复文档编号")
    products = tuple(product for document in documents for product in document.products)
    if len(products) != 14 or len({product.sku for product in products}) != 14:
        raise ValueError("TENANT-01 必须一次冻结 14 个唯一候选商品")
    return documents
