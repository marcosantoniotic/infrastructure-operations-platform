#!/usr/bin/env python3
"""Opt-in, explicit-host Windows service policy. Never start/stop a Windows service.

Adds local active/dependent items, not another service.discovery or OS template.
Observe leaves every new trigger disabled. Enforce is a separately approved cutover.
Only recorded owned triggers and two confirmed legacy trigger IDs can change status.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request

OWNER = {"tag": "iop_windows_service_policy", "value": "v1"}
SERVICES = {"AppXSvc", "InventorySvc"}
FIELDS = {"enabled", "phase", "cutover_approved", "targets", "interval", "fault_window", "stuck_window", "stale_window"}
STATES = {"Running": 0, "Paused": 1, "Start Pending": 2, "Pause Pending": 3,
          "Continue Pending": 4, "Stop Pending": 5, "Stopped": 6, "Unknown": 7}
STATE_FIELDS = ("present", "state", "clean", "exit_bad", "not_started", "startup_drift")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def validate(config):
    require(isinstance(config, dict) and set(config) == FIELDS, "Invalid policy schema")
    require(type(config["enabled"]) is bool and type(config["cutover_approved"]) is bool, "Explicit booleans required")
    require(config["phase"] in {"observe", "enforce"}, "Invalid policy phase")
    require(isinstance(config["targets"], list), "Explicit target list required")
    for key in ("interval", "fault_window", "stuck_window", "stale_window"):
        require(type(config[key]) is int and 1 <= config[key] <= 86400, "Invalid bounded timing")
    require(config["stale_window"] >= 30, "nodata requires at least 30 seconds")
    require(min(config[k] for k in ("fault_window", "stuck_window", "stale_window")) >= config["interval"] * 2, "Timing must cover multiple observations")
    require(config["enabled"] or (not config["targets"] and not config["cutover_approved"]), "Disabled policy must not carry targets/approval")
    require(not config["enabled"] or bool(config["targets"]), "Enabled policy requires explicit targets")
    require(config["phase"] != "enforce" or config["cutover_approved"], "Cutover requires separate approval")
    ids, names, legacy = set(), set(), set()
    for target in config["targets"]:
        require(isinstance(target, dict) and set(target) == {"hostid", "host", "netbox_id", "object_type", "services"}, "Invalid target schema")
        require(isinstance(target["hostid"], str) and re.fullmatch(r"[1-9][0-9]*", target["hostid"]), "Invalid host ID")
        require(isinstance(target["netbox_id"], str) and re.fullmatch(r"[1-9][0-9]*", target["netbox_id"]), "Invalid NetBox ID")
        require(target["object_type"] in {"dcim.device", "virtualization.virtualmachine"}, "Invalid ownership type")
        require(isinstance(target["host"], str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", target["host"]), "Unsafe technical hostname")
        require(target["hostid"] not in ids and target["host"] not in names, "Duplicate target")
        ids.add(target["hostid"]); names.add(target["host"])
        require(isinstance(target["services"], list) and len(target["services"]) == 2, "Exactly two explicit services required")
        require({s.get("name") for s in target["services"] if isinstance(s, dict)} == SERVICES, "Unsupported service scope")
        for service in target["services"]:
            require(set(service) == {"name", "display_name", "legacy_triggerid"}, "Invalid service policy")
            display = service["display_name"]
            require(isinstance(display, str) and 1 <= len(display) <= 250 and not re.search(r"[\x00-\x1f\x7f]", display), "Invalid localized display name")
            tid = service["legacy_triggerid"]
            require(isinstance(tid, str) and re.fullmatch(r"[1-9][0-9]*", tid) and tid not in legacy, "Invalid/duplicate legacy trigger")
            legacy.add(tid)
    return config


def policy_fingerprint(config):
    # Phase/approval are the only allowed changes after installing a policy.
    return digest({k: v for k, v in config.items() if k not in {"phase", "cutover_approved"}})


def quote(value):
    # Zabbix quoted item parameters are NOT JSON strings. Escape quotes, not
    # backslashes: doubling a regex backslash changes the native event filter.
    require(not value.endswith('\\'), "Quoted item parameter cannot end in backslash")
    return '"' + value.replace('"', '\\"') + '"'


def normalizer(services):
    # No default-on-error preprocessing: malformed/missing data is not healthy.
    expected = {s['name']: s['display_name'] for s in services}
    return 'var expected = ' + json.dumps(expected, ensure_ascii=True) + ';\n' + r'''var rows = JSON.parse(value);
if (!Array.isArray(rows)) throw 'Expected WMI row array';
var names = ['AppXSvc','InventorySvc'], result = {}, seen = {};
var states = {'Running':0,'Paused':1,'Start Pending':2,'Pause Pending':3,'Continue Pending':4,'Stop Pending':5,'Stopped':6,'Unknown':7};
for (var i=0; i<names.length; i++) result[names[i]] = {present:0,state:255,clean:0,exit_bad:0,not_started:0,startup_drift:0};
for (var i=0; i<rows.length; i++) {
 var r=rows[i];
 if (!r || names.indexOf(r.Name)<0 || seen[r.Name]) throw 'Unexpected or duplicate service row';
 if (r.DisplayName!==expected[r.Name]) throw 'Localized display name changed; review event filter';
 seen[r.Name]=true;
 if (!Object.prototype.hasOwnProperty.call(states,r.State) || ['Auto','Manual','Disabled','Boot','System','Unknown'].indexOf(r.StartMode)<0) throw 'Unknown service configuration';
 var e=r.ExitCode, s=r.ServiceSpecificExitCode;
 if (typeof e!=='number' || typeof s!=='number' || e<0 || s<0 || e>4294967295 || s>4294967295 || e%1 || s%1) throw 'Invalid exit codes';
 if (s!==0 && e!==1066) throw 'Inconsistent service-specific exit code';
 result[r.Name]={present:1,state:states[r.State],clean:(e===0&&s===0)?1:0,exit_bad:(e!==0&&e!==1077)?1:0,not_started:e===1077?1:0,startup_drift:r.StartMode==='Auto'?0:1};
}
return JSON.stringify(result);'''


def definitions(target, config):
    host, interval = target["host"], str(config["interval"])
    tags = [OWNER]
    key = 'wmi.getall[root\\cimv2,' + quote("SELECT Name,DisplayName,State,StartMode,ExitCode,ServiceSpecificExitCode FROM Win32_Service WHERE Name='AppXSvc' OR Name='InventorySvc'") + ']'
    master = {"name": "IOP WSP: read-only Windows service snapshot", "key_": key, "type": 7, "value_type": 4,
              "delay": interval, "history": "7d", "tags": tags, "preprocessing": [{"type": 21, "params": normalizer(target['services']), "error_handler": 0, "error_handler_params": ""}]}
    items = [master]; triggers = []
    for svc in sorted(target["services"], key=lambda s: s["name"]):
        name = svc["name"]; keys = {}
        for field in STATE_FIELDS:
            k = f"iop.wsp[{name},{field}]"; keys[field] = k
            items.append({"name": f"IOP WSP {name}: {field}", "key_": k, "type": 18, "value_type": 3,
                          "master_key": key, "history": "31d", "trends": "365d", "tags": tags + [{"tag": "service", "value": name}],
                          "preprocessing": [{"type": 12, "params": '$.' + name + '.' + field, "error_handler": 0, "error_handler_params": ""}]})
        regex = '(?:' + '|'.join(re.escape(x) for x in (name, svc["display_name"])) + ')'
        ev = 'eventlog.count[System,' + quote(regex) + ',,"^Service Control Manager$","^(7000|7001|7009|7011|7022|7023|7024|7031|7034)$",1000,skip]'
        items.append({"name": f"IOP WSP {name}: new SCM failures", "key_": ev, "type": 7, "value_type": 3,
                      "delay": interval, "history": "31d", "trends": "365d", "tags": tags + [{"tag": "service", "value": name}]})
        p = lambda field: '/' + host + '/' + keys[field]
        ep = '/' + host + '/' + ev; mp = '/' + host + '/' + key
        fw, sw, stale = (str(config[k]) + 's' for k in ("fault_window", "stuck_window", "stale_window"))
        samples = math.ceil(config['stuck_window'] / config['interval']) + 1
        fresh = f"nodata({mp},{stale})=0 and nodata({ep},{stale})=0"
        good = f"({fresh}) and count({p('clean')},#3,\"eq\",1)=3 and count({p('state')},#3,\"eq\",0)=3 and sum({ep},{fw})=0"
        specs = [
            ("failure", 3, f"({fresh}) and (sum({ep},{fw})>0 or count({p('exit_bad')},#3,\"eq\",1)=3)", good),
            ("missing", 2, f"nodata({mp},{stale})=0 and count({p('present')},#3,\"eq\",0)=3", f"nodata({mp},{stale})=0 and count({p('present')},#3,\"eq\",1)=3"),
            ("startup-drift", 2, f"nodata({mp},{stale})=0 and count({p('startup_drift')},#3,\"eq\",1)=3", f"nodata({mp},{stale})=0 and count({p('startup_drift')},#3,\"eq\",0)=3"),
            ("transition-stuck", 2, f"nodata({mp},{stale})=0 and min({p('state')},#{samples})>=2 and max({p('state')},#{samples})<=5 and count({p('state')},#{samples})={samples}", f"nodata({mp},{stale})=0 and (last({p('state')})=0 or (last({p('state')})=6 and last({p('clean')})=1))"),
            ("observation-lost", 2, f"nodata({mp},{stale})=1 or nodata({ep},{stale})=1 or count({p('state')},#3,\"eq\",7)=3", f"({fresh}) and count({p('state')},#3,\"ne\",7)=3")]
        for kind, severity, expression, recovery in specs:
            triggers.append({"description": f"IOP WSP {name}: {kind}", "expression": expression, "recovery_mode": 1,
                             "recovery_expression": recovery, "priority": severity, "status": 1,
                             "manual_close": 0, "tags": tags + [{"tag": "service", "value": name}, {"tag": "scope", "value": kind}]})
    return items, triggers


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("API redirects are not allowed")


class API:
    def __init__(self, url, token_file, ca_file):
        u = urllib.parse.urlsplit(url)
        require(u.scheme == 'https' and u.hostname and not u.username and not u.password and not u.query and not u.fragment, "Exact HTTPS API URL required")
        context = ssl.create_default_context(cafile=str(ca_file))
        require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, "Verified TLS required")
        self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), NoRedirect())
        self.url = url; self.token = Path(token_file).read_text().strip(); require(bool(self.token), "Empty token")

    def call(self, method, params):
        require(method.endswith('.get') or method in {'apiinfo.version', 'item.create', 'trigger.create', 'trigger.update'}, "Forbidden API mutation")
        body = json.dumps({'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}).encode()
        headers = {'Content-Type': 'application/json-rpc'}
        if method != 'apiinfo.version': headers['Authorization'] = 'Bearer ' + self.token
        request = urllib.request.Request(self.url, data=body, headers=headers)
        with self.opener.open(request, timeout=20) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        require(len(raw) <= 4 * 1024 * 1024, "API response too large")
        data = json.loads(raw); require('error' not in data, "API operation failed: " + method)
        return data['result']


def owned(obj):
    return OWNER in [{'tag': t['tag'], 'value': t.get('value', '')} for t in obj.get('tags', [])]


def status_matches(record, tid, actual, default):
    pending = record.get('pending', {})
    if pending.get('triggerid') == tid:
        return str(actual) in {pending['old'], pending['new']}
    return str(actual) == record.get('statuses', {}).get(tid, default)


def host_snapshot(api, target):
    rows = api.call('host.get', {'output': ['hostid', 'host', 'tls_accept', 'status'], 'hostids': [target['hostid']],
                               'selectTags': 'extend', 'selectParentTemplates': ['templateid', 'name']})
    require(len(rows) == 1, "Missing or ambiguous explicit host")
    host = rows[0]
    controlled = [t['tag'] for t in host['tags'] if t['tag'] in {'source', 'netbox_id', 'netbox_object_type', 'netbox_monitoring_profile'}]
    require(len(controlled) == len(set(controlled)), "Ambiguous host ownership tags")
    tags = {t['tag']: t.get('value', '') for t in host['tags']}
    require(host['host'] == target['host'] and host['status'] == '0' and host['tls_accept'] in {'2', '4', '6'}, "Host identity or encrypted active channel mismatch")
    require(tags.get('source') == 'netbox' and tags.get('netbox_id') == target['netbox_id'] and tags.get('netbox_object_type') == target['object_type'], "NetBox ownership mismatch")
    require(tags.get('netbox_monitoring_profile') == 'windows-active', "Windows profile required")
    require('Windows by Zabbix agent active' in {t['name'] for t in host['parentTemplates']}, "Keep existing official Windows template")
    require(not any(t['tag'] == 'glpi' and t.get('value') == 'ticket' for t in host['tags']), "Ticket-eligible host requires a separately reviewed notification plan")
    todo = {t['templateid'] for t in host['parentTemplates']}; seen = set()
    while todo:
        require(len(seen | todo) <= 100, "Template inheritance is too large")
        rows = api.call('template.get', {'output': ['templateid'], 'templateids': sorted(todo), 'selectTags': 'extend', 'selectParentTemplates': ['templateid']})
        require({r['templateid'] for r in rows} == todo, "Template ancestry incomplete")
        seen |= todo; todo = set()
        for row in rows:
            require(not any(t['tag'] == 'glpi' and t.get('value') == 'ticket' for t in row['tags']), "Inherited ticket eligibility requires a notification plan")
            todo |= {p['templateid'] for p in row['parentTemplates']} - seen
    return host


def current(api, target):
    items = api.call('item.get', {'output': ['itemid', 'hostid', 'key_', 'name', 'type', 'value_type', 'master_itemid', 'status', 'state', 'lastclock', 'lastvalue', 'delay', 'history', 'trends'],
                                 'hostids': [target['hostid']], 'selectTags': 'extend', 'selectPreprocessing': 'extend'})
    triggers = api.call('trigger.get', {'output': ['triggerid', 'description', 'expression', 'recovery_expression', 'recovery_mode', 'status', 'priority', 'flags', 'manual_close'],
                                       'hostids': [target['hostid']], 'selectTags': 'extend', 'selectFunctions': 'extend', 'expandExpression': True})
    require(len({i['key_'] for i in items}) == len(items), "Duplicate item keys")
    return {i['key_']: i for i in items}, triggers


def check_legacy(target, items, triggers):
    result = {}
    for svc in target['services']:
        rows = [t for t in triggers if t['triggerid'] == svc['legacy_triggerid']]
        require(len(rows) == 1, "Missing explicit legacy trigger ID")
        t = rows[0]; name = svc['name']
        expected = f'min(/{target["host"]}/service.info["{name}",state],#3)<>0'
        require(t['expression'] == expected and str(t['flags']) == '4' and not owned(t), "Legacy trigger provenance differs")
        item = items.get(f'service.info["{name}",state]')
        require(item and {str(f['itemid']) for f in t['functions']} == {item['itemid']}, "Legacy item link mismatch")
        result[t['triggerid']] = t['status']
    return result


def check_trigger_scope(target, items, triggers, record, item_defs, trigger_defs):
    """Refuse notification/ownership drift, including objects no longer tagged.

    The ledger is authoritative for identity, never permission to adopt a row or
    recreate a lost ID. Partial *recorded* creation is resumable, lost responses
    and external deletion/retagging require inspection instead of replacement.
    """
    keys = {d['key_'] for d in item_defs}
    names = {d['description'] for d in trigger_defs}
    by_id = {t['triggerid']: t for t in triggers}
    require(len(by_id) == len(triggers), "Ambiguous trigger IDs")
    recorded_items = record.get('items', {}) if record else {}
    recorded_triggers = record.get('triggers', {}) if record else {}
    require(isinstance(recorded_items, dict) and isinstance(recorded_triggers, dict), "Invalid ownership ledger")
    require(set(recorded_items) <= keys and set(recorded_triggers) <= names, "Unexpected recorded policy scope")
    require(len(set(recorded_items.values())) == len(recorded_items) and
            len(set(recorded_triggers.values())) == len(recorded_triggers), "Ambiguous recorded IDs")

    def exact_owner(row):
        return [{'tag': t['tag'], 'value': t.get('value', '')}
                for t in row.get('tags', []) if t['tag'] == OWNER['tag']] == [OWNER]

    for key, iid in recorded_items.items():
        row = items.get(key)
        require(row and row['itemid'] == iid and exact_owner(row),
                "Recorded item missing or ownership changed; inspect before recreation")
    for name, tid in recorded_triggers.items():
        row = by_id.get(tid)
        require(row and row.get('description') == name and exact_owner(row),
                "Recorded trigger missing or ownership changed; inspect before recreation")
    for key, row in items.items():
        if owned(row):
            require(key in keys and recorded_items.get(key) == row['itemid'] and exact_owner(row),
                    "Unrecorded or ambiguous owned item; inspect partial state")
    legacy_ids = {s['legacy_triggerid'] for s in target['services']}
    for row in triggers:
        name, tid = row.get('description'), row['triggerid']
        if owned(row):
            require(name in names and recorded_triggers.get(name) == tid and exact_owner(row),
                    "Unrecorded or ambiguous owned trigger; inspect partial state")
        elif name in names:
            require(False, "Unowned policy trigger name collision; never adopt or duplicate")
        if owned(row) or tid in legacy_ids or tid in recorded_triggers.values():
            require(not any(t['tag'] == 'glpi' and t.get('value') == 'ticket' for t in row.get('tags', [])),
                    "Ticket-eligible policy/legacy trigger requires a reviewed notification plan")


def atomic_save(path, value):
    path = Path(path); path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.wsp-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, 0o600); os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def reconcile(api, config, ledger, persist=lambda value: None, apply=False, rollback=False, now=None):
    import time
    config = validate(config); now = int(time.time()) if now is None else now
    if not config['enabled']:
        require(not ledger, "Refusing to remove installed policy; explicit rollback/configuration required")
        return {'changes': 0, 'writes': 0, 'disabled': True}
    fingerprint = policy_fingerprint(config)
    require(not ledger or ledger.get('fingerprint') == fingerprint, "Installed policy scope/timing changed; reviewed migration required")
    plans = []
    # Do not create events on an environment with unknown notification routing.
    actions = api.call('action.get', {'output': ['actionid', 'status', 'eventsource'], 'selectFilter': 'extend'})
    for action in actions:
        if str(action['status']) != '0' or str(action['eventsource']) != '0': continue
        f = action['filter']; cs = f['conditions']; tag_conditions = [c for c in cs if str(c['conditiontype']) == '26']
        require(str(f['evaltype']) in {'0', '1'} and len(tag_conditions) == 1 and
                str(tag_conditions[0]['operator']) == '0' and tag_conditions[0]['value'] == 'glpi' and tag_conditions[0]['value2'] == 'ticket',
                "Unknown enabled trigger notification route; review before installation")
    # Entire target set checked before the first mutation.
    for target in config['targets']:
        host = host_snapshot(api, target); actual, triggers = current(api, target); legacy = check_legacy(target, actual, triggers)
        defs, td = definitions(target, config); expected_keys = {d['key_'] for d in defs}
        require(all(not owned(i) or k in expected_keys for k, i in actual.items()), "Unexpected installed owned item")
        record = ledger.get('hosts', {}).get(target['hostid']) if ledger else None
        check_trigger_scope(target, actual, triggers, record, defs, td)
        for definition in defs:
            old = actual.get(definition['key_'])
            if old:
                require(owned(old), "Refusing item key takeover")
                require(record and record['items'].get(definition['key_']) == old['itemid'], "Owned item ID missing/different in ledger; inspect partial state")
                for k in ['name', 'type', 'value_type', 'delay', 'history', 'trends']:
                    if k in definition: require(str(old.get(k, '')) == str(definition[k]), "Installed item drift")
                pp = [{k: p[k] for k in ['type', 'params', 'error_handler', 'error_handler_params']} for p in old.get('preprocessing', [])]
                expected_pp = definition.get('preprocessing', [])
                require(digest([{k: str(v) for k, v in p.items()} for p in pp]) == digest([{k: str(v) for k, v in p.items()} for p in expected_pp]), "Installed preprocessing drift")
                if 'master_key' in definition:
                    require(definition['master_key'] in actual and old['master_itemid'] == actual[definition['master_key']]['itemid'], "Master item ownership mismatch")
        expected_triggers = {t['description']: t for t in td}
        existing = {}
        for trig in triggers:
            if owned(trig):
                require(trig['description'] in expected_triggers and trig['description'] not in existing, "Unexpected/duplicate owned trigger")
                want = expected_triggers[trig['description']]
                require(record and record['triggers'].get(trig['description']) == trig['triggerid'], "Owned trigger ID missing/different in ledger")
                require(status_matches(record, trig['triggerid'], trig['status'], '0' if record['phase'] == 'enforce' else '1'), "Trigger status changed outside policy window")
                for k in ['expression', 'recovery_expression', 'recovery_mode', 'priority', 'manual_close']:
                    require(str(trig[k]) == str(want[k]), "Installed trigger drift")
                existing[trig['description']] = trig
        if record:
            require(record['legacy'] and set(record['legacy']) == set(legacy), "Legacy ledger scope differs")
            require(record.get('phase') != 'enforce' or config['phase'] == 'enforce' or rollback, "Use explicit rollback before observe")
            require(all(status_matches(record, tid, status, '1' if record['phase'] == 'enforce' else record['legacy'][tid]) for tid, status in legacy.items()), "Legacy trigger status changed outside policy window")
        else:
            require(set(legacy.values()) == {'0'}, "Legacy triggers must initially be enabled")
        if config['phase'] == 'enforce' and not rollback:
            require(record and record.get('phase') in {'observe', 'enforce'} and set(actual) >= expected_keys and set(existing) == set(expected_triggers), "Install observe first")
            for key in expected_keys:
                item = actual[key]
                require(item['status'] == '0' and item['state'] == '0' and now - config['stale_window'] < int(item['lastclock']) <= now + 5, "Fresh supported collection required for cutover")
            for svc in target['services']:
                name = svc['name']
                require(actual[f'iop.wsp[{name},clean]']['lastvalue'] == '1' and actual[f'iop.wsp[{name},present]']['lastvalue'] == '1', "Cutover requires clean current service observations")
            require(all(actual[d['key_']]['lastvalue'] == '0' for d in defs if d['key_'].startswith('eventlog.count[')), "Unresolved SCM failures; do not retire old rules")
            for source in (d for d in defs if d['type'] == 7):
                row = actual[source['key_']]
                history = api.call('history.get', {'output': ['clock'], 'history': source['value_type'], 'itemids': [row['itemid']],
                                                  'time_from': now-config['stale_window'], 'sortfield': 'clock', 'sortorder': 'DESC', 'limit': 3})
                clocks = {int(h['clock']) for h in history}
                require(len(clocks) == 3 and max(clocks)-min(clocks) >= 2*config['interval'] and max(clocks) <= now+5,
                        "Three distinct fresh source samples spanning two intervals required")
        if rollback: require(record, "No owned rollback ledger")
        plans.append((target, host, actual, triggers, legacy, defs, td, existing, record))
    if apply:
        # Recheck every target before even persisting the first ledger mutation.
        # This is a final read barrier, not a CAS: a single writer is still required.
        for target, before, _, _, _, defs, td, _, record in plans:
            require(host_snapshot(api, target) == before, "Concurrent host/ownership edit")
            latest_items, latest_triggers = current(api, target)
            check_trigger_scope(target, latest_items, latest_triggers, record, defs, td)
    writes = changes = 0
    if apply and not ledger:
        ledger.update({'version': 1, 'fingerprint': fingerprint, 'hosts': {}}); persist(ledger)
    for target, before, actual, triggers, legacy, defs, td, existing, record in plans:
        # Stable API objects are not a CAS; a single writer/window is mandatory.
        require(host_snapshot(api, target) == before, "Concurrent host/ownership edit")
        if apply and record is None:
            record = {'legacy': legacy, 'items': {}, 'triggers': {}, 'statuses': dict(legacy), 'phase': 'observe'}
            ledger['hosts'][target['hostid']] = record; persist(ledger)
        if apply and record.get('pending'):
            pending = record['pending']; tid = pending['triggerid']
            rows = [t for t in triggers if t['triggerid'] == tid]
            require(len(rows) == 1 and status_matches(record, tid, rows[0]['status'], pending['old']), "Ambiguous pending status")
            record.setdefault('statuses', {})[tid] = str(rows[0]['status']); record.pop('pending'); persist(ledger)
        def change_status(tid, old, new):
            record['pending'] = {'triggerid': tid, 'old': str(old), 'new': str(new)}; persist(ledger)
            api.call('trigger.update', {'triggerid': tid, 'status': int(new)})
            record.setdefault('statuses', {})[tid] = str(new); record.pop('pending'); persist(ledger)
        if not rollback:
            for definition in defs:
                if definition['key_'] in actual: continue
                changes += 1
                if apply:
                    payload = {k: v for k, v in definition.items() if k != 'master_key'}
                    if 'master_key' in definition: payload['master_itemid'] = actual[definition['master_key']]['itemid']
                    payload['hostid'] = target['hostid']
                    iid = api.call('item.create', payload)['itemids'][0]; writes += 1
                    actual[definition['key_']] = dict(payload, itemid=iid)
                    record['items'][definition['key_']] = iid; persist(ledger)
            for definition in td:
                if definition['description'] in existing: continue
                changes += 1
                if apply:
                    tid = api.call('trigger.create', definition)['triggerids'][0]; writes += 1
                    existing[definition['description']] = dict(definition, triggerid=tid)
                    record['triggers'][definition['description']] = tid; persist(ledger)
                    record.setdefault('statuses', {})[tid] = '1'; persist(ledger)
        desired = '1' if rollback or config['phase'] == 'observe' else '0'
        for name, trigger in existing.items():
            if rollback: require(record['triggers'].get(name) == trigger['triggerid'], "Rollback trigger ID not owned")
            if str(trigger['status']) != desired:
                changes += 1
                if apply:
                    change_status(trigger['triggerid'], trigger['status'], desired); writes += 1
        # Retire only after all replacement triggers exist/are ready; never remove items.
        for tid, status in legacy.items():
            desired_old = record['legacy'][tid] if rollback else ('1' if config['phase'] == 'enforce' else (record['legacy'][tid] if record else '0'))
            if status != desired_old:
                changes += 1
                if apply:
                    change_status(tid, status, desired_old); writes += 1
        if apply:
            record['phase'] = 'rolled-back' if rollback else config['phase']; persist(ledger)
    return {'changes': changes, 'writes': writes, 'phase': 'rollback' if rollback else config['phase'], 'hosts': len(plans),
            'old_items_deleted': 0, 'history_cleared': False, 'windows_service_actions': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True); parser.add_argument('--state', required=True)
    parser.add_argument('--url'); parser.add_argument('--token-file'); parser.add_argument('--ca-file')
    parser.add_argument('--apply', action='store_true'); parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(); config = validate(json.loads(Path(args.config).read_text()))
    if args.validate_only: print(json.dumps({'valid': True})); return
    state = Path(args.state); require(not state.is_symlink(), "State must not be a symlink")
    ledger = json.loads(state.read_text()) if state.exists() else {}
    if not config['enabled']:
        require(not ledger, "Installed policy cannot silently disappear")
        print(json.dumps({'disabled': True, 'changes': 0, 'writes': 0})); return
    require(args.url and args.token_file and args.ca_file, "Explicit HTTPS, token file and CA file required")
    require(not args.rollback or args.apply, "Rollback is an explicit write operation")
    if args.apply:
        state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock = state.with_suffix(state.suffix + '.lock')
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        api = API(args.url, args.token_file, args.ca_file)
        require(api.call('apiinfo.version', {}) == '7.4.13', "Revalidate against the exact supported Zabbix version")
        result = reconcile(api, config, ledger, lambda v: atomic_save(state, v), apply=args.apply, rollback=args.rollback)
        print(json.dumps(result))
    finally:
        if args.apply: os.close(fd); lock.unlink()


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        # API response payloads/URLs/tokens are deliberately not logged here.
        raise SystemExit('Windows service policy refused: ' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
