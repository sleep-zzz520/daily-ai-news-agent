import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

load_dotenv()

from app.db import ROOT, connect, dumps, init_db, now
from app.mail import send_mail
from app.service import TASKS, create_run, execute_run, scheduler, spawn
from app.tools import SOURCES

Keyword = Annotated[str, Field(min_length=1, max_length=100, strip_whitespace=True)]

class Profile(BaseModel):
    nickname: str = Field(min_length=1, max_length=80)
    email: EmailStr
    topics: list[Keyword] = Field(default_factory=list, max_length=30)
    keywords: list[Keyword] = Field(default_factory=list, max_length=30)
    excluded_keywords: list[Keyword] = Field(default_factory=list, max_length=30)
    send_time: str = Field(default='09:00', pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    enabled: bool = True

@asynccontextmanager
async def lifespan(app):
    init_db()
    with connect() as db:
        db.execute("UPDATE runs SET status='failed',error='上次服务中断' WHERE status='running'")
        db.execute("UPDATE runs SET delivery='unknown' WHERE delivery='sending'")
        db.execute("UPDATE deliveries SET status='unknown',updated_at=? WHERE status='sending'", (now(),))
    timer = asyncio.create_task(scheduler())
    yield
    timer.cancel()
    await asyncio.gather(timer, return_exceptions=True)
    pending = list(TASKS)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

app = FastAPI(title='每日 AI 新闻助手', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

def user(user_id):
    with connect() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, '用户不存在')
    return json.loads(row['profile'])

def owned_run(user_id, run_id):
    with connect() as db:
        row = db.execute('SELECT * FROM runs WHERE id=? AND user_id=?', (run_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, '运行不存在')
    result = dict(row)
    result['brief'] = json.loads(result['brief']) if result['brief'] else None
    return result

@app.get('/')
def index():
    return FileResponse(ROOT / 'static/index.html')

@app.get('/api/health')
def health():
    return {'status': 'ok', 'model_configured': bool(os.getenv('OPENAI_API_KEY')),
            'mail_configured': bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM')), 'sources': SOURCES}

@app.get('/api/users')
def users():
    with connect() as db:
        return [{'id': row['id'], **json.loads(row['profile'])} for row in db.execute('SELECT * FROM users')]

@app.post('/api/users', status_code=201)
def add_user(profile: Profile):
    user_id = uuid.uuid4().hex
    with connect() as db:
        db.execute('INSERT INTO users VALUES(?,?)', (user_id, dumps(profile.model_dump(mode='json'))))
    return {'id': user_id, **profile.model_dump(mode='json')}

@app.put('/api/users/{user_id}')
def update_user(user_id: str, profile: Profile):
    user(user_id)
    with connect() as db:
        db.execute('UPDATE users SET profile=? WHERE id=?', (dumps(profile.model_dump(mode='json')), user_id))
    return {'id': user_id, **profile.model_dump(mode='json')}

@app.post('/api/users/{user_id}/runs', status_code=202)
async def start_run(user_id: str):
    user(user_id)
    if not os.getenv('OPENAI_API_KEY'):
        raise HTTPException(503, '请先在 .env 配置 OPENAI_API_KEY')
    run_id = create_run(user_id)
    if not run_id:
        raise HTTPException(409, '该用户已有任务运行中')
    spawn(execute_run(run_id))
    return {'id': run_id}

@app.get('/api/users/{user_id}/runs')
def history(user_id: str):
    user(user_id)
    with connect() as db:
        return [dict(row) for row in db.execute(
            'SELECT id,status,created_at,error,delivery FROM runs WHERE user_id=? ORDER BY created_at DESC LIMIT 100', (user_id,))]

@app.get('/api/users/{user_id}/runs/{run_id}')
def detail(user_id: str, run_id: str):
    result = owned_run(user_id, run_id)
    with connect() as db:
        result['tools'] = [dict(row) for row in db.execute('SELECT * FROM tool_calls WHERE run_id=? ORDER BY id', (run_id,))]
        delivery = db.execute('SELECT * FROM deliveries WHERE run_id=?', (run_id,)).fetchone()
        result['delivery_detail'] = dict(delivery) if delivery else None
    return result

@app.post('/api/users/{user_id}/runs/{run_id}/send')
async def send(user_id: str, run_id: str):
    run = owned_run(user_id, run_id)
    if run['status'] != 'completed':
        raise HTTPException(409, '简报尚未生成成功')
    try:
        status = await asyncio.to_thread(send_mail, run_id, user(user_id), run['brief'])
    except Exception:
        raise HTTPException(503, '投递配置异常，请检查 SMTP 配置')
    return {'delivery': status}
