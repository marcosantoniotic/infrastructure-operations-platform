#!/usr/bin/env bash
# Opt-in validation guests only. Never configure the host-only management NIC.
set -euo pipefail
validate_only=false
if [[ "${1:-}" == --validate-only ]]; then validate_only=true; shift; fi
address=${1:?IPv4 CIDR required}
gateway=${2:?Gateway required}
dns=${3:?DNS server required}
python3 - "$address" "$gateway" "$dns" <<'PY'
import ipaddress
import sys
interface = ipaddress.IPv4Interface(sys.argv[1])
gateway, dns = map(ipaddress.IPv4Address, sys.argv[2:])
if not 1 <= interface.network.prefixlen <= 30:
    raise SystemExit('Service network needs a usable IPv4 subnet')
if (gateway not in interface.network or gateway == interface.ip
        or interface.ip in (interface.network.network_address, interface.network.broadcast_address)
        or gateway in (interface.network.network_address, interface.network.broadcast_address)
        or any(a.is_unspecified or a.is_loopback or a.is_multicast for a in (interface.ip, gateway, dns))):
    raise SystemExit('Invalid service address, gateway or DNS')
PY
if "$validate_only"; then echo 'VALIDATION_NETWORK_INPUTS_OK'; exit 0; fi
test "$(id -u)" = 0
case "$(hostname -s)" in
  automation-controller|srv01-validation|srv02-standby) ;;
  *) echo 'This provisioner is limited to validation guests.' >&2; exit 1 ;;
esac
test -e /sys/class/net/ens224
test -e /sys/class/net/ens160
backup=/var/backups/validation-infrastructure-network
install -d -m 0700 "$backup"
if [ ! -d "$backup/system-connections" ]; then
  cp -a /etc/NetworkManager/system-connections "$backup/"
fi
service_uuid=$(nmcli -g GENERAL.CON-UUID device show ens224)
nat_uuid=$(nmcli -g GENERAL.CON-UUID device show ens160)
[[ -n "$nat_uuid" && "$nat_uuid" != -- ]]
fields=(ipv4.method ipv4.addresses ipv4.gateway ipv4.dns ipv4.ignore-auto-dns
        ipv4.never-default ipv4.route-metric ipv4.dns-priority ipv4.dad-timeout
        ipv6.method connection.zone connection.autoconnect)
old=(); created=false
if [[ -n "$service_uuid" && "$service_uuid" != -- ]]; then
  for field in "${fields[@]}"; do old+=("$(nmcli -g "$field" connection show uuid "$service_uuid")"); done
else
  service_uuid=''
fi
nat_default=$(nmcli -g ipv4.never-default connection show uuid "$nat_uuid")
nat_dns=$(nmcli -g ipv4.ignore-auto-dns connection show uuid "$nat_uuid")
rollback() {
  status=$?
  trap - EXIT
  if (( status != 0 )); then
    echo 'Validation network setup failed; restoring only the touched connections.' >&2
    nmcli connection modify uuid "$nat_uuid" ipv4.never-default "$nat_default" ipv4.ignore-auto-dns "$nat_dns" || true
    nmcli device reapply ens160 || true
    if "$created"; then
      nmcli connection delete uuid "$service_uuid" || true
    elif [[ -n "$service_uuid" ]]; then
      args=()
      for i in "${!fields[@]}"; do args+=("${fields[$i]}" "${old[$i]}"); done
      nmcli connection modify uuid "$service_uuid" "${args[@]}" || true
      nmcli connection up uuid "$service_uuid" || true
    fi
  fi
  exit "$status"
}
trap rollback EXIT
ip link set ens224 up
if ! ip -4 address show dev ens224 | grep -Fq "$address"; then
  arping -D -I ens224 -c 3 -w 5 "${address%/*}"
fi
if [[ -z "$service_uuid" ]]; then
  if nmcli connection show iop-infrastructure >/dev/null 2>&1; then
    echo 'Inactive service profile already exists; review it before provisioning.' >&2
    exit 1
  fi
  nmcli connection add type ethernet ifname ens224 con-name iop-infrastructure
  service_uuid=$(nmcli -g connection.uuid connection show iop-infrastructure)
  created=true
fi
nmcli connection modify uuid "$service_uuid" \
  ipv4.method manual ipv4.addresses "$address" ipv4.gateway "$gateway" \
  ipv4.dns "$dns" ipv4.ignore-auto-dns yes ipv4.never-default no \
  ipv4.route-metric 50 ipv4.dns-priority -50 ipv4.dad-timeout 3000 \
  ipv6.method disabled connection.zone public connection.autoconnect yes
nmcli connection up uuid "$service_uuid"
ping -I ens224 -c 2 -W 3 "$gateway"
ping -I ens224 -c 2 -W 3 "$dns"
getent ahostsv4 example.com >/dev/null
curl --interface ens224 -I --connect-timeout 10 --max-time 20 -fsS https://example.com >/dev/null
nmcli connection modify uuid "$nat_uuid" ipv4.never-default yes ipv4.ignore-auto-dns yes
nmcli device reapply ens160
ip route get "$gateway"
trap - EXIT
