"""Isolated synthetic host for the optional Chromium UI check; never starts AI workers."""
import json
import argparse
import os
import sys
import tempfile
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(MINDBATON_AI='0', MINDBATON_TEAM='1', MINDBATON_BRAIN='off')
import server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lan', action='store_true', help='Advertise a temporary HTTPS LAN test host')
    parser.add_argument('--port', type=int, default=3162, help='Port for --lan (default: 3162)')
    args = parser.parse_args()
    address = server.lan_ip() if args.lan else '127.0.0.1'
    if not address:
        parser.error('No IPv4 LAN address found')
    with tempfile.TemporaryDirectory() as data:
        server.open_data(data)
        aid = server.create_account('fixture', server.hash_password('fixture-only-password'), 'Maya', role='admin')
        server.AUTH.execute('UPDATE accounts SET welcomed=?,terms=? WHERE id=?',(time.time(),time.time(),aid))
        project = server.TEAM.create(aid, 'LAN test project' if args.lan else 'Relay engine')
        who = server.TEAM.access(project['id'], owner={'via':'session', 'account':aid})
        server.TEAM.settings(who, {'goals':'Keep discoveries available across coding clients and browser chats.'})
        server.TEAM.publish(who, {'kind':'decision', 'content':'Use a separate database for every project.'})
        server.TEAM.upload(who, {'session_id':'fixture-codex', 'ai':'Codex', 'title':'Queue investigation', 'messages':[
            {'message_id':'one','revision':1,'speaker':'assistant','content':'The queue saves revisions before networking.','timestamp':1792240000}]})
        http = ThreadingHTTPServer(('0.0.0.0' if args.lan else '127.0.0.1', args.port if args.lan else 0),server.Handler)
        base = f"{'https' if args.lan else 'http'}://{address}:{http.server_port}"
        ready = {'base':base, 'project':project['id'], 'dataRoot':data}
        if args.lan:
            import ssl
            import subprocess
            cert, key = str(Path(data, 'cert.pem')), str(Path(data, 'key.pem'))
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                            '-keyout', key, '-out', cert, '-subj', '/CN=Mindbaton LAN test',
                            '-addext', f'subjectAltName=IP:{address},IP:127.0.0.1,DNS:localhost'],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.chmod(key, 0o600)
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(cert, key)
            http.socket = tls.wrap_socket(http.socket, server_side=True)
            server.TEAM.discovery = server.team.team_discovery.Discovery('0.0.0.0', http.server_port, base)
            server.TEAM.discovery.name = 'Team Baton · LAN test'
            server.TEAM.discovery.start()
            server.TEAM.settings(who, {'goals':'Synthetic project for testing LAN discovery. No personal data.'})
            ready.update(invite=server.TEAM.invite(project['id'])['code'], username='fixture', password='fixture-only-password')
        print(json.dumps(ready),flush=True)
        try:
            http.serve_forever()
        finally:
            http.server_close()
            server.TEAM.close()
            server.AUTH.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
