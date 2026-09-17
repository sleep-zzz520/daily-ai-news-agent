import os
import smtplib
import ssl
from email.message import EmailMessage
from app.db import connect, now

def send_mail(run_id, profile, brief):
    host = os.getenv('SMTP_HOST')
    sender = os.getenv('SMTP_FROM')
    if not host or not sender:
        with connect() as db:
            db.execute("UPDATE runs SET delivery='not_configured' WHERE id=?", (run_id,))
        return 'not_configured'
    with connect() as db:
        row = db.execute('SELECT status FROM deliveries WHERE run_id=?', (run_id,)).fetchone()
        if row:
            return row['status']
        db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?)', (run_id, 'sending', 0, None, now()))
        db.execute("UPDATE runs SET delivery='sending' WHERE id=?", (run_id,))
    message = EmailMessage()
    message['Subject'] = brief['title']
    message['From'] = sender
    message['To'] = profile['email']
    message['Message-ID'] = f'<{run_id}@daily-ai.local>'
    lines = [brief['title'], brief['note'], '根据公开 RSS 摘要整理。', '']
    for item in brief['items']:
        lines.extend([item['title'], item['summary'], '入选理由：' + item['reason'],
                      item['source'] + ' · ' + item['published_at'], item['url'], ''])
    message.set_content('\n'.join(lines))
    status, error = 'failed', None
    for attempt in range(1, 4):
        transmitting = False
        client = None
        try:
            security = os.getenv('SMTP_SECURITY', 'starttls')
            port = int(os.getenv('SMTP_PORT', '587'))
            if security == 'ssl':
                client = smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context())
            elif security == 'starttls':
                client = smtplib.SMTP(host, port, timeout=15)
                client.starttls(context=ssl.create_default_context())
            else:
                raise ValueError('SMTP_SECURITY 仅支持 starttls 或 ssl')
            if os.getenv('SMTP_USER'):
                client.login(os.environ['SMTP_USER'], os.getenv('SMTP_PASSWORD', ''))
            transmitting = True
            client.send_message(message)
            status = 'sent'
            break
        except smtplib.SMTPResponseException as e:
            error = f'SMTP {e.smtp_code}'
            if e.smtp_code >= 500:
                break
        except (OSError, smtplib.SMTPException, ValueError) as e:
            error = type(e).__name__
            if transmitting:
                status = 'unknown'
                break
            if isinstance(e, ValueError):
                break
        finally:
            if client:
                client.close()
    with connect() as db:
        db.execute('UPDATE deliveries SET status=?,attempts=?,error=?,updated_at=? WHERE run_id=?',
                   (status, attempt, error, now(), run_id))
        db.execute('UPDATE runs SET delivery=? WHERE id=?', (status, run_id))
    return status
