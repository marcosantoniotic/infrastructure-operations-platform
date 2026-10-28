"""Create fictitious, local-only OCSP test PKI. Never install this CA in trust stores."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from asn1crypto import ocsp as asn1ocsp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509 import ocsp
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[2]


def generate(destination):
    destination = destination.resolve()
    private = (ROOT / '.validation' / 'ocsp-private').resolve()
    if destination.parent != private or destination.exists():
        raise ValueError('Use a fresh direct child of .validation/ocsp-private only')
    destination.mkdir(mode=0o700)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    def certificate(name, issuer=None, ca=False, eku=None):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        parent, parent_key = issuer if issuer else (None, key)
        builder = (x509.CertificateBuilder().subject_name(subject)
                   .issuer_name(parent.subject if parent else subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=7))
                   .add_extension(x509.BasicConstraints(ca=ca, path_length=0 if ca else None), True)
                   .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
                   .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
                       (parent.public_key() if parent else key.public_key())), False)
                   .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                       key_encipherment=not ca, data_encipherment=False, key_agreement=False,
                       key_cert_sign=ca, crl_sign=ca, encipher_only=False, decipher_only=False), True))
        if eku:
            builder = builder.add_extension(x509.ExtendedKeyUsage(eku), False)
        if name == 'controller.example.test':
            builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), False)
        cert = builder.sign(parent_key, hashes.SHA256())
        return cert, key

    issuer = certificate('IOP DISPOSABLE OCSP TEST CA', ca=True)
    wrong_issuer = certificate('IOP OTHER DISPOSABLE TEST CA', ca=True)
    leaf = certificate('controller.example.test', issuer, eku=[ExtendedKeyUsageOID.SERVER_AUTH])
    rotated = certificate('controller.example.test', issuer, eku=[ExtendedKeyUsageOID.SERVER_AUTH])
    delegate = certificate('IOP TEST AUTHORIZED RESPONDER', issuer, eku=[ExtendedKeyUsageOID.OCSP_SIGNING])
    unauthorized = certificate('IOP TEST UNAUTHORIZED RESPONDER', issuer, eku=[ExtendedKeyUsageOID.CLIENT_AUTH])
    for name, (cert, key) in {'issuer': issuer, 'wrong-issuer': wrong_issuer,
                              'leaf': leaf, 'rotated': rotated, 'delegate': delegate,
                              'unauthorized': unauthorized}.items():
        (destination / (name + '.pem')).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        path = destination / (name + '.key')
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                          serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        path.chmod(0o600)

    def response(name, status=ocsp.OCSPCertStatus.GOOD, cert=None, parent=None,
                 signer=None, this=None, next_time=None, omit_next=False, produced=None):
        cert, parent, signer = cert or leaf[0], parent or issuer[0], signer or issuer
        builder = (ocsp.OCSPResponseBuilder().add_response(cert, parent, hashes.SHA256(), status,
            this or now - timedelta(minutes=1), None if omit_next else next_time or now + timedelta(minutes=30),
            now - timedelta(minutes=2) if status == ocsp.OCSPCertStatus.REVOKED else None,
            x509.ReasonFlags.key_compromise if status == ocsp.OCSPCertStatus.REVOKED else None)
            .responder_id(ocsp.OCSPResponderEncoding.HASH, signer[0]))
        if signer != issuer:
            builder = builder.certificates([signer[0]])
        der = builder.sign(signer[1], hashes.SHA256()).public_bytes(serialization.Encoding.DER)
        if produced:
            # Fixture-only mutation, then cryptographically re-sign. Never mock
            # a parsed timestamp: negative controls must have valid signatures.
            outer = asn1ocsp.OCSPResponse.load(der)
            basic = outer['response_bytes']['response'].parsed
            basic['tbs_response_data']['produced_at'] = produced
            basic['signature'] = signer[1].sign(basic['tbs_response_data'].dump(),
                                               padding.PKCS1v15(), hashes.SHA256())
            outer['response_bytes']['response'] = basic
            der = outer.dump()
        (destination / (name + '.der')).write_bytes(der)
        return der

    good = response('good')
    response('delegated-good', signer=delegate)
    response('revoked', ocsp.OCSPCertStatus.REVOKED)
    response('unknown', ocsp.OCSPCertStatus.UNKNOWN)
    response('unauthorized', signer=unauthorized)
    response('wrong-serial', cert=rotated[0])
    response('rotated-good', cert=rotated[0])
    response('wrong-issuer', parent=wrong_issuer[0])
    response('expired', this=now - timedelta(hours=2), next_time=now - timedelta(minutes=1))
    response('future-this-update', this=now + timedelta(minutes=10), next_time=now + timedelta(minutes=30))
    response('future-produced-at', produced=now + timedelta(minutes=10))
    response('old-produced-at', produced=now - timedelta(hours=3))
    response('incoherent-produced-at', produced=now - timedelta(minutes=10))
    response('missing-next-update', omit_next=True)
    response('next-before-this', next_time=now - timedelta(minutes=2))
    (destination / 'bad-signature.der').write_bytes(good[:-1] + bytes([good[-1] ^ 1]))
    (destination / 'malformed.der').write_bytes(b'not an OCSP response')
    manifest = {'fictitious_only': True, 'created_at': now.isoformat(),
                'hostname': 'controller.example.test', 'files': {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.iterdir())}}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'destination': str(destination), 'fictitious_only': True,
                      'certificates': 6, 'responses': 17}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, required=True)
    generate(parser.parse_args().destination)
