"""Only stated guideline facts; every extracted assertion has a source citation."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal[
    "pedestrian",
    "rider",
    "car",
    "truck",
    "bus",
    "train",
    "motorcycle",
    "bicycle",
    "traffic light",
    "traffic sign",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Citation(StrictModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)


class Fact(Citation):
    field: str = Field(
        description="classes, merge.<class>, min_height_px.<class/default>, "
        "near_threshold_px, iou_loose, required_attributes"
    )


class Rule(Citation):
    id: str = Field(pattern=r"^R[1-9][0-9]*$")
    check: Literal["below_min_height", "class_not_allowed", "missing_attribute", "model_object_missing"]
    message: str = Field(
        min_length=1, description="Vietnamese reason template; rule engine supplies measured values"
    )


class VisualRule(Citation):
    id: str = Field(pattern=r"^V[1-9][0-9]*$")
    category: Category | None = None
    question: str = Field(min_length=1)


class Unclear(StrictModel):
    category: str | None = None
    field: str
    note: str = ""


class ExtractedSpec(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    classes: list[Category] = Field(default_factory=list)
    merge: dict[str, Category] = Field(default_factory=dict)
    min_height_px: dict[str, float] = Field(default_factory=dict)
    near_threshold_px: float | None = Field(default=None, ge=0)
    iou_loose: float | None = Field(default=None, gt=0, le=1)
    required_attributes: list[str] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    visual_rules: list[VisualRule] = Field(default_factory=list)
    unclear: list[Unclear] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_facts(self):
        if len(set(self.classes)) != len(self.classes):
            raise ValueError("Classes bị trùng")
        if any(
            key not in {*self.classes, "default"} or value < 0 for key, value in self.min_height_px.items()
        ):
            raise ValueError("min_height_px cần class được phép/default, ngưỡng không âm")
        if any(key == target or target not in self.classes for key, target in self.merge.items()):
            raise ValueError("Merge cần đích thuộc classes và không tự gộp")
        for start in self.merge:
            seen, current = set(), start
            while current in self.merge:
                if current in seen:
                    raise ValueError("Merge có vòng lặp")
                seen.add(current)
                current = self.merge[current]
        ids = [rule.id for rule in [*self.rules, *self.visual_rules]]
        if len(ids) != len(set(ids)):
            raise ValueError("Rule ID trùng")
        required = set()
        if self.classes:
            required.add("classes")
        if self.required_attributes:
            required.add("required_attributes")
        required.update(f"merge.{key}" for key in self.merge)
        required.update(f"min_height_px.{key}" for key in self.min_height_px)
        for key in ("near_threshold_px", "iou_loose"):
            if getattr(self, key) is not None:
                required.add(key)
        citations = {fact.field for fact in self.facts}
        if required - citations:
            raise ValueError(f"Thiếu citation cho các giá trị: {sorted(required - citations)}")
        for fact in self.facts:
            if fact.field not in required:
                raise ValueError(f"Citation cho field không có trong spec: {fact.field}")
            if fact.field.startswith("min_height_px.") or fact.field in {"near_threshold_px", "iou_loose"}:
                value = (
                    self.min_height_px[fact.field.removeprefix("min_height_px.")]
                    if fact.field.startswith("min_height_px.")
                    else getattr(self, fact.field)
                )
                # Catch simple hallucinated numeric thresholds before human review.
                numbers = [float(n.replace(",", ".")) for n in re.findall(r"-?\d+(?:[.,]\d+)?", fact.quote)]
                if value not in numbers:
                    raise ValueError(f"Ngưỡng {value} không xuất hiện trong quote {fact.field}")
        return self
