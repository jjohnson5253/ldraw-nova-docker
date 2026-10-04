"""Persistent search and inventories from Rebrickable's complete bulk catalog."""
from __future__ import annotations

import csv
import gzip
import json
import os
import sqlite3
import tempfile
import threading
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import build_opener

import settings

_lock = threading.RLock()
_worker: threading.Thread | None = None
_stop = threading.Event()
_progress: dict = {}
# Only reference data is downloaded; image URLs and image files are unnecessary.
DATASETS = {
    "inventories": ("id INTEGER PRIMARY KEY, version INTEGER, set_num TEXT", ("set_num",)),
    "inventory_parts": ("inventory_id INTEGER, part_num TEXT, color_id INTEGER, quantity INTEGER, is_spare TEXT", ("inventory_id", "part_num")),
    "inventory_minifigs": ("inventory_id INTEGER, fig_num TEXT, quantity INTEGER", ("inventory_id",)),
    "inventory_sets": ("inventory_id INTEGER, set_num TEXT, quantity INTEGER", ("inventory_id",)),
    "parts": ("part_num TEXT PRIMARY KEY, name TEXT, part_cat_id INTEGER, part_material TEXT", ()),
    "colors": ("id INTEGER PRIMARY KEY, name TEXT, rgb TEXT, is_trans TEXT", ()),
    "minifigs": ("fig_num TEXT PRIMARY KEY, name TEXT, num_parts INTEGER", ()),
    "part_relationships": ("rel_type TEXT, child_part_num TEXT, parent_part_num TEXT", ("child_part_num", "parent_part_num")),
    "elements": ("element_id TEXT PRIMARY KEY, part_num TEXT, color_id INTEGER, design_id TEXT", ("part_num",)),
    "part_categories": ("id INTEGER PRIMARY KEY, name TEXT", ()),
}


def path() -> Path:
    return settings.DATA_DIR / "catalog" / "rebrickable.sqlite"


def inventory_path() -> Path:
    return path().with_name("rebrickable-inventories.sqlite")


def connect(target: Path | None = None) -> sqlite3.Connection:
    return sqlite3.connect((target or path()).as_uri() + "?mode=ro", uri=True)


def _metadata(target: Path) -> dict:
    if not target.is_file():
        return {}
    with closing(connect(target)) as db:
        return json.loads(db.execute("SELECT value FROM metadata").fetchone()[0])


def status() -> dict:
    with _lock:
        saved = _metadata(path())
        inventories = _metadata(inventory_path())
        return {"ready": bool(saved) and _progress.get("state") != "syncing",
                "inventory_ready": bool(inventories), "state": "ready" if saved else "empty",
                **saved, **inventories, **_progress}


def _update(**values):
    with _lock:
        _progress.update(values)


def _download(name: str, folder: Path, fields: list[str] | None = None):
    # Bulk files are public. Never send the user's API key to the CDN.
    from collection import NoRedirect
    target = folder / (name + ".csv.gz")
    with build_opener(NoRedirect()).open(
        "https://cdn.rebrickable.com/media/downloads/" + name + ".csv.gz", timeout=20
    ) as response, target.open("wb") as out:
        size = 0
        while chunk := response.read(65536):
            if _stop.is_set():
                raise InterruptedError
            size += len(chunk)
            if size > 20 * 1024 * 1024:
                raise ValueError("Catalog download exceeds the size limit")
            out.write(chunk)
    with gzip.open(target, "rt", encoding="utf-8-sig", newline="") as stream:
        if fields is None:
            yield from csv.DictReader(stream)
        else:
            reader = csv.reader(stream)
            headers = next(reader)
            indexes = [headers.index(field) for field in fields]
            yield from ([row[index] for index in indexes] for row in reader)


def _publish(target: Path, destination: Path, **progress):
    with _lock:
        if _stop.is_set():
            raise InterruptedError
        os.replace(target, destination)
        _progress.clear()
        _progress.update(progress)


def _build_sets(folder: Path):
    _update(state="syncing", stage="Downloading themes")
    themes = {int(row["id"]): row for row in _download("themes", folder)}

    def theme_names(theme_id):
        names, seen = [], set()
        while theme_id in themes and theme_id not in seen:
            seen.add(theme_id)
            row = themes[theme_id]
            names.append(row["name"])
            theme_id = int(row["parent_id"]) if row["parent_id"] else None
        return " ".join(names)

    _update(stage="Downloading and indexing all sets")
    target = folder / "catalog.sqlite"
    with sqlite3.connect(target) as db:
        db.execute("CREATE TABLE sets (set_num TEXT PRIMARY KEY, name TEXT, year INTEGER, num_parts INTEGER, theme TEXT)")
        count = 0
        for row in _download("sets", folder):
            if _stop.is_set():
                raise InterruptedError
            db.execute("INSERT INTO sets VALUES (?, ?, ?, ?, ?)", (
                row["set_num"], row["name"], int(row["year"]), int(row["num_parts"]), theme_names(int(row["theme_id"]))
            ))
            count += 1
            if count % 1000 == 0:
                _update(indexed=count)
        if not count:
            raise ValueError("Empty catalog")
        saved = {"total_sets": count, "updated_at": datetime.now(timezone.utc).isoformat()}
        db.execute("CREATE TABLE metadata (value TEXT)")
        db.execute("INSERT INTO metadata VALUES (?)", (json.dumps(saved),))
    db.close()
    _publish(target, path(), state="inventory_syncing", stage="Starting parts catalog download", indexed=0)


