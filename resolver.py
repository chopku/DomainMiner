#!/usr/bin/env python3
"""
DNS Resolver Utility
Resolves a list of domains from an input file to their IPv4 addresses,
deduplicates them, and writes the results to an output file.
"""

import argparse
import ipaddress
import logging
import socket
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("dns_resolver")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Resolve domain lists for multiple interfaces into separate static route files."
    )
    parser.add_argument(
        "-d", "--dir",
        type=str,
        default="domain_list",
        help="Path to the directory containing interface configuration files (default: domain_list)"
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default="resolved",
        help="Path to the directory where resolved route files will be saved (default: resolved)"
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=5.0,
        help="Timeout in seconds for DNS queries (default: 5.0)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging"
    )
    return parser.parse_args()


def read_domains(file_path: Path) -> list[str]:
    """
    Read domains from a file, ignoring empty lines and comments.
    """
    domains = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                # Strip leading/trailing whitespaces
                cleaned_line = line.strip()
                # Skip comments and empty lines
                if not cleaned_line or cleaned_line.startswith("#"):
                    continue
                # Remove inline comments if any (e.g. "google.com # main search")
                if " #" in cleaned_line or "\t#" in cleaned_line:
                    cleaned_line = cleaned_line.split("#", 1)[0].strip()
                
                domains.append(cleaned_line)
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
    return domains


def resolve_domain(domain: str, timeout: float) -> list[str]:
    """
    Resolve a domain to its IPv4 addresses using socket.getaddrinfo.
    Returns a list of unique IPv4 addresses for the domain.
    """
    # Set default timeout for socket operations
    socket.setdefaulttimeout(timeout)
    ips = []
    try:
        # Resolve using IPv4 family only (socket.AF_INET)
        # Port 0 or None can be used since we only care about IP addresses
        results = socket.getaddrinfo(domain, None, socket.AF_INET, socket.SOCK_STREAM)
        for res in results:
            ip = res[4][0]
            if ip not in ips:
                ips.append(ip)
    except socket.gaierror as e:
        # Standard DNS resolution error (e.g., NXDOMAIN, host not found)
        logger.warning(f"Failed to resolve domain '{domain}': {e.strerror} (code: {e.errno})")
    except socket.timeout:
        logger.warning(f"DNS resolution timed out for domain '{domain}' after {timeout}s")
    except Exception as e:
        logger.error(f"Unexpected error resolving domain '{domain}': {e}")
    
    return ips


def main() -> None:
    args = parse_arguments()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    config_dir = Path(args.dir)
    output_dir = Path(args.output_dir)

    if not config_dir.exists() or not config_dir.is_dir():
        logger.error(f"Configuration directory does not exist: {config_dir}")
        sys.exit(1)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find only configuration .txt files in the config directory
    config_files = [f for f in config_dir.iterdir() if f.is_file() and f.suffix.lower() == ".txt"]
    
    if not config_files:
        logger.warning(f"No .txt configuration files found in {config_dir}")
        sys.exit(0)

    logger.info(f"Found {len(config_files)} interface configuration file(s) in {config_dir}")

    for file_path in config_files:
        # The interface name is the filename (without extension, e.g. USA_GEMINI.txt -> USA_GEMINI)
        interface_name = file_path.stem
        logger.info(f"Processing interface '{interface_name}' from file: {file_path.name}")
        
        domains = read_domains(file_path)
        if not domains:
            logger.warning(f"No valid domains found in {file_path.name}. Skipping.")
            continue
            
        logger.info(f"Found {len(domains)} domain(s) for interface '{interface_name}'")

        ip_to_domain = {}
        resolved_count = 0

        for domain in domains:
            logger.debug(f"Resolving '{domain}'...")
            ips = resolve_domain(domain, args.timeout)
            if ips:
                logger.info(f"Resolved '{domain}' -> {', '.join(ips)}")
                for ip in ips:
                    if ip not in ip_to_domain:
                        ip_to_domain[ip] = domain
                resolved_count += 1
            else:
                logger.debug(f"No IPs resolved for '{domain}'")

        # Sort the IP addresses numerically for clean output
        try:
            sorted_ips = sorted(list(ip_to_domain.keys()), key=lambda ip: ipaddress.IPv4Address(ip))
        except Exception as e:
            logger.warning(f"Failed to sort IPs using ipaddress library: {e}. Falling back to default sorting.")
            sorted_ips = sorted(list(ip_to_domain.keys()))

        # Output file name: <interface_name>.txt
        output_file_path = output_dir / f"{interface_name}.txt"
        
        try:
            with open(output_file_path, "w", encoding="utf-8") as f:
                for ip in sorted_ips:
                    domain_name = ip_to_domain[ip]
                    f.write(f"ip route {ip} 255.255.255.255 {domain_name}\n")
            logger.info(f"Successfully wrote {len(sorted_ips)} route(s) to {output_file_path.name}")
            logger.info(f"Stats for '{interface_name}': {resolved_count}/{len(domains)} domains successfully resolved")
        except Exception as e:
            logger.error(f"Failed to write output to file {output_file_path}: {e}")


if __name__ == "__main__":
    main()
