"""Owned sources, on-demand Rebrickable import, and the toolkit's BOM comparison."""
from __future__ import annotations

import asyncio
import csv
import io
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import uuid
from collections import Counter
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

import environment_config
import settings
import set_catalog
import toolkit

_lock = threading.RLock()
_api_lock = threading.Lock()
_last_request = 0.0
_cache: dict[str, tuple[float, dict]] = {}
API = "https://rebrickable.com/api/v3/lego/"
_compare_lock = asyncio.Semaphore(2)
_comparisons: dict[tuple, dict] = {}


def library() -> Path:
    env = environment_config.snapshot()
    return Path(env.get("LDRAW_DIR") or env.get("LDRAWDIR") or settings.LDRAW_DIR)


@lru_cache(maxsize=4)
def color_codes(root: Path) -> set[int]:
    return {int(c) for c in re.findall(r"\bCODE\s+(\d+)\b", (root / "LDConfig.ldr").read_text())} - {16, 24}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None  # Never forward the API key to another URL.


def catalog(path: str, **params) -> dict:
    key = environment_config.snapshot().get("REBRICKABLE_API_KEY")
    if not key:
        raise ValueError("Add REBRICKABLE_API_KEY in Settings → Environment to search and import sets")
    url = API + path + "?" + urlencode({"page_size": 1000, **params})
    global _last_request
    with _api_lock:
        cached = _cache.get(url)
        if cached and time.monotonic() - cached[0] < 3600:
            return cached[1]
        time.sleep(max(0, 1 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        try:
            with build_opener(NoRedirect()).open(Request(url, headers={"Authorization": "key " + key}), timeout=20) as response:
                data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise ValueError("Catalog response is too large")
            result = json.loads(data)
            if not isinstance(result, dict) or not isinstance(result.get("results", []), list):
                raise ValueError("Invalid catalog response")
        except Exception:
            raise ValueError("Rebrickable request failed. Check your API key, set number, and connection; try again shortly.") from None
        if len(_cache) >= 128:
            _cache.clear()
        _cache[url] = (time.monotonic(), result)
        return result


def catalog_rows(path: str, **params) -> list[dict]:
    rows = []
    for page in range(1, 31):
        data = catalog(path, page=page, **params)
        rows.extend(data["results"])
        if not data.get("next"):
            return rows
    raise ValueError("Inventory exceeds the import limit; nothing was imported")


def set_number(value: str) -> str | None:
    value = value.strip()
    if "://" in value:
        url = urlsplit(value)
        host = (url.hostname or "").removeprefix("www.")
        if url.scheme != "https" or url.port not in (None, 443):
            raise ValueError("Use an HTTPS LEGO, Rebrickable, or BrickLink set URL")
        if host == "rebrickable.com":
            value = url.path.split("/sets/")[-1].split("/")[0] if "/sets/" in url.path else ""
        elif host == "bricklink.com":
            value = parse_qs(url.query).get("S", [""])[0]
        elif host == "lego.com" and "/product/" in url.path:
            value = url.path.rstrip("/").split("-")[-1].split("/")[-1]
        else:
            raise ValueError("Use a LEGO, Rebrickable, or BrickLink set URL")
        if not re.fullmatch(r"\d{3,10}(?:-\d{1,3})?", value):
            raise ValueError("Cannot find a set number in this URL; enter the set number instead")
    if re.fullmatch(r"\d{3,10}(?:-\d{1,3})?", value):
        return value if "-" in value else value + "-1"
    return None


def search(value: str, page: int = 1) -> dict:
    if not value.strip() or len(value) > 500 or not 1 <= page <= 10000:
        raise ValueError("Enter a set name, number, or URL")
    number = set_number(value)
    return set_catalog.search(value, page, number)


def _part(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.lower().removesuffix(".dat")
    return value if re.fullmatch(r"[a-z0-9_-]+", value) else None


def _mapped(part: dict, color: dict, quantity: int) -> dict:
    candidates = {_part(p) for p in part.get("external_ids", {}).get("LDraw", [])}
    candidates.discard(None)
    candidates = {p for p in candidates if (library() / "parts" / (p + ".dat")).is_file()}
    colours = color.get("external_ids", {}).get("LDraw", {}).get("ext_ids", [])
    colours = {int(c) for c in colours if str(c).isdigit() and int(c) in color_codes(library())}
    return {"part": next(iter(candidates)) if len(candidates) == 1 else None,
            "colour": next(iter(colours)) if len(colours) == 1 else None, "quantity": quantity,
            "description": part.get("name", ""), "provider_part": part.get("part_num"), "provider_color": color.get("id")}


def preview(body: dict) -> dict:
    if body.get("set"):
        number = set_number(body["set"])
        if not number:
            raise ValueError("Choose a set from the search results")
        source = set_catalog.inventory(number, body.get("include_spares") is True)
        if source is not None:
            source["parts"] = _provider_parts(source["parts"])
        else:
            info = catalog(f"sets/{number}/")
            rows = catalog_rows(f"sets/{number}/parts/", inc_part_details=1, inc_minifig_parts=1)
            colors = {c["id"]: c for c in catalog_rows("colors/")}
            parts = [_mapped(row["part"], colors.get(row["color"]["id"], {}), row["quantity"])
                     for row in rows if not row.get("is_spare") or body.get("include_spares") is True]
            source = {"name": f"{number} · {info['name']}", "set_num": number, "parts": parts}
    else:
        text = body.get("csv", "")
        if not isinstance(text, str) or len(text.encode()) > 5 * 1024 * 1024:
            raise ValueError("Choose a CSV smaller than 5 MB")
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        fields = set(reader.fieldnames or [])
        provider = {"part_num", "color_id", "quantity"} <= fields
        if not provider and not {"part", "colour", "quantity"} <= fields:
            raise ValueError("CSV headers must be part,colour,quantity (LDraw), or part_num,color_id,quantity (Rebrickable)")
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) > 10000:
                raise ValueError("Import between 1 and 10,000 CSV rows")
        if not rows:
            raise ValueError("Import between 1 and 10,000 CSV rows")
        if provider and not body.get("include_spares"):
            rows = [r for r in rows if str(r.get("is_spare", "")).lower() not in ("true", "1")]
        parts = []
        for row in rows:
            try:
                quantity = int(row["quantity"])
                if provider:
                    row["quantity"] = quantity
                else:
                    parts.append({"part": row["part"], "colour": int(row["colour"]), "quantity": quantity})
            except (ValueError, TypeError):
                raise ValueError("CSV colors and quantities must be integers") from None
        source = {"name": body.get("name") or "Uploaded parts", "parts": _provider_parts(rows) if provider else parts}
    return clean_source(source)


def _provider_parts(rows: list[dict]) -> list[dict]:
    """Reuse batched API mapping for bulk inventories and Rebrickable CSV files."""
    colors = {str(c["id"]): c for c in catalog_rows("colors/")}
    ids = sorted({row["part_num"] for row in rows})
    if any(not _part(part) for part in ids):
        raise ValueError("Invalid Rebrickable part number")
    details = {}
    for offset in range(0, len(ids), 100):
        details.update({part["part_num"]: part for part in catalog_rows("parts/", part_nums=",".join(ids[offset:offset + 100]), inc_part_details=1)})
    return [_mapped(details.get(row["part_num"], {"part_num": row["part_num"], "name": row.get("name", "")}),
                    colors.get(str(row["color_id"]), {"id": row["color_id"]}), row["quantity"]) for row in rows]


def clean_source(source: dict) -> dict:
    if not isinstance(source, dict) or not isinstance(source.get("parts"), list) or not 1 <= len(source["parts"]) <= 10000:
        raise ValueError("A collection source needs between 1 and 10,000 part rows")
    copies = source.get("copies", 1)
    if type(copies) is not int or not 1 <= copies <= 1000 or type(source.get("available", True)) is not bool:
        raise ValueError("Use 1–1,000 copies and an availability checkbox")
    number = source.get("set_num")
    if number is not None and (not isinstance(number, str) or not re.fullmatch(r"\d{3,10}-\d{1,3}", number)):
        raise ValueError("Invalid source set number")
    parts = []
    for row in source["parts"]:
        part, colour, quantity = _part(row.get("part")), row.get("colour"), row.get("quantity")
        if type(quantity) is not int or not 0 <= quantity <= 100000:
            raise ValueError("Part quantities must be integers between 0 and 100,000")
        if row.get("part") is not None and part is None:
            raise ValueError("Invalid LDraw part ID")
        if colour is not None and (type(colour) is not int or colour not in color_codes(library())):
            raise ValueError("Use explicit colors from the LDraw library; 16 and 24 cannot describe owned colors")
        provider_part = row.get("provider_part") or part
        if part and not (library() / "parts" / (part + ".dat")).is_file():
            part = None
        parts.append({"description": str(row.get("description") or "")[:200],
                      "provider_part": str(provider_part)[:100] if provider_part else None,
                      "provider_color": row.get("provider_color") if type(row.get("provider_color")) is int else None,
                      "part": part, "colour": colour, "quantity": quantity})
    return {"name": str(source.get("name", "My parts"))[:200], "set_num": source.get("set_num"),
            "copies": copies, "available": source.get("available", True), "parts": parts}


def sources() -> list[dict]:
    with _lock:
        try:
            return json.loads((settings.DATA_DIR / "collection.json").read_text())
        except FileNotFoundError:
            return []


def save(source: dict | None, source_id: str | None = None) -> list[dict]:
    with _lock:
        rows = sources()
        if source_id and not any(r["id"] == source_id for r in rows):
            raise ValueError("This source was removed; reload My parts")
        rows = [r for r in rows if r["id"] != source_id]
        if source is not None:
            rows.append({"id": source_id or uuid.uuid4().hex, **clean_source(source)})
        if len(rows) > 200 or sum(len(r["parts"]) for r in rows) > 50000:
            raise ValueError("Collection exceeds 200 sources or 50,000 rows")
        if sum(p["quantity"] * r["copies"] for r in rows for p in r["parts"]) > 100_000_000:
            raise ValueError("Collection exceeds 100 million pieces")
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=settings.DATA_DIR, prefix=".collection-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(rows, stream)
            os.replace(tmp, settings.DATA_DIR / "collection.json")
        finally:
            Path(tmp).unlink(missing_ok=True)
        return rows


def snapshot() -> dict:
    stock = Counter()
    for source in sources():
        if source["available"]:
            for row in source["parts"]:
                key = (row["part"], row["colour"]) if row["part"] and row["colour"] is not None else (None, None)
                stock[key] += row["quantity"] * source["copies"]
    return {"parts": [{"part": part, "colour": colour, "quantity": quantity} for (part, colour), quantity in stock.items() if quantity]}


async def compare(model: Path, inventory: dict) -> dict:
    key = (str(model.resolve()), model.stat().st_mtime_ns, model.stat().st_size, hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest())
    async with _compare_lock:
        if key not in _comparisons:
            report = await _compare(model, inventory)
            if len(_comparisons) >= 128:
                _comparisons.clear()
            _comparisons[key] = report
        return _comparisons[key]


async def _compare(model: Path, inventory: dict) -> dict:
    # Backend-owned temporary files keep the authoritative snapshot/report out
    # of the agent's writable workspace. Reuse physical_context via the CLI.
    with tempfile.TemporaryDirectory(prefix="nova-inventory-") as directory:
        folder = Path(directory)
        owned, report = folder / "owned.json", folder / "bom.json"
        owned.write_text(json.dumps(inventory))
        process = await asyncio.create_subprocess_exec(
            str(toolkit.root() / ".venv/bin/python"), "-m", "ldraw_tools.cli", "bom", str(model),
            "--inventory", str(owned), "--report", str(report), cwd=toolkit.root(),
            env={"HOME": "/tmp", **toolkit.environment(), "LDRAW_NOVA_CACHE_DIR": str(settings.CONFIG_DIR / "bom-cache")},
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(process.wait(), timeout=60)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            process.kill()
            await process.wait()
            raise
        if process.returncode not in (0, 1) or not report.is_file():
            raise ValueError("Cannot inspect this model's parts list")
        data = json.loads(report.read_text())
        if "inventory" not in data or not data.get("checks_passed"):
            raise ValueError("Cannot compare an invalid or unresolved model")
        return data["inventory"]
