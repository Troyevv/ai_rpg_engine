"""Optional official offline tokenizer; no remote code or inference requests."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from functools import lru_cache
import zipfile

import requests

from backend.chat.capabilities import DEEPSEEK

URL = 'https://cdn.deepseek.com/api-docs/deepseek_v4_tokenizer.zip'
ARCHIVE_SHA256 = 'e7310d1dafe0a86d8a5629fe78a7c763760f651db9b8682718a1781dcd6fe495'
TOKENIZER_SHA256 = '89085f12ef79460ac5f66d1119325ddfc694b4ab209d80bbd81d35f081dc9614'
ENTRY = 'deepseek_v4_tokenizer/tokenizer.json'
MAX_BYTES = 8 * 1024 * 1024
LOCK = threading.Lock()


def path():
    return Path(os.getenv('RPG_CHAT_TOKENIZER_PATH') or Path(__file__).resolve().parents[2] / '.runtime/chat-tokenizers/deepseek-v4.json')


@lru_cache(maxsize=2)
def load(filename, modified, size, expected):
    if size > MAX_BYTES: return None
    data = Path(filename).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected: return None
    from tokenizers import Tokenizer
    return Tokenizer.from_str(data.decode('utf-8'))


def available():
    try:
        file = path(); info = file.stat()
        return load(str(file),info.st_mtime_ns,info.st_size,TOKENIZER_SHA256)
    except Exception:
        return None


def method(config):
    if config['provider']=='deepseek' and config['model'] in DEEPSEEK and available() is not None:
        return 'DeepSeek V4 tokenizer + оценка протокола'
    return 'Консервативная оценка UTF-8'


def count(value, config):
    text = json.dumps(value,ensure_ascii=False)
    tokenizer = available() if config['provider']=='deepseek' and config['model'] in DEEPSEEK else None
    if tokenizer is not None:
        try:
            # JSON includes full content/config; actual API framing is private, so
            # the total remains approximate and keeps protocol + 15% safety reserve.
            return len(tokenizer.encode(text,add_special_tokens=False).ids), 'DeepSeek V4 tokenizer + оценка протокола'
        except Exception:
            pass
    return len(text.encode()), 'Консервативная оценка UTF-8'


def install():
    """Explicit free setup action. Only pinned JSON is read from the archive."""
    with LOCK:
        if available() is not None: return {'installed':True,'downloaded':False}
        try:
            from tokenizers import Tokenizer
            data = bytearray()
            with requests.get(URL,stream=True,timeout=(5,20)) as response:
                response.raise_for_status()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data)>MAX_BYTES: raise ValueError('size')
            if hashlib.sha256(data).hexdigest()!=ARCHIVE_SHA256: raise ValueError('archive checksum')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if archive.getinfo(ENTRY).file_size>MAX_BYTES: raise ValueError('expanded size')
                payload=archive.read(ENTRY)
            if hashlib.sha256(payload).hexdigest()!=TOKENIZER_SHA256: raise ValueError('tokenizer checksum')
            Tokenizer.from_str(payload.decode('utf-8'))  # Parse data only; no Python/config execution.
            target=path();target.parent.mkdir(parents=True,exist_ok=True)
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as output:
                    temporary=output.name;output.write(payload)
                os.replace(temporary,target)
            finally:
                if temporary and os.path.exists(temporary): os.unlink(temporary)
            load.cache_clear()
            return {'installed':True,'downloaded':True}
        except Exception:
            raise ValueError('Не удалось установить проверенный tokenizer. Проверьте соединение, backend-зависимости и доступ на запись. Консервативная оценка остаётся доступной.') from None


if __name__=='__main__':
    print(json.dumps(install(),ensure_ascii=False))
