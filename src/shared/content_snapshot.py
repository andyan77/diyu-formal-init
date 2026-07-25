from __future__ import annotations


def visible_direction(snapshot: object) -> tuple[str | None, list[str]]:
    """Project only what a reader of a finished version may see.

    A version keeps the transparent brand translation it was actually produced with, so reopening
    an old version must not make a translated direction look like the user's untouched choice.
    Stable ids, profile ids and preference state stay out of this projection.
    """
    if not isinstance(snapshot, dict):
        return None, []
    notice = snapshot.get("translation_notice")
    applied = snapshot.get("applied_direction")
    labels = (
        [
            str(item["applied_label"])
            for item in applied
            if isinstance(item, dict) and item.get("applied_label")
        ]
        if isinstance(applied, list)
        else []
    )
    return (notice if isinstance(notice, str) and notice else None), labels
