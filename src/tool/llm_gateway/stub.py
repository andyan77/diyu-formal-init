from __future__ import annotations

from src.ports.content_generator import ContentGenerator
from src.shared.types import (
    ContentProduct,
    ContentSemanticContract,
    GeneratedArtifact,
    GenerationInput,
    GraphicProductionBundle,
    P1SemanticContract,
    P2SemanticContract,
    P3SemanticContract,
    P4SemanticContract,
    P5SemanticContract,
    RoutingInput,
    VideoProductionBundle,
)


class DeterministicContentGenerator(ContentGenerator):
    """Offline test double for route, contract, scope and version regression only."""

    @property
    def model_name(self) -> str:
        return "deterministic-content-test-stub"

    def route(self, request: RoutingInput) -> ContentProduct | None:
        text = request.weak_seed.casefold()
        if _ordinary_chat(text):
            return None
        if any(value in text for value in ("想先看", "不用解释", "不用先解释", "留点空", "门店回应", "店里这几天")):
            return "local_response"
        if any(value in text for value in ("店长", "自我怀疑", "三位客人", "我会注意")):
            return "brand_life_narrative"
        if any(value in text for value in ("单独拍", "单独用", "画面", "视觉重音", "走动里换", "重音")):
            return "visual_styling_story"
        if any(value in text for value in ("一件顶两件", "解释双面", "不要替两面站队", "商品")):
            return "product_truth"
        if any(
            value in text
            for value in (
                "哪面",
                "怎么穿",
                "怎么选",
                "先穿",
                "口袋",
                "上镜",
                "会议",
                "开完",
                "接孩子",
                "下雨",
                "骑车",
                "接着上一条",
                "复用当前",
            )
        ):
            return "dressing_decision"
        return "brand_life_narrative" if "内容" in text or "写一条" in text else None

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        contract, guide, spoken, visuals, subtitles, sound = self._parts(request)
        production = self._production(request, contract, guide, spoken, visuals, subtitles, sound)
        revision = "\n\n这次只按你的自然修改更新了同一任务的表达。" if request.revision_instruction else ""
        prior = "\n\n已承接当前合法作用域内明确授权的前情。" if request.prior_saved_body else ""
        core = "\n\n内容核心：" + " ".join(str(value) for value in vars(contract).values())
        body = _visible_body(_outline(request.primary_product), production) + core + prior + revision
        return GeneratedArtifact(
            outline=_outline(request.primary_product),
            body=body,
            model=self.model_name,
            latency_ms=0,
            retry_count=0,
            provider_usage=None,
            primary_product=request.primary_product,
            semantic_contract=contract,
            production=production,
        )

    @staticmethod
    def _production(
        request: GenerationInput,
        contract: ContentSemanticContract,
        guide: str,
        spoken: str,
        visuals: str,
        subtitles: str,
        sound: str,
    ) -> VideoProductionBundle | GraphicProductionBundle:
        if request.media_format == "graphic":
            four_images = "四张" in request.brand.production_conditions
            return GraphicProductionBundle(
                natural_guide=guide,
                hero_image="首图拍摄安排：用当前商品和本篇最关键的可见关系作出标题承诺，不使用视频截图。",
                image_sequence=(
                    "只补拍四张：第 1 张给出首图承诺；第 2 张让关键商品或关系完整可见；"
                    "第 3 张补足必要比较或动作；第 4 张完成本篇判断。每张只承担这一项职责。"
                    if four_images
                    else "第 1 张给出首图承诺；第 2 张让关键商品或关系完整可见；"
                    "第 3 张补足必要比较或动作；最后一张完成本篇判断。每张只承担这一项职责。"
                ),
                full_body="\n".join(str(value) for value in vars(contract).values()),
                layout_and_production="按当前一人一手机条件补拍或选图；不把视频帧、台词卡或长文切片当作图片序列。",
                release_caption_and_interaction="正文已经完成当前判断；不需要额外互动时自然结束。",
            )
        silent = request.primary_product == "visual_styling_story" and any(
            phrase in request.weak_seed for phrase in ("无口播", "无对白", "无解说", "不讲")
        )
        return VideoProductionBundle(
            natural_guide=guide,
            spoken_lines="无口播、无对白、无解说；由画面和同期声承担内容。" if silent else spoken,
            visual_actions=visuals,
            subtitles=subtitles,
            sound_and_production=sound,
            cover_or_first_frame="封面/首帧拍摄安排：第一眼就让当前商品关系或判断进入画面。",
            viewing_flow="从当前入口开始，依次完成事实、动作或判断，并在主价值成立处自然收束。",
            natural_duration=(
                "8 秒窄主题版：只保留仍能独立成立的一项命题，不称与原完整版本等义。"
                if "8 秒" in request.brand.production_conditions
                else "以把当前主要价值与必要边界说清为准，不套固定秒数。"
            ),
            release_caption_and_interaction="发布配文复述当前完整结论；不适用互动时自然结束。",
        )

    @staticmethod
    def _parts(
        request: GenerationInput,
    ) -> tuple[ContentSemanticContract, str, str, str, str, str]:
        product = request.primary_product
        zx_c218 = _product_facts(request, "ZX-C218")
        colors = _colors(zx_c218)
        color_pair = f"{colors[0]}和{colors[1]}" if len(colors) >= 2 else "这件外套的两面"
        weight = str(zx_c218.get("sample_weight_m_grams", "当前"))
        comparison_weight = str(zx_c218.get("comparison_single_layer_short_coat_m_grams", "对照"))
        if product == "product_truth":
            return (
                P2SemanticContract(
                    f"双面不等于一件顶两件：{color_pair}都是完整外观、两面的口袋也都可正常使用，但它仍是一件外套。",
                    f"M 码当前样衣约 {weight} 克，比同季同长度单层短外套 M 码样衣约 {comparison_weight} 克更重；不能把全部差异简单归因于双面结构。",
                    "这只说明当前样衣存在重量差异，不推断价格、面料性能、普遍上身结果或设计动机。",
                ),
                "从一件真实样衣的两面与重量差异出发，把能确认和不能下结论的部分说清楚。",
                f"别把双面说成两件。{color_pair}都能独立出现，口袋两面都能用；M 码样衣约 {weight} 克，同季同长度单层短外套 M 码样衣约 {comparison_weight} 克。它给的是一次翻面后的不同视觉，不是多买到一件外套。",
                "同一人先穿炭灰走过镜头，再在转身时翻到深绿细格纹；最后把样衣放在秤旁，但不把数字夸成性能结论。",
                "双面，不等于两件。\n能确认的，和还不能下结论的，都留在镜头里。",
                "一人一手机，保留翻面摩擦和脚步声；不补拍价格牌、库存或未经提供的材质细节。",
            )
        if product == "brand_life_narrative":
            if request.brand.brand_name != "折线之间":
                return (
                    P3SemanticContract(
                        f"{request.brand.account_name}从当前已确认的品牌表达出发，"
                        "选择尊重每个人自己的生活节奏，不替具体家庭编造经历。",
                        "受众得到的是一种可带回日常的许可：一家人可以彼此呼应，也可以各自成立。",
                        f"这由“{request.brand.content_role_name}”在已确认品牌边界内表达，"
                        "不冒充创始人、研发、门店、顾客或具体家庭。",
                    ),
                    "从已经确认的品牌关系观出发，讲清一家人不必穿成同一个答案。",
                    "一家人站在一起，不一定要穿成一套。有人喜欢安静一点，有人愿意多一点颜色；"
                    "彼此看得见，也各自舒服，就已经是一种自然的呼应。我们只说当前确认过的品牌立场，"
                    "不替任何一个真实家庭补写经历。",
                    "一人一手机，用不同衣架或空白色卡表示几种独立选择；不出现具体商品、价格、库存、"
                    "顾客或门店画面，也不把概念冒充已实拍。",
                    "一家人，可以自然呼应。\n也可以，各自成立。",
                    "使用普通室内环境与轻微生活声；不制造儿童、身体、年龄或家庭焦虑。",
                )
            return (
                P3SemanticContract(
                    "南城店店长会把“我先看看”当成需要被尊重的停顿，而不是必须立刻解决的犹豫。",
                    "受众能看见这家店怎样克制地观察和待人，而不是被要求接受一个标准答案。",
                    "这来自南城店店长/门店经营者的合法观察位置，不冒充顾客经历或总部政策。",
                ),
                "从门店里三个相似的停顿，讲清账号愿意怎样把空间留给人。",
                "今天有三位客人都说：我先看看。店长没有急着把这句话接成成交话术，只把那件 ZX-C218 挂回原位，等对方自己走近。她也会怀疑自己是不是太克制，但还是愿意把选择留在顾客手里。",
                "一人手机拍店长整理炭灰面和深绿细格纹的两次停顿；不拍顾客正脸，不复述任何个人识别信息。",
                "“我先看看”，可以只是看看。\n把空间留出来，也是一种服务。",
                "门店环境声即可；这是账号的生活观察，不是店内巡检、承诺或全国服务政策。",
            )
        if product == "local_response":
            return (
                P4SemanticContract(
                    "南城店里重复出现的“我先看看”是一次近场服务信号，不被解释成顾客的单一原因。",
                    "南城店账号的回应是：想先看就先看，不用解释。",
                    "未到店的人也能带走一种关系许可：可以按自己的节奏靠近一件衣服。",
                ),
                "从南城店已知的近场信号出发，给未到店的人一句可迁移的关系回应。",
                "如果你走进南城店，只想先看看，也完全可以。我们不替你猜今天为什么犹豫，也不催你给理由；衣服先在这里，等你按自己的节奏靠近。",
                "拍一只手把 ZX-C218 的炭灰面和深绿细格纹依次留在同一根挂杆上，再留出一段空镜。",
                "想先看就先看，不用解释。",
                "一人一手机、普通门店空间；不把这句话扩展成交易承诺、顾客画像或全国政策。",
            )
        if product == "visual_styling_story":
            return (
                P5SemanticContract(
                    f"ZX-C218 双面短外套：{color_pair}两面均为完整外观，口袋两面可用。",
                    f"同一个人、同一个走动动作里，翻面让画面从安静的{colors[0] if colors else '第一面'}重音转向更有纹理的{colors[1] if len(colors) > 1 else '另一面'}重音。",
                    "拿掉翻面、走动和两面在画面中的前后关系，这条内容不再成立为可见的造型命题。",
                ),
                "以 ZX-C218 的真实双面为锚，让同一动作改变画面的视觉重音。",
                f"人不用换。先用{colors[0] if colors else '第一面'}从门口走向镜头，走到最近处时抬手翻面；同一步继续向前，{colors[1] if len(colors) > 1 else '另一面'}接住原来的动作。不是两套造型，也不是资料朗读，是同一个人把重音换了一下。",
                f"固定机位拍连续走动：{colors[0] if colors else '第一面'}进入、手部翻面、{colors[1] if len(colors) > 1 else '另一面'}离开。两面口袋都留一个短镜头，不增加未经提供的搭配或功能主张。",
                f"人没换，画面换了重音。\n{colors[0] if colors else '第一面'}停一下，{colors[1] if len(colors) > 1 else '另一面'}再往前一步。",
                "一人一部手机、普通门店空间；保留脚步声，音乐只做轻节拍，不把概念冒充已实拍或门店陈列执行。",
            )
        if any(word in request.weak_seed for word in ("雨", "骑车", "湿")):
            choice = "把移动中的安全、耐受和到达后的可整理性放在造型完整度之前。"
            boundary = "若当天并不需要长时间移动，或已有可靠的防护与替换条件，这个排序可以改变。"
            action = "出门前做一次抬腿、转身和收纳物品的动作试验，再决定是否减少容易受潮或牵扯的部分。"
        else:
            choice = "保住已经为正式场合完成的分寸，再检查它是否允许自然移动和切换。"
            boundary = "若后一段确实需要大量活动，或一处衣物让人持续分心，就应优先调整那一处。"
            action = "在进入下一段安排前走几步、弯腰拿东西、换手拎物，观察是否还需要反复整理。"
        return (
            P1SemanticContract(choice, boundary, action),
            "从当前真实情境出发，先给出条件性选择，再留出可以改变判断的边界。",
            f"同一身衣服不必为不同场合重新证明两次自己。{choice}{boundary}{action}",
            "先拍连续走动和弯腰拿东西的自然测试，再拍一处需要调整或保留的细节。",
            "先保住分寸。\n走几步，再决定要不要改。",
            "一人一部手机，环境声和脚步声即可；不补造商品事实或顾客身份。",
        )


