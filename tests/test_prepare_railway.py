import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_railway", ROOT / "scripts/prepare_railway.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RailwayBuildTests(unittest.TestCase):
    def test_preserves_local_context_and_other_stage_copies(self):
        recipe = "COPY web/backend/ /app/web/backend/\nCOPY --from=frontend /src/dist/ /opt/web/static/\n"
        self.assertIn(recipe.rstrip(), MODULE.railway_dockerfile(recipe))

    def test_maps_each_toolkit_source_to_fetched_checkout(self):
        recipe = "COPY --from=nova *.py LICENSE ldraw_tools/ /opt/nova/\n"
        generated = MODULE.railway_dockerfile(recipe)
        self.assertIn("COPY --from=nova /source/*.py /source/LICENSE /source/ldraw_tools/ /opt/nova/", generated)

    def test_rejects_unsupported_copy_before_writing_a_build(self):
        for recipe in ('COPY --from=nova ["LICENSE", "/opt/nova/"]', "COPY --from=nova LICENSE \\"):
            with self.subTest(recipe=recipe), self.assertRaises(ValueError):
                MODULE.railway_dockerfile(recipe)

    def test_rejects_moving_refs_and_shell_input_in_source_repositories(self):
        for revision in ("main-BrickBuilderAI", "a" * 39, "a" * 40 + "; exit 0"):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                MODULE.source_stage("nova", MODULE.TOOLKIT_REPOSITORY, revision)
        with self.assertRaises(ValueError):
            MODULE.source_stage("nova", "https://github.com/a/b.git; exit 0", MODULE.TOOLKIT_REVISION)

    def test_railway_manages_persistence_without_docker_volumes(self):
        generated = MODULE.railway_dockerfile('RUN mkdir -p /data\nVOLUME ["/data", "/config"]\n')
        self.assertIn("RUN mkdir -p /data", generated)
        self.assertNotIn('VOLUME [', generated)

    def test_checked_in_build_matches_current_upstream_recipe_and_pins(self):
        self.assertEqual((ROOT / "Railway.Dockerfile").read_text(), MODULE.railway_dockerfile((ROOT / "Dockerfile").read_text()))


if __name__ == "__main__":
    unittest.main()
