"""Offline contracts only; never starts Docker, collectors or an environment."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

def runner_code():
    path = ROOT / 'scripts/ci/test-technical-grafana.py'
    tree = ast.parse(path.read_text())
    assert isinstance(tree.body[-1], ast.Expr) and isinstance(tree.body[-1].value, ast.Call)
    assert tree.body[-1].value.func.id == 'exec'
    tree.body.pop()  # Inspect generated code, never execute the disposable runner.
    namespace = {'__file__': str(path)}
    exec(compile(tree, str(path), 'exec'), namespace)
    return namespace['code']

def visual_class():
    spec = importlib.util.spec_from_file_location('technical_grafana_contract', ROOT / 'scripts/tests/technical_grafana.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'requests': types.ModuleType('requests')}):
        spec.loader.exec_module(module)
    return module

class Contracts(unittest.TestCase):
    def test_runner_compiles_and_requires_disposable_opt_in(self):
        code = runner_code()
        compile(code, '<generated-disposable-runner>', 'exec')
        self.assertIn("os.environ.get('IOP_DISPOSABLE_PLATFORM_TEST') == '1'", code)
        self.assertIn("assert len(rows)==9", code)
        self.assertIn("not x['HostConfig']['PortBindings']", code)
        self.assertIn("assert state()==baseline", code)

    def test_uses_official_plugin_without_unsigned_exception(self):
        code = runner_code()
        self.assertIn('FROM grafana/grafana:13.1.6', code)
        self.assertIn('plugins install alexanderzobnin-zabbix-app 6.10.2', code)
        self.assertNotIn('ALLOW_LOADING_UNSIGNED', code)
        self.assertNotIn('grafana-profiles:20261107', code)

    def test_old_api_matrix_remains_independent(self):
        old = (ROOT / 'scripts/tests/functional_netbox_platform_mapping.py').read_text()
        self.assertNotIn('TechnicalGrafana', old)
        code = runner_code()
        self.assertIn("root/'scripts/tests/functional_netbox_technical_groups.py'", code)
        self.assertIn('IOP_TECHNICAL_VISUAL_TEST=', code)
        self.assertIn("'--user', '0', '-e', 'IOP_TECHNICAL_VISUAL_TEST=' + os.environ.get('IOP_TECHNICAL_VISUAL_TEST', '0'), 'netbox',", code)

    def test_dashboard_groups_are_exact_and_no_tag_dependency(self):
        dashboards = list((ROOT / 'technical-dashboards').glob('*.json'))
        self.assertEqual(len(dashboards), 4)
        uids = set()
        for path in dashboards:
            dashboard = json.loads(path.read_text(encoding='utf-8'))
            self.assertNotIn(dashboard['uid'], uids)
            uids.add(dashboard['uid'])
            variables = dashboard['templating']['list']
            self.assertEqual({v['name'] for v in variables}, {'profile', 'host'})
            self.assertEqual(next(v for v in variables if v['name']=='host')['query']['group'], '/^${profile:regex}$/')
            for panel in dashboard['panels']:
                for query in panel.get('targets', []):
                    self.assertNotIn('hostTags', query)
                    self.assertEqual(query['group']['filter'], '/^${profile:regex}$/')

    def visual_fixture(self, root):
        module = visual_class()
        instance = module.TechnicalGrafana.__new__(module.TechnicalGrafana)
        instance.root = root
        instance.owned = {'101', '102'}
        instance.original = {'101':'1', '102':'1'}
        calls = []
        instance.req = lambda *args: calls.append(('grafana', args))
        def zx(method, params):
            calls.append((method, params))
            if method == 'item.get': return [{'itemid':'201', 'hostid':'101', 'status':'0'}]
            if method == 'host.update': self.assertIn(params['hostid'], instance.owned)
            return {}
        instance.zx = zx
        return module, instance, calls

    def test_visual_restores_owned_state_on_success(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); (root/'secrets').mkdir(); (root/'visual-complete').touch()
            _, instance, calls = self.visual_fixture(root)
            instance.visual_review()
            self.assertEqual([v for m,v in calls if m=='host.update'][-2:], [{'hostid':'101','status':1}, {'hostid':'102','status':1}])
            self.assertEqual([v for m,v in calls if m=='item.update'][-1], [{'itemid':'201','status':0}])
            self.assertTrue((root/'secrets/grafana-viewer').is_file())

    def test_visual_restores_owned_state_on_timeout(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); (root/'secrets').mkdir()
            module, instance, calls=self.visual_fixture(root)
            with patch.object(module.time, 'monotonic', side_effect=[0, 601]):
                with self.assertRaisesRegex(AssertionError, 'expired'): instance.visual_review()
            self.assertEqual([v for m,v in calls if m=='host.update'][-2:], [{'hostid':'101','status':1}, {'hostid':'102','status':1}])
            self.assertEqual([v for m,v in calls if m=='item.update'][-1], [{'itemid':'201','status':0}])

if __name__ == '__main__':
    unittest.main()
