# Credential governance and rotation

## Scope

The public catalog at `config/credential-catalog.json` records metadata only:
logical identifier, system, purpose, privilege, accountable role, review
frequency and rotation mode. It must never contain a credential value, token,
hash, OAuth payload, private address or personal identifier.

Actual values remain in 1Password, the operating-system keyring, Ansible Vault
or the protected runtime files described by each role.

## Rotation modes

- **periodic**: rotate before `max_age_days`, and after any suspected exposure;
- **event-driven**: review on schedule, but rotate only after exposure,
  ownership change, cryptographic requirement change or decommissioning;
- **provider-managed**: the provider refreshes short-lived material; operators
  review consent, scope, account ownership and revocation capability.

Application signing keys and the Restic repository password are event-driven
because an unplanned replacement can invalidate sessions, tokens or recovery
data. A review is still mandatory.

## Quarterly review

1. run `scripts/validate-credential-governance.ps1`;
2. compare active integrations with the catalog;
3. confirm every external credential still has the documented minimum scope;
4. review administrator accounts and remove unused principals;
5. confirm the accountable role and password-manager item owner;
6. record only the review date, logical identifier and outcome;
7. open a pull request for metadata or policy changes.

Never record the value, the last characters of a token, a password-manager item
URL containing identifiers or an OAuth configuration export.

## Managed-secret rotation

1. create a fresh recovery point;
2. generate the replacement in the password manager;
3. update the encrypted inventory with `ansible-vault edit`;
4. follow the component-specific sequence below;
5. validate authentication and application health;
6. revoke the previous credential;
7. sanitize evidence and remove temporary clipboard or local files.

| Credential class | Required sequence |
|---|---|
| Application administrator | update application, update Vault, validate new login, reject old login |
| Database account | alter database account, update Vault/runtime file, recreate consumers, validate backup |
| Redis service account | update server and both consumers in one window, then validate queues/cache |
| NetBox signing key or pepper | approved outage, impact review, replace Vault value, recreate all NetBox services |
| Restic repository password | use Restic key management, validate restore with new key, then remove old key |
| OAuth configuration | reauthorize minimum scope, validate external backup, revoke old authorization |

## Emergency revocation

Suspected disclosure overrides the periodic schedule:

1. disable or revoke the credential at the authoritative system;
2. preserve sanitized incident evidence;
3. create a replacement with minimum privilege;
4. deploy and validate it;
5. search logs and repository history without printing secret values;
6. execute the incident-response runbook.

## Automated validation

```powershell
.\scripts\validate-credential-governance.ps1
```

The check requires one catalog record for every variable in
`vault.example.yml`, rejects duplicate identifiers, validates review and
rotation limits, and rejects value-bearing property names.
