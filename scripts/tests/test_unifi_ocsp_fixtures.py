"""Fixture integrity and real loopback TLS tests, NOT collector OCSP acceptance.

Use the isolated requirements and IOP_OCSP_FIXTURE_DIR. No operational networks.
The response signatures below are independently checked, not blindly parsed.
"""
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import threading
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import ocsp
from cryptography.x509.oid import ExtendedKeyUsageOID


FIXTURE = os.environ.get('IOP_OCSP_FIXTURE_DIR')


@unittest.skipUnless(FIXTURE, 'Requires generated disposable OCSP fixtures')
class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(FIXTURE).resolve()
        if 'ocsp-private' not in cls.root.parts or '.validation' not in cls.root.parts:
            raise ValueError('Refuse non-disposable fixtures')
        cls.manifest = json.loads((cls.root / 'manifest.json').read_text())
        assert cls.manifest['fictitious_only'] is True
        cls.now = datetime.fromisoformat(cls.manifest['created_at'])
        cls.issuer = cls.cert('issuer')
        cls.leaf = cls.cert('leaf')

    @classmethod
    def cert(cls, name):
        return x509.load_pem_x509_certificate((cls.root / (name + '.pem')).read_bytes())

    def response(self, name):
        return ocsp.load_der_ocsp_response((self.root / (name + '.der')).read_bytes())

    def verify_signature(self, response, signer):
        signer.public_key().verify(response.signature, response.tbs_response_bytes,
                                   padding.PKCS1v15(), response.signature_hash_algorithm)

    def test_manifest_hashes(self):
        for name, digest in self.manifest['files'].items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((self.root / name).read_bytes()).hexdigest(), digest)

    def test_certificate_profile_and_signatures(self):
        self.assertTrue(self.issuer.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        ku = self.issuer.extensions.get_extension_for_class(x509.KeyUsage).value
        self.assertTrue(ku.key_cert_sign and ku.crl_sign)
        self.issuer.verify_directly_issued_by(self.issuer)
        for name in ['leaf', 'rotated', 'delegate', 'unauthorized']:
            with self.subTest(name=name):
                self.cert(name).verify_directly_issued_by(self.issuer)

    def test_status_and_identity_vectors(self):
        request = ocsp.OCSPRequestBuilder().add_certificate(self.leaf, self.issuer, hashes.SHA256()).build()
        for name, status in [('good', ocsp.OCSPCertStatus.GOOD),
                             ('revoked', ocsp.OCSPCertStatus.REVOKED),
                             ('unknown', ocsp.OCSPCertStatus.UNKNOWN)]:
            response = self.response(name)
            self.verify_signature(response, self.issuer)
            self.assertEqual(response.certificate_status, status)
            self.assertEqual(response.serial_number, request.serial_number)
            self.assertEqual(response.issuer_name_hash, request.issuer_name_hash)
            self.assertEqual(response.issuer_key_hash, request.issuer_key_hash)
        self.assertNotEqual(self.response('wrong-serial').serial_number, request.serial_number)
        wrong = self.response('wrong-issuer')
        self.verify_signature(wrong, self.issuer)
        self.assertNotEqual(wrong.issuer_key_hash, request.issuer_key_hash)

    def test_delegated_and_unauthorized_responder(self):
        for name, cert_name, authorized in [('delegated-good', 'delegate', True),
                                           ('unauthorized', 'unauthorized', False)]:
            response = self.response(name)
            signer = self.cert(cert_name)
            signer.verify_directly_issued_by(self.issuer)
            self.verify_signature(response, signer)
            eku = signer.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            self.assertEqual(ExtendedKeyUsageOID.OCSP_SIGNING in eku, authorized)
            self.assertEqual(response.responder_key_hash,
                             x509.SubjectKeyIdentifier.from_public_key(signer.public_key()).digest)

    def test_invalid_signature_and_malformed_vectors(self):
        from cryptography.exceptions import InvalidSignature
        with self.assertRaises(InvalidSignature):
            self.verify_signature(self.response('bad-signature'), self.issuer)
        with self.assertRaises(ValueError):
            self.response('malformed')

    def test_negative_time_vectors_are_signed_not_mocked(self):
        for name in ['expired', 'future-this-update', 'future-produced-at', 'old-produced-at',
                     'incoherent-produced-at', 'missing-next-update', 'next-before-this']:
            with self.subTest(name=name):
                self.verify_signature(self.response(name), self.issuer)
        self.assertLess(self.response('expired').next_update_utc, self.now)
        self.assertGreater(self.response('future-this-update').this_update_utc, self.now + timedelta(minutes=5))
        self.assertGreater(self.response('future-produced-at').produced_at_utc, self.now + timedelta(minutes=5))
        self.assertLess(self.response('old-produced-at').produced_at_utc, self.now - timedelta(hours=2))
        self.assertLess(self.response('incoherent-produced-at').produced_at_utc,
                        self.response('incoherent-produced-at').this_update_utc - timedelta(minutes=5))
        self.assertIsNone(self.response('missing-next-update').next_update_utc)
        self.assertLess(self.response('next-before-this').next_update_utc,
                        self.response('next-before-this').this_update_utc)

    def tls_exchange(self, ca='issuer', hostname='controller.example.test', certificate='leaf'):
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(str(self.root / (certificate + '.pem')),
                               str(self.root / (certificate + '.key')))
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(5)
        received, failures = [], []

        def serve():
            try:
                connection, _ = listener.accept()
                connection.settimeout(5)
                with server.wrap_socket(connection, server_side=True) as secured:
                    received.append(secured.recv(4096))
                    secured.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok')
            except ssl.SSLError:
                pass  # Expected alert from bad trust or name control.
            except Exception as error:
                failures.append(error)
            finally:
                listener.close()

        worker = threading.Thread(target=serve)
        worker.start()
        client = ssl.create_default_context(cafile=str(self.root / (ca + '.pem')))
        try:
            with socket.create_connection(listener.getsockname(), timeout=5) as raw:
                with client.wrap_socket(raw, server_hostname=hostname) as secured:
                    peer = x509.load_der_x509_certificate(secured.getpeercert(binary_form=True))
                    expected = self.cert(certificate)
                    self.assertEqual(peer.fingerprint(hashes.SHA256()), expected.fingerprint(hashes.SHA256()))
                    secured.sendall(b'GET /fixture-read-only HTTP/1.1\r\nHost: controller.example.test\r\nConnection: close\r\n\r\n')
                    self.assertIn(b'200 OK', secured.recv(4096))
        finally:
            worker.join(7)
            self.assertFalse(worker.is_alive())
            self.assertFalse(failures, failures)
        return received

    def test_real_tls_accepts_fictitious_ca_and_rotated_certificate(self):
        self.assertTrue(self.tls_exchange())
        self.assertTrue(self.tls_exchange(certificate='rotated'))

    def test_real_tls_rejects_wrong_ca(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.tls_exchange(ca='wrong-issuer')

    def test_real_tls_rejects_wrong_hostname(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.tls_exchange(hostname='wrong.example.test')


if __name__ == '__main__':
    unittest.main()
