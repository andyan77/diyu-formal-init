from __future__ import annotations

from src.ports.content_generator import ContentGenerator
from src.shared.types import GeneratedArtifact, GenerationInput, P1SemanticContract


class DeterministicP1Generator(ContentGenerator):
    """Offline test double; it is deliberately never presented as a real model result."""

    @property
    def model_name(self) -> str:
        return "deterministic-p1-test-stub"

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        body, contract = self._p1_body(request)
        return GeneratedArtifact(
            outline="围绕当前最难兼顾的场景，形成选择、边界与一个低成本验证动作。",
            body=body,
            model=self.model_name,
            latency_ms=0,
            retry_count=0,
            provider_usage=None,
            semantic_contract=contract,
        )

    @staticmethod
    def _p1_body(request: GenerationInput) -> tuple[str, P1SemanticContract]:
        seed = request.weak_seed
        revision = "这次已按你的修改要求重写为新版本。" if request.revision_instruction else ""
        prior = "这次只承接你明确保存的同一作用域前情。" if request.prior_saved_body else ""
        if any(word in seed for word in ("雨", "骑车", "风", "湿")):
            choice = "把移动中的安全、耐受和到达后的可整理性放在造型完整度之前。"
            boundary = "若当天并不需要长时间移动，或已有可靠的防护与替换条件，这个排序可以改变。"
            action = (
                "出门前做一次抬腿、转身和收纳物品的动作试验，再决定是否减少容易受潮或牵扯的部分。"
            )
            body = (
                "遇到天气和移动方式都在添变量时，不需要把自己塞进一套“万能通勤装”。"
                "先选能让动作和路程不成为负担的组合，再保留一处让人精神起来的细节。\n\n"
                f"{choice}{boundary}{action}\n\n{prior}{revision}"
            )
        else:
            choice = "保住已经为正式场合完成的分寸，再检查它是否允许自然移动和切换。"
            boundary = "若后一段确实需要大量活动，或一处衣物让人持续分心，就应优先调整那一处。"
            action = "在进入下一段安排前走几步、弯腰拿东西、换手拎物，观察是否还需要反复整理。"
            body = (
                "同一身衣服不必为不同场合重新证明两次自己。先留住前一段已经建立的整洁和判断，"
                "再把真正影响行动的部分减轻，往往比整套推倒更从容。\n\n"
                f"{choice}{boundary}{action}\n\n{prior}{revision}"
            )
        return body, P1SemanticContract(choice, boundary, action)
