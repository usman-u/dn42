import yaml
from jinja2 import Environment, FileSystemLoader
import os

with open("config.yaml") as f:
    config = yaml.safe_load(f)

env = Environment(loader=FileSystemLoader("templates"))

wg_template = env.get_template("wg.j2")
bgp_template = env.get_template("bgp.j2")
route_map_template = env.get_template("route_maps.j2")
global_template = env.get_template("global.j2")
common = config.get("global", {})

for node in config["nodes"]:
    node_name = node["name"]
    peers = config.get("peers", {}).get(node_name, [])

    os.makedirs(node_name, exist_ok=True)

    for peer in peers:
        wg_config = wg_template.render(node=node, peer=peer, common=common)
        if peer.get("asn"):
            filename = f"wg{peer['asn']}.conf"

        path = os.path.join(node_name, filename)
        with open(path, "w") as f:
            f.write(wg_config)
        print(f"[+] Generated: {path}")

    global_config_rendered = global_template.render(node=node, common=common)
    bgp_config = bgp_template.render(node=node, peers=peers, common=common)
    frr_path = os.path.join(node_name, "frr.conf")
    with open(frr_path, "w") as f:
        f.write(global_config_rendered)
        f.write(bgp_config)
    print(f"[+] Generated BGP config: {frr_path}")

    route_map_config = route_map_template.render(node=node, peers=peers, common=common)
    
    with open(frr_path, "a") as f:
        f.write("\n")
        f.write("! Route-maps configuration\n")
        f.write(route_map_config)
    
    print(f"[+] Appended route-maps to: {frr_path}")