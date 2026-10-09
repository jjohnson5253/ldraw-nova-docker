from pathlib import Path
import pytest
import subprocess
import settings
from parts_policy import expanded_inventory
from parts_catalog import PartsCatalog, PartsUnavailable
from parts_inventory import check_rigid_transform

MODEL = '0 FILE root.ldr\n1 4 0 0 0 1 0 0 0 1 0 0 0 1 child.ldr\n0 FILE child.ldr\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n'


def model_inventory(source, library):
    return expanded_inventory(source.read_bytes(), settings.TOOLKIT_DIR, library)


def library():
    path = Path('/opt/ldraw/ldraw')
    if not path.exists():
        pytest.skip('Real LDraw library available in the Nova image')
    return path


def test_real_hierarchy_colors_and_unknown_dependencies(tmp_path):
    source = tmp_path / 'model.mpd'; source.write_text(MODEL)
    inventory = model_inventory(source, library())
    assert inventory == {('3001', 4): 1}
    catalog = PartsCatalog.from_csv('part_id,color_id\n3001,4\n')
    catalog.validate(inventory)
    source.write_text(MODEL.replace('1 4 ', '1 0 '))
    with pytest.raises(PartsUnavailable):
        catalog.validate(model_inventory(source, library()))
    for reference in ('missing.ldr', 'missing.dat'):
        source.write_text(MODEL.replace('3001.dat', reference))
        with pytest.raises((ValueError, FileNotFoundError, KeyError, subprocess.SubprocessError)):
            model_inventory(source, library())


def test_real_parser_rejects_embedded_part_override(tmp_path):
    source = tmp_path / 'model.mpd'; source.write_text(MODEL + '0 FILE 3001.dat\n0 Fake\n')
    with pytest.raises(PartsUnavailable):
        model_inventory(source, library())


def test_rounded_rotation_is_allowed_but_geometry_changes_are_rejected():
    check_rigid_transform([[0.707107, 0, 0.707107], [0, 1, 0], [-0.707107, 0, 0.707107]])
    for matrix in ([[2, 0, 0], [0, 1, 0], [0, 0, 1]],
                   [[1, 0.1, 0], [0, 1, 0], [0, 0, 1]],
                   [[-1, 0, 0], [0, 1, 0], [0, 0, 1]],
                   [[float('nan'), 0, 0], [0, 1, 0], [0, 0, 1]]):
        with pytest.raises(ValueError):
            check_rigid_transform(matrix)
