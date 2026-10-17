"""Small, IPv4 LAN-only Team Baton discovery. Advertisements contain no project data."""
import ipaddress
import json
import re
import secrets
import socket
import threading
import time
from urllib.parse import urlparse

GROUP, PORT = '239.255.77.66', 45837
PROTOCOL = 'mindbaton-team/1'
NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', '127.0.0.0/8', '100.64.0.0/10'))


def local_peer(address):
    try:
        ip = ipaddress.ip_address(address)
        return any(ip in network for network in NETWORKS)
    except ValueError:
        return False


def https_origin(value):
    try:
        u = urlparse(value)
        if (u.scheme == 'https' and u.hostname and not u.username and not u.password
                and not u.query and not u.fragment and u.path in ('', '/')
                and re.fullmatch(r'[A-Za-z0-9.\[\]:-]{1,255}', u.netloc)
                and u.hostname != 'localhost' and u.port != 0):
            try:
                ip = ipaddress.ip_address(u.hostname)
                if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
                    return None
            except ValueError:
                pass
            return 'https://' + u.netloc.lower()
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def decode(packet, peer):
    if len(packet) > 1024 or not local_peer(peer[0]):
        return None
    try:
        data = json.loads(packet)
        if (isinstance(data, dict) and data.get('protocol') == PROTOCOL
                and isinstance(data.get('nonce'), str) and re.fullmatch(r'[a-f0-9]{32}', data['nonce'])):
            return data
    except (ValueError, UnicodeError, RecursionError):
        pass
    return None


def host_record(data, peer, nonce, own_id):
    if not data or data.get('kind') != 'host' or data.get('nonce') != nonce or data.get('id') == own_id:
        return None
    name, port, identity = data.get('name'), data.get('port'), data.get('id')
    if (not isinstance(name, str) or not 1 <= len(name) <= 80 or not name.strip()
            or any(ord(c) < 32 for c in name) or type(port) is not int or not 1 <= port <= 65535
            or not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity)):
        return None
    return dict(name=name, address=f'{peer[0]}:{port}', url=https_origin(data.get('url')))


class Discovery:
    def __init__(self, host, port, public_url=None):
        self.id, self.port = secrets.token_hex(16), port
        self.name = 'Team Baton · ' + socket.gethostname().split('.')[0][:48]
        self.url = https_origin(public_url)
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == 'localhost'
        self.advertise = bool(self.url) or not loopback
        self.socket = None
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.cached, self.checked = None, 0
        self.listener_error = False

    def start(self):
        if not self.advertise:
            return
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', PORT))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(GROUP) + socket.inet_aton('0.0.0.0'))
            sock.settimeout(.5)
            self.socket = sock
            threading.Thread(target=self.listen, name='team-baton-discovery', daemon=True).start()
        except OSError:
            if sock:
                sock.close()
            self.listener_error = True

    def close(self):
        self.stop.set()
        if self.socket:
            self.socket.close()

    def listen(self):
        last_reply = 0
        while not self.stop.is_set():
            try:
                packet, peer = self.socket.recvfrom(1025)
                data = decode(packet, peer)
                now = time.monotonic()
                if data and data.get('kind') == 'find' and now - last_reply >= .2:
                    last_reply = now  # bound unauthenticated discovery traffic; never read auth or project storage
                    reply = dict(protocol=PROTOCOL, kind='host', nonce=data['nonce'], id=self.id,
                                 name=self.name, port=self.port, url=self.url)
                    self.socket.sendto(json.dumps(reply).encode(), peer)
            except socket.timeout:
                continue
            except OSError:
                if not self.stop.is_set():
                    self.listener_error = True
                return

    def scan(self):
        # shortcut: IPv4 multicast uses the default interface; add interface selection if multi-LAN installs need it.
        with self.lock:
            if self.cached is not None and time.monotonic() - self.checked < 10:
                return self.cached
            hosts, nonce, error = {}, secrets.token_hex(16), False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.bind(('', 0))
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                    query = json.dumps(dict(protocol=PROTOCOL, kind='find', nonce=nonce)).encode()
                    deadline = time.monotonic() + 2
                    next_send = 0
                    while time.monotonic() < deadline and len(hosts) < 32:
                        now = time.monotonic()
                        if now >= next_send:
                            sock.sendto(query, (GROUP, PORT))
                            next_send = now + .75
                        sock.settimeout(max(.001, min(deadline, next_send) - time.monotonic()))
                        try:
                            packet, peer = sock.recvfrom(1025)
                        except socket.timeout:
                            continue
                        record = host_record(decode(packet, peer), peer, nonce, self.id)
                        if record:
                            hosts[record['url'] or record['address']] = record
            except OSError:
                error = True
            self.cached = dict(state='unavailable' if error else 'ready', hosts=sorted(hosts.values(), key=lambda h: h['name'].casefold()),
                               advertising='unavailable' if self.listener_error else 'https' if self.url else 'needs_https' if self.advertise else 'local_only',
                               checked_at=time.time())
            self.checked = time.monotonic()
            return self.cached
