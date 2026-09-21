Role Name
=========

A brief description of the role goes here.

Requirements
------------

Any pre-requisites that may not be covered by Ansible itself or the role should be mentioned here. For instance, if the role uses the EC2 module, it may be a good idea to mention in this section that the boto package is required.

Role Variables
--------------
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


A description of the settable variables for this role should go here, including any variables that are in defaults/main.yml, vars/main.yml, and any variables that can/should be set via parameters to the role. Any variables that are read from other roles and/or the global scope (ie. hostvars, group vars, etc.) should be mentioned here as well.

Dependencies
------------

A list of other roles hosted on Galaxy should go here, plus any details in regards to parameters that may need to be set for other roles, or variables that are used from other roles.

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

    - hosts: servers
      roles:
         - { role: username.rolename, x: 42 }

License
-------

BSD

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
