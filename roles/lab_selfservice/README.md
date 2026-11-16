# lab_selfservice

Administrative deployment role for Rocky Linux 9 with SELinux enforcing. It installs an
administrator-supplied self-service release of release format 2 through the installer that the
release itself carries (installer contract 2), then configures the host around it. The role holds
no payload file names, versions or launchers: everything installed below `/opt`, `/usr/local` and
`/usr/share/polkit-1/actions` comes from the archive.

## Inputs

- `lab_selfservice_release_archive`: absolute controller path of the reviewed archive. Only the
  content counts: the path is excluded from the deployment digest.
- `lab_selfservice_release_sha256`: SHA256 of that archive. It identifies the release; a version
  number does not.
- `lab_selfservice_policy`: the complete administrative policy, installed as
  `/etc/infralab-selfservice/policy.json` (0600).
- `lab_selfservice_settings`: optional service settings, default `{}`. Allowed keys and ranges
  (all integers): `command_timeout_seconds` 10-3600, `provision_timeout_seconds` 60-7200,
  `stop_timeout_seconds` 10-900, `participant_cpu_quota_percent` 10-6400,
  `participant_memory_max_mib` 128-1048576, `participant_tasks_max` 16-65536,
  `lock_wait_seconds` 1-3600, `operation_retention_days` 1-3650, `orphan_pending_hours` 1-8760,
  `rate_limit_per_hour` 10-100000, `console_tail_bytes` 1024-1048576, `backup_keep` 1-365. The
  role refuses any other key, value or type before it changes anything, admission included
  (step 1), adds `schema_version: 1` (do not set it yourself) and installs
  `/etc/infralab-selfservice/settings.json` (0600), which `lab-selfservice-admin` reads for every
  command. The three `participant_*` values (defaults 100, 512, 128) also set the participant
  slice limits.
- `lab_selfservice_image_sha256`: policy image ID to reviewed SHA256, for every policy image.
- Flags (`defaults/main.yml`): `lab_selfservice_install` defaults to `true`; activation and
  management default to `false`: `lab_selfservice_enabled`, `lab_selfservice_manage_enforcement`,
  `lab_selfservice_manage_network_guard`, `lab_selfservice_disk_budget_confirmed`,
  `lab_selfservice_management_protection_confirmed`, `lab_selfservice_access_audit_confirmed`.

Variables may be templates; the deployment digest is computed from their resolved values. A
setting's value must still render as an integer: a literal integer, a bare reference to an
integer variable such as `"{{ keep }}"` and a reference to a whole settings mapping are
accepted, while a filter expression such as `"{{ keep | int }}"` renders a string and is refused.

No input is a secret, and the role uses no `no_log`. Keep credentials out of these variables.

## What the role does, in order

1. Requires Rocky 9, enforcing SELinux and, for activation, the install, confirmation and
   enforcement flags. When installing, it then checks the inputs before it changes anything,
   admission included: absolute archive path, SHA256, policy users with plain lowercase
   usernames and integer UIDs (they become command arguments), settings (keys and ranges
   above, no `schema_version`).
2. Computes the deployment digest over the resolved values of every `lab_selfservice_*`
   variable except the archive path. When nothing changed and self-service stays enabled, it
   runs `lab-selfservice-admin verify-install`. When the digest differs from
   `/etc/infralab-selfservice/deployment-receipt`, self-service is disabled, the administrator
   command is missing or `verify-install` does not pass (any non-zero exit, a missing
   subcommand included), it removes the admission marker and closes the Polkit gate first, so
   the installer never replaces files while participants are admitted.
3. Runs `lab-selfservice-admin check` when the administrator command exists. It waits for the
   registry lock, so running operations finish before anything changes.
4. When admission stays open, runs `lab-selfservice-admin audit --deployment` first.
5. Preflight: required RPMs, the mounted pool `/var/lib/libvirt/images/selfservice`, image
   digests, an executable `/usr/bin/genisoimage` and real Linux bridges for every policy network.
