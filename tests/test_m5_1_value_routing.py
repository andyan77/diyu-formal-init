from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import psycopg
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from src.brain.content_service import ContentService
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.seed_demo import BRAND_ID, TENANT_ID
from src.shared.types import (
    ContentProduct,
    GeneratedArtifact,
    GenerationInput,
    RoutingInput,
    TrustedScope,
)
from src.tool.llm_gateway.stub import DeterministicContentGenerator
from tests.conftest import SIBLING_BRAND_ID

R0 = "Hello，今天店里挺安静的，我有点困。"
R1_A = "这件衣服两面口袋都能用，翻过来也挺上镜。我不想把两面都夸一遍。顾客拿着它比了半天，最怕看完内容还是不知道今天到底把哪一面穿在外面；过两天想换个感觉时，也应该知道什么时候反过来。"
R1_B = "大家总问“这两面到底哪一面更值得选”，也想看翻面。我不想替她们站队，更不想只拍得好看。就用我们现在知道的这些，让人不再把“双面”轻率地理解成“一件顶两件”；能确认什么、当前还不能下什么结论，都说到位。"
R1_C = "两面口袋都能用，重量差也有记录，评论里还是在问两面怎么选。这次先别回答，也别把资料念给她。还是同一个人、同一组动作；她刷到时，应该直接看见炭灰和深绿细格纹会把整个人的重音换到不同地方。"
R2_A = "上周南城店三位客人进门第一句都是“我自己看看就好”，我们都只回“需要时叫我”，没有追问。我想拍第三次听见这句话时的那一秒：嘴上说不急，心里其实还在想，是不是自己哪里没做好。ZX-C218 作为出镜服装，造型、走位、转身、镜头和声音都做完整；但别拍成服务升级，也别把穿法本身当成观看理由。我想让人多认识一点，这个会克制、也会自我怀疑的店长。"
R2_B = "我本来就不爱追着人问，这件事很像我的性格。ZX-C218 可以穿在身上，画面也可以认真做，但这条别把我写成“温柔店长”。上周南城店三位客人都说“我自己看看就好”，我们只回“需要时叫我”，没有追问。我想让没来过的人也带走一句话：进门想先自己看一会儿，不用先解释，南城店会给这几分钟留点空。"
R3 = "前一篇保持不动。另外，用同一件 ZX-C218 再做一条不讲这次顾客经历、也不需要认识我是谁就能成立的内容。它要能单独拍、单独用，只靠炭灰和深绿细格纹在走动里换重音。"


@dataclass
class CapturingContentGenerator(DeterministicContentGenerator):
    routes: list[RoutingInput] = field(default_factory=list)
    inputs: list[GenerationInput] = field(default_factory=list)

    def route(self, request: RoutingInput) -> ContentProduct | None:
        self.routes.append(request)
        return super().route(request)

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        self.inputs.append(request)
        return super().generate(request)


def _store_scope() -> TrustedScope:
    return TrustedScope(
        TENANT_ID,
        UUID("00000000-0000-0000-0000-000000000014"),
        BRAND_ID,
        UUID("00000000-0000-0000-0000-000000000032"),
    )


def _product(task: dict[str, object], app_database_url: str) -> str:
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute("SELECT primary_content_product FROM business_tasks WHERE id=%s", (task["task_id"],))
        row = cursor.fetchone()
    assert row is not None
    return str(row[0])


