# Windows service policy (opt-in)

Dedicated, explicit-host policy for AppXSvc and InventorySvc on Zabbix 7.4.13.
Defaults to disabled; not imported by `site.yml` or the NetBox synchronizer.
No service/task start/stop, template unlink, item deletion, history clear,
firewall change, extra listener, agent script or credential change.

The dedicated playbook requires **one** host in `windows_service_policy_runner`.
That runner needs Python 3 and verified HTTPS access to the Zabbix API, a private
token file, public CA file and a persistent private ledger directory.

`observe` creates host-local active WMI/event-count items and dependent metrics,
but keeps all new triggers disabled and the two generic discovered triggers
enabled. `enforce` requires separate `cutover_approved`, the existing ledger,
fresh supported samples, clean observations and a reviewed notification route.
It enables the replacements and retires only the two confirmed old trigger IDs.
It does **not** acknowledge, close, suppress or delete existing events.

Inventory must explicitly identify host ID, technical name, NetBox object type/ID,
both internal service names, their localized display names and old trigger IDs.
Missing/wrong IDs, item-key takeover, broad notification routes, inherited ticket
eligibility, plaintext active transport and installed scope/timing drift refuse
before writes. A single runner and an operator maintenance window are required;
API read/compare/write is not an atomic distributed transaction.

The JSON schema has these defaults (targets omitted here; do not invent IDs):

```json
{
  "enabled": false,
  "phase": "observe",
  "cutover_approved": false,
  "targets": [],
  "interval": 60,
  "fault_window": 600,
  "stuck_window": 600,
  "stale_window": 300
}
```

The command is dry-run by default. `--validate-only` needs no API credentials;
`--apply` is explicit. API URL, token and CA are separate CLI file references.
No secrets belong in the policy JSON or command arguments.

For an approved rollback, keep the same enabled configuration and ledger, then
run the dedicated reconciler with `--apply --rollback`. It disables only its
recorded replacement triggers and restores the saved legacy trigger statuses.
All old/new items, IDs and history remain. Run `observe` again before any new
cutover. Do not remove the ledger or disable the role to bypass its installed
guard. Preserve the ledger in pre/post-change configuration backups.

The intent journal recovers status updates with a lost response. It is not an
object-creation transaction: a lost create response before its ID is persisted
requires manual inspection of partial state, not name-based adoption or cleanup.
Rollback still validates scope/ownership/notification routing and can refuse if
another writer changed those preconditions; do not erase the ledger to bypass it.

Trigger-level `glpi=ticket` is refused on owned and legacy triggers in dry-run,
observe, enforce and rollback, as is inherited host/template ticket eligibility.
Every recorded item/trigger must still have its exact ID and one exact ownership
tag. Missing, renamed or retagged objects are not recreated or adopted by name;
unexpected name collisions and unrecorded owned objects also require inspection.
Recorded partial creation can resume; an unrecorded/lost create response cannot.
Harmless local tags remain untouched. All targets are re-read before the first
ledger mutation; this narrows drift detection but is not a CAS or permission for
multiple writers. Do not remove ticket tags just to bypass a refused rollback.

## Detection and limits

- Native `wmi.getall`: readonly SELECT of two Win32_Service rows. Malformed,
  duplicate, unexpected or invalid numeric data fails preprocessing, never zeroes.
- A successful empty result produces a missing-service warning, not healthy.
- `eventlog.count` active checks: bounded SCM failures, including start failures,
  timeout and unexpected termination. Localized service display names are
  escaped; 7036 normal-state events are not errors. `skip` applies only to newly
  created items; initial historical evidence is a separate operator baseline.
- Exit 1077 (never started) is visible separately, not classified as a crash.
  `Stopped` plus zero exit codes alone is not an end-to-end functional test.
- A failure requires later clean running observations AND a failure-free window
  to recover. Silence or missing data alone does not clear it. An idle service
  may remain in failure until its next naturally successful run: never force a
  service start to make a test green.
- Transition duration is sampled: `ceil(window/interval)+1` consecutive samples,
  assuming the configured producer interval. Gaps are guarded by `nodata`.
  Faster synthetic/malicious producers can shorten this sampled time; this is
  not a security-grade elapsed-time measurement.
- WMI/SCM freshness is monitored independently. Component functional SLAs and
  registry success freshness are not inferred or enabled without an agreed
  cadence. No inference from an old scheduled-task result.

The acceptance harness uses a disposable Linux stack, fictitious PSK agent-data
messages and real Zabbix APIs/LLD/preprocessing/triggers. It is **not** a Windows
WMI/eventlog reader integration test. Native Windows acceptance and its limits
must be reviewed before LAB01 deployment; no LAB01/OPS access is needed for tests.

Follow-up: [native Windows reader results](../../docs/testing/windows-service-native-2026-11-05.md)
cover real Agent 2 WMI/SCM, cursor/permissions/rotation/reconnection and policy
cutover/rollback on a non-domain disposable VM. This is a separate functional
acceptance slice, not a LAB01 deployment approval or long-duration/default-window
fault test. The historical native run used the pre-guard-fix core; the later
metadata guard corrections are covered separately by offline regressions and
real isolated API tests. WMI, preprocessing and trigger definitions are unchanged.

References: [Windows item keys](https://www.zabbix.com/documentation/7.4/en/manual/config/items/itemtypes/zabbix_agent/win_keys),
[trigger update](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/trigger/update).
