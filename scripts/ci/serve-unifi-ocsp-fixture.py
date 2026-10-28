"""Persistent loopback-only emulator for disposable Ansible/Compose acceptance."""
import argparse
import json
from pathlib import Path
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main(root, certificate='leaf'):
    if 'ocsp-private' not in root.parts or not json.loads((root / 'manifest.json').read_text())['fictitious_only']:
        raise ValueError('Test fixtures only')
    if certificate == 'rotated':
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.x509 import ocsp
        issuer = x509.load_pem_x509_certificate((root / 'issuer.pem').read_bytes())
        leaf = x509.load_pem_x509_certificate((root / 'rotated.pem').read_bytes())
        key = serialization.load_pem_private_key((root / 'issuer.key').read_bytes(), None)
        now = datetime.now(timezone.utc)
        response = (ocsp.OCSPResponseBuilder().add_response(leaf, issuer, hashes.SHA256(),
            ocsp.OCSPCertStatus.REVOKED, now - timedelta(minutes=1), now + timedelta(minutes=30),
            now - timedelta(minutes=2), x509.ReasonFlags.key_compromise)
            .responder_id(ocsp.OCSPResponderEncoding.HASH, issuer).sign(key, hashes.SHA256()))
        (root / 'rotated-revoked.der').write_bytes(response.public_bytes(serialization.Encoding.DER))
        (root / 'responder-mode.txt').write_text('good')
    class HTTP(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.path == '/ocsp':
                mode = (root / 'responder-mode.txt').read_text().strip() if (root / 'responder-mode.txt').exists() else 'good'
                if certificate == 'rotated' and mode in ('good', 'revoked'):
                    mode = 'rotated-' + mode
                data = (root / (mode + '.der')).read_bytes()
                content_type = 'application/ocsp-response'
            elif self.path == '/api/auth/login':
                data = b'{"meta":{"rc":"ok"},"data":[]}'
                content_type = 'application/json'
            else:
                self.send_error(405)
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            if self.path.endswith('/stat/sites') or self.path.endswith('/self/sites'):
                data = [{'name': 'default', '_id': 'fixture-site', 'desc': 'Fictitious site'}]
            elif self.path.endswith('/stat/device'):
                data = [{'name': 'fixture-ap', '_id': 'fixture-ap', 'mac': '00:00:5e:00:53:01',
                         'type': 'uap', 'state': 1, 'user-num_sta': 3, 'guest-num_sta': 1}]
            else:
                data = []
            body = json.dumps({'meta': {'rc': 'ok', 'server_version': '10.0.0'}, 'data': data}).encode()
            if self.path.endswith('/device-tags'):
                body = b'[]'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    controller = ThreadingHTTPServer(('127.0.0.1', 41443), HTTP)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(root / (certificate + '.pem')), str(root / (certificate + '.key')))
    controller.socket = context.wrap_socket(controller.socket, server_side=True)
    ocsp = ThreadingHTTPServer(('127.0.0.1', 41089), HTTP)
    threading.Thread(target=ocsp.serve_forever, daemon=True).start()
    controller.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--certificate', choices=['leaf', 'rotated'], default='leaf')
    args = parser.parse_args()
    main(args.fixture, args.certificate)
