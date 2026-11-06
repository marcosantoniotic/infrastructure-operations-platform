"""Parity and signed fixture tests. Require explicit disposable fixture input."""
from datetime import datetime,timedelta
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import unittest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509 import ocsp

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'roles/observability/files'))
import unifi_ocsp as runtime
spec=importlib.util.spec_from_file_location('guard_options',ROOT/'filter_plugins/unifi_ocsp.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)

class OptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=Path(os.environ['IOP_OCSP_FIXTURE_DIR']).resolve()
        assert 'ocsp-private' in cls.fixture.parts
        cls.manifest=json.loads((cls.fixture/'manifest.json').read_text());assert cls.manifest['fictitious_only']
        cls.now=datetime.fromisoformat(cls.manifest['created_at'])
        cls.leaf=x509.load_pem_x509_certificate((cls.fixture/'leaf.pem').read_bytes())
        cls.issuer=x509.load_pem_x509_certificate((cls.fixture/'issuer.pem').read_bytes())
    def test_guard_runtime_parity(self):
        count=0
        for digest,profile,accepted,age in itertools.product(
                ['sha256','sha1','md5',None],['strict','bounded-24h','auto',None],
                [False,True,'true',1], [1,3600,3601,86400,86401,True,3600.0]):
            cfg=dict(certid_hash_algorithm=digest,freshness_profile=profile,freshness_risk_accepted=accepted,max_age_seconds=age)
            with self.subTest(cfg=cfg):
                try:expected=guard.options(cfg)
                except ValueError:
                    with self.assertRaises(runtime.Denied):runtime.policy_options(cfg)
                else:self.assertEqual(runtime.policy_options(cfg),expected)
            count+=1
        self.assertEqual(count,448)
        self.assertEqual(runtime.policy_options({}),('sha256','strict',3600))
        # Ansible 2.19 retains integer subclasses for provenance. They are
        # integers, unlike booleans/floats; guard and JSON runtime must agree.
        class TaggedInteger(int):pass
        self.assertEqual(guard.options({'max_age_seconds':TaggedInteger(3600)}),('sha256','strict',3600))
        self.assertEqual(runtime.policy_options({'max_age_seconds':TaggedInteger(3600)}),('sha256','strict',3600))
        for cfg in [dict(freshness_profile='bounded-24h',freshness_risk_accepted=True),
                    dict(freshness_profile='bounded-24h',max_age_seconds=7200)]:
            with self.assertRaises(runtime.Denied):runtime.policy_options(cfg)
    def test_signed_status_identity_signature_and_times_for_both_certids(self):
        denied=['revoked','unknown','bad-signature','unauthorized','wrong-serial','wrong-issuer',
                'expired','future-this-update','future-produced-at','incoherent-produced-at',
                'missing-next-update','next-before-this','old-produced-at','weak-signature']
        for digest in ['sha256','sha1']:
            for name in ['good','delegated-good']+denied:
                with self.subTest(digest=digest,name=name):
                    data=(self.fixture/(name+'-'+digest+'.der')).read_bytes()
                    if name in denied:
                        with self.assertRaises(runtime.Denied):runtime.validate_response(data,self.leaf,self.issuer,self.now,certid_hash_algorithm=digest)
                    else:
                        response=ocsp.load_der_ocsp_response(data)
                        self.assertEqual(response.signature_hash_algorithm.name,'sha256')
                        self.assertGreater(runtime.validate_response(data,self.leaf,self.issuer,self.now,certid_hash_algorithm=digest),self.now.timestamp())
    def test_age_boundary_and_non_negotiable_next_update(self):
        for digest in ['sha256','sha1']:
            data=(self.fixture/('age-2h-'+digest+'.der')).read_bytes()
            with self.assertRaises(runtime.Denied):runtime.validate_response(data,self.leaf,self.issuer,self.now,certid_hash_algorithm=digest)
            runtime.validate_response(data,self.leaf,self.issuer,self.now,max_age=7200,certid_hash_algorithm=digest)
            with self.assertRaises(runtime.Denied):runtime.validate_response(data,self.leaf,self.issuer,self.now+timedelta(seconds=1),max_age=7200,certid_hash_algorithm=digest)
            response=ocsp.load_der_ocsp_response(data)
            with self.assertRaises(runtime.Denied):runtime.validate_response(data,self.leaf,self.issuer,response.next_update_utc,max_age=86400,certid_hash_algorithm=digest)
            old=(self.fixture/('age-25h-'+digest+'.der')).read_bytes()
            with self.assertRaises(runtime.Denied):runtime.validate_response(old,self.leaf,self.issuer,self.now,max_age=86400,certid_hash_algorithm=digest)
    def test_wrong_certid_hash_rejected_even_with_correct_signature(self):
        for requested,answered in [('sha256','sha1'),('sha1','sha256')]:
            data=(self.fixture/('good-'+answered+'.der')).read_bytes()
            with self.assertRaises(runtime.Denied) as caught:runtime.validate_response(data,self.leaf,self.issuer,self.now,certid_hash_algorithm=requested)
            self.assertEqual(caught.exception.reason,'identity')

if __name__=='__main__':unittest.main()
