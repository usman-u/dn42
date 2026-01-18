#!/usr/bin/env python3
"""Generate network topology diagrams: geographic map and logical view."""

import yaml
from pathlib import Path
import sys
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import numpy as np
import networkx as nx

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    HAS_CARTOPY = True
except ImportError:
    HAS_CARTOPY = False
    print("Warning: cartopy not installed. Install with: pip install cartopy")
    print("Geographic map will be simplified.")


# Geographic coordinates for locations (longitude, latitude)
LOCATION_COORDS = {
    # Router locations (extracted from hostname prefixes)
    "lhr": (-0.4543, 51.4700),      # London Heathrow area
    "ewr": (-74.1745, 40.6895),     # Newark, NJ
    "lax": (-118.4085, 33.9416),    # Los Angeles
    "ams": (4.7683, 52.3105),       # Amsterdam
    "fra": (8.5706, 50.0379),       # Frankfurt
    "frk": (8.5706, 50.0379),       # Frankfurt (alt code)
    "sin": (103.9915, 1.3644),      # Singapore
    "sgx": (103.9915, 1.3644),      # Singapore (alt code)
    "syd": (151.1772, -33.9399),    # Sydney
    "nrt": (140.3929, 35.7720),     # Tokyo Narita
    "hkg": (113.9145, 22.3080),     # Hong Kong

    # Country code to approximate coordinates (for peers)
    "GB": (-0.1276, 51.5074),       # London, UK
    "US": (-95.7129, 37.0902),      # Central US
    "NL": (4.8952, 52.3702),        # Amsterdam, Netherlands
    "DE": (10.4515, 51.1657),       # Germany center
    "FR": (2.3522, 48.8566),        # Paris, France
    "JP": (139.6917, 35.6895),      # Tokyo, Japan
    "SG": (103.8198, 1.3521),       # Singapore
    "AU": (151.2093, -33.8688),     # Sydney, Australia
    "CA": (-106.3468, 56.1304),     # Canada center
    "HK": (114.1694, 22.3193),      # Hong Kong
}

# Logical diagram positions - approximate geographic layout (normalized to [-1, 1] range)
# Layout mimics a globe view with west on left, east on right
LOGICAL_POSITIONS = {
    "lhr": (-0.3, 0.5),       # London - Europe, upper middle
    "frk": (-0.1, 0.4),       # Frankfurt - Europe, slightly east of London
    "ewr": (-0.7, 0.3),       # Newark - US East Coast
    "lax": (-1.0, 0.1),       # LA - US West Coast
    "sgx": (0.6, -0.3),       # Singapore - Southeast Asia
}

USMAN_ASN = "4242421869"


def load_inventory():
    """Load inventory and host variables."""
    base_path = Path(__file__).parent.parent

    hosts_file = base_path / "inventory" / "hosts.yml"
    with open(hosts_file) as f:
        hosts = yaml.safe_load(f)

    routers = []
    for host in hosts["all"]["children"]["routers"]["hosts"].keys():
        host_var_path = base_path / "inventory" / "host_vars" / host / "main.yml"
        if host_var_path.exists():
            with open(host_var_path) as f:
                host_vars = yaml.safe_load(f)
                host_vars["hostname"] = host
                routers.append(host_vars)

    return routers


def load_global_config():
    """Load global configuration."""
    base_path = Path(__file__).parent.parent
    global_vars_path = base_path / "inventory" / "group_vars" / "all" / "global.yml"
    if global_vars_path.exists():
        with open(global_vars_path) as f:
            return yaml.safe_load(f)
    return {}


def get_router_coords(hostname):
    """Get coordinates for a router based on its hostname prefix."""
    prefix = hostname.split("-")[0].lower()
    return LOCATION_COORDS.get(prefix, LOCATION_COORDS["lhr"])


def get_logical_position(hostname):
    """Get logical diagram position for a router."""
    prefix = hostname.split("-")[0].lower()
    return LOGICAL_POSITIONS.get(prefix, (0, 0))


