"""One-time local CA setup. No external service, domain or administrator server install."""
from datetime import datetime,timedelta,timezone
import argparse
import ipaddress
import json
from pathlib import Path
import socket
import os

ROOT=Path(__file__).resolve().parent


def lan_ip():
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(('192.0.2.1',9))  # Routing lookup only; sends no packet.
            return sock.getsockname()[0]
        except OSError:
            return socket.gethostbyname(socket.gethostname())


def configure(root,ip,port=8443):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
    address=ipaddress.ip_address(ip)
    if not address.is_private or address.is_unspecified or address.is_multicast:
        raise ValueError('Use a private LAN address, for example 192.168.1.57.')
    if not 1024<=port<=65535:raise ValueError('HTTPS port must be 1024..65535.')
    runtime=Path(root)/'.runtime';folder=runtime/'tls';folder.mkdir(parents=True,exist_ok=True)
    if os.name!='nt':folder.chmod(0o700)
    now=datetime.now(timezone.utc)
    keyfile=folder/'rootCA.key';certfile=folder/'rootCA.pem'
    def write_key(path,key):
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        if os.name!='nt':path.chmod(0o600)
    if keyfile.exists() and certfile.exists():
        ca_key=serialization.load_pem_private_key(keyfile.read_bytes(),password=None)
        ca=x509.load_pem_x509_certificate(certfile.read_bytes())
        if ca.not_valid_after_utc<now+timedelta(days=30):raise ValueError('Local CA expires soon. Renew the local CA and install its new certificate on the phone.')
    elif keyfile.exists() or certfile.exists():
        raise ValueError('Incomplete local CA. Restore both rootCA.pem and rootCA.key before continuing.')
    else:
        ca_key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'AI RPG Engine Local CA')])
        ca=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=False,key_cert_sign=True,crl_sign=True,
                content_commitment=False,data_encipherment=False,key_agreement=False,encipher_only=False,decipher_only=False),critical=True)
            .sign(ca_key,hashes.SHA256()))
        write_key(keyfile,ca_key);certfile.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (folder/'rootCA.cer').write_bytes(ca.public_bytes(serialization.Encoding.DER))
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'AI RPG Engine')])
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(ca.subject).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=365))
          .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1')),x509.IPAddress(address)]),critical=False)
          .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
          .sign(ca_key,hashes.SHA256()))
    write_key(folder/'server.key',key);(folder/'server.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    config={'ip':str(address),'port':port}
    (runtime/'https.json').write_text(json.dumps(config),encoding='utf-8')
    print(f'HTTPS configured: https://{address}:{port}')
    print('Start with start.bat. Install .runtime/tls/rootCA.cer as a CA certificate on the phone once.')
    print('Keep rootCA.key private. Certificate renewal with the same CA does not require reinstalling trust.')
    return config


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ip',default=lan_ip());p.add_argument('--port',type=int,default=8443);a=p.parse_args()
    configure(ROOT,a.ip,a.port)
