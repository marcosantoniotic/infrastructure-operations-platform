# Maintenance window

Performs an explicitly authorized, evidence-producing monthly maintenance
workflow. It validates capacity, creates recovery points for NetBox, Zabbix,
Grafana and Prometheus, optionally replicates them externally, applies RHEL
updates, optionally refreshes pinned container images, reboots only when
required, and verifies every local application endpoint.

The role deliberately has no timer. An operator must provide
`maintenance_authorized=true` and a non-empty change reference. This prevents
unattended package or container changes.

Sanitized evidence is stored below
`/var/log/infrastructure-platform/maintenance`. It contains timestamps,
component names and results, but no credentials, private records or backup
contents.

The maintenance metric is set to incomplete before the first recovery point and
is changed to successful only after every post-check and evidence write passes.
The corresponding alert waits two hours so a normal supervised window does not
generate a false incident.
