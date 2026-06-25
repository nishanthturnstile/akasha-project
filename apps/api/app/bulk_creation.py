"""Idempotent generator functions for reference/lookup tables.

Each function reads from a JSON file in scripts/data/ and inserts
rows that don't already exist.  Each can be called standalone with
any SQLAlchemy Session; dependencies (FK targets) must already exist.

Usage:
    from app.db import session_scope
    from app.bulk_creation import generate_all

    with session_scope() as session:
        generate_all()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Crop, IrrigationType, SeedingType, TillageType, Variety

DATA_DIR = Path("/app/data/reference")

SEEDING_TYPES = [
    ("direct_seed", "Seeds sown directly in the field"),
    ("transplant", "Started in nursery, moved to field"),
    ("planting_cutting", "Vegetative propagation by cuttings or tubers"),
    ("vine", "Perennial vine crop"),
    ("perennial_tree", "Long-lived tree or shrub crop"),
]


def _load_json(filename: str) -> Any:
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def generate_irrigation_types(session: Session) -> int:
    data = _load_json("irrigation-types.json")
    count = 0
    for item in data:
        if session.query(IrrigationType).filter_by(name=item["name"]).first():
            continue
        session.add(
            IrrigationType(name=item["name"], description=item.get("description"))
        )
        count += 1
    return count


def generate_tillage_types(session: Session) -> int:
    data = _load_json("tillage-types.json")
    count = 0
    for item in data:
        if session.query(TillageType).filter_by(name=item["name"]).first():
            continue
        session.add(
            TillageType(name=item["name"], description=item.get("description"))
        )
        count += 1
    return count


def generate_seeding_types(session: Session) -> int:
    count = 0
    for name, desc in SEEDING_TYPES:
        if session.query(SeedingType).filter_by(name=name).first():
            continue
        session.add(SeedingType(name=name, description=desc))
        count += 1
    return count


def generate_crops(session: Session) -> int:
    data = _load_json("crops.json")
    seeding_map = {st.name: st.id for st in session.query(SeedingType).all()}
    SEEDING_INT_TO_NAME = {
        0: "direct_seed",
        1: "transplant",
        2: "planting_cutting",
        3: "vine",
        4: "perennial_tree",
    }
    count = 0
    for item in data:
        if session.query(Crop).filter_by(name=item["name_en"]).first():
            continue
        st_int = item["seeding_type"]
        st_name = SEEDING_INT_TO_NAME.get(st_int) if isinstance(st_int, int) else st_int
        seeding_type_id = seeding_map.get(st_name)
        maturity_options = [
            m["name"] for m in (item.get("maturities") or [])
        ] or None
        bbch = item.get("bbch_mode")
        if isinstance(bbch, int):
            bbch = str(bbch)
        characteristic = item.get("characteristic")
        if isinstance(characteristic, int):
            characteristic = str(characteristic)
        session.add(
            Crop(
                name=item["name_en"],
                seeding_type_id=seeding_type_id,
                color=item.get("color"),
                maturity_options=maturity_options,
                has_weather_risk=item.get("has_weather_risks", False),
                bbch_mode=bbch,
                characteristic=characteristic,
            )
        )
        count += 1
    return count


def generate_varieties(session: Session) -> int:
    data = _load_json("varieties.json")
    crop_map = {c.name: c.id for c in session.query(Crop).all()}
    count = 0
    for crop_name, varieties in data.items():
        crop_id = crop_map.get(crop_name)
        if not crop_id:
            continue
        for item in varieties:
            if (
                session.query(Variety)
                .filter_by(crop_id=crop_id, name=item["name"])
                .first()
            ):
                continue
            maturity_options = item.get("maturity_options") or item.get("maturities")
            session.add(
                Variety(
                    crop_id=crop_id,
                    name=item["name"],
                    maturity_options=maturity_options or None,
                )
            )
            count += 1
    return count


def generate_all() -> dict[str, int]:
    counts: dict[str, int] = {}
    with session_scope() as s:
        counts["seeding_types"] = generate_seeding_types(s)
    with session_scope() as s:
        counts["irrigation_types"] = generate_irrigation_types(s)
    with session_scope() as s:
        counts["tillage_types"] = generate_tillage_types(s)
    with session_scope() as s:
        counts["crops"] = generate_crops(s)
    with session_scope() as s:
        counts["varieties"] = generate_varieties(s)
    return counts
