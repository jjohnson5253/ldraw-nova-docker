import inference
import claude_agent
import browser_auth
import pytest


def test_sdk_runtime_is_opt_in_for_api_keys_and_keeps_other_providers_and_proxies(monkeypatch):
    api = {'auth_mode': 'api_key', 'litellm_params': {'model': 'anthropic/claude-opus-5-5'}}
    monkeypatch.delenv('LDRAW_NOVA_CLAUDE_API_RUNTIME', raising=False)
    assert not inference.uses_claude_sdk(api)
    assert inference.uses_claude_sdk({**api, 'auth_mode': 'browser'})
    monkeypatch.setenv('LDRAW_NOVA_CLAUDE_API_RUNTIME', 'sdk')
    assert inference.uses_claude_sdk(api)
    assert not inference.uses_claude_sdk({**api, 'litellm_params': {'model': 'openai/gpt-5.5'}})
    assert not inference.uses_claude_sdk({**api, 'litellm_params': {**api['litellm_params'], 'api_base': 'https://proxy.example'}})


def test_sdk_api_key_stays_in_protected_api_environment_and_browser_login_is_unchanged(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'inherited-key')
    browser = claude_agent.sdk_environment({'auth_mode': 'browser'})
    api = claude_agent.sdk_environment({'auth_mode': 'api_key', 'litellm_params': {
        'model': 'anthropic/claude-opus-5-5', 'api_key': 'configured-key'}})
    assert browser['ANTHROPIC_API_KEY'] == ''
    assert api['ANTHROPIC_API_KEY'] == 'configured-key'
    assert api['CLAUDE_CODE_OAUTH_TOKEN'] == api['ANTHROPIC_AUTH_TOKEN'] == ''
    assert api['HOME'] == api['CLAUDE_CONFIG_DIR']
    assert api['HOME'] != browser['HOME']
    assert browser_auth.claude_env()['ANTHROPIC_API_KEY'] == ''


def test_missing_api_key_fails_instead_of_falling_back_to_browser_login():
    with pytest.raises(ValueError, match='configured Anthropic API key'):
        claude_agent.sdk_environment({'auth_mode': 'api_key', 'litellm_params': {
            'model': 'anthropic/claude-opus-5-5'}})
