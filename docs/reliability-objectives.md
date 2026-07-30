# Reliability objectives

## Purpose

This policy defines measurable recovery objectives for the Infrastructure
Operations Platform. The values are initial engineering targets for the
reference environment and must be reviewed when workload criticality, data
volume, dependencies or available recovery resources change.

RPO (Recovery Point Objective) is the maximum acceptable data loss measured in
time. RTO (Recovery Time Objective) is the target time to restore a usable
service after recovery is authorized. Neither objective is a guarantee: each
one requires periodic recovery evidence.

## Recovery objectives

| Service or data class | RPO | RTO | Recovery source | Current evidence |
|---|---:|---:|---|---|
| NetBox database and media | 24 hours | 4 hours | encrypted external PostgreSQL dump and media archive | full application recovery validated |
| Zabbix database and operational data | 24 hours | 4 hours | encrypted external MySQL dump and server data archive | full application recovery validated |
| Grafana provisioned dashboards | per merged change | 2 hours | Git and Ansible | reproducible deployment validated |
| Grafana runtime state | 24 hours | 4 hours | consistent persistent volume archive | isolated external recovery validated |
| Prometheus TSDB | 24 hours | 8 hours | consistent persistent volume archive | isolated external recovery validated |
| Traefik, Portainer and Cockpit configuration | per merged change | 2 hours | Git, Ansible and encrypted secrets | reproducible deployment validated |
| RHEL host baseline | per merged change | 4 hours | Packer, Vagrant and Ansible | clean build validated |

The NetBox and Zabbix RPO is supported by daily timers. A backup older than 26
hours or a failed execution generates a Prometheus alert. Meeting the RTO still
depends on host capacity, operator availability and access to required secrets.

## Retention policy

| Data | Local retention | Long-term target | Enforcement |
|---|---:|---:|---|
| NetBox backup sets | 14 days | 14 daily, 8 weekly and 3 monthly externally | local and encrypted external backup roles |
| Zabbix backup sets | 14 days | 14 daily, 8 weekly and 3 monthly externally | local and encrypted external backup roles |
| Observability backup sets | 14 days | 14 daily, 8 weekly and 3 monthly externally | local and encrypted external backup roles |
| Prometheus metrics | 30 days or 8 GB, whichever is reached first | none by default | Prometheus startup flags |
| Zabbix history | 30 days | not applicable | item/template retention and housekeeping review |
| Zabbix trends | 365 days | not applicable | item/template retention and housekeeping review |
| Git-managed configuration | repository history | repository lifetime | protected Git workflow |
| Operational recovery evidence | 12 months | 12 months | sanitized maintenance records |

Local retention does not provide disaster recovery when the backup and service
share the same host. NetBox and Zabbix backup sets are therefore replicated to
encrypted external storage and exercised from an isolated recovery VM.

## Validation cadence

| Control | Frequency | Required evidence |
|---|---|---|
| backup execution and age | continuous | Prometheus metrics and alerts |
| checksum and isolated database restore | monthly | sanitized command result and timestamp |
| full platform reconstruction | quarterly | elapsed time, recovered components and deviations |
| RPO/RTO review | every six months or after material change | approved update to this document |
| retention and storage capacity review | monthly | usage, projected exhaustion and cleanup status |

## Measurement rules

- RPO is measured from the timestamp of the newest successfully restored
  recovery point, not merely from the newest file.
- RTO starts when recovery is authorized and ends only after authentication,
  essential data, proxy access and monitoring have been validated.
- A test that exceeds its target creates a corrective action; the target is not
  silently changed to match the result.
- Evidence must be sanitized. Dumps, credentials, private addresses and secret
  material must never be committed to the public repository.

## Known gaps

- the clean-host drill includes a manual external RHEL registration dependency;
  unattended reconstruction requires an approved registration mechanism;
- external DNS and identity dependencies require separate continuity controls.

## Latest recovery evidence

On 2026-07-30, snapshot `08dbadb0` was restored into the isolated
`srv01-recovery` VM. Restic restored and verified 53 files and directories
(79.344 MiB), both SHA-256 manifests passed, the NetBox PostgreSQL and Zabbix
MySQL databases were replaced, persistent application data was restored, and
both applications returned HTTP 200 through Traefik HTTPS. The application-data
recovery completed in 65 seconds; the complete repeat workflow, including
preparation and repository checks, completed in 114 seconds. Snapshot contents,
credentials, OAuth data, private addressing and database records are
intentionally excluded from this public evidence.

Later on 2026-07-30, a second exercise started from a newly created,
unprovisioned `srv01-recovery` VM. The workflow installed the RHEL baseline,
Docker, Traefik, Cockpit, NetBox, Zabbix, Portainer, Prometheus, Grafana and the
external recovery tooling, then restored snapshot `ceac638d`. Restic restored
and verified 65 files and directories (106.612 MiB). NetBox and Zabbix database
structures, application data and HTTPS routes were independently validated.
The final successful automated pass took 441 seconds, including platform
reconstruction and application recovery; the data restoration phase took 88
seconds.

Measured from the original recovery authorization through the external RHEL
registration and corrective reruns, usable service was recovered in 2,128
seconds (35 minutes 28 seconds), within the four-hour RTO. The first pass
identified and corrected Windows CRLF handling in staged remote commands, the
NetBox cold-start health grace period and a transient Zabbix bootstrap API
condition. This result is therefore recorded as a successful engineering drill
with corrective deviations, not as a clean first-pass execution. Credentials,
private addressing and recovered records are excluded from this evidence.

On the same date, snapshot `ce35e743` extended the encrypted recovery point to
the Grafana runtime volume and Prometheus TSDB. Restic restored and verified 84
files and directories (288.223 MiB). All component SHA-256 manifests passed.
The isolated recovery VM restored NetBox, Zabbix, Grafana and Prometheus,
validated both relational databases, Grafana database health, Prometheus
readiness and historical TSDB loading, and completed the application recovery
in 107 seconds. The external backup timer remained disabled on the recovery
target.
