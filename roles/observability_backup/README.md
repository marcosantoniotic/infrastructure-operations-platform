# Observability backup role

Creates consistent local recovery sets for the Grafana runtime state and
Prometheus TSDB. The services are stopped cleanly for the shortest practical
interval while their named volumes are archived, then immediately restarted.

Verification restores both archives into disposable Docker volumes, starts
isolated containers with the pinned application images, validates their health
APIs and removes every temporary resource.

The backup directory is suitable for subsequent encrypted Restic replication.
No credentials, recovered records or backup archives belong in Git.
