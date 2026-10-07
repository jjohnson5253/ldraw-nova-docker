import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import agent
import main
import parts_policy
import settings
import tools
from parts_catalog import PartsUnavailable
from store import ChatStore

CATALOG = 'part_id,color_id,name,sku,unit_price,weight_kg,max_quantity\n3001,4,Brick 2 x 4,A,0.15,0.00219,4\n'
MODEL = b'1 4 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n'


@pytest.fixture
def configured(tmp_path, monkeypatch):
    policy = parts_policy.ChatPartsPolicy(tmp_path / 'protected')
    store = ChatStore(tmp_path / 'chats', tmp_path / 'output')
    chat_id = store.create_chat()['id']
    policy.configure(store, chat_id, CATALOG)
    monkeypatch.setattr(parts_policy, 'policy', policy)
    monkeypatch.setattr(parts_policy.sandbox, 'give_to_agent', lambda path: None)
    return policy, store, chat_id


def test_reference_cannot_change_authority_and_symlinks_are_replaced(configured, tmp_path):
    policy, store, chat_id = configured
    reference = store.work_dir(chat_id) / 'allowed-parts.csv'
    reference.write_text(CATALOG.replace('3001,4', '3001,0'))
    assert policy.load(chat_id).search('3001', 4)['total'] == 1
    assert policy.path(chat_id).stat().st_mode & 0o777 == 0o600
    reference.unlink()
    victim = tmp_path / 'keep'; victim.write_text('keep')
    reference.symlink_to(victim)
    policy.prepare(store, chat_id)
    assert victim.read_text() == 'keep'
    assert not reference.is_symlink()
    with pytest.raises(ValueError):
        policy.path('../escape')


def test_defaults_freeze_per_chat_and_invalid_catalog_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(parts_policy.sandbox, 'give_to_agent', lambda path: None)
    default = tmp_path / 'default.csv'; default.write_text(CATALOG)
    policy = parts_policy.ChatPartsPolicy(tmp_path / 'protected', default)
    store = SimpleNamespace(work_dir=lambda chat: tmp_path / chat)
    assert policy.prepare(store, 'chat')
    default.write_text(CATALOG.replace('3001,4', '3001,0'))
    assert policy.load('chat').search(color_id=4)['total'] == 1
    assert policy.load('other').search(color_id=0)['total'] == 1
    with pytest.raises(ValueError):
        policy.configure(store, 'chat', 'invalid')
    assert policy.load('chat').search(color_id=4)['total'] == 1


def test_server_configuration_selects_any_inventory(monkeypatch):
    monkeypatch.delenv('NOVA_PARTS_CATALOG')
    assert parts_policy.default_catalog_path() == settings.TOOLKIT_DIR / 'ldraw_tools/data/brickwith_parts.csv'
    monkeypatch.setenv('NOVA_PARTS_CATALOG', '/config/my-parts.csv')
    assert parts_policy.default_catalog_path() == Path('/config/my-parts.csv')
    monkeypatch.setenv('NOVA_PARTS_CATALOG', 'relative.csv')
    with pytest.raises(ValueError):
        parts_policy.default_catalog_path()


def test_shared_agent_prompt_and_tools_include_policy(configured, monkeypatch):
    _, store, chat_id = configured
    monkeypatch.setattr(agent.toolkit, 'instructions', lambda: 'instructions')
    monkeypatch.setattr(agent.toolkit, 'builder_guides', lambda: 'guides')
    assert 'MANDATORY PARTS POLICY' in agent.system_prompt(store, chat_id)
    assert {'list_allowed_parts', 'check_model_parts'} <= set(tools.TOOLS)
    names = {schema["function"]["name"] for schema in agent.available_tools({"permissions": "read_only"})}
    assert {"list_allowed_parts", "check_model_parts"} <= names


def test_publication_gate_runs_before_toolkit_or_model_storage(configured, monkeypatch):
    _, store, chat_id = configured
    ctx = tools.ToolContext(chat_id=chat_id, store=store, emit=lambda *args: None)
    model = store.work_dir(chat_id) / 'model.mpd'; model.write_bytes(MODEL)
    monkeypatch.setattr(parts_policy, 'expanded_inventory', lambda *args: {('3001', 0): 1})
    async def must_not_run(*args, **kwargs):
        raise AssertionError('Toolkit called before inventory validation')
    monkeypatch.setattr(tools, 'run_command', must_not_run)
    result = asyncio.run(tools.dispatch(ctx, 'publish_model', {'path': str(model)}))
    assert 'blocked publication' in result.content and not result.models
    assert not store.models(chat_id)
    check = asyncio.run(tools.dispatch(ctx, 'check_model_parts', {'path': str(model)}))
    assert json.loads(check.content)['valid'] is False
    monkeypatch.setattr(parts_policy, 'expanded_inventory', lambda *args: {('3001', 4): 1})
    check = asyncio.run(tools.dispatch(ctx, 'check_model_parts', {'path': str(model)}))
    assert json.loads(check.content)['parts_subtotal'] == '0.15'
    search = asyncio.run(tools.dispatch(ctx, 'list_allowed_parts', {'query': '3001', 'limit': 1}))
    assert json.loads(search.content)['total'] == 1
    bad = asyncio.run(tools.dispatch(ctx, 'list_allowed_parts', {'limit': 1000}))
    assert 'limit between' in bad.content


def test_native_catalog_endpoint_preserves_chat_and_running_boundaries(configured, monkeypatch):
    _, store, chat_id = configured
    monkeypatch.setattr(main, 'get_store', lambda: store)
    client = TestClient(main.app)
    endpoint = '/api/chats/' + chat_id + '/parts-catalog'
    assert client.put(endpoint, json={'csv': CATALOG}).json()['allowed_combinations'] == 1
    assert client.put('/api/chats/missing/parts-catalog', json={'csv': CATALOG}).status_code == 404
    assert client.put(endpoint, json={'csv': 'invalid'}).status_code == 400
    monkeypatch.setattr(agent, 'is_running', lambda chat: True)
    assert client.put(endpoint, json={'csv': CATALOG}).status_code == 409
    assert client.put(endpoint, headers={'Origin': 'https://other.example'}, json={'csv': CATALOG}).status_code == 403
