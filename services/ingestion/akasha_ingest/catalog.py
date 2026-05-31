"""pgSTAC catalog operations (Slice 1).

Wraps pypgstac for: schema migration, and idempotent (upsert) loading of the
Sentinel-2 L2A collection + sample item. pypgstac is imported lazily so this
module imports cleanly without it installed (static validation / `info`).

pypgstac 0.9.x matches the stac-fastapi-pgstac:5.0.2 runtime (>=0.8,<0.10).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Iterable

from . import config


def _require_dsn() -> str:
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set (required for pgSTAC).")
    return config.DATABASE_URL


def migrate_catalog() -> str:
    """Run pgSTAC migrations to the pypgstac-bundled schema version (idempotent)."""
    from pypgstac.db import PgstacDB  # lazy
    from pypgstac.migrate import Migrate  # lazy

    with PgstacDB(dsn=_require_dsn()) as db:
        version = Migrate(db).run_migration()
    return f"pgSTAC migrated to {version}"


def _write_ndjson(records: Iterable[dict]) -> Path:
    tmp = tempfile.NamedTemporaryFile("w", suffix=".ndjson", delete=False, encoding="utf-8")
    with tmp:
        for rec in records:
            tmp.write(json.dumps(rec) + "\n")
    return Path(tmp.name)


def load_collection(method: str = "upsert") -> str:
    from pypgstac.db import PgstacDB  # lazy
    from pypgstac.load import Loader, Methods  # lazy

    collection = json.loads(config.collection_file().read_text())
    ndjson = _write_ndjson([collection])
    try:
        with PgstacDB(dsn=_require_dsn()) as db:
            Loader(db=db).load_collections(str(ndjson), insert_mode=Methods(method))
    finally:
        ndjson.unlink(missing_ok=True)
    return f"loaded collection {collection.get('id')} (method={method})"


def load_items(method: str = "upsert") -> str:
    from pypgstac.db import PgstacDB  # lazy
    from pypgstac.load import Loader, Methods  # lazy

    item = json.loads(config.item_file().read_text())
    ndjson = _write_ndjson([item])
    try:
        with PgstacDB(dsn=_require_dsn()) as db:
            Loader(db=db).load_items(str(ndjson), insert_mode=Methods(method))
    finally:
        ndjson.unlink(missing_ok=True)
    return f"loaded item {item.get('id')} (method={method})"
