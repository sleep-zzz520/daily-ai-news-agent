import asyncio
import json
import httpx
import pytest
from app.agent import llm_turn
from app.llm_config import api_key, endpoint
from test_agent import isolated_db

@pytest.mark.parametrize('glm', [True, False])
def test_provider_payload(monkeypatch, glm):
    monkeypatch.setenv('LLM_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'unrelated-inherited-key')
    monkeypatch.setenv('LLM_MODEL', 'glm-4.7' if glm else 'gpt-4.1-mini')
    monkeypatch.setenv('LLM_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4/' if glm else 'https://api.openai.com/v1')
    def handler(request):
        data = json.loads(request.content)
        assert request.headers['Authorization'] == 'Bearer test-key'
        assert str(request.url) == endpoint()
        assert data['tool_choice'] == 'auto' and len(data['tools']) == 6
        assert ('max_tokens' in data) == glm
        assert ('store' in data) != glm
        if glm:
            assert data['thinking'] == {'type': 'disabled'}
        return httpx.Response(200, json={'choices': [{'message': {'content': '{}'}}]})
    cls = httpx.AsyncClient
    monkeypatch.setattr('app.agent.httpx.AsyncClient', lambda **kwargs: cls(transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(llm_turn([{'role': 'user', 'content': 'JSON'}]))['content'] == '{}'

def test_error_does_not_leak_body(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'test-key')
    cls = httpx.AsyncClient
    def handler(request):
        return httpx.Response(401, json={'error': {'code': '1000', 'message': 'secret-test-key'}})
    monkeypatch.setattr('app.agent.httpx.AsyncClient', lambda **kwargs: cls(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(ValueError) as e:
        asyncio.run(llm_turn([]))
    assert '1000' in str(e.value) and 'secret' not in str(e.value)

def test_legacy_fallback_and_https_validation(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'legacy-test-key')
    assert api_key() == 'legacy-test-key'
    monkeypatch.setenv('LLM_BASE_URL', 'http://example.com/v1')
    with pytest.raises(ValueError, match='HTTPS'):
        endpoint()
