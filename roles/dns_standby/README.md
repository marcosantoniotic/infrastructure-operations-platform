# Standby DNS role

Deploys a pinned AdGuard Home container only on the `standby` inventory group.
The container uses host networking so DNS requests retain their client source
address. Firewalld permits DNS and initial administration only from explicit
networks.

Port `3000/tcp` is used only by the first-run wizard. After setup, the default
administration endpoint moves to port `80/tcp`. Both ports are restricted to
the explicit administration networks so repeated automation remains valid
across the lifecycle transition.

The container receives an explicit `SSL_CERT_FILE` path so encrypted upstream
DNS and filter downloads use the image CA trust bundle consistently.

The role intentionally stops at the initial setup endpoint. It does not change
DHCP, advertise the resolver or commit the generated `AdGuardHome.yaml`. Finish
initial setup through the restricted administration network, then model local
records and protected credentials in a later controlled change.
