"""Discovery trust boundaries and a real loopback UDP exchange; no LAN probes."""
import json
import socket
import threading
import unittest
from unittest.mock import patch

import team_discovery as discovery


class DiscoveryTests(unittest.TestCase):
    def test_only_safe_https_origins_are_openable(self):
        self.assertEqual(discovery.https_origin('https://Baton.local:8443/'), 'https://baton.local:8443')
        for value in (None, {}, 12, 'http://baton.local', 'javascript:alert(1)', 'https://user:pw@baton.local',
                      'https://baton.local/path', 'https://baton.local/?code=secret', 'https://baton.local/#secret',
                      'https://baton.local:0', 'https://baton.local:99999', 'https://localhost', 'https://127.0.0.1',
                      'https://[::1]', 'https://0.0.0.0', 'https://239.1.2.3'):
            self.assertIsNone(discovery.https_origin(value), value)

    def test_untrusted_packets_are_bounded_and_correlated(self):
        nonce = 'a' * 32
        reply = dict(protocol=discovery.PROTOCOL, kind='host', nonce=nonce, id='b' * 32,
                     name='Studio', port=3004, url='https://studio.local')
        peer = ('192.168.1.2', 45837)
        parsed = discovery.decode(json.dumps(reply).encode(), peer)
        self.assertEqual(discovery.host_record(parsed, peer, nonce, 'c' * 32),
                         dict(name='Studio', address='192.168.1.2:3004', url='https://studio.local'))
        self.assertIsNone(discovery.host_record(parsed, peer, 'd' * 32, 'c' * 32))
        self.assertIsNone(discovery.host_record(parsed, peer, nonce, 'b' * 32))
        for override in ({'port': True}, {'port': 0}, {'port': 65536}, {'name': '\nStudio'}, {'name': 'x' * 81},
                         {'id': 'fake'}, {'kind': 'find'}):
            self.assertIsNone(discovery.host_record({**parsed, **override}, peer, nonce, 'c' * 32))
        for packet in (b'not json', b'[]', b'x' * 1025, b'{' * 1024):
            self.assertIsNone(discovery.decode(packet, peer))
        self.assertIsNone(discovery.decode(json.dumps(reply).encode(), ('8.8.8.8', 1)))
        unsafe = discovery.host_record({**parsed, 'url': 'javascript:alert(1)'}, peer, nonce, 'c' * 32)
        self.assertIsNone(unsafe['url'])

    def test_real_udp_discovery_deduplicates_and_caches_without_project_data(self):
        host = discovery.Discovery('0.0.0.0', 3004, 'https://studio.local')
        host.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        host.socket.bind(('127.0.0.1', 0))
        host.socket.settimeout(.1)
        thread = threading.Thread(target=host.listen)
        thread.start()
        client = discovery.Discovery('127.0.0.1', 3005)
        try:
            with patch.object(discovery, 'GROUP', '127.0.0.1'), patch.object(discovery, 'PORT', host.socket.getsockname()[1]):
                result = client.scan()
            self.assertEqual(result['state'], 'ready')
            self.assertEqual(len(result['hosts']), 1)
            self.assertEqual(result['hosts'][0]['url'], 'https://studio.local')
            self.assertEqual(set(result['hosts'][0]), {'name', 'address', 'url'})
            self.assertEqual(result['advertising'], 'local_only')
            with patch.object(discovery.socket, 'socket', side_effect=AssertionError('cached scan sent packets')):
                self.assertIs(client.scan(), result)
        finally:
            host.close()
            thread.join(1)
            client.close()
        self.assertFalse(thread.is_alive())

    def test_network_failure_and_local_only_listener(self):
        client = discovery.Discovery('127.0.0.1', 3004)
        with patch.object(discovery.socket, 'socket', side_effect=OSError('network unavailable')):
            client.start()
            self.assertEqual(client.scan()['state'], 'unavailable')
        host = discovery.Discovery('0.0.0.0', 3004)
        with patch.object(discovery.socket, 'socket') as factory:
            factory.return_value.bind.side_effect = OSError('port in use')
            host.start()
            self.assertTrue(host.listener_error)
            factory.return_value.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
