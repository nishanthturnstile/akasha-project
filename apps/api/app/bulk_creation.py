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
import os
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Crop, IrrigationType, PredefinedSeason, SeedingType, TillageType, Variety

DEFAULT_DATA_DIR = Path("/app/data/reference")

SEEDING_TYPES = [
    ("direct_seed", "Seeds sown directly in the field"),
    ("transplant", "Started in nursery, moved to field"),
    ("planting_cutting", "Vegetative propagation by cuttings or tubers"),
    ("vine", "Perennial vine crop"),
    ("perennial_tree", "Long-lived tree or shrub crop"),
]


def _candidate_data_dirs() -> list[Path]:
    """Return possible reference-data directories for Docker and repo checkouts."""

    candidates: list[Path] = []
    env_dir = os.environ.get("AKASHA_REFERENCE_DATA_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    candidates.append(DEFAULT_DATA_DIR)

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "scripts" / "data")
        candidates.append(parent / "data" / "reference")

    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def _data_path(filename: str) -> Path:
    for data_dir in _candidate_data_dirs():
        path = data_dir / filename
        if path.exists():
            return path
    searched = ", ".join(str(path) for path in _candidate_data_dirs())
    raise FileNotFoundError(
        f"Reference data file {filename!r} was not found. Searched: {searched}"
    )


def _load_json(filename: str) -> Any:
    with open(_data_path(filename), encoding="utf-8") as f:
        return json.load(f)


def generate_irrigation_types(session: Session) -> int:
    data = _load_json("irrigation-types.json")
    existing = {name for (name,) in session.query(IrrigationType.name).all()}
    count = 0
    for item in data:
        if item["name"] in existing:
            continue
        session.add(
            IrrigationType(name=item["name"], description=item.get("description"))
        )
        existing.add(item["name"])
        count += 1
    return count


def generate_tillage_types(session: Session) -> int:
    data = _load_json("tillage-types.json")
    existing = {name for (name,) in session.query(TillageType.name).all()}
    count = 0
    for item in data:
        if item["name"] in existing:
            continue
        session.add(
            TillageType(name=item["name"], description=item.get("description"))
        )
        existing.add(item["name"])
        count += 1
    return count


def generate_seeding_types(session: Session) -> int:
    existing = {name for (name,) in session.query(SeedingType.name).all()}
    count = 0
    for name, desc in SEEDING_TYPES:
        if name in existing:
            continue
        session.add(SeedingType(name=name, description=desc))
        existing.add(name)
        count += 1
    return count


CROP_JSON_FILENAME = "crop-akasha.json"

SEEDING_INT_TO_NAME = {
    0: "direct_seed",
    1: "transplant",
    2: "planting_cutting",
    3: "vine",
    4: "perennial_tree",
}


def generate_crops(session: Session) -> int:
    data_path = _data_path(CROP_JSON_FILENAME)
    data = json.loads(data_path.read_bytes())

    db_count = session.query(Crop).count()
    json_count = len(data)

    if db_count == json_count:
        return 0

    if db_count > 0:
        session.query(Variety).delete()
        session.query(Crop).delete()
        session.flush()

    seeding_map = {st.name: st.id for st in session.query(SeedingType).all()}

    count = 0
    for item in data:
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
                has_variety=item.get("has_varieties", False),
            )
        )
        count += 1
    return count


def generate_varieties(session: Session) -> int:
    data = _load_json("varieties.json")
    crop_map = {c.name: c.id for c in session.query(Crop).all()}
    existing = {
        (crop_id, name)
        for crop_id, name in session.query(Variety.crop_id, Variety.name).all()
    }
    count = 0
    for crop_name, varieties in data.items():
        crop_id = crop_map.get(crop_name)
        if not crop_id:
            continue
        for item in varieties:
            key = (crop_id, item["name"])
            if key in existing:
                continue
            maturity_options = item.get("maturity_options") or item.get("maturities")
            session.add(
                Variety(
                    crop_id=crop_id,
                    name=item["name"],
                    maturity_options=maturity_options or None,
                )
            )
            existing.add(key)
            count += 1
    return count


def _mmdd_to_date(mmdd: str) -> date:
    """Convert 'MM-DD' to date using current year (determined later)."""
    parts = mmdd.split("-")
    return date(date.today().year, int(parts[0]), int(parts[1]))


def _resolve_year(mmdd: str, base_year: int, period_start_month: int, wraps: bool) -> date:
    """Convert 'MM-DD' to a full date. If the season wraps to the next year
    (end month < start month), dates whose month is before *period_start_month*
    belong to the *next* year."""
    parts = mmdd.split("-")
    month = int(parts[0])
    day = int(parts[1])
    year = base_year if not (wraps and month < period_start_month) else base_year + 1
    return date(year, month, day)


def generate_predefined_seasons(session: Session) -> int:
    data = _load_json("predefined-seasons.json")
    existing = {name for (name,) in session.query(PredefinedSeason.season_name).all()}
    count = 0
    for item in data:
        if item["season_name"] in existing:
            continue

        ps_mmdd = item.get("period_start_date")
        pe_mmdd = item.get("period_end_date")
        if not ps_mmdd or not pe_mmdd:
            continue

        ps_month = int(ps_mmdd.split("-")[0])
        pe_month = int(pe_mmdd.split("-")[0])
        wraps = pe_month < ps_month
        base_year = date.today().year

        period_start = date(base_year, ps_month, int(ps_mmdd.split("-")[1]))
        period_end = _resolve_year(pe_mmdd, base_year, ps_month, wraps)

        def _resolve(v, _by=base_year, _ps=ps_month, _w=wraps):
            return _resolve_year(v, _by, _ps, _w) if v else None

        sowing_start = _resolve(item.get("sowing_start_date"))
        sowing_end = _resolve(item.get("sowing_end_date"))
        harvesting_start = _resolve(item.get("harvesting_start_date"))
        harvesting_end = _resolve(item.get("harvesting_end_date"))

        session.add(
            PredefinedSeason(
                season_name=item["season_name"],
                period_start_date=period_start,
                period_end_date=period_end,
                sowing_start_date=sowing_start,
                sowing_end_date=sowing_end,
                harvesting_start_date=harvesting_start,
                harvesting_end_date=harvesting_end,
                main_water_source=item.get("main_water_source"),
            )
        )
        existing.add(item["season_name"])
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
    with session_scope() as s:
        counts["predefined_seasons"] = generate_predefined_seasons(s)
    return counts
