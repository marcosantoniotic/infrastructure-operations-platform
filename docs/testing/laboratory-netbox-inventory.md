# Real laboratory inventory versus demonstration data

A corporate laboratory site should represent the whole environment, not one
application project. Use a stable site code, a descriptive corporate-lab name,
the actual virtualization cluster, and project tags for workloads such as IOP
Validation. The AD DNS domain is environment metadata, not the site identifier.

## Controlled copy from another NetBox

- Read only the approved source site and its required catalog dependencies.
- Create independent destination objects; do not preserve source numeric IDs.
- Do not copy users, credentials, tokens, configuration contexts or secrets.
- Preserve physical asset status and distinguish imported data from live checks.
- Reconcile virtual machine resources, interfaces and addresses with the actual
  hypervisor and guest configuration.
- Keep future VLANs/prefixes reserved until deployment is verified.
- Keep legacy networks visibly pending validation, rather than claiming they
  are deployed solely because the source inventory lists them as active.
- Do not delete or modify source objects as part of the copy.
- Media, custom fields and component templates require a separate reviewed
  migration when needed; they are not implied by the inventory-only copy.

Create a pre-change VM snapshot and a database backup, simulate changes in a
rolled-back transaction, then apply and verify the object relationships. Keep
raw exports and local evidence in ignored private configuration.

## Protecting real inventory from the demo provisioner

The ignored `.validation/vagrant.json` accepts an optional
`netbox_provision_demo_inventory` boolean. Set it to `false` for a laboratory
that has transitioned to real inventory. `Run-ValidationNetBox.ps1` propagates
that choice; omission preserves its existing demonstration default.

The matching private Ansible variables on the controller must also contain
`netbox_provision_demo_inventory: false`. This prevents a later application
deployment from restoring demonstration addresses over the real inventory.

Existing demonstration records can remain distinctly labeled as legacy.
Fictional addresses must not remain primary addresses of real workloads.

## Reviewed media, templates and historical notes

Before an approved complement migration, create a fresh destination snapshot
and database backup. Export only the selected models and notes from the source,
using natural keys rather than copying database primary keys. Keep the source
read-only and do not transfer user accounts or authentication data.

For media, validate content hashes and image decoding before writing. The
NetBox `MEDIA_ROOT` environment setting must match the persistent media mount
(`/opt/netbox/netbox/media` in this role). A mismatched setting can leave valid
files inaccessible to the application. Recreate only the relevant application
containers with the existing image, without pulling or rebuilding, when applying
this setting to an existing laboratory.

Import rear/power templates before dependent front/outlet templates and remap
their relationships. Preserve journal dates, original attribution as provenance,
and the distinction between historical tests and tests performed today. These
notes are not a replacement for the original object's complete change log.

Verify media over HTTP as well as on disk, compare template fields and historical
notes, and repeat the importer to check that it creates no duplicate records.
Reconcile virtual disks using the configured NetBox disk units; do not resize
guest disks or change global units solely to match a displayed number.

## Verification boundary

Successful inventory validation confirms the recorded relationships and observed
configuration. It does not validate every physical asset, prove router failover,
deploy planned VLANs, join machines to AD, or publish application ports.
Record those limitations alongside the private as-built evidence.
