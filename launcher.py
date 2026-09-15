"""Double-click launcher: stdlib bootstrap, production build, one managed server."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / '.runtime'
FRONTEND = ROOT / 'frontend'
STATE = RUNTIME / 'server.json'


def request(url, token=None):
    req = urllib.request.Request(url, data=b'{}' if token else None,
                                 headers={'X-Control-Token': token, 'Content-Type': 'application/json'} if token else {})
    with urllib.request.urlopen(req, timeout=2) as response:
        return json.load(response)


def frontend_digest():
    paths = [FRONTEND / n for n in ('package.json', 'package-lock.json', 'index.html', 'vite.config.ts', 'tsconfig.json')]
    paths += sorted((FRONTEND / 'src').rglob('*'))
    digest = hashlib.sha256()
    for path in paths:
        if path.is_file():
            digest.update(str(path.relative_to(FRONTEND)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def prepare():
    if sys.version_info < (3, 10):
        raise RuntimeError('Install Python 3.10 or newer.')
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], check=True)
    requirements = hashlib.sha256((ROOT / 'requirements.txt').read_bytes()).hexdigest()
    stamp = RUNTIME / 'requirements.sha256'
    if not stamp.exists() or stamp.read_text() != requirements:
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True, cwd=ROOT)
        stamp.write_text(requirements)
    build = FRONTEND / 'dist' / '.buildhash'
    digest = frontend_digest()
    if not (FRONTEND / 'dist/index.html').exists() or not build.exists() or build.read_text() != digest:
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            raise RuntimeError('Install Node.js 22.12+ (including npm), then run start.bat again.')
        subprocess.run([npm, 'ci'], cwd=FRONTEND, check=True)
        subprocess.run([npm, 'run', 'build'], cwd=FRONTEND, check=True)
        build.write_text(digest)
    return python


def start(open_browser=True):
    RUNTIME.mkdir(exist_ok=True)
    # OS lock survives no crash; protects simultaneous double-clicks without stale PID files.
    with (RUNTIME / 'launcher.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError('AI RPG Engine is already starting. Please wait.') from None
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if STATE.exists():
            old = json.loads(STATE.read_text())
            try:
                if request(old['url'] + '/api/health').get('service') == 'ai-rpg-engine':
                    if open_browser:
                        webbrowser.open(old['url'])
                    print('Already running: ' + old['url'])
                    return
            except (OSError, ValueError):
                pass
        python = prepare()
        port = int(os.getenv('RPG_PORT', '8000'))
        token = secrets.token_urlsafe(32)
        url = f'http://127.0.0.1:{port}'
        # Refuse any occupied port; never terminate another application's process.
        import socket
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                raise RuntimeError(f'Port {port} is busy. Stop the other server or set RPG_PORT.') from None
        env = {**os.environ, 'RPG_CONTROL_TOKEN': token, 'RPG_PORT': str(port), 'PYTHONUTF8': '1'}
        with (RUNTIME / 'server.log').open('ab') as log:
            process = subprocess.Popen([str(python), str(ROOT / 'launcher.py'), 'serve'], cwd=ROOT,
                                       env=env, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                       start_new_session=os.name != 'nt')
        STATE.write_text(json.dumps({'url': url, 'token': token}), encoding='utf-8')
        if os.name != 'nt':
            STATE.chmod(0o600)
        for _ in range(150):
            if process.poll() is not None:
                raise RuntimeError('Server exited. See .runtime/server.log.')
            try:
                if request(url + '/api/health').get('status') == 'ready':
                    print('AI RPG Engine: ' + url)
                    if open_browser:
                        webbrowser.open(url)
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        raise RuntimeError('Server readiness timed out. See .runtime/server.log; stop.bat can stop it.')


def stop():
    if not STATE.exists():
        print('No managed server is running.')
        return
    state = json.loads(STATE.read_text())
    try:
        request(state['url'] + '/api/_shutdown', state['token'])
    except urllib.error.HTTPError:
        raise RuntimeError('Server identity does not match. No process was terminated.') from None
    except OSError:
        print('Server is already stopped.')
    else:
        print('Stopping AI RPG Engine. Active generation is being cancelled.')
    STATE.unlink(missing_ok=True)


def serve():
    import uvicorn
    from backend.api.app import create_app
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=int(os.getenv('RPG_PORT', '8000')), log_level='info', timeout_graceful_shutdown=3))
    app.state.shutdown = lambda: setattr(server, 'should_exit', True)
    server.run()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['start', 'stop', 'serve'], nargs='?', default='start')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'start':
            start(not args.no_browser)
        elif args.command == 'stop':
            stop()
        else:
            serve()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
