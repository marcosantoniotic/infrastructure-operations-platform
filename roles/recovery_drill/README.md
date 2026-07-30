# Isolated disaster recovery drill

Rebuilds NetBox and Zabbix data from the latest encrypted Restic recovery point
on an explicitly authorized `srv01-recovery` host. The role validates the
hostname, checks every backup manifest, restores PostgreSQL, MySQL and media,
then verifies application endpoints and essential database tables.

This role is intentionally destructive to the application data on its target.
It refuses to run unless `recovery_drill_authorized: true`, the inventory host
is `srv01-recovery`, and the operating system hostname matches the expected
recovery hostname.

Never target a production or primary validation host with this playbook.
