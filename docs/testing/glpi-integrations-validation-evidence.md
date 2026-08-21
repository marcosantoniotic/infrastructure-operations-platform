# GLPI integrations laboratory validation evidence

## Scope

This record certifies Gate G5 in the isolated project laboratory. It contains
no credentials, private addresses or operational data.

Validation date: 2026-08-17.

Validated path:

```text
NetBox canonical device reference -> Zabbix event tags -> internal bridge -> GLPI ticket
```

## Result

| Control | Result |
|---|---|
| Dedicated GLPI technical user and OAuth client | Passed |
| Restricted Zabbix API token self-test | Passed |
| Exactly one managed Zabbix action | Passed and enabled |
| Exactly one managed webhook media type | Passed and enabled |
| Webhook without the shared secret | Rejected with HTTP 401 |
| Synthetic problem delivery | One GLPI ticket created |
| Repeated problem delivery | Suppressed as duplicate |
| Synthetic recovery delivery | One timeline followup created |
| Repeated recovery delivery | Suppressed as duplicate |
| Final GLPI ticket status | `5` (`Solved`) |
| Canonical NetBox reference | `type=device`, numeric ID and URL present |
| Persistent correlation state | One row in state `recovered` |
| Bridge health endpoint | `{"status":"ok"}` |
| Final Ansible convergence | `changed=0`, `unreachable=0`, `failed=0` |

## Reproducible acceptance

The acceptance runner posts the same problem twice and the same recovery twice.
It fails unless all four responses reference one ticket and only the second
delivery of each state is classified as duplicate:

```bash
sudo docker compose \
  --project-directory /opt/zabbix-glpi-bridge \
  run --rm zabbix-glpi-bridge \
  python /usr/local/libexec/zabbix-glpi-bridge.py validate-event-flow
```

Sanitized result:

```text
Event flow passed event=<synthetic-event-id> ticket=<synthetic-ticket-id>
ticket=<synthetic-ticket-id> status=5 netbox_ref=yes
followups=1 recovery_ref=yes
correlation=<synthetic-event-id> ticket=<synthetic-ticket-id> state=recovered
actions=1 action_enabled=True media_types=1 media_enabled=True
unauthorized_status=401
```

The test creates a synthetic ticket and therefore must be run only in an
authorized validation window. No backup, restore or production migration is
performed by this validation.

## Corrections incorporated during certification

1. GLPI High-Level API access is enabled idempotently before OAuth validation.
2. OAuth requests select the approved GLPI profile and entity explicitly.
3. Zabbix API version discovery is performed without an authorization header,
   as required by the public `apiinfo.version` method.
4. The GLPI recovery followup uses the supported nested route
   `/Assistance/Ticket/{id}/Timeline/Followup`.
5. The bridge persists the Zabbix problem `eventid` under an immediate SQLite
   transaction, preventing duplicate tickets and duplicate recovery followups.

## Gate statement

This evidence approves Gate G5 for the generic project workflow. It proves the
event contract and canonical reference with synthetic data; it does not contain
or approve any environment-specific legacy migration.