def _ordinary_chat(text: str) -> bool:
    return any(value in text for value in ("hello", "你好", "有点困", "挺安静", "谢谢")) and not any(
        value in text for value in ("写", "内容", "双面", "外套", "穿", "商品", "拍")
    )


def _outline(product: ContentProduct) -> str:
    return {
        "dressing_decision": "帮助受众完成一个带边界的穿衣选择。",
        "product_truth": "解释一项真实商品理解及其当前边界。",
        "brand_life_narrative": "让受众认识账号怎样观察、判断和待人。",
        "local_response": "从南城店近场信号给出可迁移的关系回应。",
        "visual_styling_story": "让真实商品在画面关系中形成新的穿着可能。",
    }[product]


def _product_facts(request: GenerationInput, sku: str) -> dict[str, object]:
    return next((product.facts for product in request.products if product.sku == sku), {})


def _colors(facts: dict[str, object]) -> tuple[str, ...]:
    raw = facts.get("colors")
    return tuple(str(value) for value in raw) if isinstance(raw, list) else ()


def _visible_body(title: str, production: VideoProductionBundle | GraphicProductionBundle) -> str:
    if isinstance(production, VideoProductionBundle):
        sections: tuple[tuple[str, str], ...] = (
            ("自然导读", production.natural_guide),
            ("封面/首帧", production.cover_or_first_frame),
            ("完整观看链", production.viewing_flow),
            ("完整台词/解说", production.spoken_lines),
            ("画面与动作", production.visual_actions),
            ("字幕", production.subtitles),
            ("声音与制作提示", production.sound_and_production),
            ("自然时长", production.natural_duration),
            ("发布配文与互动", production.release_caption_and_interaction),
        )
    else:
        sections = (
            ("自然导读", production.natural_guide),
            ("首图方案", production.hero_image),
            ("图序与每张职责", production.image_sequence),
            ("完整发布正文", production.full_body),
            ("拍摄/排版提示", production.layout_and_production),
            ("发布配文与互动", production.release_caption_and_interaction),
        )
    return "标题：" + title + "\n\n" + "\n\n".join(f"{heading}：{value}" for heading, value in sections)


DeterministicP1Generator = DeterministicContentGenerator
