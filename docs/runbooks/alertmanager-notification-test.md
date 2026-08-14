# Alertmanager notification validation

## Purpose

Validate the complete Prometheus-to-Alertmanager email path after initial
enablement or SMTP credential rotation. The test must prove both firing and
resolved delivery without exposing credentials or leaving a synthetic incident
active.

## Authorization and prerequisites

- use an approved operational test reference;
- confirm the sender is authorized by the SMTP provider;
- store the SMTP password only in Ansible Vault;
- keep Alertmanager bound to loopback unless a separate ingress decision has
  been approved;
- confirm the recipient mailbox is monitored during the test.

When rotating an SMTP key, keep the previous key active until the new key has
passed the complete test.

## Controlled test

1. converge `playbooks/observability.yml` with
   `observability_alertmanager_enabled: true`;
2. require Alertmanager readiness and exactly one active Alertmanager in
   Prometheus `/api/v1/alertmanagers`;
3. post a uniquely named critical synthetic alert to
   `http://127.0.0.1:9093/api/v2/alerts`;
4. wait longer than the configured critical `group_wait`;
5. require `alertmanager_notifications_total{integration="email"}` to
   increment while every email failure counter remains unchanged;
6. confirm delivery in the SMTP provider or destination mailbox;
7. resolve the same alert by posting identical labels with an expired
   `endsAt`;
8. require the synthetic alert to disappear from the active Alertmanager API;
9. after the route `group_interval`, require a second successful email
   notification for the resolved state;
10. run observability convergence again and require `changed=0` and
    `failed=0`.

Use labels dedicated to the test, for example:

```text
alertname=IOPSyntheticEmailTest
severity=critical
service=alertmanager-test
```

Do not reuse a real service alert name because grouping and inhibition could
change the test result.

## Success criteria

- the firing email is accepted and delivered;
- the resolved email is accepted and delivered;
- no SMTP notification failure counter increments;
- no synthetic alert remains active;
- Prometheus still reports exactly one active Alertmanager;
- all scrape targets and containers remain healthy;
- a second Ansible convergence is idempotent.

Only after these criteria pass may the previous SMTP key be revoked. Record the
test reference and timestamps, but never the key value or Vault content.
