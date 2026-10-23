# Optional infrastructure network for VMware validation

The validation environment can use an existing VMware Workstation LAN Segment
as its service network while retaining its host-only management backchannel.
This does not change the operational environment or configure the routers.

## Configuration

Keep the existing `controller_ip`, `platform_ip`, `standby_ip` and `recovery_ip`
fields in the ignored `.validation/vagrant.json`. They remain the host-only
addresses used by host-side administration and existing SSH tunnels.

An optional `infrastructure_network` object contains:

| Field | Meaning |
| --- | --- |
| `segment_id` | Existing local VMware LAN Segment identifier, verified against router NICs |
| `gateway` | Service network gateway or verified VRRP virtual address |
| `dns` | Internal DNS server that resolves the lab domain and external names |
| `addresses` | Mapping from Vagrant machine name to service IPv4 CIDR |

Only machines listed in `addresses` receive the additional interface. The
current staged rollout includes `automation-controller`, `srv01-validation`
and `srv02-standby`; recovery remains on its previous network.

The provider attaches `ethernet2` to the LAN Segment, using PCI slot 224 and
vmxnet3. RHEL configures `ens224` through the optional
`Configure-ValidationInfrastructure.sh` provisioner. For an access segment,
the guest sends untagged traffic; do not add guest VLAN tags merely because
the segment represents a VLAN elsewhere in the topology.

The service interface supplies the default route and internal DNS. NAT remains
connected for the Vagrant communicator but does not supply a default route or
DNS after successful service-network checks. The host-only NIC remains intact.

## Safe rollout and checks

1. Confirm addressing, router transport, DNS and address availability.
2. Shut down each target normally and create a pre-change snapshot.
3. Attach and configure one machine, preserving the host-only backchannel.
4. Validate the gateway, domain DNS, external HTTPS and actual selected route.
5. Repeat for the remaining authorized machines and update collector endpoints.
6. Run preflight against the service addresses and verify application health.
7. Record the as-built state in the private lab inventory and laboratory NetBox.

`Run-ValidationPreflight.ps1` selects configured infrastructure addresses for
platform and standby, while retaining the host-only controller access. The
observability, AdGuard metrics and Zabbix validation runners also prefer their
relevant service endpoints when this configuration is present.

Application HTTP ports remain bound according to the existing security policy.
A new service IP does not automatically publish loopback-only ports. Continue
using the configured SSH tunnels unless a separate access change is approved.

Preserving multiple management paths is transitional and does not constitute
full isolation. Recovery segmentation and router ACL changes require their own
approved implementation. No router failover is implied by ordinary health checks.

## Rollback

Input validation is available without changing networking using
`bash Configure-ValidationInfrastructure.sh --validate-only <CIDR> <GATEWAY> <DNS>`.
The provisioner is limited to the three validation guest hostnames. It backs up
NetworkManager profiles and attempts to restore only the touched connections
on failed gateway/DNS/HTTPS checks; this is not a substitute for a VM snapshot.

Use the preserved host-only connection to restore the previous NetworkManager
configuration, or restore the appropriate pre-change VM snapshot in a controlled
window. Restore the matching ignored Vagrant configuration and inventory as well,
so subsequent provisioning does not reapply the infrastructure interface.
Snapshots of application VMs contain time-sensitive data; assess changes since
the snapshot before restoring them.

Keep real addresses, LAN Segment IDs, credentials and raw evidence in private
configuration, not in public documentation or commits.
