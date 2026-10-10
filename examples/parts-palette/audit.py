"""Independently expand both real example outputs and compare them to the CSV.

Run with the paired toolkit interpreter and PYTHONPATH pointing to that toolkit:
  python audit.py /opt/ldraw/ldraw restricted.mpd unrestricted.mpd
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ldraw_tools.catalog_inventory import model_inventory
from ldraw_tools.parts_catalog import PartsCatalog, PartsUnavailable


def audit(source: Path, library: Path, palette: PartsCatalog) -> dict:
    inventory = model_inventory(source, library)
    try:
        palette.validate(inventory)
        valid, error = True, None
    except PartsUnavailable as exc:
        valid, error = False, str(exc)
    rows = [{"part_id": part, "color_id": color, "quantity": quantity,
             "in_palette": (part, color) in palette.parts}
            for (part, color), quantity in sorted(inventory.items())]
    return {"file": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "physical_parts": sum(inventory.values()), "distinct_pairs": len(inventory),
            "outside_palette_parts": sum(row['quantity'] for row in rows if not row['in_palette']),
            "palette_valid": valid, "error": error, "inventory": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('library', type=Path)
    parser.add_argument('restricted', type=Path)
    parser.add_argument('unrestricted', type=Path)
    args = parser.parse_args()
    palette = PartsCatalog.load(Path(__file__).with_name('garden-tower.csv'))
    print(json.dumps({"palette": "garden-tower.csv", "allowed_combinations": len(palette.parts),
                      "restricted": audit(args.restricted, args.library, palette),
                      "unrestricted": audit(args.unrestricted, args.library, palette)}, indent=2))


if __name__ == '__main__':
    main()
