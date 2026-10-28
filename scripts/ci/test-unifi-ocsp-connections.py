"""Run REAL local TLS/OCSP against copied AP collector and patched UnPoller.

Only the Docker-inspect discovery input is substituted for AP counts. No mock
TLS socket, crypto parser, OCSP network client or UnPoller transport is used.
"""
import argparse
import base64
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import ssl
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'roles/observability/files'
sys.path.insert(0, str(FILES))
from unifi_ocsp import Denied, Policy, validate_response


def load_collector():
    spec = importlib.util.spec_from_file_location('ap_counts', FILES / 'unifi-ap-counts.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def handle_error(self, *args):
        pass  # Expected certificate rejection; never print requests/cookies.


@contextmanager
def serve(handler, tls=None):
    server = Server(('127.0.0.1', 0), handler)
    if tls:
        server.socket = tls.wrap_socket(server.socket, server_side=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(3)


def main(fixture, binary):
    fixture = fixture.resolve()
    if 'ocsp-private' not in fixture.parts or not (fixture / 'manifest.json').is_file():
        raise ValueError('Disposable test fixtures required')
    manifest = json.loads((fixture / 'manifest.json').read_text())
    assert manifest['fictitious_only'] is True
    collector = load_collector()
    observed = {'requests': [], 'ocsp': [], 'mode': 'good', 'status': 200}

    class OCSP(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            observed['ocsp'].append({'body': base64.b64encode(body).decode(),
                                     'credentials': bool(self.headers.get('Authorization') or self.headers.get('Cookie'))})
            mode = observed['mode']
            if mode == 'timeout':
                time.sleep(2)
            if mode == 'redirect':
                self.send_response(302)
                self.send_header('Location', 'http://not-allowed.example.test/')
                self.end_headers()
                return
            data = b'x' * 65537 if mode == 'oversized' else (fixture / ((mode if mode not in ('timeout', 'http') else 'good') + '.der')).read_bytes()
            self.send_response(503 if mode == 'http' else 200)
            self.send_header('Content-Type', 'application/ocsp-response')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except OSError:
                pass

    class Controller(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *args):
            pass
        def reply(self, post=False):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0))) if post else b''
            observed['requests'].append({'path': self.path, 'post': post,
                'credentials': bool(body or self.headers.get('Cookie')),
                'connection': self.client_address[1], 'session_resumed': self.connection.session_reused})
            if self.path.endswith('/stat/sites') or self.path.endswith('/self/sites'):
                data = [{'name': 'default', 'desc': 'Fictitious site', '_id': 'fixture-site'}]
            elif self.path.endswith('/stat/device'):
                data = [{'name': 'fixture-ap', 'mac': '00:00:5e:00:53:01', '_id': 'fixture-ap',
                         'type': 'uap', 'state': 1, 'user-num_sta': 3, 'guest-num_sta': 1}]
            else:
                data = []
            payload = json.dumps({'meta': {'rc': 'ok', 'server_version': '10.0.0'}, 'data': data}).encode()
            if self.path.endswith('/device-tags'):
                payload = b'[]'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            if post:
                self.send_header('Set-Cookie', 'fixture=session; Secure; HttpOnly; Path=/')
            self.end_headers()
            self.wfile.write(payload)
        def do_GET(self):
            self.reply()
        def do_POST(self):
            if self.path != '/api/auth/login':
                raise AssertionError('Unexpected controller write')
            self.reply(True)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(fixture / 'leaf.pem'), str(fixture / 'leaf.key'))
    results = []
    with serve(OCSP) as responder, serve(Controller, context) as controller:
        url = 'https://controller.example.test:' + str(controller.server_port)
        counter = 0

        def config_for(name):
            nonlocal counter
            counter += 1
            state = fixture / (name + '-' + str(counter) + '-state.json')
            state.write_text(json.dumps({'version': 1, 'revoked': [], 'cache': {}, 'last_clock': 0}))
            Path(str(state) + '.lock').write_bytes(b'0')
            policy = {'issuer_file': str(fixture / 'issuer.pem'), 'state_file': str(state),
                      'responder_url': 'http://ocsp.example.test:' + str(responder.server_port) + '/ocsp',
                      'responder_address': '127.0.0.1', 'timeout_seconds': 0.4,
                      'cache_ttl_seconds': 60,
                      'collector': 'unpoller' if name.startswith('unpoller') else 'ap_counts',
                      'metrics_file': str(fixture / (name + '-' + str(counter) + '-metrics.prom'))}
            policy_path = fixture / (name + '-' + str(counter) + '-policy.json')
            policy_path.write_text(json.dumps(policy))
            return policy_path, policy

        def run(kind, policy_path, ca='issuer', hostname='controller.example.test', metrics=False, remote=False):
            destination = url.replace('controller.example.test', hostname)
            if kind == 'python':
                password = fixture / 'fictitious-password.txt'
                password.write_text('test-only-password')
                env = ['UP_UNIFI_DEFAULT_URL=' + destination, 'UP_UNIFI_DEFAULT_VERIFY_SSL=true', 'UP_UNIFI_DEFAULT_USER=fixture-user']
                config = {'hostname': hostname, 'internal_address': '127.0.0.1',
                          'port': controller.server_port, 'ca_file': str(fixture / (ca + '.pem')),
                          'url': destination, 'username': 'fixture-user',
                          'password_file': str(password), 'ocsp_policy_file': str(policy_path)}
                try:
                    with patch.object(collector.subprocess, 'check_output', return_value=json.dumps([{'Config': {'Env': env}}]).encode()):
                        data = collector.collect(config)
                    return 'iop_unifi_ap_users' in data, data
                except Exception as error:
                    return False, str(error)
            else:
                with socket.socket() as reserve:
                    reserve.bind(('127.0.0.1', 0))
                    metrics_port = reserve.getsockname()[1]
                configuration = {'poller': {'quiet': True}, 'influxdb': {'disable': True},
                                 'prometheus': {'disable': not metrics, 'namespace': 'unpoller',
                                                'http_listen': '127.0.0.1:' + str(metrics_port), 'interval': '1s'},
                                 'unifi': {'defaults': {'url': destination, 'user': 'fixture-user',
                                      'pass': 'test-only-password', 'verify_ssl': True, 'save_sites': True}}}
                if remote:
                    configuration['unifi'].update(remote=True, remote_api_key='fixture-key')
                path = fixture / 'unpoller-test.json'
                path.write_text(json.dumps(configuration))
                environment = {k: v for k, v in os.environ.items() if not k.startswith(('UP_', 'IOP_UNIFI_OCSP_'))}
                environment.update(IOP_UNIFI_OCSP_POLICY=str(policy_path), IOP_UNIFI_OCSP_PYTHON=sys.executable,
                    IOP_UNIFI_OCSP_VERIFIER=str(FILES / 'unifi_ocsp.py'), IOP_UNIFI_OCSP_CA_FILE=str(fixture / (ca + '.pem')),
                    IOP_UNIFI_OCSP_CONTROLLER_ADDRESS='127.0.0.1')
                if metrics:
                    process = subprocess.Popen([str(binary), '--config', str(path)], env=environment,
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    result = ''
                    try:
                        for _ in range(30):
                            try:
                                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                                result = opener.open('http://127.0.0.1:' + str(metrics_port) + '/metrics', timeout=3).read().decode()
                                if 'Fictitious site (default)' in result and 'unpoller_topology_vertices_total' in result:
                                    return True, result
                            except OSError:
                                pass
                            if process.poll() is not None:
                                break
                            time.sleep(0.5)
                    finally:
                        process.terminate()
                        stdout, stderr = process.communicate(timeout=10)
                    return False, result[-1000:] + (stdout + stderr).decode(errors='replace')[-2000:]
                process = subprocess.run([str(binary), '--config', str(path), '--dumpjson', 'other /api/stat/sites'],
                                         env=environment, capture_output=True, timeout=35)
                text = (process.stdout + process.stderr).decode(errors='replace')
                return process.returncode == 0 and 'fixture-site' in text, text

        modes = ['good', 'delegated-good', 'revoked', 'unknown', 'bad-signature', 'unauthorized',
                 'wrong-serial', 'wrong-issuer', 'expired', 'future-this-update', 'future-produced-at',
                 'old-produced-at', 'incoherent-produced-at', 'missing-next-update', 'next-before-this',
                 'malformed', 'oversized', 'redirect', 'http', 'timeout']
        for kind in ['python', 'unpoller']:
            for mode in modes:
                observed['mode'] = mode
                policy_path, _ = config_for(kind + '-' + mode)
                before = len(observed['requests'])
                passed, text = run(kind, policy_path)
                expected = mode in ('good', 'delegated-good')
                assert passed == expected, (kind, mode, text[-2000:])
                requests = observed['requests'][before:]
                if not expected:
                    assert not requests, (kind, mode, 'application bytes reached controller')
                else:
                    assert any(r['post'] for r in requests), (kind, 'no authentication exercised')
                    assert len({r['connection'] for r in requests}) == len(requests), (kind, 'connection reused')
                    assert not any(r['session_resumed'] for r in requests), (kind, 'TLS session resumed')
                results.append({'collector': kind, 'case': mode, 'pass': True,
                                'application_requests': len(requests), 'no_pooling_or_resumption': True})
                print(kind, mode, 'PASS', flush=True)
            observed['mode'] = 'good'
            policy_path, bad_ca_policy = config_for(kind + '-bad-ca')
            before = len(observed['requests'])
            passed, text = run(kind, policy_path, ca='wrong-issuer')
            assert not passed and len(observed['requests']) == before, (kind, 'bad CA')
            assert 'reason="tls"} 1' in Path(bad_ca_policy['metrics_file']).read_text()
            results.append({'collector': kind, 'case': 'wrong-ca', 'pass': True, 'application_requests': 0})
            policy_path, _ = config_for(kind + '-bad-hostname')
            before = len(observed['requests'])
            passed, _ = run(kind, policy_path, hostname='wrong.example.test')
            assert not passed and len(observed['requests']) == before, (kind, 'bad hostname')
            results.append({'collector': kind, 'case': 'wrong-hostname', 'pass': True, 'application_requests': 0})
            # A cache hit must survive responder outage; an expired cache must not.
            policy_path, policy = config_for(kind + '-cache')
            assert run(kind, policy_path)[0]
            observed['mode'] = 'http'
            assert run(kind, policy_path)[0], (kind, 'valid cache did not survive outage')
            state = json.loads(Path(policy['state_file']).read_text())
            for entry in state['cache'].values():
                entry['deadline'] = 0
            Path(policy['state_file']).write_text(json.dumps(state))
            before = len(observed['requests'])
            assert not run(kind, policy_path)[0] and len(observed['requests']) == before
            results.append({'collector': kind, 'case': 'valid-and-expired-cache', 'pass': True})
            # Confirmed revocation is sticky even after endpoint recovers with GOOD.
            observed['mode'] = 'revoked'
            policy_path, policy = config_for(kind + '-sticky')
            assert not run(kind, policy_path)[0]
            assert json.loads(Path(policy['state_file']).read_text())['revoked']
            observed['mode'] = 'good'
            before = len(observed['requests'])
            assert not run(kind, policy_path)[0] and len(observed['requests']) == before
            results.append({'collector': kind, 'case': 'sticky-revocation', 'pass': True})
            # Change actual TLS leaf while a GOOD cache for the old leaf exists.
            policy_path, _ = config_for(kind + '-rotation')
            assert run(kind, policy_path)[0]
            context.load_cert_chain(str(fixture / 'rotated.pem'), str(fixture / 'rotated.key'))
            before = len(observed['requests'])
            assert not run(kind, policy_path)[0] and len(observed['requests']) == before
            observed['mode'] = 'rotated-good'
            assert run(kind, policy_path)[0]
            context.load_cert_chain(str(fixture / 'leaf.pem'), str(fixture / 'leaf.key'))
            observed['mode'] = 'good'
            results.append({'collector': kind, 'case': 'actual-leaf-rotation-and-recovery', 'pass': True})
            # Idempotent repeated checks do not change cached bytes or deny state.
            policy_path, policy = config_for(kind + '-repeat')
            assert run(kind, policy_path)[0]
            old_state = json.loads(Path(policy['state_file']).read_text())
            assert run(kind, policy_path)[0]
            new_state = json.loads(Path(policy['state_file']).read_text())
            assert old_state['cache'] == new_state['cache'] and old_state['revoked'] == new_state['revoked']
            results.append({'collector': kind, 'case': 'stable-cache-and-deny-state-repeat', 'pass': True})
            if kind == 'unpoller':
                policy_path, _ = config_for('unpoller-remote-refused')
                before = len(observed['requests'])
                passed, text = run(kind, policy_path, remote=True)
                assert not passed and 'unifi_ocsp_remote_unsupported' in text and len(observed['requests']) == before
                results.append({'collector': kind, 'case': 'remote-cloud-mode-refused', 'pass': True})
                policy_path, _ = config_for('unpoller-metrics')
                passed, text = run(kind, policy_path, metrics=True)
                assert passed, ('real Prometheus endpoint', text)
                results.append({'collector': kind, 'case': 'actual-prometheus-metrics', 'pass': True})
        assert observed['ocsp'] and not any(r['credentials'] for r in observed['ocsp'])
    output = {'real_tls_and_ocsp_network': True, 'actual_unpoller_binary': True,
              'python_inspect_input_substituted': True, 'operational_access': False,
              'cases': results, 'ocsp_received_credentials': False}
    (fixture / 'connection-results.json').write_text(json.dumps(output, indent=2))
    print('RESULT', len(results), 'cases passed', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    args = parser.parse_args()
    main(args.fixture, args.binary.resolve())
