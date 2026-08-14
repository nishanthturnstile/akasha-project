from __future__ import annotations

import json

from app import bulk_creation
from app.models import Crop, CropGrowthStage, SeedingType


class _Query:
    def __init__(self, session: _Session, model: type) -> None:
        self.session = session
        self.model = model
        self.crop_id: int | None = None

    def all(self):
        if self.model is Crop:
            return list(self.session.crops)
        if self.model is SeedingType:
            return list(self.session.seeding_types)
        if self.model is CropGrowthStage:
            return list(self.session.stages)
        raise AssertionError(f"Unexpected query model: {self.model}")

    def filter(self, criterion):
        self.crop_id = criterion.right.value
        return self

    def delete(self, synchronize_session=False):
        assert synchronize_session is False
        before = len(self.session.stages)
        self.session.stages[:] = [
            stage for stage in self.session.stages if stage.crop_id != self.crop_id
        ]
        return before - len(self.session.stages)


class _Session:
    def __init__(self) -> None:
        self.crops: list[Crop] = []
        self.seeding_types = [SeedingType(id=1, name="direct_seed")]
        self.stages: list[CropGrowthStage] = []
        self._next_crop_id = 1

    def query(self, model: type) -> _Query:
        return _Query(self, model)

    def add(self, value) -> None:
        if isinstance(value, Crop):
            self.crops.append(value)
        elif isinstance(value, CropGrowthStage):
            self.stages.append(value)
        else:
            raise AssertionError(f"Unexpected added model: {value}")

    def flush(self) -> None:
        for crop in self.crops:
            if crop.id is None:
                crop.id = self._next_crop_id
                self._next_crop_id += 1


def test_generate_crops_upserts_and_refreshes_stages_without_deleting_other_crops(
    tmp_path, monkeypatch
):
    data_path = tmp_path / bulk_creation.CROP_JSON_FILENAME
    data = [
        {
            "name_en": "Wheat",
            "color": "#old",
            "maturities": [{"name": "early"}],
            "seeding_type": 0,
            "has_varieties": False,
            "has_weather_risks": False,
            "bbch_mode": 10,
            "characteristic": 2,
            "stages": [
                {"name": "Germination", "duration": "0-10"},
                {"name": "Tillering", "duration": "25-45"},
            ],
        }
    ]
    data_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(bulk_creation, "_data_path", lambda filename: data_path)

    session = _Session()
    assert bulk_creation.generate_crops(session) == 1
    wheat = session.crops[0]
    wheat_id = wheat.id
    assert [(stage.seq, stage.name) for stage in session.stages] == [
        (1, "Germination"),
        (2, "Tillering"),
    ]

    unrelated = Crop(id=99, name="Unrelated crop")
    session.crops.append(unrelated)
    data[0]["color"] = "#new"
    data[0]["stages"] = [
        {"name": "Germination", "duration": "0-12"},
        {"name": "Stem Extension", "duration": "30-50"},
        {"name": "Harvest", "duration": "120-140"},
    ]
    data_path.write_text(json.dumps(data), encoding="utf-8")

    assert bulk_creation.generate_crops(session) == 0
    assert wheat.id == wheat_id
    assert wheat.color == "#new"
    assert unrelated in session.crops
    assert [(stage.seq, stage.name, stage.duration) for stage in session.stages] == [
        (1, "Germination", "0-12"),
        (2, "Stem Extension", "30-50"),
        (3, "Harvest", "120-140"),
    ]
