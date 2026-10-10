"""Rebuild the lookout MPD from its editable JSON plan."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
subprocess.run([str(root / "ldraw-agent"), "build",
                str(root / "output/red-garden-lookout.plan.json"),
                "--output", str(root / "output/red-garden-lookout.mpd"),
                "--force"], check=True, cwd=root)
