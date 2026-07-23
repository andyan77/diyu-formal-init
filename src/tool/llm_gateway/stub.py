from __future__ import annotations

from src.ports.content_generator import ContentGenerator
from src.shared.types import (
    GeneratedArtifact,
    GenerationInput,
    P1ProductionBundle,
    P1SemanticContract,
)


class DeterministicP1Generator(ContentGenerator):
    """Offline test double; it is deliberately never presented as a real model result."""

    @property
    def model_name(self) -> str:
        return "deterministic-p1-test-stub"

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        body, contract, production = self._p1_body(request)
        return GeneratedArtifact(
            outline="围绕当前最难兼顾的场景，形成选择、边界与一个低成本验证动作。",
            body=body,
            model=self.model_name,
            latency_ms=0,
            retry_count=0,
            provider_usage=None,
            semantic_contract=contract,
            production=production,
        )

    @staticmethod
    def _p1_body(request: GenerationInput) -> tuple[str, P1SemanticContract, P1ProductionBundle]:
        seed = request.weak_seed
        revision = "这次已按你的修改要求重写为新版本。" if request.revision_instruction else ""
        prior = "这次只承接你明确保存的同一作用域前情。" if request.prior_saved_body else ""
        if any(word in seed for word in ("雨", "骑车", "风", "湿")):
            choice = "把移动中的安全、耐受和到达后的可整理性放在造型完整度之前。"
            boundary = "若当天并不需要长时间移动，或已有可靠的防护与替换条件，这个排序可以改变。"
            action = (
                "出门前做一次抬腿、转身和收纳物品的动作试验，再决定是否减少容易受潮或牵扯的部分。"
            )
            production = P1ProductionBundle(
                "先承认下雨和骑车会改变选择，不用把它说成意志力测试。",
                f"今天先别追求一身都很完整。{choice}{boundary}{action}",
                "出门前在门口抬腿、转身，再把包放到肩上；到办公室后只整理一处精神点。",
                "下雨天，先把行动留出来。\n到达后，再整理一处精神点。",
                "自然环境声保留一点雨声；一人手机固定拍半身和动作，不加夸张转场。",
            )
        else:
            choice = "保住已经为正式场合完成的分寸，再检查它是否允许自然移动和切换。"
            boundary = "若后一段确实需要大量活动，或一处衣物让人持续分心，就应优先调整那一处。"
            action = "在进入下一段安排前走几步、弯腰拿东西、换手拎物，观察是否还需要反复整理。"
            production = P1ProductionBundle(
                "从会议结束的停顿切入：不是换一套人，只是把同一身衣服带进下一段生活。",
                f"同一身衣服不必为不同场合重新证明两次自己。{choice}{boundary}{action}",
                "先拍收起电脑、走出门口的连续动作，再拍弯腰拿东西和换手拎物的自然测试。",
                "会议结束，不必整套推倒。\n走几步，看看哪里还在分心。",
                "一人一部手机，环境声和脚步声即可；镜头按动作顺序剪，不补造门店或商品画面。",
            )
        body = (
            f"自然导读\n{production.natural_guide}\n\n完整台词/解说\n{production.spoken_lines}\n\n"
            f"画面与动作\n{production.visual_actions}\n\n字幕\n{production.subtitles}\n\n"
            f"声音与制作提示\n{production.sound_and_production}\n\n{prior}{revision}"
        )
        return body, P1SemanticContract(choice, boundary, action), production
