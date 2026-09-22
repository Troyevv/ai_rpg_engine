import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from local_https import configure


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def test_local_ca_preserved_and_both_listeners_share_app(tmp_path):
    secure=port();plain=port()
    configure(tmp_path,'127.0.0.1',secure)
    ca=tmp_path/'.runtime/tls/rootCA.pem';original=ca.read_bytes()
    configure(tmp_path,'127.0.0.1',secure)
    assert ca.read_bytes()==original
    context=ssl.create_default_context(cafile=str(ca))
    env={**os.environ,'RPG_PORT':str(plain),'RPG_HOST':'127.0.0.1','RPG_CONTROL_TOKEN':'test-control','RPG_DB_PATH':str(tmp_path/'test.db')}
    code=f"import launcher;from pathlib import Path;launcher.RUNTIME=Path({str(tmp_path/'.runtime')!r});launcher.serve()"
    process=subprocess.Popen([sys.executable,'-c',code],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f'https://127.0.0.1:{secure}/api/health',context=context,timeout=.3) as r:
                    assert json.load(r)['status']=='ready'
                break
            except OSError:time.sleep(.05)
        else:raise AssertionError('HTTPS did not become ready')
        data=json.dumps({'name':'Общая рабочая область'}).encode()
        req=urllib.request.Request(f'http://127.0.0.1:{plain}/api/workspaces',data=data,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as r:wid=json.load(r)['id']
        with urllib.request.urlopen(f'https://127.0.0.1:{secure}/api/workspaces',context=context) as r:
            assert json.load(r)[0]['id']==wid
        req=urllib.request.Request(f'http://127.0.0.1:{plain}/api/_shutdown',data=b'{}',headers={'X-Control-Token':'test-control'})
        urllib.request.urlopen(req).close();process.wait(timeout=8)
        assert process.returncode==0
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=8)
