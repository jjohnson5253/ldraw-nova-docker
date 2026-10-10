"""Regression coverage for restoring the single, complete generation workflow."""
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import agent
import main
import model_catalog
import settings
import tools
from sandbox import RunResult
from store import ChatStore
from test_agent import chunk, scripted, tool_call_chunks


@pytest.mark.parametrize("legacy_mode", ["preview", "verify", None])
def test_old_modes_cannot_select_an_unchecked_workflow(legacy_mode):
    entry = {"litellm_params": {"model": "openai/gpt-6-luna"}}
    options = model_catalog.validate_options(entry, {"build_mode": legacy_mode})
    assert "build_mode" not in options
    assert options["effort"] == model_catalog.entry_profile(entry)["default_effort"]
    assert "unchecked" not in next(t for t in agent.available_tools(options)
        if t["function"]["name"] == "publish_model")["function"]["description"]


def test_generation_continues_review_after_publication(monkeypatch, tmp_path):
    import llm_config
    store = ChatStore(tmp_path / "chats", tmp_path / "output")
    chat = store.create_chat()
    entry = llm_config.create({"litellm_params": {"model": "openai/gpt-6-luna", "api_key": "test"},
                              "capabilities": {"tools": True, "vision": True}})
    fake, calls = scripted([
        tool_call_chunks("publish", "publish_model", {"path": "output/model.mpd"}),
        [chunk(content="Visual review complete. Done.")],
    ])
    async def dispatch(ctx, name, args):
        assert not hasattr(ctx, "build_mode")
        return tools.ToolResult("Geometry checked", models=[{"id": "model"}])
    monkeypatch.setattr(agent, "dispatch", dispatch)
    monkeypatch.setattr(agent.litellm, "acompletion", fake)
    async def run():
        await agent.start_turn(store, chat["id"], "Create a model", entry["id"],
                               {"permissions": "full", "build_mode": "preview"})
        await agent._runs[chat["id"]].task
    asyncio.run(run())
    assert len(calls) == 2
    assert store.messages(chat["id"])[-1]["content"] == "Visual review complete. Done."
    assert "PREVIEW WORKFLOW OVERRIDE" not in calls[0]["messages"][0]["content"]


def test_publication_always_runs_geometry_and_render(monkeypatch, tmp_path):
    store = ChatStore(tmp_path / "chats", tmp_path / "output")
    chat = store.create_chat()
    (store.work_dir(chat["id"]) / "model.mpd").write_text("0 FILE model.ldr\n1 4 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n")
    monkeypatch.setattr(settings, "GENERATED_DIR", tmp_path / "generated")
    calls = []
    async def command(ctx, argv, timeout):
        calls.append(argv)
        if argv[1] == "validate":
            Path(argv[-1]).write_text("{}")
        return RunResult(exit_code=0, stdout="", stderr="", timed_out=False, seconds=0)
    monkeypatch.setattr(tools, "run_command", command)
    result = asyncio.run(tools.t_publish_model(tools.ToolContext(chat["id"], store, lambda *_: None), "model.mpd"))
    assert [a[1] for a in calls] == ["validate", "render"]
    assert "--geometry" in calls[0] and json.loads(result.content)["checks_passed"]


def test_removed_verification_endpoint_is_unavailable():
    assert TestClient(main.app).post("/api/chats/chat/verify", json={}).status_code in {404, 405}
