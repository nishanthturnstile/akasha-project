from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RenderProfileName = Literal["standard", "contrast"]

CONTRAST_PALETTE_V1 = (
    "#6e3b1f",
    "#b86b2c",
    "#e7c64b",
    "#9bcf53",
    "#3f9f4a",
    "#0b5d37",
)


@dataclass(frozen=True, slots=True)
class RenderDescriptor:
    requested: RenderProfileName
    applied: RenderProfileName
    version: str
    thresholds: tuple[float, ...]
    palette: tuple[str, ...]
    fallback_reason: str | None = None


def resolve_render_descriptor(
    requested: RenderProfileName,
    minimum: float | None,
    maximum: float | None,
) -> RenderDescriptor:
    if requested == "standard":
        return RenderDescriptor("standard", "standard", "standard-v1", (), ())
    if minimum is None or maximum is None:
        return RenderDescriptor("contrast", "standard", "standard-v1", (), (), "missing_statistics")
    if minimum == maximum:
        return RenderDescriptor("contrast", "standard", "standard-v1", (), (), "constant_scene")
    span = maximum - minimum
    return RenderDescriptor(
        "contrast",
        "contrast",
        "equal-bands-v1",
        tuple(minimum + n * span / 5 for n in range(1, 6)),
        CONTRAST_PALETTE_V1,
    )


def category_for_value(
    value: float | None, thresholds: list[float] | tuple[float, ...]
) -> int | None:
    if value is None:
        return None
    return sum(value >= threshold for threshold in thresholds)
