# Standby DNS role

Deploys a pinned AdGuard Home container only on the `standby` inventory group.
The container uses host networking so DNS requests retain their client source
address. Firewalld permits DNS and initial administration only from explicit
networks.

The role intentionally stops at the initial setup endpoint. It does not change
DHCP, advertise the resolver or commit the generated `AdGuardHome.yaml`. Finish
initial setup through the restricted administration network, then model local
records and protected credentials in a later controlled change.
