# AdGuard metrics collector

Collects selected read-only AdGuard Home API statistics into the Node Exporter
textfile directory. Credentials remain in root-only files and never appear in
container configuration or Prometheus scrape URLs.

The collector runs as a hardened systemd oneshot service on a timer and writes
the metric file atomically. The technical API identity still has administrative
capability because AdGuard Home does not provide read-only roles.
