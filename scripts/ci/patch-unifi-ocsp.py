"""Apply exact-source guarded OCSP hooks to a disposable unifi v5.30.0 tree."""
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch(directory):
    path = directory / 'unifi.go'
    source = path.read_text()
    if 'iopOCSPGuard' in source:
        raise ValueError('Refuse double patch')
    # Source checksum is attested separately; these anchors must match exactly once.
    changes = [
        ('\tvar jar http.CookieJar', '\tif err := iopOCSPGuard(config); err != nil { return nil, err }\n\n\tvar jar http.CookieJar'),
        ('\tif config.APIKey == "" {\n\t\t// old user/pass style', '\tiopOCSPClient(client, config.URL)\n\n\tif config.APIKey == "" {\n\t\t// old user/pass style'),
        ('\tresp, err := client.Do(req)', '\tiopOCSPClient(client, u.URL)\n\tresp, err := client.Do(req)'),
    ]
    before = hashlib.sha256(source.encode()).hexdigest()
    if before != '2fe6aaddc4001494748bc1433eb6eb87d54ae6fb87bcb3a8dc0555a58e3a4852':
        raise ValueError('Upstream v5.30.0 source checksum mismatch')
    for old, new in changes:
        if source.count(old) != 1:
            raise ValueError('Unexpected upstream transport source')
        source = source.replace(old, new)
    path.write_text(source)
    (directory / 'iop_ocsp.go').write_bytes((ROOT / 'roles/observability/files/unifi-ocsp-transport.go').read_bytes())
    remote = directory / 'remote.go'
    text = remote.read_text()
    anchor = 'func (c *RemoteAPIClient) makeRequestOnce(method, path string, queryParams map[string]string) ([]byte, error) {'
    if text.count(anchor) != 1:
        raise ValueError('Unexpected upstream remote transport source')
    remote.write_text(text.replace(anchor, anchor + '\n\tif iopOCSPEnabled() { return nil, errors.New("unifi_ocsp_remote_unsupported") }'))
    print('PATCHED_SOURCE_SHA256=' + before)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    patch(parser.parse_args().directory)
