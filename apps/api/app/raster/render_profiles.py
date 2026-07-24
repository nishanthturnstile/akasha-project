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
    *,
    lower_percentile: float | None = None,
    upper_percentile: float | None = None,
) -> RenderDescriptor:
    if requested == "standard":
        return RenderDescriptor("standard", "standard", "standard-v1", (), ())
    if minimum is None or maximum is None:
        return RenderDescriptor("contrast", "standard", "standard-v1", (), (), "missing_statistics")
    stretch_min = lower_percentile if lower_percentile is not None else minimum
    stretch_max = upper_percentile if upper_percentile is not None else maximum
    if stretch_min is None or stretch_max is None:
        return RenderDescriptor("contrast", "standard", "standard-v1", (), (), "missing_statistics")
    if minimum == maximum:
        return RenderDescriptor("contrast", "standard", "standard-v1", (), (), "constant_scene")
    percentile_stretch = lower_percentile is not None and upper_percentile is not None
    if stretch_min >= stretch_max:
        # Very small or quantized fields can have identical P02/P98 values even
        # though valid outliers still provide a usable range.
        stretch_min, stretch_max = minimum, maximum
        percentile_stretch = False
    span = stretch_max - stretch_min
    version = "percentile-2-98-v1" if percentile_stretch else "equal-bands-v1"
    return RenderDescriptor(
        "contrast",
        "contrast",
        version,
        tuple(stretch_min + n * span / 5 for n in range(1, 6)),
        CONTRAST_PALETTE_V1,
    )


def category_for_value(
    value: float | None, thresholds: list[float] | tuple[float, ...]
) -> int | None:
    if value is None:
        return None
    return sum(value >= threshold for threshold in thresholds)
