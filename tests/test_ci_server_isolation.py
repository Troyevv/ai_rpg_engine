"""Exercise the real browser fixture in two processes, without sharing its globals/DB."""
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def test_two_fixture_servers_keep_saves_isolated(tmp_path):
    processes = []
    clients = []
    try:
        for index in range(2):
            directory = tmp_path / str(index)
            directory.mkdir()
            port = free_port()
            env = dict(os.environ, E2E_PORT=str(port), E2E_DB_PATH=str(directory / 'game.sqlite3'),
                       TMPDIR=str(directory), RPG_SEMANTIC_ENABLED='0')
            log = open(directory / 'server.log', 'w')
            process = subprocess.Popen([sys.executable, str(ROOT / 'tests/e2e_server.py')],
                                       cwd=ROOT, env=env, stdout=log, stderr=log)
            log.close()
            processes.append(process)
            clients.append(httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=10, trust_env=False))
        deadline = time.monotonic() + 40
        for client in clients:
            while True:
                try:
                    if client.get('/api/health').status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert time.monotonic() < deadline, 'Fixture server startup timed out'
                assert all(p.poll() is None for p in processes), 'Fixture server exited'
                time.sleep(0.1)
        # Repeat concurrent writes; each server retains only its own saves.
        for iteration in range(3):
            with ThreadPoolExecutor(max_workers=2) as pool:
                selections = list(pool.map(lambda c: c.post('/test/seed').json(), clients))
            for index, selection in enumerate(selections):
                assert clients[index].get(f'/api/saves/{selection["save"]}').status_code == 200
                assert selection["save"] == iteration + 1
        extra = clients[0].post("/test/seed").json()
        assert clients[0].get(f'/api/saves/{extra["save"]}').status_code == 200
        for index, count in enumerate((4, 3)):
            with sqlite3.connect(tmp_path / str(index) / "game.sqlite3") as db:
                assert db.execute("SELECT COUNT(*) FROM saves").fetchone()[0] == count
        assert (tmp_path / '0/game.sqlite3').stat().st_ino != (tmp_path / '1/game.sqlite3').stat().st_ino
    finally:
        for client in clients:
            client.close()
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
