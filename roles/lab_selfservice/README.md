# lab_selfservice

Administrative deployment role for Rocky Linux 9 with SELinux enforcing. Installs
an administrator-supplied private release and an independent readable `labctl`
client. No user Ansible role or private Git download is provided.

The tested delivery contract is installer contract 1, collection 0.1.0, service
0.1.0, protocol 1 and registry schema 3. The manifest contains every file digest
and the content digest of the bundled managed `vms` role. Supply the exact trusted
controller archive and SHA256; a collection version alone does not identify an
uncommitted build. Check the exact release/collection pair before rollout.

Required inputs: `lab_selfservice_release_archive` (absolute controller path),
`lab_selfservice_release_sha256`, complete `lab_selfservice_policy`, and
`lab_selfservice_image_sha256` (mapping of policy image ID to reviewed SHA256).
See `defaults/main.yml` for closed activation flags. No credentials in these vars.

Prerequisites: virtualization/network/firewall setup, existing personal accounts
with policy-matching stable UIDs, approved standalone images, existing bridges,
and a dedicated mounted filesystem at `/var/lib/libvirt/images/selfservice` with
capacity for the full virtual disk budget plus overhead. The role checks its RPM
prerequisites, executable `/usr/bin/genisoimage`, actual Linux bridges, image hashes and mount; it does not format storage or create accounts.
Use `virt_node` and `init` administratively first. Participant `init_users` must omit
`sudoers_rule` and privileged groups; `init` appends groups, so existing grants need
explicit administrator removal. Preserve administrators' access.

Keep `firewalld_unmanaged_objects_clean: false` whenever self-service policy exists.
Never remove policy to bypass the cleanup guard. Preserve management/iDRAC rules.

Fresh installation starts with `lab_selfservice_enabled: false`. Review runtime,
access, network and storage evidence before enabling all confirmation/enforcement
flags. Updates close admission and drain existing operations. The private server
and dependencies live under root-only `/opt/infralab-selfservice`; public client
and PyYAML live separately under `/opt/infralab-labctl`. The server uses its own
protocol copy. Previously obtained source copies cannot be revoked by permissions.

Disable without deleting resources: set `lab_selfservice_enabled: false`,
`lab_selfservice_install: false`, `lab_selfservice_manage_network_guard: false`.
Registry, ownership, disks and forwards are retained. Backup and restore must be
consistent; reinstalling an OS without its registry does not adopt existing VMs.
Production execution and publication require administrator authorization.
