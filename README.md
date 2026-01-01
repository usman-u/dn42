# DN42 Network Automation

Ansible-based Infrastructure as Code for DN42 BGP routers running FRR (BGP + OSPF) and WireGuard.

## Network Topology

![Network Topology](topology.png)

*To regenerate: `uv run python scripts/generate_topology.py`*

## Public Routing Policy

This network implements a cold potato routing policy designed to prefer local egress points and minimise latency. Routes are selected based on BGP local-pref, followed by latency-based MED.

### Local Preference Hierarchy

| LPREF | Criterion |
|-------|-----------|
| 500 | Anycast prefix originating from this AS (reserved for future anycast services) |
| 300 | Prefix announced directly by peer (AS_PATH length = 1) |
| 230 | Prefix's country community matches this router's country |
| 220 | Prefix's country community matches peer's country |
| 210 | Prefix's region community matches this router's region |
| 200 | Prefix's region community matches peer's region |
| 100 | Default (prefix matches DN42 ranges) |

### Multi-Exit Discriminator (MED)

When multiple routes share the same LOCAL_PREF and AS_PATH length, the tie-breaker is the Multi-Exit Discriminator (MED), which is set to the measured tunnel latency in microseconds. Lower latency paths are preferred.

Transit is not currently provided.

## Quick Start

### Prerequisites

**Control node (local machine):**
- Python 3.11+
- `uv` package manager
- SSH access to routers

**Managed nodes (routers):**
- Ubuntu 24.04 or Debian
- Python 3 installed
- Passwordless sudo configured

### Installation

```bash
# Install dependencies
uv sync

# Install Ansible collections
uv run ansible-galaxy collection install -r requirements.yml

# Test connectivity
uv run ansible all -m ping
```

### Usage

**Dry-run (shows changes without applying):**
```bash
uv run ansible-playbook -i inventory/hosts.yml playbooks/site.yml --check --diff
uv run ansible-playbook -i inventory/hosts.yml playbooks/site.yml --check --diff --limit lhr-r001
uv run ansible-playbook -i inventory/hosts.yml playbooks/site.yml --check --diff --tags frr
```

**Apply changes:**
```bash
uv run ansible-playbook -i inventory/hosts.yml playbooks/site.yml
uv run ansible-playbook -i inventory/hosts.yml playbooks/site.yml --limit lhr-r001
uv run ansible-playbook -i inventory/hosts.yml playbooks/site.yml --tags wireguard
```

**With vault (for encrypted secrets):**
```bash
uv run ansible-playbook -i inventory/hosts.yml playbooks/site.yml --vault-password-file .vault-password
```

**Available tags:**
- `common` - Base packages and system setup
- `network` - Network configuration
- `wireguard` / `wg` - WireGuard tunnels
- `frr` / `bgp` / `routing` - FRR BGP configuration

### One-time Setup

**Configure passwordless sudo on routers:**
```bash
uv run ansible-playbook -i inventory/hosts.yml playbooks/setup-sudo.yml
```

## Configuration

Configuration is data-driven using YAML files with JSON schema validation:

- [inventory/group_vars/all/global.yml](inventory/group_vars/all/global.yml) - Global settings (ASN, community lists, prefix lists, route-maps)
- [inventory/host_vars/\<hostname\>/main.yml](inventory/host_vars/) - Per-router config (loopback, peers, network, BGP networks)
- [inventory/host_vars/\<hostname\>/vault.yml](inventory/host_vars/) - Encrypted secrets (WireGuard private keys)

### Global Configuration ([global.yml](inventory/group_vars/all/global.yml))

Network-wide parameters:

#### Core Network
- `dn42_asn` - Your DN42 ASN
- `intra_network_tunnels` - WireGuard tunnels between your routers
- `static_routes` - Network-wide static routes

#### iBGP Configuration
- `ibgp_enabled` - Enable/disable iBGP full mesh
- `ibgp_mesh` - List of router hostnames to participate in full mesh
- `ibgp_config` - Timers, BFD, route reflector settings

#### OSPF Configuration
- `ospf_enabled` - Enable/disable OSPF routing
- `ospf_config` - Area ID, reference bandwidth, hello/dead intervals

#### BGP Policy
- `bgp_community_lists` - BGP community lists
- `bgp_large_community_lists` - Large community lists
- `bgp_as_path_acls` - AS path access lists
- `ip_prefix_lists` - IPv4 prefix lists
- `ipv6_prefix_lists` - IPv6 prefix lists
- `route_maps` - Global route-maps (non-peer specific)

