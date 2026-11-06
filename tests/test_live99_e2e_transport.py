"""The fixture API must not leave sockets eligible for idle-timeout reuse."""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def test_fixture_responses_end_connections_without_retrying_requests(tmp_path):
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    env = dict(os.environ, E2E_PORT=str(port), E2E_DB_PATH=str(tmp_path/'fixture.sqlite'))
    env.pop('DEEPSEEK_API_KEY', None)
    with (tmp_path/'server.log').open('w') as log:
        proc = subprocess.Popen([sys.executable, 'tests/e2e_server.py'], cwd=root, env=env,
                                stdout=log, stderr=subprocess.STDOUT)
        client = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
        try:
            deadline = time.monotonic() + 15
            # Startup readiness only; the two asserted requests below have no retry.
            while True:
                assert proc.poll() is None, (tmp_path/'server.log').read_text()
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2):
                        break
                except OSError:
                    assert time.monotonic() < deadline, 'Fixture server did not start'
                    time.sleep(.05)
            ports, bodies = [], []
            for _ in range(2):
                client.request('GET', '/api/health')
                ports.append(client.sock.getsockname()[1])
                response = client.getresponse()
                assert response.status == 200
                bodies.append(json.loads(response.read()))
                assert client.sock is None, 'Completed fixture response left a pooled idle socket'
            assert len(set(ports)) == 2
            assert bodies[0] == bodies[1]
        finally:
            client.close()
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
