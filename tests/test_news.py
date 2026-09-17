import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest
from app.tools import Tools
from test_agent import isolated_db
CLIENT = httpx.AsyncClient

def client_mock(monkeypatch, handler):
    cls = CLIENT
    monkeypatch.setattr('app.tools.httpx.AsyncClient', lambda **kwargs: cls(transport=httpx.MockTransport(handler), **kwargs))

def rss():
    date = format_datetime(datetime.now(timezone.utc) - timedelta(hours=1))
    return f'''<rss version="2.0"><channel><title>Test</title><link>https://example.com</link><description>AI</description>
    <item><title>AI Agent开源</title><link>https://example.com/news#top</link><description>更新摘要</description><pubDate>{date}</pubDate></item>
    <item><title>重复</title><link>https://example.com/news</link><pubDate>{date}</pubDate></item>
    <item><title>无时间</title><link>https://example.com/undated</link></item>
    </channel></rss>'''

def test_fetch_partial_failure_cache_and_dedup(tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(503) if 'google' in str(request.url) else httpx.Response(200, text=rss())
    client_mock(monkeypatch, handler)
    t = Tools(tmp_path / 'run', datetime.now(timezone.utc) - timedelta(hours=24))
    result = asyncio.run(t.fetch_news(['huggingface', 'google'], t.since.isoformat()))
    assert len(result['news']) == 1
    assert result['news'][0]['url'] == 'https://example.com/news'
    assert len(result['errors']) == 1 and t.path('news.json').exists()
    assert not asyncio.run(t.fetch_news(['huggingface'], t.since.isoformat()))['news']

def test_recent_and_all_sources_failure(tmp_path, monkeypatch):
    client_mock(monkeypatch, lambda request: httpx.Response(200, text=rss()))
    t = Tools(tmp_path / 'run', datetime.now(timezone.utc) - timedelta(hours=24), ['https://example.com/news'])
    assert not asyncio.run(t.fetch_news(['huggingface'], t.since.isoformat()))['news']
    assert t.successful_sources
    client_mock(monkeypatch, lambda request: httpx.Response(200, text='<html>not a feed</html>'))
    failed = Tools(tmp_path / 'failed', t.since)
    assert asyncio.run(failed.fetch_news(['google'], failed.since.isoformat()))['errors']
    assert not failed.successful_sources

def test_since_validation(tmp_path):
    t = Tools(tmp_path / 'run', datetime.now(timezone.utc) - timedelta(hours=24))
    with pytest.raises(ValueError):
        asyncio.run(t.fetch_news(['huggingface'], '2020-01-01'))
