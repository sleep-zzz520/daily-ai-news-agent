import asyncio
import json
import smtplib
from fastapi.testclient import TestClient
from app.db import connect, dumps, init_db, now
from app.mail import send_mail
from app.main import app
from app.service import create_run, execute_run
from test_agent import ARTICLE, BRIEF as RAW_BRIEF, PROFILE, isolated_db

BRIEF = {**RAW_BRIEF, 'items': [{**RAW_BRIEF['items'][0], 'source': ARTICLE['source'],
                              'published_at': ARTICLE['published_at']}]}

def completed_run():
    run = create_run('u')
    with connect() as db:
        db.execute("UPDATE runs SET status='completed',brief=? WHERE id=?", (dumps(BRIEF), run))
    return run

def test_api_profile_history_and_isolation():
    with TestClient(app) as c:
        assert c.get('/').status_code == 200
        assert c.get('/api/health').json()['status'] == 'ok'
        assert c.post('/api/users', json={**PROFILE, 'send_time': '25:00'}).status_code == 422
        new = c.post('/api/users', json=PROFILE).json()
        assert c.put('/api/users/'+new['id'], json={**PROFILE, 'topics': ['Agent']}).status_code == 200
        run = completed_run()
        assert c.get(f'/api/users/u/runs/{run}').json()['brief']['title'] == 'AI 简报'
        assert len(c.get('/api/users/u/runs').json()) == 1
        assert c.get(f'/api/users/{new["id"]}/runs/{run}').status_code == 404
        assert c.post('/api/users/u/runs').status_code == 503
        assert c.post(f'/api/users/u/runs/{run}/send').json()['delivery'] == 'not_configured'
        with connect() as db:
            db.execute('UPDATE runs SET brief=? WHERE id=?', (dumps({**BRIEF, 'is_demo': True}), run))
        assert c.post(f'/api/users/u/runs/{run}/send').status_code == 409

def test_recovery():
    run = create_run('u')
    with connect() as db:
        db.execute("UPDATE runs SET delivery='sending' WHERE id=?", (run,))
        db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?)', (run, 'sending', 1, None, now()))
    with TestClient(app) as c:
        result = c.get(f'/api/users/u/runs/{run}').json()
        assert result['status'] == 'failed' and result['delivery'] == 'unknown'

def test_execution_persists_and_automatic_mail(monkeypatch):
    sent = []
    async def fake_generate(*args):
        return BRIEF
    monkeypatch.setattr('app.service.generate', fake_generate)
    monkeypatch.setattr('app.service.send_mail', lambda *args: sent.append(args[0]))
    run = create_run('u')
    asyncio.run(execute_run(run, automatic=True))
    with connect() as db:
        assert db.execute('SELECT status FROM runs WHERE id=?', (run,)).fetchone()[0] == 'completed'
    assert sent == [run]

def configure(monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.com')
    monkeypatch.setenv('SMTP_FROM', 'sender@example.com')
    monkeypatch.setenv('SMTP_SECURITY', 'starttls')

class FakeSMTP:
    sent = []
    def __init__(self, *args, **kwargs): pass
    def starttls(self, **kwargs): pass
    def login(self, *args): pass
    def send_message(self, message): self.sent.append(message)
    def close(self): pass

def test_mail_success_idempotent(monkeypatch):
    configure(monkeypatch)
    FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    run = completed_run()
    assert send_mail(run, PROFILE, BRIEF) == 'sent'
    assert send_mail(run, PROFILE, BRIEF) == 'sent'
    assert len(FakeSMTP.sent) == 1

def test_mail_unknown_no_retry(monkeypatch):
    configure(monkeypatch)
    class Unknown(FakeSMTP):
        count = 0
        def send_message(self, message):
            Unknown.count += 1
            raise OSError('disconnected')
    monkeypatch.setattr(smtplib, 'SMTP', Unknown)
    run = completed_run()
    assert send_mail(run, PROFILE, BRIEF) == 'unknown'
    assert send_mail(run, PROFILE, BRIEF) == 'unknown'
    assert Unknown.count == 1

def test_mail_temporary_retry_and_permanent_failure(monkeypatch):
    configure(monkeypatch)
    class Temporary(FakeSMTP):
        count = 0
        def send_message(self, message):
            Temporary.count += 1
            if Temporary.count < 3:
                raise smtplib.SMTPDataError(451, b'temporary')
    monkeypatch.setattr(smtplib, 'SMTP', Temporary)
    assert send_mail(completed_run(), PROFILE, BRIEF) == 'sent'
    assert Temporary.count == 3
    class Permanent(FakeSMTP):
        def send_message(self, message):
            raise smtplib.SMTPDataError(550, b'rejected')
    monkeypatch.setattr(smtplib, 'SMTP', Permanent)
    assert send_mail(completed_run(), PROFILE, BRIEF) == 'failed'
