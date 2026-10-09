import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import agent
import main
import model_catalog
import settings
import toolkit
import tools
from sandbox import RunResult
from store import ChatStore
from test_agent import chunk, scripted, tool_call_chunks


MODEL = b"0 FILE preview.ldr\n1 4 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n"


@pytest.fixture
def store(tmp_path):
    return ChatStore(tmp_path / "chats", tmp_path / "output")


def test_build_mode_default_validation_and_limits():
    entry = {"litellm_params": {"model": "openai/gpt-6-luna"}}
    assert model_catalog.validate_options(entry, {})["build_mode"] == "preview"
    assert model_catalog.validate_options(entry, {})["effort"] == "low"
    assert model_catalog.validate_options(entry, {"build_mode": "verify"})["build_mode"] == "verify"
    with pytest.raises(ValueError, match="build mode"):
        model_catalog.validate_options(entry, {"build_mode": "unchecked"})
    assert agent.step_limit({"build_mode": "preview"}) < agent.step_limit({"build_mode": "verify"}) == agent.MAX_STEPS


def test_preview_prompt_avoids_loading_full_workflow(monkeypatch, store):
    chat = store.create_chat()
    def forbidden():
        pytest.fail("Preview should not load the full validation workflow")
    monkeypatch.setattr(toolkit, "instructions", forbidden)
    monkeypatch.setattr(toolkit, "builder_guides", forbidden)
    prompt = agent.system_prompt(store, chat["id"], {"build_mode": "preview"})
    assert "QUICK PREVIEW" in prompt and "Verify Build" in prompt
    assert "{work_dir}" not in prompt
    schemas = {s["function"]["name"]: s["function"]["description"] for s in agent.available_tools({})}
    assert "unchecked" in schemas["publish_model"]
    assert "runs toolkit geometry validation" in next(s for s in tools.TOOL_SCHEMAS if s["function"]["name"] == "publish_model")["function"]["description"]


def test_preview_preserves_bytes_and_skips_all_commands(monkeypatch, store, tmp_path):
    monkeypatch.setattr(settings, "GENERATED_DIR", tmp_path / "generated")
    async def forbidden(*args, **kwargs):
        pytest.fail("Preview must not run validation or render commands")
    monkeypatch.setattr(tools, "run_command", forbidden)
    chat = store.create_chat()
    source = store.work_dir(chat["id"]) / "preview.mpd"
    source.write_bytes(MODEL)
    ctx = tools.ToolContext(chat["id"], store, lambda *_: None, build_mode="preview")
    result = asyncio.run(tools.t_publish_model(ctx, "output/preview.mpd"))
    [ref] = result.models
    target = store.resolve(chat["id"], ref["model"])
    assert target.read_bytes() == MODEL
    source.write_bytes(b"changed later")
    assert target.read_bytes() == MODEL
    info = json.loads(result.content)
    assert ref["validation_status"] == "preview" and not info["checks_passed"]
    assert "validation" not in info and not target.with_suffix(".png").exists()
    assert info["viewer_url"].startswith("/viewer/")


@pytest.mark.parametrize("exit_code,status", [(0, "passed"), (1, "failed")])
def test_verification_keeps_geometry_gate_and_render(monkeypatch, store, tmp_path, exit_code, status):
    monkeypatch.setattr(settings, "GENERATED_DIR", tmp_path / "generated")
    calls = []
    async def command(ctx, argv, timeout):
        calls.append(argv)
        if argv[1] == "validate":
            Path(argv[-1]).write_text("{}")
        return RunResult(exit_code=exit_code, stdout="", stderr="", timed_out=False, seconds=0)
    monkeypatch.setattr(tools, "run_command", command)
    chat = store.create_chat()
    (store.work_dir(chat["id"]) / "model.mpd").write_bytes(MODEL)
    result = asyncio.run(tools.t_publish_model(tools.ToolContext(chat["id"], store, lambda *_: None), "model.mpd"))
    assert [argv[1] for argv in calls] == ["validate", "render"]
    assert result.models[0]["validation_status"] == status
    assert json.loads(result.content)["checks_passed"] == (exit_code == 0)


def test_each_prompt_returns_to_preview_and_stops_after_publication(monkeypatch, store, tmp_path):
    import llm_config
    monkeypatch.setattr(settings, "GENERATED_DIR", tmp_path / "generated")
    entry = llm_config.create({"litellm_params": {"model": "openai/gpt-6-luna", "api_key": "test"},
                              "capabilities": {"tools": True, "vision": True}})
    fake, calls = scripted([[*tool_call_chunks("publish", "publish_model", {"path": "model.mpd"})]] * 2)
    monkeypatch.setattr(agent.litellm, "acompletion", fake)
    async def forbidden(*args, **kwargs):
        pytest.fail("No commands expected when publishing previews")
    monkeypatch.setattr(tools, "run_command", forbidden)
    chat = store.create_chat()
    (store.work_dir(chat["id"]) / "model.mpd").write_bytes(MODEL)
    store.update_chat(chat["id"], options={"build_mode": "verify"})
    async def run():
        for text in ("make a car", "make it red"):
            await agent.start_turn(store, chat["id"], text, entry["id"], {"permissions": "full"})
            await agent._runs[chat["id"]].task
            assert store.get_chat(chat["id"])["options"]["build_mode"] == "preview"
    asyncio.run(run())
    assert len(calls) == 2 and len(store.models(chat["id"])) == 2
    assert "Preview ready" in store.messages(chat["id"])[-1]["content"]


