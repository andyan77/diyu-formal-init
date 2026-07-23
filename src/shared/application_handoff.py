from __future__ import annotations


def requests_display_merchandising(text: str) -> bool:
    normalized = text.casefold()
    return (
        "门店" in normalized
        and "库存" in normalized
        and "双层挂杆" in normalized
        and any(marker in normalized for marker in ("上杆", "下杆", "数量", "执行步骤"))
    )


def requests_content_production(text: str) -> bool:
    normalized = text.casefold()
    return (
        "面向顾客" in normalized
        and "抖音" in normalized
        and any(marker in normalized for marker in ("口播", "拍摄脚本"))
    )
