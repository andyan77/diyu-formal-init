from src.shared.content_presentation import project_content_body


def test_user_projection_removes_compiler_scaffold_and_keeps_complete_artifact() -> None:
    stored = """标题：看得见的结构，查得到的性能

商品新增理解：先区分肉眼可见结构与必须查看资料才能判断的性能。

限制：没有资料时不判断性能。

成立边界：只讲完整轮廓、牛角扣和可见结构。

自然导读：这篇给受众一个到手就能用的观察方法。

完整台词/解说：先看轮廓，再看牛角扣。性能问题，留给资料。

画面与动作：手机先固定，创作者持衣进入画面。

发布配文与互动：你会先看哪处结构？"""

    visible = project_content_body(stored)

    assert visible.startswith("标题：看得见的结构")
    assert "内容概要：这篇给受众" in visible
    assert "完整台词/解说：" in visible
    assert "画面与动作：" in visible
    assert "发布配文与互动：" in visible
    for internal in ("商品新增理解", "限制：", "成立边界", "账号观察", "画面成立条件"):
        assert internal not in visible