#### WireGuard Defaults
- `wg_defaults` - Default settings for all WireGuard interfaces

### Host Configuration ([host_vars/\<hostname\>/main.yml](inventory/host_vars/))

Per-router parameters:

#### Required Parameters
- `fqdn` - Fully qualified domain name
- `loopback` - Loopback IPv4 address (used for BGP router-id)
- `wan_ip` - Public/WAN IP for intra-network tunnels
- `dn42_region` - Geographic region
- `iso_3166_country_code` - ISO 3166-1 alpha-2 country code
- `ingress_bgp_large_community` - Large community set on ingress routes
- `wg_privkey` - WireGuard private key (encrypt with Ansible Vault)
- `wg_pubkey` - WireGuard public key

#### Optional Parameters
- `network_config` - OS-agnostic network interface configuration
- `bgp_router_id` - BGP router ID (defaults to loopback)
- `bgp_options` - BGP global options
- `bgp_networks` - Networks to advertise via BGP
- `bgp_peers` - Simple BGP peers (non-DN42)
- `peers` - DN42 WireGuard+BGP peers

#### Parameter Overrides

**All parameters from global.yml can be overridden in host_vars** for per-host customization via Ansible's variable precedence (host_vars > group_vars):

- `ospf_enabled` - Disable OSPF on specific router
- `ospf_config` - Use different timers or area
- `ibgp_enabled` - Exclude router from iBGP mesh
- `ibgp_config` - Different timers for specific router
- `static_routes` - Add host-specific static routes
- BGP policy overrides (prefix lists, communities, route-maps, etc.)

## Intra-Network Tunnels

Simplified format using router names with auto-generated parameters:

```yaml
# inventory/group_vars/all/global.yml
intra_network_tunnels:
  - routers: [lhr-r001, ewr-r001]
    port: auto  # or explicit port number
```

**Auto-generation:**
- **Interface name**: `wg-{location_a}-{location_b}` (sorted alphabetically by location code)
  - Example: `lhr-r001` + `ewr-r001` → `wg-ewr-lhr`
- **IPv4 link-local**: `169.254.255.{last_octet}/30` (for OSPF)
- **IPv6 link-local**: `fe80::1869:{last_octet}/64` (for iBGP)
- **Port** (when "auto"): `5000 + last_octet_a + last_octet_b`
  - Example: lhr-r001 (.161) + ewr-r001 (.162) = port 5323
- **Endpoint**: Uses peer's `wan_ip:port` from host_vars

## Network Configuration

OS-agnostic format supporting both Ubuntu (netplan) and Debian (/etc/network/interfaces):

```yaml
network_config:
  interfaces:
    - name: enp1s0
      addresses: ["192.168.1.10/24"]
      dhcp: false
      gateway: "192.168.1.1"
      nameservers: ["8.8.8.8"]
      search_domains: ["example.com"]
      routes:
        - to: "10.0.0.0/8"
          via: "192.168.1.254"
```

## Secrets Management

WireGuard private keys are encrypted with Ansible Vault:

```bash
# Encrypt vault file
ansible-vault encrypt inventory/host_vars/lhr-r001/vault.yml

# Create password file (add to .gitignore)
echo "your-vault-password" > .vault-password
chmod 600 .vault-password

# Edit encrypted file
ansible-vault edit inventory/host_vars/lhr-r001/vault.yml
```

See [VAULT-SETUP.md](VAULT-SETUP.md) for detailed instructions on vault setup and git secret scrubbing.

## Adding a New Router

1. Add to [inventory/hosts.yml](inventory/hosts.yml):
```yaml
routers:
  hosts:
    lhr-r003:
      ansible_host: 10.0.10.253
      ansible_user: usman
```

2. Create `inventory/host_vars/lhr-r003/` directory
3. Create `inventory/host_vars/lhr-r003/main.yml` (copy from existing router)
4. Create `inventory/host_vars/lhr-r003/vault.yml` with encrypted secrets
5. Run: `uv run ansible-playbook -i inventory/hosts.yml playbooks/site.yml --check --diff --limit lhr-r003 --vault-password-file .vault-password`
6. Apply: `uv run ansible-playbook -i inventory/hosts.yml playbooks/site.yml --limit lhr-r003 --vault-password-file .vault-password`

## Adding a New DN42 Peer

Add to the `peers` array in [inventory/host_vars/\<hostname\>/main.yml](inventory/host_vars/):

