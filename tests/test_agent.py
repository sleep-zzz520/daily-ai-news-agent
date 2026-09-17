import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.agent import generate, validate_brief
from app.db import connect, dumps, init_db, now
from app.service import create_run, due_profiles
from app.tools import Tools

PROFILE = {'nickname': '测试', 'email': 'test@example.com', 'topics': ['开源'],
           'keywords': [], 'excluded_keywords': [], 'send_time': '09:00', 'enabled': True}
ARTICLE = {'url': 'https://example.com/news', 'title': 'Open model', 'summary': '开源模型更新',
           'source': 'Test RSS', 'published_at': datetime.now(timezone.utc).isoformat()}
BRIEF = {'title': 'AI 简报', 'note': '根据摘要整理', 'items': [
    {'url': ARTICLE['url'], 'title': '开源模型更新', 'summary': '模型发布了新版本。', 'reason': '关注开源模型'}]}

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    monkeypatch.delenv('SMTP_HOST', raising=False)
    init_db()
    with connect() as db:
        db.execute('INSERT INTO users VALUES(?,?)', ('u', dumps(PROFILE)))

def tools(tmp_path):
    t = Tools(tmp_path / 'workspace', datetime.now(timezone.utc) - timedelta(hours=24))
    t.news[ARTICLE['url']] = ARTICLE
    t.successful_sources.add('test')
    return t

def call(name, args):
    return {'id': name, 'type': 'function', 'function': {'name': name, 'arguments': dumps(args)}}

@pytest.mark.parametrize('sequence', [
    [('list_dir', {'path': '.'}), ('read_file', {'path': 'preferences.json'})],
    [('write_file', {'path': 'draft.txt', 'content': '开源'}), ('search_content', {'keyword': '开源', 'dir': '.'}),
     ('read_file', {'path': 'draft.txt'}), ('read_file', {'path': 'draft.txt'})],
    [],
])
def test_model_controls_sequence(tmp_path, sequence):
    run = create_run('u')
    responses = [{'role': 'assistant', 'tool_calls': [call(name, args)]} for name, args in sequence]
    responses.append({'role': 'assistant', 'content': dumps(BRIEF)})
    async def turn(messages):
        return responses.pop(0)
    result = asyncio.run(generate(run, PROFILE, turn=turn, tools=tools(tmp_path)))
    assert result['items'][0]['source'] == 'Test RSS'
    with connect() as db:
        names = [r[0] for r in db.execute('SELECT name FROM tool_calls WHERE run_id=? ORDER BY id', (run,))]
    assert names == [s[0] for s in sequence]

def test_no_sources_and_fabricated_citation(tmp_path):
    t = tools(tmp_path)
    t.successful_sources.clear()
    with pytest.raises(ValueError, match='来源'):
        validate_brief(dumps(BRIEF), t, PROFILE)
    t.successful_sources.add('test')
    bad = {**BRIEF, 'items': [{**BRIEF['items'][0], 'url': 'https://example.com/fake'}]}
    with pytest.raises(ValueError, match='引用'):
        validate_brief(dumps(bad), t, PROFILE)

def test_exclusion_duplicate_and_empty(tmp_path):
    t = tools(tmp_path)
    with pytest.raises(ValueError, match='排除'):
        validate_brief(dumps(BRIEF), t, {**PROFILE, 'excluded_keywords': ['开源']})
    with pytest.raises(ValueError, match='重复'):
        validate_brief(dumps({**BRIEF, 'items': BRIEF['items'] * 2}), t, PROFILE)
    assert validate_brief(dumps({**BRIEF, 'items': []}), t, PROFILE)['items'] == []

def test_empty_result_explains_candidates_and_deduplication(tmp_path):
    t = tools(tmp_path)
    empty = dumps({**BRIEF, 'items': []})
    assert '1 条候选' in validate_brief(empty, t, PROFILE)['note']
    t.news.clear()
    assert '没有返回候选' in validate_brief(empty, t, PROFILE)['note']
    t.deduplicated_urls.add(ARTICLE['url'])
    assert '自动推送已去重' in validate_brief(empty, t, PROFILE)['note']

@pytest.mark.parametrize('path', ['../.env', '/etc/passwd', '../../x'])
def test_path_escape(tmp_path, path):
    with pytest.raises(ValueError):
        tools(tmp_path).path(path)

def test_symlink(tmp_path):
    t = tools(tmp_path)
    (t.root / 'link').symlink_to(tmp_path)
    with pytest.raises(ValueError):
        t.path('link/anything')

@pytest.mark.parametrize('command', ['env', 'cat ../.env', 'cat /etc/passwd', 'cat a;env', 'head -c 20 a',
                                      'python -c pass', 'cat $(env)', 'cat a > b', 'cat'])
def test_unsafe_bash(tmp_path, command):
    with pytest.raises(ValueError):
        asyncio.run(tools(tmp_path).bash(command))

def test_allowed_bash(tmp_path):
    t = tools(tmp_path)
    t.path('text.txt').write_text('hello\nworld\n')
    assert asyncio.run(t.bash('wc -l text.txt'))['stdout'].strip().startswith('2')

def test_loop_limit_and_errors(tmp_path):
    run = create_run('u')
    async def turn(messages):
        return {'role': 'assistant', 'tool_calls': [call('read_file', {'path': 'missing'})]}
    with pytest.raises(ValueError, match='15轮'):
        asyncio.run(generate(run, PROFILE, turn=turn, tools=tools(tmp_path)))
    with connect() as db:
        rows = db.execute('SELECT result FROM tool_calls WHERE run_id=?', (run,)).fetchall()
    assert len(rows) == 15 and 'error' in rows[0][0]

def test_call_count_limit(tmp_path):
    run = create_run('u')
    async def turn(messages):
        return {'role': 'assistant', 'tool_calls': [call('list_dir', {'path': '.'}) for _ in range(31)]}
    with pytest.raises(ValueError, match='30次'):
        asyncio.run(generate(run, PROFILE, turn=turn, tools=tools(tmp_path)))

def test_unique_daily_and_active():
    assert create_run('u', 'u:day')
    assert create_run('u') is None
    with connect() as db:
        db.execute("UPDATE runs SET status='completed'")
    assert create_run('u', 'u:day') is None
    assert create_run('u', 'u:other')

def test_due_timezone_pause():
    assert not due_profiles(datetime(2026, 9, 17, 0, 59, tzinfo=timezone.utc))
    assert due_profiles(datetime(2026, 9, 17, 1, 0, tzinfo=timezone.utc)) == [('u', 'u:2026-09-17')]
    with connect() as db:
        db.execute('UPDATE users SET profile=?', (dumps({**PROFILE, 'enabled': False}),))
    assert not due_profiles()
