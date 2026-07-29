# Cockpit role

Installs the native RHEL web console, enables socket activation, and configures
its reverse-proxy trust boundary through explicit origins and forwarded headers.

Direct firewall exposure is disabled by default. When Traefik integration is
enabled, Cockpit remains a native host service and Traefik connects to its
local HTTPS endpoint through a dedicated backend transport.