def test_verify_endpoint_uses_latest_published_revision_and_retains_permissions(monkeypatch, store, tmp_path):
    monkeypatch.setattr(main, "get_store", lambda: store)
    monkeypatch.setattr(settings, "GENERATED_DIR", tmp_path / "generated")
    settings.GENERATED_DIR.mkdir()
    chat = store.create_chat(llm_model_id="original")
    store.update_chat(chat["id"], options={"permissions": "ask", "build_mode": "preview", "effort": "low"})
    for file in ("old.mpd", "latest.mpd"):
        target = settings.GENERATED_DIR / file
        target.write_bytes(MODEL)
        store.add_model(chat["id"], file, target, [], validation_status="preview")
    calls = []
    async def start(*args):
        calls.append(args)
    monkeypatch.setattr(agent, "start_turn", start)
    client = TestClient(main.app)
    response = client.post(f"/api/chats/{chat['id']}/verify", json={"llm_model_id": "chosen"})
    assert response.status_code == 202
    [args] = calls
    assert "latest.mpd" in args[2] and "old.mpd" not in args[2]
    assert args[3] == "chosen" and args[4]["permissions"] == "ask"
    assert args[4]["build_mode"] == "verify" and "effort" not in args[4]
    selected_id = store.models(chat["id"])[0]["id"]
    response = client.post(f"/api/chats/{chat['id']}/verify", json={"model_id": selected_id, "permissions": "full"})
    assert response.status_code == 202
    assert "old.mpd" in calls[-1][2] and "latest.mpd" not in calls[-1][2]
    assert calls[-1][4]["permissions"] == "full"
    assert client.post(f"/api/chats/{chat['id']}/verify", json={"model_id": "another-chat-model"}).status_code == 404
    assert client.post(f"/api/chats/{chat['id']}/verify", json={"permissions": "invalid"}).status_code == 422


def test_verify_endpoint_rejects_missing_busy_deleted_and_foreign_model(monkeypatch, store, tmp_path):
    monkeypatch.setattr(main, "get_store", lambda: store)
    client = TestClient(main.app)
    assert client.post("/api/chats/no-such-chat/verify", json={}).status_code == 404
    chat = store.create_chat()
    url = f"/api/chats/{chat['id']}/verify"
    assert client.post(url, json={}).status_code == 400
    monkeypatch.setattr(agent, "is_running", lambda *_: True)
    assert client.post(url, json={}).status_code == 409
    monkeypatch.setattr(agent, "is_running", lambda *_: False)
    target = tmp_path / "missing.mpd"
    store.add_model(chat["id"], "missing", target, [])
    assert client.post(url, json={}).status_code == 400
    target.write_bytes(MODEL)
    assert client.post(url, json={}).status_code == 400


def test_claude_preview_uses_short_limit_and_denies_post_publication_tools(monkeypatch, store):
    import claude_agent
    from claude_agent_sdk import AssistantMessage, TextBlock
    recorded = {}
    class Client:
        def __init__(self, options): recorded["options"] = options
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def query(self, message): recorded["input"] = [m async for m in message]
        async def interrupt(self): recorded["interrupted"] = True
        async def receive_response(self):
            publish = next(t for t in recorded["tools"] if t.name == "publish_model")
            await publish.handler({"path": "model.mpd"})
            shell = next(t for t in recorded["tools"] if t.name == "run_shell")
            recorded["denied"] = await shell.handler({"command": "./check-model.sh model.mpd"})
            yield AssistantMessage(content=[TextBlock(text="Preview ready")], model="claude-opus-5-5")
    def server(**kwargs):
        recorded["tools"] = kwargs["tools"]
        return {}
    calls = []
    async def execute(run, ctx, call_id, name, args):
        calls.append((name, ctx.build_mode))
        return tools.ToolResult("preview", models=[{"id": "preview"}])
    monkeypatch.setattr(claude_agent, "ClaudeSDKClient", Client)
    monkeypatch.setattr(claude_agent, "create_sdk_mcp_server", server)
    chat = store.create_chat()
    run = agent.Run(chat["id"], options={"build_mode": "preview", "permissions": "full"})
    saved = []
    asyncio.run(claude_agent.run_claude(store, run, {"litellm_params": {"model": "anthropic/claude-opus-5-5"}},
                                       saved.append, execute, "QUICK PREVIEW", True))
    assert recorded["options"].max_turns == agent.PREVIEW_MAX_STEPS
    assert calls == [("publish_model", "preview")]
    assert recorded["interrupted"] and "Preview ready" in saved[-1]["content"]
    assert "already published" in recorded["denied"]["content"][0]["text"]
