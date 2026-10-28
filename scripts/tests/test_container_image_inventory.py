"""Exercise the real PowerShell scanner/validator against disposable YAML."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ImageInventoryTests(unittest.TestCase):
    def execute(self, source, success=True):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            defaults = root / 'roles/test/defaults'
            defaults.mkdir(parents=True)
            (defaults / 'main.yml').write_text(source)
            results = []
            for name in ['get-container-images.ps1', 'validate-container-images.ps1']:
                target = root / 'scripts' / name
                shutil.copyfile(ROOT / 'scripts' / name, target)
                result = subprocess.run(['pwsh', '-NoProfile', '-File', str(target)], capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
                results.append(result.stdout)
            return results

    def test_empty_optional_does_not_consume_next_key_and_block_scalar_works(self):
        output = self.execute('optional_image: ""\nprevious_image: \'\'\nplain_image:\nother_setting: value\nrequired_image: >-\n  example.invalid/app:1.2\n')
        self.assertEqual(json.loads(output[0]), ['example.invalid/app:1.2'])

    def test_malformed_block_cannot_consume_next_key(self):
        self.execute('required_image: >-\nother_image: example.invalid/app:1.2\n', success=False)

    def test_nonempty_unpinned_image_remains_rejected(self):
        self.execute('required_image: invalid-reference\n', success=False)


if __name__ == '__main__':
    unittest.main()
