# lab_selfservice

Administrative deployment role for Rocky Linux 9 with SELinux enforcing. It installs an
administrator-supplied self-service release of release format 2 through the installer that the
release itself carries (installer contract 2), then configures the host around it. The role holds
no payload file names, versions or launchers, except the release version read of step 3:
everything installed below `/opt`, `/usr/local` and `/usr/share/polkit-1/actions` comes from the
archive.

## Inputs

- `lab_selfservice_release_archive`: absolute controller path of the reviewed archive. Only the
  content counts: the path is excluded from the deployment digest. The archive must be a release
  of 0.3 or later; an installed 0.2.0 is upgraded (step 3).
- `lab_selfservice_release_sha256`: SHA256 of that archive. It identifies the release; a version
  number does not.
- `lab_selfservice_policy`: the complete administrative policy, installed as
  `/etc/infralab-selfservice/policy.json` (0600).
- `lab_selfservice_settings`: optional service settings, default `{}`, every value an integer
  (table below). The role refuses any other key, value or type before it changes anything,
  admission included (step 1), adds `schema_version: 1` (do not set it yourself) and installs
  `/etc/infralab-selfservice/settings.json` (0600), which `lab-selfservice-admin` reads for every
  command. The three `participant_*` values also set the participant slice limits.
- `lab_selfservice_image_sha256`: policy image ID to reviewed SHA256, for every policy image.
- Flags (`defaults/main.yml`): `lab_selfservice_install` defaults to `true`; activation and
  management default to `false`: `lab_selfservice_enabled`, `lab_selfservice_manage_enforcement`,
  `lab_selfservice_manage_network_guard`, `lab_selfservice_disk_budget_confirmed`,
  `lab_selfservice_management_protection_confirmed`, `lab_selfservice_access_audit_confirmed`.
  Each must be a real boolean: the first task refuses a string, number or null before anything
  else, so pass `-e '{"lab_selfservice_enabled": false}'` or a vars file, not `-e name=false`.

| Key | Default | Range | Used from |
| --- | --- | --- | --- |
| `command_timeout_seconds` | 120 | 10-3600 | 0.2 |
| `provision_timeout_seconds` | 900 | 60-7200 | 0.2 |
| `stop_timeout_seconds` | 90 | 10-900 | 0.2 |
| `participant_cpu_quota_percent` | 100 | 10-6400 | 0.2 |
| `participant_memory_max_mib` | 512 | 128-1048576 | 0.2 |
| `participant_tasks_max` | 128 | 16-65536 | 0.2 |
| `lock_wait_seconds` | 120 | 1-3600 | 0.3 |
| `operation_retention_days` | 180 | 1-3650 | 0.3 |
| `orphan_pending_hours` | 24 | 1-8760 | 0.3 |
| `rate_limit_per_hour` | 240 | 10-100000 | 0.3 |
| `console_tail_bytes` | 65536 | 1024-1048576 | 0.6 |
| `backup_keep` | 14 | 1-365 | 0.5 |

From 0.3, `lock_wait_seconds` bounds how long a participant request waits for the registry
lock; `operation_retention_days` is the age after which failed operations that reserved nothing
and the command and crash logs are pruned; `orphan_pending_hours` the age after which a pending
operation that reserved nothing is closed; `rate_limit_per_hour` the number of new operations
one account may start per hour (a replay of an existing operation is not counted). Keys of a
later release are accepted and have no effect yet.

These variables are the only inputs. Every other variable the role uses is internal and named
`_lab_*`; extra vars outside the documented inputs are unsupported, because Ansible ranks extra
vars above every variable the role sets. A variable with the `lab_selfservice_` prefix that is
not listed here is ignored, by the deployment digest too.

Variables may be templates; the deployment digest is computed from their resolved values. A
setting's value must still render as an integer: a literal integer, a bare reference to an
integer variable such as `"{{ keep }}"` and a reference to a whole settings mapping are
accepted, while a filter expression such as `"{{ keep | int }}"` renders a string and is refused.

