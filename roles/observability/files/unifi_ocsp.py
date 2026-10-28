"""Connection-bound OCSP verifier, shared with patched UnPoller via stdin CLI.

No TLS bypass, AIA fetching, environment proxies, credentials or redirects.
State must live on a persistent private volume; absence is a hard failure.
"""
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509 import ocsp
from cryptography.x509.oid import ExtendedKeyUsageOID, SignatureAlgorithmOID


class Denied(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__('unifi_ocsp_' + reason)


def validate_response(data, leaf, issuer, now, skew=120, max_age=3600):
    """Authenticate a single CertID response before interpreting status/times."""
    try:
        response = ocsp.load_der_ocsp_response(data)
        if response.response_status != ocsp.OCSPResponseStatus.SUCCESSFUL:
            raise Denied('malformed')
        singles = list(response.responses)
        if len(singles) != 1:
            raise Denied('identity')
        single = singles[0]
        if response.extensions:
            if any(e.critical for e in response.extensions):
                raise Denied('malformed')
        if any(e.critical for e in response.single_extensions):
            raise Denied('malformed')
        leaf.verify_directly_issued_by(issuer)
        request = ocsp.OCSPRequestBuilder().add_certificate(leaf, issuer, single.hash_algorithm).build()
        if (single.serial_number != leaf.serial_number or
                single.issuer_name_hash != request.issuer_name_hash or
                single.issuer_key_hash != request.issuer_key_hash):
            raise Denied('identity')
        candidates = [issuer] + list(response.certificates)
        signer = None
        for candidate in candidates:
            if response.responder_name is not None:
                matches = candidate.subject == response.responder_name
            else:
                matches = x509.SubjectKeyIdentifier.from_public_key(candidate.public_key()).digest == response.responder_key_hash
            if matches:
                signer = candidate
                break
        if signer is None:
            raise Denied('responder')
        if signer.fingerprint(hashes.SHA256()) != issuer.fingerprint(hashes.SHA256()):
            signer.verify_directly_issued_by(issuer)
            eku = signer.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            ku = signer.extensions.get_extension_for_class(x509.KeyUsage).value
            if ExtendedKeyUsageOID.OCSP_SIGNING not in eku or not ku.digital_signature:
                raise Denied('responder')
        for cert in [leaf, issuer, signer]:
            if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
                raise Denied('time')
        if response.signature_hash_algorithm.name not in ('sha256', 'sha384', 'sha512'):
            raise Denied('signature')
        key = signer.public_key()
        if isinstance(key, rsa.RSAPublicKey) and response.signature_algorithm_oid in (
                SignatureAlgorithmOID.RSA_WITH_SHA256, SignatureAlgorithmOID.RSA_WITH_SHA384,
                SignatureAlgorithmOID.RSA_WITH_SHA512):
            key.verify(response.signature, response.tbs_response_bytes, padding.PKCS1v15(), response.signature_hash_algorithm)
        elif isinstance(key, ec.EllipticCurvePublicKey) and response.signature_algorithm_oid in (
                SignatureAlgorithmOID.ECDSA_WITH_SHA256, SignatureAlgorithmOID.ECDSA_WITH_SHA384,
                SignatureAlgorithmOID.ECDSA_WITH_SHA512):
            key.verify(response.signature, response.tbs_response_bytes, ec.ECDSA(response.signature_hash_algorithm))
        else:
            raise Denied('signature')
        produced, this, next_time = response.produced_at_utc, single.this_update_utc, single.next_update_utc
        if next_time is None:
            raise Denied('time')
        timestamp = now.timestamp()
        if (produced.timestamp() > timestamp + skew or this.timestamp() > timestamp + skew or
                timestamp >= next_time.timestamp() or next_time <= this or
                produced.timestamp() < this.timestamp() - skew or
                produced.timestamp() > next_time.timestamp() + skew or
                timestamp - produced.timestamp() > max_age or timestamp - this.timestamp() > max_age or
                not signer.not_valid_before_utc <= produced < signer.not_valid_after_utc):
            raise Denied('time')
        if single.certificate_status == ocsp.OCSPCertStatus.REVOKED:
            raise Denied('revoked')
        if single.certificate_status != ocsp.OCSPCertStatus.GOOD:
            raise Denied('unknown')
        return min(next_time.timestamp(), leaf.not_valid_after_utc.timestamp(),
                   issuer.not_valid_after_utc.timestamp(), signer.not_valid_after_utc.timestamp(),
                   produced.timestamp() + max_age, this.timestamp() + max_age)
    except Denied:
        raise
    except InvalidSignature:
        raise Denied('signature') from None
    except x509.ExtensionNotFound:
        raise Denied('responder') from None
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise Denied('malformed') from None


class Policy:
    def __init__(self, config):
        self.config = config
        self.issuer = x509.load_pem_x509_certificate(Path(config['issuer_file']).read_bytes())
        self.state = Path(config['state_file'])
        self.endpoint = urlsplit(config['responder_url'])
        self.address = str(ipaddress.ip_address(config['responder_address']))
        self.timeout = config.get('timeout_seconds', 5)
        self.limit = config.get('response_limit', 65536)
        self.entries = config.get('cache_entries', 128)
        self.skew = config.get('clock_skew_seconds', 120)
        self.max_age = config.get('max_age_seconds', 3600)
        self.cache_ttl = config.get('cache_ttl_seconds', 300)
        if (self.endpoint.scheme not in ('http', 'https') or not self.endpoint.hostname or
                self.endpoint.username or self.endpoint.password or self.endpoint.fragment or
                self.endpoint.query or not self.endpoint.path or
                not 0 < self.timeout <= 10 or not 0 < self.limit <= 65536 or
                not 0 < self.entries <= 128 or not 0 <= self.skew <= 120 or
                not 0 < self.cache_ttl <= self.max_age <= 3600):
            raise Denied('config')
        self.endpoint.port  # reject malformed ports before any connection
        if not self.state.is_file():
            raise Denied('state')

    @contextmanager
    def locked(self):
        # Lock file provisioned once alongside the state. Never unlink a lock:
        # waiters must serialize on the same inode across atomic state replaces.
        with open(str(self.state) + '.lock', 'r+b') as lock:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0)
                deadline = time.monotonic() + self.timeout
                while True:
                    try:
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise Denied('timeout') from None
                        time.sleep(0.02)
            else:
                import fcntl
                deadline = time.monotonic() + self.timeout
                while True:
                    try:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise Denied('timeout') from None
                        time.sleep(0.02)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def save(self, state):
        fd, name = tempfile.mkstemp(dir=self.state.parent, prefix='.ocsp-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream, separators=(',', ':'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.state)
            # Persist the directory entry as well as file contents before a
            # confirmed revocation may be acknowledged. Fail closed on error.
            # Windows has no portable directory fsync; operational containers
            # are Linux and acceptance tests require this durability boundary.
            if os.name == 'posix':
                directory = os.open(self.state.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def fetch(self, request):
        endpoint, address, timeout = self.endpoint, self.address, self.timeout
        class FixedDestination(http.client.HTTPConnection):
            def connect(connection):
                raw = socket.create_connection((address, connection.port), timeout=timeout)
                connection.sock = raw
                if endpoint.scheme == 'https':
                    try:
                        connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=endpoint.hostname)
                    except Exception:
                        raw.close()
                        raise
        connection = FixedDestination(endpoint.hostname, endpoint.port or (443 if endpoint.scheme == 'https' else 80), timeout=timeout)
        timer = None
        try:
            connection.connect()
            secured = connection.sock
            def abort():
                try:
                    secured.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                secured.close()
            timer = threading.Timer(timeout, abort)
            timer.daemon = True
            timer.start()
            connection.request('POST', endpoint.path, body=request,
                               headers={'Content-Type': 'application/ocsp-request', 'Accept': 'application/ocsp-response'})
            response = connection.getresponse()
            if (response.status != 200 or response.getheader('Content-Type', '').split(';')[0].strip() != 'application/ocsp-response' or
                    sum(len(k) + len(v) for k, v in response.getheaders()) > 8192):
                raise Denied('http')
            data = response.read(self.limit + 1)
            if not data or len(data) > self.limit:
                raise Denied('malformed')
            return data
        except Denied:
            raise
        except (TimeoutError, socket.timeout):
            raise Denied('timeout') from None
        except ssl.SSLError:
            raise Denied('tls') from None
        except (OSError, http.client.HTTPException):
            raise Denied('unavailable') from None
        finally:
            if timer:
                timer.cancel()
            connection.close()

    def check(self, peer_der):
        try:
            result = self._check(peer_der)
        except Denied as error:
            self.record(error.reason, False)
            raise
        self.record(result, True)
        return result

    def record(self, reason, success):
        # Bounded vocabulary only; metrics cannot contain names, URLs or serials.
        reasons = {'good', 'cache', 'tls', 'revoked', 'unknown', 'signature', 'responder',
                   'identity', 'time', 'timeout', 'http', 'malformed', 'cache_expired',
                   'unavailable', 'clock', 'state', 'config', 'internal'}
        if reason not in reasons:
            reason = 'internal'
        path = self.config.get('metrics_file')
        collector = self.config.get('collector', 'unknown')
        if not path:
            return
        if collector not in ('unpoller', 'ap_counts'):
            raise Denied('config')
        # A failed metrics write is not allowed to relax a denial.
        destination = Path(path)
        text = ('# TYPE iop_unifi_ocsp_last_check_success gauge\n'
                f'iop_unifi_ocsp_last_check_success{{collector="{collector}"}} {int(success)}\n'
                '# TYPE iop_unifi_ocsp_last_check_reason gauge\n' +
                ''.join(f'iop_unifi_ocsp_last_check_reason{{collector="{collector}",reason="{label}"}} {int(reason == label)}\n' for label in sorted(reasons)) +
                f'iop_unifi_ocsp_last_check_timestamp_seconds{{collector="{collector}"}} {int(time.time())}\n')
        fd, name = tempfile.mkstemp(dir=destination.parent, prefix='.ocsp-metrics-')
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(text)
            os.chmod(name, 0o644)
            os.replace(name, destination)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _check(self, peer_der):
        leaf = x509.load_der_x509_certificate(peer_der)
        try:
            leaf.verify_directly_issued_by(self.issuer)
        except (ValueError, TypeError, InvalidSignature):
            raise Denied('identity') from None
        key = hashlib.sha256(peer_der + self.issuer.public_bytes(serialization.Encoding.DER)).hexdigest()
        now = datetime.now(timezone.utc)
        with self.locked():
            now = datetime.now(timezone.utc)
            if self.state.stat().st_size > 16 * 1024 * 1024:
                raise Denied('state')
            state = json.loads(self.state.read_text())
            if (state.get('version') != 1 or not isinstance(state.get('revoked'), list) or
                    not isinstance(state.get('cache'), dict) or len(state['cache']) > self.entries):
                raise Denied('state')
            if key in state['revoked']:
                raise Denied('revoked')
            if now.timestamp() < state.get('last_clock', 0):
                state['cache'] = {}
                self.save(state)
                raise Denied('clock')
            cached = state['cache'].get(key)
            if cached and now.timestamp() < cached['deadline']:
                try:
                    validate_response(base64.b64decode(cached['der'], validate=True), leaf, self.issuer, now, self.skew, self.max_age)
                    state['last_clock'] = now.timestamp()
                    self.save(state)
                    return 'cache'
                except Denied:
                    del state['cache'][key]
            request = ocsp.OCSPRequestBuilder().add_certificate(leaf, self.issuer, hashes.SHA256()).build().public_bytes(serialization.Encoding.DER)
            try:
                data = self.fetch(request)
                now = datetime.now(timezone.utc)
                deadline = validate_response(data, leaf, self.issuer, now, self.skew, self.max_age)
            except Denied as error:
                if error.reason == 'revoked':
                    if len(state['revoked']) >= 4096:
                        # Never evict a confirmed revocation to make room.
                        raise Denied('state') from None
                    state['revoked'].append(key)
                    state['cache'].pop(key, None)
                    self.save(state)
                if cached and error.reason in ('timeout', 'unavailable', 'http'):
                    raise Denied('cache_expired') from None
                raise
            timestamp = now.timestamp()
            state['cache'] = {k: v for k, v in state['cache'].items() if v['deadline'] > timestamp}
            if len(state['cache']) >= self.entries:
                del state['cache'][min(state['cache'], key=lambda k: state['cache'][k]['deadline'])]
            state['cache'][key] = {'deadline': min(deadline, timestamp + self.cache_ttl),
                                   'der': base64.b64encode(data).decode('ascii')}
            state['last_clock'] = timestamp
            self.save(state)
            return 'good'


def main():
    # Fixed CLI protocol: certificate only, no credentials, no caller URLs.
    try:
        config = json.loads(Path(sys.argv[1]).read_text())
        payload = sys.stdin.buffer.read(65537)
        if len(payload) > 65536:
            raise Denied('identity')
        request = json.loads(payload)
        policy = Policy(config)
        if request == {'tls_failure': True}:
            policy.record('tls', False)
            raise Denied('tls')
        result = policy.check(base64.b64decode(request['leaf'], validate=True))
        print(json.dumps({'ok': True, 'reason': result}))
    except Exception as error:
        print(json.dumps({'ok': False, 'reason': error.reason if isinstance(error, Denied) else 'internal'}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
