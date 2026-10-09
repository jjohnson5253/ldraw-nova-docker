import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import preview_build
import tools
from store import ChatStore


@pytest.mark.parametrize("raises", [False, True])
def test_adapter_restores_structural_checker_and_reports_unchecked(raises):
    original = lambda *_: pytest.fail("Global geometry must be deferred")
    cli = SimpleNamespace(geometry_report=original)
    def run(args):
        assert cli.geometry_report(None, None, args)["complete"] is False
        if raises:
            raise ValueError("Invalid plan")
        return {"checks_passed": True, "written": True}, 0
    cli.run = run
    if raises:
        with pytest.raises(ValueError, match="Invalid plan"):
            preview_build.run_build(cli, SimpleNamespace(command="build"))
    else:
        report, status = preview_build.run_build(cli, SimpleNamespace(command="build"))
        assert status == 0 and report["written"] and report["construction_checks_passed"]
        assert not report["checks_passed"] and report["structural_checks_deferred"]
    assert cli.geometry_report is original


def test_adapter_refuses_other_commands():
    with pytest.raises(ValueError, match="only the build command"):
        preview_build.run_build(None, SimpleNamespace(command="validate"))


@pytest.mark.parametrize("mode,command,adapter", [
    ("preview", "build", True), ("verify", "build", False),
    ("preview", "render", False), ("verify", "validate", False),
])
def test_toolkit_routes_only_preview_construction(monkeypatch, mode, command, adapter):
    async def collect(ctx, argv, timeout):
        assert timeout == 90
        assert (argv[0] == "python3") == adapter
        assert argv[-2:] == [command, "plan.json"]
        if adapter:
            assert argv[1].endswith("/preview_build.py")
        return tools.ToolResult("ok")
    monkeypatch.setattr(tools, "_run_and_collect", collect)
    asyncio.run(tools.t_run_toolkit(SimpleNamespace(build_mode=mode), [command, "plan.json"], 90))


@pytest.mark.parametrize("prefix", [["--library", "/parts"], ["--shadow=/shadow", "--no-shadow"]])
def test_preview_build_routing_preserves_global_arguments(monkeypatch, prefix):
    arguments = [*prefix, "build", "plan.json"]
    async def collect(ctx, argv, timeout):
        assert argv[0] == "python3" and argv[2:] == arguments
        return tools.ToolResult("ok")
    monkeypatch.setattr(tools, "_run_and_collect", collect)
    asyncio.run(tools.t_run_toolkit(SimpleNamespace(build_mode="preview"), arguments))


@pytest.fixture
def builder_dir():
    with tempfile.TemporaryDirectory(prefix="preview-builder-test-") as directory:
        root = Path(directory)
        root.chmod(0o755)  # the sandboxed builder must traverse its own test root
        yield root


def test_real_preview_build_keeps_invalid_plans_and_overwrite_gates(builder_dir):
    store = ChatStore(builder_dir / "chats", builder_dir / "output")
    chat = store.create_chat()
    work = store.work_dir(chat["id"])
    plan = {"version": 1, "author": "Preview test", "sections": [{"name": "model.ldr", "description": "Two disconnected bricks", "steps": [[
        {"id": "left", "purpose": "Left brick", "ref": "3001.dat", "colour": 4, "at": [0, 0, 0]},
        {"id": "right", "purpose": "Right brick", "ref": "3001.dat", "colour": 4, "at": [400, 0, 0]},
    ]]}]}
    (work / "plan.json").write_text(json.dumps(plan))
    ctx = tools.ToolContext(chat["id"], store, lambda *_: None, build_mode="preview")
    def build(*extra):
        return asyncio.run(tools.run_command(ctx, ["python3", str(preview_build.__file__),
            "build", "output/plan.json", "--output", "output/model.mpd", *extra], 90))
    result = build("--report", "output/report.json")
    assert result.exit_code == 0, result.as_text()
    report = json.loads((work / "report.json").read_text())
    assert report["written"] and report["construction_checks_passed"]
    assert not report["checks_passed"] and report["geometry"]["complete"] is False
    text = (work / "model.mpd").read_text()
    assert "400 0 0" in text
    assert build().exit_code == 2  # existing output still requires --force
    plan["sections"][0]["steps"][0][0]["ref"] = "definitely-missing-part.dat"
    (work / "plan.json").write_text(json.dumps(plan))
    assert build("--force").exit_code != 0
    assert (work / "model.mpd").read_text() == text  # bad plan cannot replace valid output