No input is a secret, and the role uses no `no_log`. Keep credentials out of these variables.

## What the role does, in order

1. Refuses any flag that is not a real boolean. Requires Rocky 9, enforcing SELinux and, for
   activation, the install, confirmation and enforcement flags. When installing, it then
   checks the inputs before it changes anything, admission included: absolute archive path,
   SHA256, policy users with plain lowercase usernames, integer UIDs (they become command
   arguments) and a real boolean `enabled`, settings (keys and ranges above, no
   `schema_version`).
2. Computes the deployment digest over the resolved values of the inputs above except the
   archive path. When nothing changed and self-service stays enabled, it runs
   `lab-selfservice-admin verify-install` and, when that passes, `audit --deployment`. When the
   digest differs from `/etc/infralab-selfservice/deployment-receipt`, self-service is
   disabled, the administrator command is missing, `verify-install` does not pass (any non-zero
   exit, a missing subcommand included) or the audit fails, it removes the admission marker and
   closes the Polkit gate first, so the installer never replaces files while participants are
   admitted. A failed audit (a hand-broken `policy.json` fails it too) then stops the play with
   admission closed; fix the cause and run the role again. A failed `verify-install` instead
   lets the run repair the installation.
3. Runs `lab-selfservice-admin check --wait 300` when the administrator command exists. It waits
   at most 300 s for the registry lock, so running operations finish before anything changes;
   any failure stops the play. The installed release decides the command: `--wait` arrived in
   0.3, so when `service_version` in `/opt/infralab-selfservice/release-manifest.json` is older
   (v0.2.0), or a contract 1 installation has no such manifest, the role runs plain `check`,
   which waits without a bound. A manifest that cannot be read or names no `X.Y.Z` version stops
   the play. That path is the one payload file name the role knows; the read goes once no host
   runs a release before 0.3.
4. Preflight: required RPMs, the mounted pool `/var/lib/libvirt/images/selfservice`, image
   digests, an executable `/usr/bin/genisoimage` and real Linux bridges for every policy network.
5. Install:
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
   - reloads systemd (`daemon_reload`) whenever the installer reported a change, so units of the
     release such as `infralab-selfservice.slice` are loaded before admission can reopen;
   - restores the label of the pool directory itself, never recursively: libvirt owns the labels
     of guest disks.
6. Installs `settings.json`, then the policy and the exact membership of the `lab-selfservice`
   group (existing accounts with matching UIDs only).
7. Runs `lab-selfservice-admin migrate` on every installing run. It brings the registry to the
   schema of the installed release, with a backup, and reports a change only when a step ran;
   at the current schema it changes nothing. Every other command that opens the registry
   refuses an older schema, and `migrate` needs the installed policy, so it runs here, before
   any of them. On a changed run admission is closed at that point, and a failing `migrate`
   leaves it closed. The next run then stops at its first `check`, which refuses the older
   schema: fix the cause, run `/usr/local/sbin/lab-selfservice-admin migrate` as root (it backs
   up the registry first) and run the role again.
8. Enforcement: refuses privileged accounts through
   `lab-selfservice-admin account-check USER UID` before any restriction, then writes the
   participant slice drop-ins (`CPUQuota`, `MemoryMax`, `MemorySwapMax=0`, `TasksMax`) and the
   KVM udev rule and restricts `/dev/kvm`.
9. Runs `lab-selfservice-admin check --wait 300`, then `verify-install` (the installed trees must
   equal the manifest exactly), then, for activation, `audit --deployment`.
10. Installs or verifies the dedicated `infralab-selfservice` libvirt network filter.
11. Writes the receipt, then the admission marker and the open Polkit rule, last.

## What the role does not do

- It does not copy release files, create Python environments, or install launchers, the Polkit
  action or systemd units: the bundled installer does.
- It does not create accounts, bridges or storage or format anything. It migrates the registry
  only through `lab-selfservice-admin migrate` (step 7).
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
