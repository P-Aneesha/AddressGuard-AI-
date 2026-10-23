"""Resolve a hostname through public DNS when the system resolver cannot.

Some home routers fail to resolve managed-database hostnames (for example
Neon's nested *.aws.neon.tech names). When that happens the app looks the name
up directly on public resolvers and hands libpq the IP as ``hostaddr``. The
original hostname is still passed as ``host``, so TLS SNI and certificate
verification are unchanged.
"""
import random
import socket
import struct

PUBLIC_RESOLVERS = ("8.8.8.8", "1.1.1.1")


def system_can_resolve(host, port=5432):
    try:
        socket.getaddrinfo(host, port)
        return True
    except (socket.gaierror, UnicodeError):
        return False


def _build_query(host):
    query_id = random.randint(0, 0xFFFF)
    header = struct.pack(">HHHHHH", query_id, 0x0100, 1, 0, 0, 0)  # recursion desired
    qname = b"".join(bytes([len(label)]) + label.encode("ascii") for label in host.strip(".").split("."))
    return query_id, header + qname + b"\x00" + struct.pack(">HH", 1, 1)  # type A, class IN


def _skip_name(data, offset):
    while True:
        length = data[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:  # compression pointer
            return offset + 2
        offset += length + 1


def _parse_a_records(data, query_id):
    resp_id, flags, qdcount, ancount, _, _ = struct.unpack(">HHHHHH", data[:12])
    if resp_id != query_id or flags & 0x000F:  # mismatched reply or error rcode (e.g. NXDOMAIN)
        return []
    offset = 12
    for _ in range(qdcount):
        offset = _skip_name(data, offset) + 4
    addresses = []
    for _ in range(ancount):
        offset = _skip_name(data, offset)
        rtype, _, _, rdlength = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        if rtype == 1 and rdlength == 4:
            addresses.append(socket.inet_ntoa(data[offset:offset + 4]))
        offset += rdlength
    return addresses


def resolve_via_public_dns(host, resolvers=PUBLIC_RESOLVERS, timeout=3.0):
    """Return the first IPv4 address for ``host`` from a public resolver, or None."""
    for resolver in resolvers:
        query_id, packet = _build_query(host)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(packet, (resolver, 53))
                data, _ = sock.recvfrom(4096)
            addresses = _parse_a_records(data, query_id)
        except (OSError, struct.error, IndexError, UnicodeError):
            continue
        if addresses:
            return addresses[0]
    return None
