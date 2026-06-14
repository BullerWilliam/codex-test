import ipaddress
import json
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed


# Replace this with a subnet you own, for example: "192.168.1.0/24"
subnet = "0.0.0.0/0"

# Common ports often seen on IP cameras or their streaming/admin services.
CAMERA_PORTS = (80, 443, 554, 8000, 8080, 8554)
CONNECT_TIMEOUT_SECONDS = 0.35
MAX_WORKERS = 128


def has_open_camera_port(ip_address: str) -> bool:
    for port in CAMERA_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(CONNECT_TIMEOUT_SECONDS)
            if sock.connect_ex((ip_address, port)) == 0:
                return True
    return False


def iter_host_ips(subnet_cidr: str) -> list[str]:
    network = ipaddress.ip_network(subnet_cidr, strict=False)
    return [str(host) for host in network.hosts()]


def find_candidate_camera_ips(subnet_cidr: str) -> list[str]:
    hosts = iter_host_ips(subnet_cidr)
    matches: list[str] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(has_open_camera_port, host): host for host in hosts
        }
        for future in as_completed(future_map):
            host = future_map[future]
            try:
                if future.result():
                    matches.append(host)
            except OSError:
                continue

    return sorted(matches, key=ipaddress.ip_address)


if __name__ == "__main__":
    candidate_ips = find_candidate_camera_ips(subnet)
    print(json.dumps(candidate_ips, indent=2))
