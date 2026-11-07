# Signed Zabbix source and profile dashboards

This opt-in role delivers an additive Grafana Compose overlay, a private HTTPS
source and four dashboards in a separate provider/folder. It never creates host
groups, changes Zabbix hosts or runs the synchronizer. Those changes require their
own reviewed dry-run. Existing Prometheus configuration and dashboard files are
not replaced.

Set `grafana_profiles_enabled` in the selected environment inventory. Supply an
immutable image containing the official signed plugin, its expected version, the
existing internal TLS network, the HTTPS API hostname, the public CA certificate
and a dedicated read-only reader credential. Keep credentials in Vault. The API
source uses validated TLS and disables direct database connections. No CA private
key, unsigned-plugin exception, extra published port or TLS bypass is supported.
Administrative API access must use HTTPS or loopback HTTP. The role does not
build/distribute the plugin image or create the Zabbix account: both are explicit
prerequisites. A host-local image ID is not a portable registry artifact.

Before each change, provide `grafana_profiles_change_approved` and
`grafana_profiles_backup_confirmed` as temporary execution variables, after
verifying a fresh backup. Explicit adoption of an already prepared source uses
`grafana_profiles_adopt_existing` for that execution only. Dashboard UID
collisions and unowned overrides fail before artifact delivery.

Run `playbooks/grafana-profiles.yml` against the intended inventory with an
explicit host limit. It recreates only Grafana with `dependencies: false` and
validates plugin signature/version and source health. The observability role
includes preparation when enabled and preserves the overlay on subsequent
deployments. Removing the opt-in after installation fails before rendering.

The four JSON candidates retain their queries and UIDs. The delivery replaces
the synthetic banner and candidate tag, and converts the Windows service state
panel to a readable paginated table of the last collected state. The original
queries and server-side history are unchanged. Label the actual environment
through `grafana_profiles_label`. Missing samples are not proof of health, and
stopped Windows services alone are not proof of failure.
The supplied selectors expect `IOP - Linux`, `IOP - Windows` and `IOP - ICMP`;
align the synchronizer's explicit profile-to-group map with those names rather
than renaming an existing profile key.

Backup the Grafana SQLite database consistently, configuration and its encrypted
secret recovery material, inventory, dashboards, sources and host membership
before applying. Record the exact host/group IDs and local memberships. A visual
rollback restores only the prior image/provisioning and the owned dashboard UIDs;
do not restore application databases or delete volumes. Preserve installed
technical-group ownership markers unless performing a separately reviewed
decommission. Keep the source/groups if merely reverting dashboard delivery.

An image and a verified local backup are prerequisites, not a complete VM restore
test. Successful source health does not prove every panel has data. Validate
queries, viewer permissions, selectors, idempotency and all four real dashboards
after the intended hosts have joined their technical groups.

Publication review added stricter source/folder/provider adoption checks and
administrative endpoint validation. These follow-up guards are tested offline;
they were not reapplied to LAB01 or OPS during PR preparation. Confirm CI and
an isolated Ansible adoption/failure matrix before considering promotion.

The role claims its already-validated namespace with a `preparing` journal
before creating the first artifact. A failed write, Compose validation or health
check leaves that claim available for a controlled retry; successful shared
validation commits `validated`. Existing version-1 markers without a phase are
accepted for compatibility. The journal never authorizes adopting a foreign
namespace on the first run: collision checks precede the claim.

Both the dedicated playbook and the observability deployment call the same
`validate.yml` after deployment. Invalid signature/version or source health
therefore fails either path before committing validation. A retry still requires
the explicit approval and backup flags. The journal is not a transaction or an
automatic rollback of application data.

`scripts/ci/test-grafana-profile-role.py` exercises the real Ansible file, guard,
URI and journal tasks on a disposable Linux runner. Only Compose deployment,
API responses, fixture UID/GID and deliberate failure injection are substituted.
It does not contact a Docker daemon, a real Zabbix API, LAB01 or OPS. Its synthetic
API checks control-flow failures, not cryptographic validation or live plugin
acceptance; the independent signed-plugin integration job retains that scope.
