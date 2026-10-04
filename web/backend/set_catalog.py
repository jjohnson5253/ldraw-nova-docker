"""Persistent set search, populated from Rebrickable's complete bulk catalog."""
from __future__ import annotations

import csv
import gzip
import json
import os
import sqlite3
import tempfile
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import build_opener

import settings

_lock = threading.RLock()
_worker: threading.Thread | None = None
_stop = threading.Event()
_progress: dict = {}


def path() -> Path:
    return settings.DATA_DIR / "catalog" / "rebrickable.sqlite"


def connect() -> sqlite3.Connection:
    return sqlite3.connect(path().as_uri() + "?mode=ro", uri=True)


def status() -> dict:
    with _lock:
        saved = {}
        if path().is_file():
            with closing(connect()) as db:
                saved = json.loads(db.execute("SELECT value FROM metadata").fetchone()[0])
        return {"ready": bool(saved) and _progress.get("state") != "syncing", "state": "ready" if saved else "empty", **saved, **_progress}


def _update(**values):
    with _lock:
        _progress.update(values)


def _download(name: str, folder: Path):
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
        yield from csv.DictReader(stream)


def _build():
    try:
        path().parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rebrickable-", dir=path().parent) as folder:
            folder = Path(folder)
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
            # A failed refresh leaves the previously downloaded catalog usable.
            with _lock:
                if _stop.is_set():
                    raise InterruptedError
                os.replace(target, path())
                _progress.clear()
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
        if (_worker and _worker.is_alive()) or (path().is_file() and not refresh):
            return
        _stop.clear()
        _progress.clear()
        _update(state="syncing", stage="Starting catalog download", indexed=0)
        _worker = threading.Thread(target=_build, name="rebrickable-catalog", daemon=True)
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
