# DN42 Network Automation

Ansible-based Infrastructure as Code for DN42 BGP routers running FRR and WireGuard.

## Public Routing Policy

This network performs cold potato routing with the following local preferences:

| LPREF | Criterion                                    | Notes                   |
|-------|----------------------------------------------|-------------------------|
| 500   | Anycast prefix originating from USMAN        | Reserved for future use |
| 300   | Prefix originates from peer (AS_PATH len=1)  |                         |
| 210   | Prefix matches neighbour's country           |                         |
| 200   | Prefix matches neighbour's region            |                         |
| 100   | Default                                      |                         |

Latency of eBGP peerings is measured (in microseconds) and set as MED on ingress to inform path selection as a tie-breaker when LPREF and AS_PATH length are equal.

Transit is not currently provided.

## Ansible Quick Start

### Prerequisites

**Control node (local machine):**
- Python 3.11+
- `uv` package manager
- SSH access to routers

**Managed nodes (routers):**
- Ubuntu 24.04
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
- `netplan` - Network configuration
- `wireguard` / `wg` - WireGuard tunnels
- `frr` / `bgp` / `routing` - FRR BGP configuration

### One-time Setup

**Configure passwordless sudo on routers:**
```bash
uv run ansible-playbook -i inventory/hosts.yml playbooks/setup-sudo.yml
```

## Configuration

Configuration is data-driven using YAML files with JSON schema validation:

- `inventory/group_vars/all/global.yml` - Global settings (ASN, community lists, prefix lists, route-maps)
- `inventory/host_vars/<hostname>/main.yml` - Per-router config (loopback, peers, netplan, BGP networks)
- `inventory/host_vars/<hostname>/vault.yml` - Encrypted secrets (WireGuard private keys)

### Secrets Management

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

### Adding a New Router

1. Add to `inventory/hosts.yml`:
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

### Adding a New DN42 Peer

Add to the `peers` array in `inventory/host_vars/<hostname>/main.yml`:

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

- **roles/common** - Base packages, sysctl tuning
- **roles/netplan** - Network interface configuration
- **roles/wireguard** - WireGuard tunnel management (wg-quick)
- **roles/frr** - FRRouting BGP daemon with pre/post BGP summary checks

All roles support idempotent updates with automatic diffing and validation.

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
│   ├── netplan/                   # Network config
│   ├── wireguard/                 # WireGuard tunnels
│   └── frr/                       # FRR BGP routing
├── schemas/                       # JSON schemas for validation
└── pyproject.toml                 # Python dependencies
```
