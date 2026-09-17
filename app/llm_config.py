import os
from urllib.parse import urlsplit

def api_key():
    return os.getenv('LLM_API_KEY') or os.getenv('OPENAI_API_KEY')

def model_name():
    return os.getenv('LLM_MODEL') or os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')

def endpoint():
    base = os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('LLM_BASE_URL 必须为不含凭据的 HTTPS 基础地址')
    return base + '/chat/completions'
