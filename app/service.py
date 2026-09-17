import asyncio
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app.agent import generate
from app.db import connect, dumps, now
from app.mail import send_mail
from app.llm_config import api_key

TASKS = set()

def spawn(coro):
    task = asyncio.create_task(coro)
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    return task

def create_run(user_id, daily_key=None):
    run_id = uuid.uuid4().hex
    with connect() as db:
        if not db.execute('SELECT id FROM users WHERE id=?', (user_id,)).fetchone():
            raise LookupError('用户不存在')
        try:
            db.execute('INSERT INTO runs(id,user_id,daily_key,status,created_at) VALUES(?,?,?,?,?)',
                       (run_id, user_id, daily_key, 'running', now()))
        except sqlite3.IntegrityError:
            return None
    return run_id

async def execute_run(run_id, automatic=False):
    try:
        with connect() as db:
            run = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            profile = json.loads(db.execute('SELECT profile FROM users WHERE id=?', (run['user_id'],)).fetchone()[0])
            previous = db.execute("SELECT brief FROM runs WHERE user_id=? AND status='completed' AND created_at>=?",
                (run['user_id'], (datetime.now(timezone.utc) - timedelta(days=7)).isoformat())).fetchall()
        recent = [item['url'] for row in previous for item in json.loads(row['brief'])['items']]
        brief = await generate(run_id, profile, recent)
        with connect() as db:
            db.execute("UPDATE runs SET status='completed',brief=? WHERE id=?", (dumps(brief), run_id))
        if automatic:
            await asyncio.to_thread(send_mail, run_id, profile, brief)
    except asyncio.CancelledError:
        with connect() as db:
            db.execute("UPDATE runs SET status='failed',error='服务关闭，运行中断' WHERE id=? AND status='running'", (run_id,))
        raise
    except Exception as e:
        # Store actionable errors without credentials, URLs with keys, or request bodies.
        safe = str(e) if isinstance(e, ValueError) else type(e).__name__
        with connect() as db:
            db.execute("UPDATE runs SET status=CASE WHEN status='running' THEN 'failed' ELSE status END,error=? WHERE id=?",
                       (safe[:500], run_id))

def due_profiles(current=None):
    current = current or datetime.now(ZoneInfo('Asia/Shanghai'))
    current = current.astimezone(ZoneInfo('Asia/Shanghai'))
    with connect() as db:
        users = db.execute('SELECT * FROM users').fetchall()
    return [(row['id'], row['id'] + ':' + current.date().isoformat()) for row in users
            if (profile := json.loads(row['profile']))['enabled'] and current.strftime('%H:%M') >= profile['send_time']]

async def scheduler():
    # ponytail: one process owns scheduling; use a durable queue for multi-worker deployment.
    while True:
        for user_id, key in (due_profiles() if api_key() else []):
            run_id = create_run(user_id, key)
            if run_id:
                spawn(execute_run(run_id, automatic=True))
        await asyncio.sleep(60)
