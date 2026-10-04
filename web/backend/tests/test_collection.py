import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import agent
import collection
import llm_config
import settings
import tools
from main import app
from store import ChatStore


@pytest.fixture
def owned(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    return {"name": "Loose bricks", "parts": [{"part": "3001.dat", "colour": 4, "quantity": 3}], "copies": 2, "available": True}


def test_source_copies_exclusions_edits_removal_and_offline_csv(owned):
    source = collection.preview({"name": "Bricks.csv", "csv": "\ufeffpart,colour,quantity\n3001.dat,4,3\n"})
    assert source["parts"][0]["part"] == "3001"
    [saved] = collection.save({**source, "copies": 2})
    collection.save(source)
    frozen = collection.snapshot()
    assert frozen["parts"] == [{"part": "3001", "colour": 4, "quantity": 9}]
    collection.save({**saved, "available": False}, saved["id"])
    assert collection.snapshot()["parts"][0]["quantity"] == 3
    collection.save(None, saved["id"])
    assert len(collection.sources()) == 1
    assert frozen["parts"][0]["quantity"] == 9  # later edits cannot change a captured turn
    with pytest.raises(ValueError):
        collection.save(saved, saved["id"])


@pytest.mark.parametrize("url", ["21354", "21354-1", "https://www.lego.com/en-us/product/twilight-the-cullen-house-21354",
    "https://rebrickable.com/sets/21354-1/twilight/", "https://www.bricklink.com/v2/catalog/catalogitem.page?S=21354-1"])
def test_set_urls_extract_numbers_without_fetching_untrusted_urls(url):
    assert collection.set_number(url) == "21354-1"
    with pytest.raises(ValueError):
        collection.set_number("https://evil.example/sets/21354-1/")
    with pytest.raises(ValueError):
        collection.set_number("http://rebrickable.com/sets/21354-1/")


def test_provider_mapping_ambiguity_and_spares_are_explicit(owned, monkeypatch):
    color = {"id": 5, "external_ids": {"LDraw": {"ext_ids": [4]}}}
    part = {"part_num": "3001", "name": "Brick", "external_ids": {"LDraw": ["3001"]}}
    def catalog(path, **params):
        if path == "sets/21354-1/":
            return {"name": "Test set", "set_num": "21354-1"}
        if path == "colors/":
            return {"results": [color]}
        if path == "sets/21354-1/parts/":
            assert params["inc_minifig_parts"] == 1 and params["inc_part_details"] == 1
            return {"results": [{"part": part, "color": color, "quantity": 2, "is_spare": False},
                                {"part": part, "color": color, "quantity": 1, "is_spare": True}]}
        if path == "parts/":
            return {"results": [part]}
        raise AssertionError(path)
    monkeypatch.setattr(collection, "catalog", catalog)
    normal = collection.preview({"set": "21354"})
    assert len(normal["parts"]) == 1 and normal["parts"][0]["colour"] == 4
    assert len(collection.preview({"set": "21354", "include_spares": True})["parts"]) == 2
    mapped = collection.preview({"csv": "part_num,color_id,quantity\n3001,5,2\n"})
    assert mapped["parts"][0]["part"] == "3001"
    ambiguous = collection._mapped({**part, "external_ids": {"LDraw": ["3001", "3003"]}}, color, 2)
    assert ambiguous["part"] is None
    assert collection._mapped(part, {"id": 5}, 2)["colour"] is None
    collection.save({"name": "Unmapped", "parts": [ambiguous]})
    assert collection.snapshot()["parts"] == [{"part": None, "colour": None, "quantity": 2}]


def test_reject_partial_pagination_and_bad_csv(owned, monkeypatch):
    monkeypatch.setattr(collection, "catalog", lambda *a, **kw: {"results": [], "next": "more"})
    with pytest.raises(ValueError, match="nothing was imported"):
        collection.catalog_rows("sets/21354-1/parts/")
    for csv in ("part,colour,quantity\n3001,4,-1", "part,colour,quantity\n3001,16,1", "part,colour,quantity\n3001,99999,1", "part,colour,quantity\n3001,4,1.5", "bad,headers\nx,y"):
        with pytest.raises(ValueError):
            collection.preview({"csv": csv})
    assert collection.sources() == []


def test_api_import_is_reviewed_before_persisting_and_reports_real_bom(owned):
    client = TestClient(app)
    result = client.post("/api/collection/preview", json={"name": "My bricks.csv", "csv": "part,colour,quantity\n3001,4,1\n"})
    assert result.status_code == 200 and client.get("/api/collection").json()["sources"] == []
    saved = client.post("/api/collection/sources", json=result.json())
    assert saved.status_code == 200
    path = settings.GENERATED_DIR / "collection-test.mpd"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("0 FILE bricks.ldr\n0 Bricks\n0 Name: bricks.ldr\n0 Author: Test\n0 !LDRAW_ORG Model\n"
                    "1 4 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n1 4 100 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n0 NOFILE\n")
    try:
        response = client.get("/api/collection/compare", params={"url": "/files/generated/collection-test.mpd"})
        assert response.status_code == 200, response.text
        report = response.json()
        assert (report["required"], report["owned"], report["missing"]) == (2, 1, 1)
        assert client.get("/api/collection/compare", params={"url": "/files/generated/../../config/models.json"}).status_code == 404
    finally:
        path.unlink()
    assert client.delete("/api/collection/sources/" + saved.json()["sources"][0]["id"]).status_code == 200


@pytest.mark.parametrize("prefer", [False, True])
def test_turn_attaches_a_frozen_inventory_and_empty_collection_does_not_start(owned, monkeypatch, prefer):
    store = ChatStore(settings.CHATS_DIR, settings.OUTPUT_DIR)
    entry = llm_config.create({"model_name": "Collection test", "litellm_params": {"model": "openai/gpt-6-luna", "api_key": "test"}, "capabilities": {"tools": True, "vision": True}})
    chat = store.create_chat()
    captures = []
    async def fake_turn(store, run, entry):
        captures.append(run.options)
    monkeypatch.setattr(agent, "_run_turn", fake_turn)
    async def run():
        with pytest.raises(ValueError, match="Add available"):
            await agent.start_turn(store, chat["id"], "Build a bridge", entry["id"], {"use_only_my_parts": not prefer, "prefer_my_parts": prefer})
        assert store.messages(chat["id"]) == []
        collection.save(owned)
        await agent.start_turn(store, chat["id"], "Build a bridge", entry["id"], {"use_only_my_parts": not prefer, "prefer_my_parts": prefer})
        await agent._runs[chat["id"]].task
    asyncio.run(run())
    [document] = store.messages(chat["id"])[0]["_documents"]
    payload = json.loads(store.resolve(chat["id"], document["path"]).read_text())
    assert payload == {"parts": [{"part": "3001", "colour": 4, "quantity": 6}]}
    assert captures[0]["_inventory"] == payload
    assert not any(k.startswith("_") for k in store.get_chat(chat["id"])["options"])
    prompt = agent.system_prompt(store, chat["id"], captures[0]["_inventory_path"], prefer)
    assert ("Use as many of my parts as possible is selected" if prefer else "Use only my parts is selected") in prompt
    assert "--inventory" in prompt
    if prefer:
        assert "same part" in prompt and "Unowned parts are allowed" in prompt
    # Agent edits to its attachment cannot alter the publication gate.
    store.resolve(chat["id"], document["path"]).write_text('{"parts":[]}')
    assert captures[0]["_inventory"]["parts"][0]["quantity"] == 6


@pytest.mark.parametrize("valid", [True, False])
def test_publish_gate_rejects_shortages_or_invalid_geometry_without_copying_a_new_model(owned, monkeypatch, valid):
    store = ChatStore(settings.CHATS_DIR, settings.OUTPUT_DIR)
    chat = store.create_chat()
    ctx = tools.ToolContext(chat["id"], store, lambda *args: None, inventory={"parts": []})
    (ctx.work_dir / "model.mpd").write_text("0 FILE test.ldr\n0 Test\n0 NOFILE\n")
    async def validation(ctx, command, timeout):
        assert command[1] == "validate"
        from sandbox import RunResult
        Path(command[-1]).write_text('{"checks_passed":true}')
        return RunResult(0 if valid else 1, "", "", False, 0)
    async def shortage(*args):
        return {"matches": False, "required": 4, "owned": 1, "missing": 3}
    monkeypatch.setattr(tools, "run_command", validation)
    monkeypatch.setattr(collection, "compare", shortage)
    before = set(settings.GENERATED_DIR.glob("*.mpd"))
    result = asyncio.run(tools.t_publish_model(ctx, "model.mpd", "Shortage test"))
    assert ("exceeds the owned inventory" if valid else "requires a valid model") in result.content
    assert result.models == [] and store.models(chat["id"]) == []
    assert set(settings.GENERATED_DIR.glob("*.mpd")) == before


@pytest.mark.parametrize("prefer", [False, True])
def test_real_inventory_publication_matches_the_expanded_bom(owned, prefer):
    import os
    os.chmod(settings.CHATS_DIR.parent.parent, 0o755)
    store = ChatStore(settings.CHATS_DIR, settings.OUTPUT_DIR)
    chat = store.create_chat()
    ctx = tools.ToolContext(chat["id"], store, lambda *args: None)
    async def run():
        built = await tools.t_run_toolkit(ctx, ["build", "examples/bridge.plan.json", "--output", "output/bridge.mpd"])
        assert "exit code 0" in built.content, built.content
        report = ctx.work_dir / "bom.json"
        counted = await tools.run_command(ctx, ["./ldraw-agent", "bom", "output/bridge.mpd", "--report", str(report)], 60)
        assert counted.exit_code == 0, counted.as_text()
        ctx.inventory = {"parts": [{"part": r["part"], "colour": r["colour_code"], "quantity": r["quantity"]} for r in json.loads(report.read_text())["bom"]]}
        ctx.prefer_my_parts = prefer
        if prefer:
            # Best effort may publish a valid model with shortages; exact counts
            # must remain truthful and its model must not be marked strict.
            ctx.inventory["parts"] = [{**ctx.inventory["parts"][0], "quantity": 1}]
        published = await tools.t_publish_model(ctx, "output/bridge.mpd", "Owned bridge")
        assert len(published.models) == 1, published.content
        assert published.models[0]["use_only_my_parts"] is (not prefer)
        checked = json.loads(published.content)["inventory"]
        assert checked["required"] == 5 and checked["unresolved"] == 0
        assert checked["matches"] is (not prefer)
        assert (checked["owned"], checked["missing"]) == ((1, 4) if prefer else (5, 0))
    asyncio.run(run())


@pytest.mark.parametrize("prefer", [False, True])
def test_rebuild_keeps_full_permission_and_selects_requested_inventory_mode(owned, monkeypatch, prefer):
    import main
    collection.save(owned)
    store = ChatStore(settings.CHATS_DIR, settings.OUTPUT_DIR)
    monkeypatch.setattr(main, "get_store", lambda: store)
    chat = store.create_chat()
    store.update_chat(chat["id"], options={"permissions": "full", "use_only_my_parts": True})
    path = settings.GENERATED_DIR / "adapt-mode-test.mpd"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("0 Cottage")
    captured = {}
    async def start(store, chat_id, text, llm_id, options):
        captured.update(options=options, text=text)
    monkeypatch.setattr(agent, "start_turn", start)
    try:
        response = TestClient(app).post("/api/collection/adapt", json={
            "url": "/files/generated/adapt-mode-test.mpd", "chat_id": chat["id"], "prefer_my_parts": prefer})
        assert response.status_code == 202, response.text
        assert captured["options"]["permissions"] == "full"
        assert captured["options"]["use_only_my_parts"] is (not prefer)
        assert captured["options"]["prefer_my_parts"] is prefer
        assert ("same part in an owned color" if prefer else "using only my owned parts") in captured["text"]
        assert path.read_text() == "0 Cottage"
    finally:
        path.unlink()