```yaml
peers:
  - name: EXAMPLE
    wg_pubkey: "base64pubkey=="
    wg_endpoint: "peer.example.com:51820"
    wg_address: "fe80::1/64"
    wg_listenport: auto
    asn: "4242420000"
    peer_address: "fe80::2"
    latency_us: "5000"
    dn42_region: Europe
    iso_3166_country_code: GB
```

The automation will:
- Create WireGuard tunnel configuration
- Generate peer-specific BGP route-maps (inbound: per-peer with region/country preferences, outbound: generic)
- Configure BGP neighbor with soft-reconfiguration and extended-nexthop

## Architecture

### Roles

- **[roles/common](roles/common/)** - Base packages, sysctl tuning
- **[roles/network](roles/network/)** - OS-agnostic network interface configuration
- **[roles/wireguard](roles/wireguard/)** - WireGuard tunnel management (wg-quick)
- **[roles/frr](roles/frr/)** - FRRouting BGP+OSPF daemon with pre/post configuration checks

All roles support idempotent updates with automatic diffing and validation.

### Validation

Configuration validation happens automatically before deployment:

- **Ubuntu (Netplan)**: `netplan --dry-run generate`
- **Debian (interfaces)**: `ifup --no-act {interface}`
- **FRR**: `vtysh --dryrun --inputfile {config}`

Failed validation prevents deployment.

## Verification Commands

### iBGP Status
```bash
sudo vtysh -c "show bgp summary"
sudo vtysh -c "show bgp ipv4 unicast summary"
sudo vtysh -c "show bgp ipv6 unicast summary"
```

### OSPF Status
```bash
sudo vtysh -c "show ip ospf neighbor"
sudo vtysh -c "show ip ospf database"
sudo vtysh -c "show ip ospf interface"
sudo vtysh -c "show ip route ospf"
```

### WireGuard Tunnels
```bash
# All interfaces
wg show

# Specific interface
wg show wg-ewr-lhr

# Listen ports
wg show all listen-port
```

### BGP Routes
```bash
# All routes
sudo vtysh -c "show ip bgp"

# Specific neighbor
sudo vtysh -c "show bgp neighbor 172.22.132.162"

# Route details
sudo vtysh -c "show bgp ipv4 unicast 172.20.0.0/24"
```

## Project Structure

```
.
├── inventory/
│   ├── hosts.yml                  # Ansible inventory
│   ├── group_vars/all/global.yml  # Global BGP config
│   └── host_vars/                 # Per-router config
├── playbooks/
│   ├── site.yml                   # Main playbook
│   └── setup-sudo.yml             # One-time sudo setup
├── roles/
│   ├── common/                    # System setup
│   ├── network/                   # Network config
│   ├── wireguard/                 # WireGuard tunnels
│   └── frr/                       # FRR BGP routing
├── schemas/                       # JSON schemas for validation
│   ├── global.schema.json
│   └── node.schema.json
├── scripts/
│   └── generate_topology.py      # Topology diagram generator
└── pyproject.toml                 # Python dependencies
```

## Troubleshooting

### Configuration Not Applied

1. Check Ansible facts:
```bash
ansible <hostname> -m setup
```

2. Verify variable precedence:
```bash
ansible-inventory --host <hostname> --yaml
```

3. Check handlers were notified:
```bash
ansible-playbook playbooks/site.yml -vv
```

### WireGuard Tunnel Not Working

1. Verify peer keys:
```bash
wg show wg-ewr-lhr
```

2. Check endpoint resolution:
```bash
ping <peer_wan_ip>
```

3. Verify firewall allows UDP port:
```bash
sudo netstat -ulnp | grep <port>
```

### BGP Session Down

1. Check interface status:
```bash
ip -6 addr show | grep fe80::1869
```

2. Verify reachability:
```bash
ping6 -I wg-ewr-lhr fe80::1869:162
```

3. Check FRR logs:
```bash
sudo journalctl -u frr -f
```

## JSON Schema Validation

Enable IntelliSense in VSCode:

```json
// .vscode/settings.json
{
  "yaml.schemas": {
    "schemas/global.schema.json": "inventory/group_vars/all/global.yml",
    "schemas/node.schema.json": "inventory/host_vars/*/main.yml"
  }
}
```

## References

- [DN42 Wiki](https://wiki.dn42.dev/)
- [FRR Documentation](https://docs.frrouting.org/)
- [WireGuard Documentation](https://www.wireguard.com/)
- [Ansible Documentation](https://docs.ansible.com/)