def _build_inventories(folder: Path):
    target = folder / "inventories.sqlite"
    counts = {}
    with closing(sqlite3.connect(target)) as db, db:
        for name, (schema, indexes) in DATASETS.items():
            _update(state="inventory_syncing", stage="Downloading and indexing " + name.replace("_", " "), indexed=0)
            fields = [column.split()[0] for column in schema.split(", ")]
            db.execute(f"CREATE TABLE {name} ({schema})")

            def rows():
                count = 0
                for row in _download(name, folder, fields):
                    count += 1
                    if count % 10000 == 0:
                        if _stop.is_set():
                            raise InterruptedError
                        _update(indexed=count)
                    yield row
                counts[name] = count

            db.executemany(f"INSERT INTO {name} VALUES ({','.join('?' for _ in fields)})", rows())
            for field in indexes:
                db.execute(f"CREATE INDEX {name}_{field} ON {name} ({field})")
        if not counts["inventories"] or not counts["inventory_parts"] or not counts["parts"]:
            raise ValueError("Empty inventory catalog")
        saved = {"total_parts": counts["parts"], "total_inventory_rows": counts["inventory_parts"],
                 "inventory_updated_at": datetime.now(timezone.utc).isoformat()}
        db.execute("CREATE TABLE metadata (value TEXT)")
        db.execute("INSERT INTO metadata VALUES (?)", (json.dumps(saved),))
    _publish(target, inventory_path())


def _build(refresh: bool):
    try:
        path().parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rebrickable-", dir=path().parent) as folder:
            folder = Path(folder)
            if refresh or not path().is_file():
                _build_sets(folder)
            if refresh or not inventory_path().is_file():
                _build_inventories(folder)
    except InterruptedError:
        with _lock:
            _progress.clear()
    except Exception:
        _update(state="error", stage="", error="Catalog download failed. Check your connection and retry.")


def ensure(*, refresh: bool = False):
    import environment_config
    global _worker
    with _lock:
        if not environment_config.snapshot().get("REBRICKABLE_API_KEY"):
            return
        if (_worker and _worker.is_alive()) or (path().is_file() and inventory_path().is_file() and not refresh):
            return
        _stop.clear()
        _progress.clear()
        _update(state="syncing" if refresh or not path().is_file() else "inventory_syncing", stage="Starting catalog download", indexed=0)
        _worker = threading.Thread(target=_build, args=(refresh,), name="rebrickable-catalog", daemon=True)
        _worker.start()


def shutdown():
    _stop.set()
    if _worker:
        _worker.join(timeout=25)


def search(value: str, page: int, number: str | None) -> dict:
    terms = value.strip().split()
    clause = "set_num = ?" if number else " AND ".join("(name LIKE ? ESCAPE '\\' OR theme LIKE ? ESCAPE '\\')" for _ in terms)
    params = [number] if number else ["%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for term in terms for _ in range(2)]
    with _lock:
        if not path().is_file() or _progress.get("state") == "syncing":
            raise ValueError("The set catalog is not ready. Wait for indexing to finish, or retry the download in My parts.")
        with closing(connect()) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT set_num, name, year, num_parts FROM sets WHERE " + clause +
                              " ORDER BY (num_parts > 0) DESC, year DESC, set_num LIMIT 21 OFFSET ?", [*params, (page - 1) * 20]).fetchall()
    return {"sets": [dict(row) for row in rows[:20]], "next": len(rows) > 20}


def inventory(number: str, include_spares: bool = False) -> dict | None:
    """Expand the latest inventories, including minifigures and contained sets."""
    with _lock:
        if not path().is_file() or not inventory_path().is_file():
            return None  # Use the API while the bulk inventory catalog downloads.
        with closing(connect()) as db:
            info = db.execute("SELECT name FROM sets WHERE set_num = ?", (number,)).fetchone()
        if not info:
            return None
        with closing(connect(inventory_path())) as db:
            db.row_factory = sqlite3.Row
            stock = Counter()

            def expand(item: str, copies: int, ancestors: set[str]):
                if item in ancestors or len(ancestors) >= 20:
                    raise ValueError("Cyclic or excessively nested set inventory")
                found = db.execute("SELECT id FROM inventories WHERE set_num = ? ORDER BY version DESC, id DESC LIMIT 1", (item,)).fetchone()
                if not found:
                    raise LookupError(item)  # Incomplete bulk data: fall back to the API.
                inventory_id = found["id"]
                for row in db.execute("SELECT part_num, color_id, quantity, is_spare FROM inventory_parts WHERE inventory_id = ?", (inventory_id,)):
                    if include_spares or str(row["is_spare"]).lower() not in {"true", "t", "1"}:
                        stock[row["part_num"], row["color_id"]] += row["quantity"] * copies
                for table, field in (("inventory_minifigs", "fig_num"), ("inventory_sets", "set_num")):
                    for row in db.execute(f"SELECT {field}, quantity FROM {table} WHERE inventory_id = ?", (inventory_id,)):
                        expand(row[field], copies * row["quantity"], ancestors | {item})
                if len(stock) > 10000 or sum(stock.values()) > 100_000_000:
                    raise ValueError("Inventory exceeds the import limit")

            try:
                expand(number, 1, set())
            except LookupError:
                return None
            ids = sorted({part for part, _ in stock})
            names = {row["part_num"]: row["name"] for row in db.execute(
                "SELECT part_num, name FROM parts WHERE part_num IN (" + ",".join("?" for _ in ids) + ")", ids)}
            parts = [{"part_num": part, "color_id": color, "quantity": quantity, "name": names.get(part, "")}
                     for (part, color), quantity in stock.items()]
            return {"name": f"{number} · {info[0]}", "set_num": number, "parts": parts}