def generate_geo_map(routers, output_file="topology-geo.png"):
    """Generate geographic map showing internal network on a world map."""

    global_config = load_global_config()
    intra_network_tunnels = global_config.get("intra_network_tunnels", [])

    # Collect router data
    router_nodes = []
    router_positions_geo = {}
    router_labels = {}

    for router in routers:
        hostname = router["hostname"]
        loopback = router.get("loopback", "")
        coords = get_router_coords(hostname)

        router_nodes.append(hostname)
        router_positions_geo[hostname] = coords
        router_labels[hostname] = f"{hostname}\n{loopback}"

    # Collect internal tunnel data
    ibgp_edges = []
    edge_info = {}

    for tunnel in intra_network_tunnels:
        router_pair = tunnel.get("routers", [])
        if len(router_pair) == 2:
            router_a, router_b = router_pair
            if router_a in router_nodes and router_b in router_nodes:
                ibgp_edges.append((router_a, router_b))
                ospf_cost = tunnel.get("ospf_cost", "auto")
                edge_info[(router_a, router_b)] = f"{ospf_cost}ms"

    # Create figure with world map projection
    if HAS_CARTOPY:
        fig = plt.figure(figsize=(16, 7))
        # Use PlateCarree for simple lat/lon view with custom extent
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())

        # Set extent to show northern hemisphere focused on our network
        # (West: LA, East: Singapore, cropping southern hemisphere)
        ax.set_extent([-130, 120, -10, 65], crs=ccrs.PlateCarree())

        # Add map features
        ax.add_feature(cfeature.LAND, facecolor='#f5f5f5', edgecolor='none')
        ax.add_feature(cfeature.OCEAN, facecolor='#e8f4fc', edgecolor='none')
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor='#888888')
        ax.add_feature(cfeature.BORDERS, linewidth=0.3, edgecolor='#cccccc', linestyle=':')

        # Draw internal GRE edges as straight lines (PlateCarree)
        for edge in ibgp_edges:
            router_a, router_b = edge
            lon_a, lat_a = router_positions_geo[router_a]
            lon_b, lat_b = router_positions_geo[router_b]

            ax.plot([lon_a, lon_b], [lat_a, lat_b],
                   color='#1565c0', linewidth=3, alpha=0.8,
                   transform=ccrs.PlateCarree(), zorder=2)

        # Draw router nodes
        for hostname in router_nodes:
            lon, lat = router_positions_geo[hostname]
            ax.scatter(lon, lat, c='#4a90e2', s=350, marker='s',
                      edgecolors='black', linewidths=2,
                      transform=ccrs.PlateCarree(), zorder=10)

            # Adjust label position based on location to avoid overlap
            prefix = hostname.split("-")[0].lower()
            if prefix == "sgx":
                # Singapore - put label to the left (inside the map)
                label_offset_lon = -12
                label_offset_lat = 0
                ha = 'right'
                va = 'center'
            elif prefix == "frk":
                # Frankfurt - put label to the right and up
                label_offset_lon = 8
                label_offset_lat = 5
                ha = 'left'
                va = 'bottom'
            elif prefix == "lhr":
                # London - put label to the left
                label_offset_lon = -8
                label_offset_lat = 3
                ha = 'right'
                va = 'bottom'
            elif prefix == "lax":
                # LA - put label below
                label_offset_lon = 0
                label_offset_lat = -8
                ha = 'center'
                va = 'top'
            elif prefix == "ewr":
                # Newark - put label below
                label_offset_lon = 0
                label_offset_lat = -8
                ha = 'center'
                va = 'top'
            else:
                label_offset_lon = 0
                label_offset_lat = -8
                ha = 'center'
                va = 'top'

            ax.text(lon + label_offset_lon, lat + label_offset_lat, router_labels[hostname],
                   fontsize=9, ha=ha, va=va, fontweight='bold',
                   transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                            edgecolor='#4a90e2', alpha=0.95),
                   zorder=11)

        # Draw edge labels - positioned directly on the links
        for edge in ibgp_edges:
            router_a, router_b = edge
            lon_a, lat_a = router_positions_geo[router_a]
            lon_b, lat_b = router_positions_geo[router_b]

            # Position at midpoint of the edge
            mid_lon = (lon_a + lon_b) / 2
            mid_lat = (lat_a + lat_b) / 2

            label_text = edge_info.get(edge, "")
            ax.text(mid_lon, mid_lat, label_text,
                   fontsize=7, ha='center', va='center',
                   transform=ccrs.PlateCarree(),
                   bbox=dict(boxstyle='round,pad=0.15', facecolor='white',
                            edgecolor='#1565c0', alpha=0.9),
                   zorder=5)

    else:
        # Fallback without cartopy - simple plot
        fig, ax = plt.subplots(figsize=(16, 9))

        # Calculate extent based on router positions
        all_lons = [pos[0] for pos in router_positions_geo.values()]
        all_lats = [pos[1] for pos in router_positions_geo.values()]
        lon_margin = 20
        lat_margin = 15

        ax.set_xlim(min(all_lons) - lon_margin, max(all_lons) + lon_margin)
        ax.set_ylim(min(all_lats) - lat_margin, max(all_lats) + lat_margin)
        ax.set_facecolor('#e8f4fc')

        for edge in ibgp_edges:
            router_a, router_b = edge
            lon_a, lat_a = router_positions_geo[router_a]
            lon_b, lat_b = router_positions_geo[router_b]
            ax.plot([lon_a, lon_b], [lat_a, lat_b],
                   color='#1565c0', linewidth=3, alpha=0.8, zorder=2)

        for hostname in router_nodes:
            lon, lat = router_positions_geo[hostname]
            ax.scatter(lon, lat, c='#4a90e2', s=300, marker='s',
                      edgecolors='black', linewidths=2, zorder=10)
            ax.text(lon, lat - 5, router_labels[hostname],
                   fontsize=9, ha='center', va='top', fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                            edgecolor='#4a90e2', alpha=0.95),
                   zorder=11)

    ax.set_title(f"AS{USMAN_ASN} - Geographic Network View\n(iBGP + OSPF + LDP over GRE)",
                fontsize=14, fontweight='bold', pad=10)

    # Legend
    geo_legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor='#4a90e2',
               markersize=12, markeredgecolor='black', label=f'USMAN Routers (AS{USMAN_ASN})'),
        Line2D([0], [0], color='#1565c0', linewidth=3, linestyle='-',
               label='GRE Tunnel (iBGP + OSPF + LDP)'),
    ]
    ax.legend(handles=geo_legend_elements, loc='lower left', fontsize=9,
             framealpha=0.95, edgecolor='#333333')

    plt.tight_layout()

    # Save
    output_path = Path(__file__).parent.parent / output_file
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"Geographic topology saved to: {output_path}")
    plt.close()

    return output_path


