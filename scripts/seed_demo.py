"""Create clearly labeled offline sample data, never call a model or send mail."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from app.db import connect, dumps, init_db, now

def seed():
    init_db()
    user_id, run_id = uuid.uuid4().hex, uuid.uuid4().hex
    profile = {'nickname': '离线演示（模拟数据）', 'email': 'demo@example.com',
               'topics': ['开源模型'], 'keywords': [], 'excluded_keywords': [],
               'send_time': '09:00', 'enabled': False}
    brief = {'is_demo': True, 'title': '离线示例简报 · 非真实新闻',
             'note': '此数据仅用于演示页面，由脚本写入；未调用模型、未获取今日新闻、未发送邮件。',
             'items': [{'title': '示例：一项开源模型更新', 'summary': '这是一段模拟摘要，用于检查简报阅读、来源链接和历史记录的显示。',
                        'reason': '模拟展示与“开源模型”偏好的关联。', 'source': '模拟来源',
                        'url': 'https://example.com/', 'published_at': now()}]}
    with connect() as db:
        db.execute('INSERT INTO users VALUES(?,?)', (user_id, dumps(profile)))
        db.execute('INSERT INTO runs(id,user_id,status,created_at,brief) VALUES(?,?,?,?,?)',
                   (run_id, user_id, 'completed', now(), dumps(brief)))
        db.execute('INSERT INTO tool_calls(run_id,name,arguments,result,duration) VALUES(?,?,?,?,?)',
                   (run_id, '模拟记录：read_file', dumps({'path': 'preferences.json'}),
                    dumps({'note': '脚本构造，非真实模型调用', 'topics': profile['topics']}), 0.0))
    print('已创建暂停订阅的模拟用户；页面刷新后选择“离线演示（模拟数据）”。')

if __name__ == '__main__':
    seed()
