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
| Grafana runtime state | 24 hours | 4 hours | persistent volume backup | external backup pending |
| Prometheus TSDB | 24 hours | 8 hours | TSDB snapshot or volume backup | recovery procedure pending |
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

- Grafana runtime state and Prometheus TSDB do not yet have proven restore
  procedures;
- the NetBox and Zabbix application-data recovery was measured at 65 seconds,
  but a clean host reconstruction RTO still requires a timed run that includes
  image creation and the external RHEL registration dependency;
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