def generate_logical_diagram(routers, output_file="topology-logical.png"):
    """Generate logical topology diagram showing full network with geographic-like layout."""

    global_config = load_global_config()
    intra_network_tunnels = global_config.get("intra_network_tunnels", [])
    segment_routing_enabled = global_config.get("segment_routing_enabled", False)
    sr_label = "+SR" if segment_routing_enabled else ""

    # Collect router data with fixed positions
    router_nodes = []
    router_labels = {}
    pos = {}

    for router in routers:
        hostname = router["hostname"]
        loopback = router.get("loopback", "")
        router_nodes.append(hostname)
        router_labels[hostname] = f"{hostname}\n{loopback}"
        pos[hostname] = np.array(get_logical_position(hostname))

    # Collect internal tunnel data
    ibgp_edges = []
    edge_labels_internal = {}

    for tunnel in intra_network_tunnels:
        router_pair = tunnel.get("routers", [])
        if len(router_pair) == 2:
            router_a, router_b = router_pair
            if router_a in router_nodes and router_b in router_nodes:
                ibgp_edges.append((router_a, router_b))
                ospf_cost = tunnel.get("ospf_cost", "auto")
                edge_labels_internal[(router_a, router_b)] = f"{ospf_cost}ms"

    # Collect peer data
    dn42_peers = []
    other_peers = []
    peer_labels = {}
    external_edges = []
    edge_labels_external = {}
    peer_to_router = {}

    for router in routers:
        hostname = router["hostname"]

        # DN42 peers
        if "peers" in router:
            for peer in router["peers"]:
                peer_name = peer["name"]
                peer_asn = peer["asn"]
                peer_id = f'{peer_name}_{peer_asn}'
                country = peer.get("iso_3166_country_code", "GB")

                dn42_peers.append(peer_id)
                peer_labels[peer_id] = f"{peer_name}\nAS{peer_asn}"
                peer_to_router[peer_id] = hostname

                external_edges.append((hostname, peer_id))
                latency_ms = int(peer["latency_us"]) / 1000
                edge_labels_external[(hostname, peer_id)] = f"{latency_ms:.0f}ms"

        # Non-DN42 peers
        if "bgp_peers" in router:
            for peer in router["bgp_peers"]:
                peer_name = peer["name"]
                peer_asn = peer["remote_as"]
                peer_id = f'{peer_name}_{peer_asn}'
                peer_type = peer.get("type", "unknown")

                other_peers.append(peer_id)
                peer_labels[peer_id] = f"{peer_name}\nAS{peer_asn}"
                peer_to_router[peer_id] = hostname

                external_edges.append((hostname, peer_id))
                edge_labels_external[(hostname, peer_id)] = ""

    # Calculate center of router positions
    if router_nodes:
        router_positions_arr = np.array([pos[r] for r in router_nodes])
        router_center = router_positions_arr.mean(axis=0)

    # Position peers around their connected routers
    # Group peers by router
    peers_by_router = {}
    for peer_id in dn42_peers + other_peers:
        router = peer_to_router.get(peer_id)
        if router:
            if router not in peers_by_router:
                peers_by_router[router] = []
            peers_by_router[router].append(peer_id)

    # Position each router's peers in a fan around it
    for router, peers in peers_by_router.items():
        router_pos = pos[router]
        # Direction from center to router (peers go on the outside)
        direction = router_pos - router_center
        if np.linalg.norm(direction) > 0:
            direction = direction / np.linalg.norm(direction)
        else:
            direction = np.array([1, 0])

        # Base angle in the direction away from center
        base_angle = np.arctan2(direction[1], direction[0])

        # Spread peers in a fan
        n_peers = len(peers)
        if n_peers == 1:
            angles = [base_angle]
        else:
            # Spread over 120 degrees (pi/1.5 radians)
            spread = np.pi / 1.5
            angles = np.linspace(base_angle - spread/2, base_angle + spread/2, n_peers)

        peer_distance = 0.45  # Distance from router to peer

        for i, peer_id in enumerate(peers):
            angle = angles[i]
            pos[peer_id] = router_pos + peer_distance * np.array([np.cos(angle), np.sin(angle)])

    # Create graph
    G = nx.Graph()
    for hostname in router_nodes:
        G.add_node(hostname)
    for peer_id in dn42_peers + other_peers:
        G.add_node(peer_id)
    for edge in ibgp_edges:
        G.add_edge(edge[0], edge[1])
    for edge in external_edges:
        G.add_edge(edge[0], edge[1])

    # Create figure
    fig, ax = plt.subplots(figsize=(16, 10))

    # Draw internal zone (MPLS/LDP domain) - use a rounded rectangle
    if router_nodes:
        router_xs = [pos[r][0] for r in router_nodes]
        router_ys = [pos[r][1] for r in router_nodes]
        padding = 0.25

        rect_x = min(router_xs) - padding
        rect_y = min(router_ys) - padding
        rect_width = max(router_xs) - min(router_xs) + 2 * padding
        rect_height = max(router_ys) - min(router_ys) + 2 * padding

        internal_zone = mpatches.FancyBboxPatch(
            (rect_x, rect_y), rect_width, rect_height,
            boxstyle=mpatches.BoxStyle("Round", pad=0.05, rounding_size=0.15),
            facecolor='#e3f2fd', alpha=0.6, zorder=0,
            linestyle='--', linewidth=2, edgecolor='#1976d2'
        )
        ax.add_patch(internal_zone)

        # Label for the domain
        ax.annotate(
            f'AS{USMAN_ASN} - MPLS/LDP Domain',
            xy=(rect_x + rect_width / 2, rect_y - 0.05),
            ha='center', va='top',
            fontsize=11, fontweight='bold', color='#1976d2',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#1976d2', alpha=0.95)
        )

    # Draw external edges first (behind nodes)
    if external_edges:
        nx.draw_networkx_edges(
            G, pos, edgelist=external_edges,
            width=1.5, alpha=0.5, edge_color='#888888',
            style='dashed', ax=ax
        )

    # Draw internal edges
    if ibgp_edges:
        nx.draw_networkx_edges(
            G, pos, edgelist=ibgp_edges,
            width=4, alpha=0.9, edge_color='#1565c0',
            style='solid', ax=ax
        )

    # Draw router nodes
    nx.draw_networkx_nodes(
        G, pos, nodelist=router_nodes,
        node_color='#4a90e2', node_size=4500,
        node_shape='o', edgecolors='black', linewidths=2,
        ax=ax
    )

    # Draw DN42 peer nodes
    if dn42_peers:
        nx.draw_networkx_nodes(
            G, pos, nodelist=dn42_peers,
            node_color='#66bb6a', node_size=1800,
            node_shape='o', edgecolors='black', linewidths=1.5,
            ax=ax
        )

    # Draw non-DN42 peer nodes
    if other_peers:
        nx.draw_networkx_nodes(
            G, pos, nodelist=other_peers,
            node_color='#ffa726', node_size=1500,
            node_shape='D', edgecolors='black', linewidths=1.5,
            ax=ax
        )

    # Draw labels for routers (inside the node)
    nx.draw_networkx_labels(
        G, pos, labels={h: router_labels[h] for h in router_nodes},
        font_size=8, font_weight='bold',
        ax=ax
    )

    # Draw labels for peers
    nx.draw_networkx_labels(
        G, pos, labels=peer_labels,
        font_size=7, font_weight='normal',
        ax=ax
    )

    # Draw edge labels (internal) - position along the edge
    for edge, label in edge_labels_internal.items():
        x1, y1 = pos[edge[0]]
        x2, y2 = pos[edge[1]]
        # Position at 40% along the edge
        t = 0.4
        mx = x1 + t * (x2 - x1)
        my = y1 + t * (y2 - y1)
        ax.text(mx, my, label, fontsize=7, ha='center', va='center',
               color='#1565c0', fontweight='bold',
               bbox=dict(boxstyle='round,pad=0.1', facecolor='white', edgecolor='none', alpha=0.9))

    ax.set_title(f"AS{USMAN_ASN} - Logical Network Topology",
                fontsize=14, fontweight='bold', pad=15)
    ax.axis('off')

    # Set axis limits with margin
    all_x = [p[0] for p in pos.values()]
    all_y = [p[1] for p in pos.values()]
    margin = 0.3
    ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
    ax.set_ylim(min(all_y) - margin - 0.15, max(all_y) + margin)

    # Legend
    logical_legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#4a90e2',
               markersize=14, markeredgecolor='black', label=f'USMAN Routers (AS{USMAN_ASN})'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#66bb6a',
               markersize=10, markeredgecolor='black', label='DN42 Peers (eBGP/WireGuard)'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor='#ffa726',
               markersize=8, markeredgecolor='black', label='Non-DN42 Peers'),
        Line2D([0], [0], color='#1565c0', linewidth=4, linestyle='-',
               label=f'Internal: iBGP + OSPF + LDP{sr_label} (GRE)'),
        Line2D([0], [0], color='#888888', linewidth=1.5, linestyle='--',
               label='External: eBGP Peering (WireGuard)'),
        mpatches.Patch(facecolor='#e3f2fd', edgecolor='#1976d2', linestyle='--',
                      label='MPLS/LDP Domain Boundary'),
    ]
    ax.legend(handles=logical_legend_elements, loc='lower left', fontsize=9,
             framealpha=0.95, edgecolor='#333333', ncol=2)

    plt.tight_layout()

    # Save
    output_path = Path(__file__).parent.parent / output_file
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"Logical topology saved to: {output_path}")
    plt.close()

    return output_path


def main():
    """Generate both topology diagrams."""
    try:
        routers = load_inventory()

        # Generate both diagrams
        generate_geo_map(routers, "topology-geo.png")
        generate_logical_diagram(routers, "topology-logical.png")

        print("\nBoth diagrams generated successfully!")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