def test_x01_routes_assets_versions_and_shared_product_truth(app_database_url: str) -> None:
    generator = CapturingContentGenerator()
    service = ContentService(
        PostgresContentRepository(app_database_url, _store_scope().account_id, ("ZX-C218",)), generator
    )
    scope = _store_scope()

    ordinary = service.create_from_weak_seed(scope, R0)
    assert ordinary["kind"] == "greeting"

    p1 = service.create_from_weak_seed(scope, R1_A)
    p2 = service.create_from_weak_seed(scope, R1_B)
    p5 = service.create_from_weak_seed(scope, R1_C)
    p3 = service.create_from_weak_seed(scope, R2_A)
    p4 = service.create_from_weak_seed(scope, R2_B)
    independent = service.create_from_weak_seed(scope, R3, UUID(str(p3["version_id"])))
    assert [item["kind"] for item in (p1, p2, p5, p3, p4, independent)] == ["content"] * 6
    assert [_product(item, app_database_url) for item in (p1, p2, p5, p3, p4, independent)] == [
        "dressing_decision",
        "product_truth",
        "visual_styling_story",
        "brand_life_narrative",
        "local_response",
        "visual_styling_story",
    ]
    assert p3["task_id"] != independent["task_id"]
    assert service.fetch_version(scope, UUID(str(p3["task_id"])), 1)["body"] == p3["body"]
    p1_v2 = service.revise(scope, UUID(str(p1["task_id"])), "把开头放轻一点。")
    assert p1_v2["version"] == 2
    assert _product(p1_v2, app_database_url) == "dressing_decision"

    received = {item.primary_product: {asset.asset_id for asset in item.active_domain_assets} for item in generator.inputs}
    assert received["product_truth"] == {"A-TRANSLATE-001", "A-MAT-005", "D-EXPLAIN-001"}
    assert received["brand_life_narrative"] == {"D-PERSONA-001", "D-PERSONA-002", "D-CRAFT-002"}
    assert received["local_response"] == {"C-LOCAL-001", "C-LOCAL-002", "D-RESPONSE-002"}
    assert received["visual_styling_story"] == {"B-VIS-001", "B-VIS-003", "B-VIS-005", "B-VIS-006"}
    p2_input = next(item for item in generator.inputs if item.primary_product == "product_truth")
    p2_assets = {asset.asset_id: asset.body for asset in p2_input.active_domain_assets}
    assert "厚度增加可能改变支撑和体积" not in p2_assets["A-MAT-005"]
    assert "不得把“厚=挺”“轻=软”“双面=更硬”直接写入商品认知" in p2_assets["A-MAT-005"]
    assert "已知结构、材质或工艺可用于解释可能的穿着、使用或视觉影响" not in p2_assets[
        "A-TRANSLATE-001"
    ]
    assert "不得编造设计故事、研发目的、性能验证" in p2_assets["A-TRANSLATE-001"]
    assert "条件—效果—原因—代价—不适用的专业解释" not in p2_assets["D-EXPLAIN-001"]
    product_inputs = [item for item in generator.inputs if item.primary_product in {"product_truth", "visual_styling_story"}]
    assert all(item.products and item.products[0].sku == "ZX-C218" for item in product_inputs)
    assert "960 克" in str(p2["body"])
    assert "炭灰纯色" in str(p5["body"])
    assert "想先看就先看，不用解释" in str(p4["body"])
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT input_receipt FROM generation_runs WHERE task_id=%s ORDER BY started_at DESC LIMIT 1",
            (p5["task_id"],),
        )
        receipt = cursor.fetchone()
    assert receipt is not None
    assert receipt[0]["primary_content_product"] == "visual_styling_story"
    assert receipt[0]["product_refs"] == ["ZX-C218"]
    p5_v2 = service.revise(scope, UUID(str(p5["task_id"])), "把开头放轻一点。")
    assert p5_v2["version"] == 2
    assert generator.inputs[-1].products[0].sku == "ZX-C218"


def test_store_identity_ui_and_account_boundary(app_database_url: str) -> None:
    app = create_app(Settings.model_validate({}))
    with TestClient(app) as store:
        store.get("/ui/select/content-store")
        page = store.get("/content")
        assert "南城店内容运营甲" in page.text
        assert "折线之间·南城店账号·抖音" in page.text
        assert "南城店店长/门店经营者" in page.text
        created = store.post("/api/v1/content", json={"weak_seed": R2_A}).json()
        saved = store.post(f"/api/v1/content-versions/{created['version_id']}/save")
        assert saved.status_code == 200
    with TestClient(app) as headquarters:
        headquarters.get("/ui/select/content")
        assert headquarters.get(f"/api/v1/tasks/{created['task_id']}/versions/1").status_code == 422
        assert headquarters.post(
            f"/api/v1/tasks/{created['task_id']}/revisions", json={"instruction": "改一下"}
        ).status_code == 422
        assert headquarters.post(f"/api/v1/content-versions/{created['version_id']}/save").status_code == 422


def test_sibling_brand_product_never_enters_store_content_input(
    app_database_url: str, migrator_database_url: str
) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "INSERT INTO brand_products (id,tenant_id,brand_id,sku,facts) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,brand_id,sku) DO UPDATE SET facts=EXCLUDED.facts",
            (
                UUID("00000000-0000-0000-0000-000000000091"),
                TENANT_ID,
                SIBLING_BRAND_ID,
                "ZX-C218",
                Jsonb({"tempting_story": "兄弟品牌诱饵，不得进入当前生成"}),
            ),
        )
    generator = CapturingContentGenerator()
    service = ContentService(
        PostgresContentRepository(app_database_url, _store_scope().account_id, ("ZX-C218",)), generator
    )
    created = service.create_from_weak_seed(_store_scope(), R1_C)
    assert created["kind"] == "content"
    assert "兄弟品牌诱饵" not in str(generator.inputs[-1].products)
    assert generator.inputs[-1].brand.brand_name == "折线之间"
