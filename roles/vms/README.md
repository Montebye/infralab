vms
===

Administrative creation and deletion of libvirt virtual machines on the lab hypervisor.
The role is for administrators only. Self-service VMs are provisioned by the
self-service executor itself; this role never handles them and refuses their name space.

Requirements
------------

- EL 9 hypervisor with libvirt, `virsh`, `virt-install` and `qemu-img` in `/usr/bin`.
- A cloud base image at `vms_image` (checked only when a VM has to be created).
- The directory given as `disk.path` of every VM to create must exist.

Role Variables
--------------

Defaults (`defaults/main.yml`):

| Variable | Default | Meaning |
| --- | --- | --- |
| `vms_libvirt_uri` | `qemu:///system` | libvirt connection used for every `virsh` and `virt-install` call |
| `vms_reserved_name_pattern` | `^ss-[0-9]+-` | VM names reserved for self-service |
| `vms_reserved_disk_path` | `/var/lib/libvirt/images/selfservice` | disk directory reserved for self-service |

Required from the inventory or the play:

- `vms`: list of VMs. Every item has `name` and `state` (`present` or `absent`). A VM to
  create also needs `memory` (MiB), `vcpu`, `os-variant`, `networks` (each with `bridge`,
  `ip`, `interface` and optional `gateway`) and `disk` (`size` in GiB, `path` directory).
- `vms_image`: backing qcow2 image for new disks.
- `vms_users`: cloud-init users (`name`, optional `sudo`, `password_in_hash`, `authorized_keys`).
- `vms_ns_servers`, `vms_domain`: resolvers and search domain written to the network config.

Example:

```yml
vms_users:
  - name: myadmin
    sudo: ALL=(ALL) ALL
    password_in_hash: <some password hash>
    authorized_keys: "{{ vms_authorized_keys }}"

vms_ns_servers:
  - 8.8.8.8
  - 1.1.1.1

vms_image: /var/lib/libvirt/images/rocky-9_8_generic_cloud.qcow2
vms_domain: example.com

vms_authorized_keys:
  - <some public key>

vms:
  - name: rocky9
    state: absent
    memory: 2048
    vcpu: 2
    os-variant: rocky9
    networks:
      - bridge: br-mgmt
        ip: 10.10.0.10/24
        interface: eth0
        gateway: 10.10.0.1
      - bridge: br-int
        ip: 10.10.2.10/24
        interface: eth1
    disk:
      size: 12
      path: "/var/lib/libvirt/images"
  - name: test02.{{ vms_domain }}
    state: absent
    memory: 2048
    vcpu: 2
    os-variant: rocky9
    networks:
      - bridge: br-mgmt
        ip: 10.10.0.11/24
        interface: eth0
        gateway: 10.10.0.1
      - bridge: br-internal
        ip: 10.10.2.11/24
        interface: eth1
    disk:
      size: 12
      path: "/var/lib/libvirt/images"
```

Reserved name space
-------------------

Before any `virsh`, `qemu-img` or `virt-install` call the role asserts, for every item of
`vms`, that the name does not match `vms_reserved_name_pattern` and that neither `disk.path`
nor any of the four files the role writes, `<disk.path>/<name>.qcow2`,
`<disk.path>/<name>-user-data`, `<disk.path>/<name>-meta-data` and
`<disk.path>/<name>-network-config` (each normalised), is `vms_reserved_disk_path` or lies
below it. A violation fails the play and
names the VM; nothing on the hypervisor is changed. Self-service VMs are handled only by
the self-service tools.

Behaviour
---------

- `state: present` creates a VM only when no domain of that name exists; an existing domain
  is left unchanged. The disk is a qcow2 overlay on `vms_image`; cloud-init files are
  written next to it in `disk.path`.
- `state: absent` stops a running domain and then runs
  `virsh undefine --remove-all-storage`: **deletion removes all storage volumes of the
  domain**. Domains in any power state other than `running` or `shut off` are refused.

Dependencies
------------

None.

Example Playbook
----------------

```yml
- hosts: hypervisor
  roles:
    - sadyr0012.infralab.vms
```

License
-------

GPL-2.0-or-later

Author Information
------------------

Sadyr sadyr0012@gmail.com
