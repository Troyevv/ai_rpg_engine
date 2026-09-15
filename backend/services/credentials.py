"""Server-side encrypted credentials, shared by browser devices on this installation."""
import os
import threading
from cryptography.fernet import Fernet, InvalidToken

LOCK = threading.Lock()


class Credentials:
    def __init__(self, repo):
        self.repo = repo
        self.path = repo.path.parent / '.credential-key'

    def cipher(self):
        with LOCK:
            if not self.path.exists():
                with self.repo.connect() as db:
                    if db.execute('SELECT 1 FROM provider_credentials LIMIT 1').fetchone():
                        raise ValueError('Не найден ключ шифрования. Восстанови .credential-key из резервной копии.')
                fd = os.open(self.path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
                with os.fdopen(fd,'wb') as f:
                    f.write(Fernet.generate_key())
            return Fernet(self.path.read_bytes())

    def put(self, provider, key):
        encrypted = self.cipher().encrypt(key.strip().encode())
        with self.repo.connect() as db:
            db.execute('INSERT INTO provider_credentials VALUES(?,?) ON CONFLICT(provider) DO UPDATE SET encrypted_key=excluded.encrypted_key', (provider,encrypted))

    def resolve(self, provider, supplied=None):
        if provider == 'local':
            return None
        if supplied and supplied.strip():
            self.put(provider,supplied)
            return supplied.strip()
        with self.repo.connect() as db:
            row = db.execute('SELECT encrypted_key FROM provider_credentials WHERE provider=?',(provider,)).fetchone()
        if row:
            try:
                return self.cipher().decrypt(row[0]).decode()
            except InvalidToken:
                raise ValueError('Не удалось расшифровать API-ключ. Введи его заново.') from None
        return None  # llm layer can still use environment variables.

    def status(self):
        with self.repo.connect() as db:
            stored = bool(db.execute("SELECT 1 FROM provider_credentials WHERE provider='deepseek'").fetchone())
        return {'deepseek': stored or bool(os.getenv('DEEPSEEK_API_KEY'))}

    def delete(self, provider):
        with self.repo.connect() as db:
            db.execute('DELETE FROM provider_credentials WHERE provider=?',(provider,))
