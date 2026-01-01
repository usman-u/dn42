#!/usr/bin/env python3
"""Generate network topology diagram from Ansible inventory."""

import yaml
from pathlib import Path
import sys
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def load_inventory():
    """Load inventory and host variables."""
    base_path = Path(__file__).parent.parent

    # Load hosts
    hosts_file = base_path / "inventory" / "hosts.yml"
    with open(hosts_file) as f:
        hosts = yaml.safe_load(f)

    # Load host_vars
    routers = []
    for host in hosts["all"]["children"]["routers"]["hosts"].keys():
        host_var_path = base_path / "inventory" / "host_vars" / host / "main.yml"
        if host_var_path.exists():
            with open(host_var_path) as f:
                host_vars = yaml.safe_load(f)
                host_vars["hostname"] = host
                routers.append(host_vars)

    return routers

def generate_graph(routers, output_file="topology.png"):
    """Generate network topology graph as PNG."""
    base_path = Path(__file__).parent.parent
    G = nx.Graph()

    # Track node types for coloring and positioning
    node_colors = {}
    node_labels = {}
    edge_labels = {}
    edge_styles = {}  # Track edge styles
    router_nodes = []
    dn42_peers = []
    other_peers = []
    ibgp_edges = []

    USMAN_ASN = "4242421869"

    # Add router nodes
    for router in routers:
        hostname = router["hostname"]
        loopback = router.get("loopback", "")
        node_id = hostname

        G.add_node(node_id)
        node_colors[node_id] = "#4a90e2"  # Blue for routers
        node_labels[node_id] = f"{hostname}\n{loopback}\nAS{USMAN_ASN}"
        router_nodes.append(node_id)

    # Add intra-network connections (iBGP + IS-IS)
    global_vars_path = base_path / "inventory" / "group_vars" / "all" / "global.yml"
    if global_vars_path.exists():
        with open(global_vars_path) as f:
            global_config = yaml.safe_load(f)
            intra_network_tunnels = global_config.get("intra_network_tunnels", [])

            intra_network_tunnels = global_config.get("intra_network_tunnels", [])
            segment_routing_enabled = global_config.get("segment_routing_enabled", False)

            # Determine label based on SR status
            sr_label = "+SR" if segment_routing_enabled else ""

            for tunnel in intra_network_tunnels:
                # New simplified format: routers: [router_a, router_b]
                router_pair = tunnel.get("routers", [])

                if len(router_pair) == 2:
                    router_a, router_b = router_pair

                    if router_a in router_nodes and router_b in router_nodes:
                        G.add_edge(router_a, router_b)
                        edge_labels[(router_a, router_b)] = f"iBGP+OSPF{sr_label}\nWireGuard"
                        edge_styles[(router_a, router_b)] = "solid"
                        ibgp_edges.append((router_a, router_b))

    # Add peer connections
    for router in routers:
        hostname = router["hostname"]

        # DN42 peers
        if "peers" in router:
            for peer in router["peers"]:
                peer_name = peer["name"]
                peer_asn = peer["asn"]
                peer_id = f'{peer_name}_{peer_asn}'
                country = peer["iso_3166_country_code"]

                G.add_node(peer_id)
                node_colors[peer_id] = "#66bb6a"  # Green for DN42 peers
                node_labels[peer_id] = f"{peer_name}\nAS{peer_asn}\n{country}"
                dn42_peers.append(peer_id)

                # Add edge with latency
                G.add_edge(hostname, peer_id)
                latency_ms = int(peer["latency_us"]) / 1000
                edge_labels[(hostname, peer_id)] = f"{latency_ms:.1f}ms\nWireGuard"

        # Non-DN42 peers
        if "bgp_peers" in router:
            for peer in router["bgp_peers"]:
                peer_name = peer["name"]
                peer_asn = peer["remote_as"]
                peer_id = f'{peer_name}_{peer_asn}'
                peer_type = peer.get("type", "unknown")

                G.add_node(peer_id)
                node_colors[peer_id] = "#ffa726"  # Orange for non-DN42 peers
                node_labels[peer_id] = f"{peer_name}\nAS{peer_asn}\n{peer_type}"
                other_peers.append(peer_id)

                # Add edge
                G.add_edge(hostname, peer_id)
                edge_labels[(hostname, peer_id)] = "BGP"

    # Create the plot
    plt.figure(figsize=(16, 12), facecolor='white')

    # Use spring layout with custom positioning
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    # Adjust positions: move non-DN42 peers closer to routers, DN42 peers further out
    for router in router_nodes:
        router_pos = pos[router]

        # Move non-DN42 peers closer (0.4x distance)
        for peer in other_peers:
            if G.has_edge(router, peer):
                peer_pos = pos[peer]
                direction = peer_pos - router_pos
                pos[peer] = router_pos + direction * 0.4

        # Move DN42 peers further (1.3x distance)
        for peer in dn42_peers:
            if G.has_edge(router, peer):
                peer_pos = pos[peer]
                direction = peer_pos - router_pos
                pos[peer] = router_pos + direction * 1.3

    # Draw nodes
    for color in ["#4a90e2", "#66bb6a", "#ffa726"]:
        nodes = [n for n in G.nodes() if node_colors[n] == color]
        nx.draw_networkx_nodes(
            G, pos,
            nodelist=nodes,
            node_color=color,
            node_size=4500,
            node_shape='o',
            edgecolors='black',
            linewidths=2
        )

    # Draw edges - iBGP edges first (solid, thicker, darker)
    if ibgp_edges:
        nx.draw_networkx_edges(
            G, pos,
            edgelist=ibgp_edges,
            width=3,
            alpha=0.8,
            edge_color='#2c5aa0',  # Darker blue
            style='solid'
        )

    # Draw external edges (dashed, thinner)
    external_edges = [edge for edge in G.edges() if edge not in ibgp_edges and (edge[1], edge[0]) not in ibgp_edges]
    nx.draw_networkx_edges(
        G, pos,
        edgelist=external_edges,
        width=2,
        alpha=0.5,
        edge_color='#666666',
        style='dashed'
    )

    # Draw labels
    nx.draw_networkx_labels(
        G, pos,
        labels=node_labels,
        font_size=9,
        font_weight='bold',
        font_family='sans-serif'
    )

    # Draw edge labels
    nx.draw_networkx_edge_labels(
        G, pos,
        edge_labels=edge_labels,
        font_size=7,
        font_color='#333333'
    )

    # Add legend
    from matplotlib.lines import Line2D
    legend_elements = [
        mpatches.Patch(facecolor='#4a90e2', edgecolor='black', label='USMAN Routers (AS4242421869)'),
        mpatches.Patch(facecolor='#66bb6a', edgecolor='black', label='DN42 Peers'),
        mpatches.Patch(facecolor='#ffa726', edgecolor='black', label='Non-DN42 Peers'),
        Line2D([0], [0], color='#2c5aa0', linewidth=3, linestyle='-', label='iBGP + IS-IS (Intra-network)'),
        Line2D([0], [0], color='#666666', linewidth=2, linestyle='--', label='eBGP Peering')
    ]
    plt.legend(handles=legend_elements, loc='upper left', fontsize=10)

    plt.title("DN42 Network Topology", fontsize=16, fontweight='bold', pad=20)
    plt.axis('off')
    plt.tight_layout()

    # Save the figure
    output_path = Path(__file__).parent.parent / output_file
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"Topology diagram saved to: {output_path}")

    return output_path

def main():
    """Generate topology diagram."""
    try:
        routers = load_inventory()
        output_file = sys.argv[1] if len(sys.argv) > 1 else "topology.png"
        generate_graph(routers, output_file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