6. Install:
   - creates `/var/lib/infralab-selfservice` (0700), `/etc/infralab-selfservice` (0755), the pool
     directory (0711) and `/var/lib/infralab-selfservice/releases` (0700); a symbolic link or a
     file in place of any of them stops the play;
   - checks the release record `releases/installed` before anything is copied;
   - copies `files/verify-release.py` to `/var/lib/infralab-selfservice/verify-release.py` and the
     archive to `releases/<sha256>.tar.gz` (both 0600), and verifies the SHA256, the format and
     every member before extraction;
   - extracts into a fresh `releases/<sha256>/`; an earlier extraction is always discarded;
   - runs `/usr/bin/python3 -IB releases/<sha256>/installer/install.py apply --staging
     releases/<sha256>` as root. The installer takes the registry lock (at most 120 s), swaps the
     trees, writes the single files, removes what the release no longer contains, restores the
     SELinux labels of what it installed and proves the result against the manifest. Its
     `changed` decides whether the task changed. Its file lists, thousands of lines on the first
     upgrade, are not printed at the default verbosity;
   - records the installed and the previously installed SHA256 in `releases/installed` and
     removes every other entry directly below `releases/`; links are removed, never followed;
   - restores the label of the pool directory itself, never recursively: libvirt owns the labels
     of guest disks.
7. Installs `settings.json`, then the policy and the exact membership of the `lab-selfservice`
   group (existing accounts with matching UIDs only).
8. Enforcement: refuses privileged accounts through
   `lab-selfservice-admin account-check USER UID` before any restriction, then writes the
   participant slice drop-ins (`CPUQuota`, `MemoryMax`, `MemorySwapMax=0`, `TasksMax`) and the
   KVM udev rule and restricts `/dev/kvm`.
9. Runs `lab-selfservice-admin check`, then `verify-install` (the installed trees must equal the
   manifest exactly), then, for activation, `audit --deployment`.
10. Installs or verifies the dedicated `infralab-selfservice` libvirt network filter.
11. Writes the receipt, then the admission marker and the open Polkit rule, last.

## What the role does not do

- It does not copy release files, create Python environments, or install launchers, the Polkit
  action or systemd units: the bundled installer does.
- It does not create accounts, bridges or storage, format anything, or migrate the registry.
- It does not change sudoers, the firewalld configuration or any libvirt object other than the
  dedicated network filter.

## Upgrade from installer contract 1

The first run with a format 2 release changes the digest, so admission closes before the
installer runs. The installer replaces both trees: the private and public virtual environments,
the bundled collection, the runner and the other contract 1 files disappear, and so do
`ansible-tmp`, `ansible-remote` and an empty `jobs` below `/var/lib/infralab-selfservice`. A
`jobs` directory that is not empty stops the installer before any change; finish those jobs first.
After the first successful run, retention removes the contract 1 `releases/release.tar.gz` and its
extracted directory. A `wheels` directory left in `/var/lib/infralab-selfservice` by an offline
kit is not touched; remove it administratively when nothing needs it.

There is no downgrade to a release of format 1 through this role: the verifier refuses format 1
archives. Roll back with a snapshot, or with the previous format 2 archive and its SHA256 (the
previously installed one stays in `releases/`).

## Administrative warnings

Prepare virtualization, networking, firewall, the participants' personal accounts with stable
UIDs matching the policy, approved standalone images, bridges and a dedicated mounted filesystem
at `/var/lib/libvirt/images/selfservice` with capacity for the full virtual disk budget plus
overhead. Use `virt_node` and `init` administratively first. Participant `init_users` must omit
`sudoers_rule` and privileged groups; `init` appends groups, so existing grants need explicit
administrator removal. Preserve administrators' access.

Keep `firewalld_unmanaged_objects_clean: false` whenever self-service policy exists. Never remove
policy to bypass the cleanup guard. Preserve management and iDRAC rules.

A fresh installation starts with `lab_selfservice_enabled: false`. Review runtime, access, network
and storage evidence before enabling all confirmation and enforcement flags. Updates close
admission and drain running operations first. The private server lives in root-only
`/opt/infralab-selfservice`; the public client lives separately in `/opt/infralab-labctl` and runs
on the distribution Python. Previously obtained source copies cannot be revoked by permissions.

Disable without deleting resources: set `lab_selfservice_enabled: false`,
`lab_selfservice_install: false` and `lab_selfservice_manage_network_guard: false`. Registry,
ownership, disks and forwards are retained. Backup and restore must be consistent; reinstalling an
OS without its registry does not adopt existing VMs. Production execution and publication require
administrator authorization.
