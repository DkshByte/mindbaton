#!/usr/bin/env python3
"""Team Baton's stdlib client: explicit session bindings, durable queue and dated context cache.

Run `python3 team_client.py --help`. No global current project and no personal-memory credentials.
"""
import argparse
import getpass
import hashlib
import ipaddress
import json
import os
import queue
from pathlib import Path
import re
import shlex
import sqlite3
import sys
import time
import threading
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request
import uuid

MARKED = re.compile(r'\[team-baton\][\s\S]*?(?:\[/team-baton\]|$)', re.I)


class CaptureError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with os.fdopen(os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(temp), str(path))


def validate_host(host, private=False):
    u = urllib.parse.urlparse(host)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
        raise CaptureError('host must be an HTTP(S) origin without credentials or a path')
    loopback = u.hostname == 'localhost'
    try:
        loopback = loopback or ipaddress.ip_address(u.hostname).is_loopback
    except ValueError:
        pass
    if u.scheme != 'https' and not loopback and not private:
        raise CaptureError('cross-device access requires HTTPS; --private-network is only for an encrypted network')
    return host.rstrip('/')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # credentials must never be forwarded to a different host


class Client:
    def __init__(self, config, root=None, max_bytes=50_000_000):
        self.config = config
        self.host = validate_host(config['host'], config.get('private_network', False))
        self.project, self.token = config['project'], config['token']
        if not re.fullmatch(r'[a-f0-9]{32}', self.project) or not self.token.startswith('tb_'):
            raise CaptureError('need a project ID and project device credential')
        self.scope = digest(self.host + '\n' + self.project + '\n' + digest(self.token))
        self.root = Path(root or Path.home() / '.mindbaton' / 'team')
        path = self.root / self.scope
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path / 'client.db'), isolation_level=None, timeout=10)
        os.chmod(str(path / 'client.db'), 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS bindings(tool TEXT,native TEXT,session TEXT UNIQUE,PRIMARY KEY(tool,native));
          CREATE TABLE IF NOT EXISTS seen(session TEXT,id TEXT,version INTEGER,content TEXT,speaker TEXT,timestamp REAL,signature TEXT,
            PRIMARY KEY(session,id));
          CREATE TABLE IF NOT EXISTS aliases(session TEXT,source TEXT,id TEXT,PRIMARY KEY(session,source));
          CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY,body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS cache(query TEXT PRIMARY KEY,body TEXT NOT NULL,updated REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS status(k TEXT PRIMARY KEY,v TEXT NOT NULL);
        ''')
        if 'signature' not in {row[1] for row in self.db.execute('PRAGMA table_info(seen)')}:
            self.db.execute('ALTER TABLE seen ADD COLUMN signature TEXT')
        self.max_bytes = max_bytes

    def bind(self, tool, native):
        if tool not in ('claude', 'codex') or not native or len(native) > 200:
            raise CaptureError('need claude/codex and an explicit session ID')
        self.db.execute('INSERT OR IGNORE INTO bindings VALUES(?,?,?)', (tool, native, uuid.uuid4().hex))
        return self.bound(tool, native)

    def bound(self, tool, native):
        row = self.db.execute('SELECT session FROM bindings WHERE tool=? AND native=?', (tool, native)).fetchone()
        return row[0] if row else None

    def status(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO status VALUES(?,?)', (key, str(value)))

    def request(self, path, body=None, timeout=3):
        req = urllib.request.Request(self.host + '/team/' + self.project + '/' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        finished = queue.Queue(maxsize=1)
        def fetch():
            try:
                with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as r:
                    finished.put((None, json.load(r)))
            except urllib.error.HTTPError as e:
                try:
                    result = json.loads(e.read())
                except (ValueError, OSError):
                    result = {}
                finished.put((e, result))
            except (OSError, ValueError) as e:
                finished.put((e, {}))
        threading.Thread(target=fetch, daemon=True).start()
        try:
            error, result = finished.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError('project retrieval deadline exceeded') from None
        if error:
            if isinstance(error, urllib.error.HTTPError) and error.code in (401, 403, 409):
                self.status('stopped', result.get('error', f'access denied ({error.code})'))
                self.db.execute('DELETE FROM cache')
            raise error
        return result

    def capture(self, session, turns, ai, model=None, branch=None):
        """Save revisions and network work in one transaction, before attempting delivery."""
        self.db.execute('BEGIN IMMEDIATE')
        try:
            messages = []
            for turn in turns:
                content = MARKED.sub('', turn['content']).strip()
                if not content:
                    continue
                mid, role = turn['id'], turn['speaker']
                if role not in ('user', 'assistant') or not isinstance(mid, str) or len(mid) > 160:
                    raise CaptureError('unsupported visible message')
                old = self.db.execute('SELECT * FROM seen WHERE session=? AND id=?', (session, mid)).fetchone()
                if len(content) > 60000:
                    raise CaptureError('visible message exceeds the host limit; capture retained in the source transcript')
                effective_model = turn.get('model') or (model if role == 'assistant' else None)
                signature = digest(json.dumps([content, role, ai, effective_model, branch]))
                if old and old['signature'] == signature:
                    continue
                version = old['version'] + 1 if old else 1
                ts = old['timestamp'] if old else turn.get('timestamp', time.time())
                msg = dict(message_id=mid, revision=version, speaker=role, content=content, timestamp=ts,
                           ai=ai, **({'model': effective_model} if effective_model else {}),
                           **({'branch': branch} if branch else {}))
                messages.append(msg)
                self.db.execute('INSERT OR REPLACE INTO seen VALUES(?,?,?,?,?,?,?)', (session, mid, version, content, role, ts, signature))
            batch = []
            for msg in messages:
                candidate = batch + [msg]
                if batch and (len(candidate) > 100 or len(json.dumps(dict(session_id=session, messages=candidate, ai=ai)).encode()) > 900000):
                    self.db.execute('INSERT INTO queue(body) VALUES(?)', (json.dumps(dict(session_id=session, messages=batch, ai=ai)),))
                    batch = []
                batch.append(msg)
            if batch:
                self.db.execute('INSERT INTO queue(body) VALUES(?)', (json.dumps(dict(session_id=session, messages=batch, ai=ai)),))
            pending = self.db.execute('SELECT body FROM queue').fetchall()
            if sum(len(row[0].encode()) for row in pending) > self.max_bytes:
                raise CaptureError('capture storage full; existing pending work preserved')
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def flush(self):
        stopped = self.db.execute("SELECT v FROM status WHERE k='stopped'").fetchone()
        if stopped:
            raise CaptureError(stopped[0])
        row = self.db.execute("SELECT v FROM status WHERE k='retry_at'").fetchone()
        if row and float(row[0]) > time.time():
            return False
        for row in self.db.execute('SELECT id,body FROM queue ORDER BY id').fetchall():
            body = json.loads(row['body'])
            try:
                ack = self.request('upload', body)
                expected = {(m['message_id'], m['revision']) for m in body['messages']}
                got = {(m['message_id'], m['revision']) for m in ack.get('accepted', [])}
                if got != expected:
                    raise CaptureError('host acknowledgement did not match; pending update retained')
                self.db.execute('DELETE FROM queue WHERE id=?', (row['id'],))
                self.status('backoff', 0)
                self.status('retry_at', 0)
            except (OSError, ValueError, KeyError) as e:
                old = self.db.execute("SELECT v FROM status WHERE k='backoff'").fetchone()
                delay = min(60, max(1, float(old[0]) * 2 if old else 1))
                self.status('backoff', delay)
                self.status('retry_at', time.time() + delay)
                self.status('error', type(e).__name__)
                return False
        return True

    def briefing(self, query=''):
        stopped = self.db.execute("SELECT v FROM status WHERE k='stopped'").fetchone()
        if stopped:
            return '[team-baton]\nProject access stopped: ' + stopped[0] + '\n[/team-baton]'
        key = query[:500]
        try:
            result = self.request('context?q=' + urllib.parse.quote(key), timeout=3)
            self.db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)', (key, json.dumps(result), time.time()))
            self.db.execute('DELETE FROM cache WHERE query NOT IN (SELECT query FROM cache ORDER BY updated DESC LIMIT 12)')
            return result['text']
        except (OSError, ValueError, KeyError):
            if self.db.execute("SELECT 1 FROM status WHERE k='stopped'").fetchone():
                return '[team-baton]\nProject access stopped. No shared context available.\n[/team-baton]'
            row = self.db.execute('SELECT body,updated FROM cache WHERE query=?', (key,)).fetchone()
            row = row or self.db.execute('SELECT body,updated FROM cache ORDER BY updated DESC LIMIT 1').fetchone()
            if row:
                stamp = datetime.fromtimestamp(row['updated'], timezone.utc).isoformat()
                body = json.loads(row['body'])['text']
                return body.replace('[team-baton]', '[team-baton]\nHost unreachable. Context outdated; cached at ' + stamp + '.', 1)
            return '[team-baton]\nHost unreachable; no shared context available. New messages remain queued.\n[/team-baton]'


def transcript(tool, path):
    """Tested visible-message adapters; unknown records fail explicitly instead of losing a transcript silently."""
    out, model = [], None
    with open(path, encoding='utf-8') as f:
        for number, line in enumerate(f, 1):
            try:
                r = json.loads(line)
            except ValueError as e:
                raise CaptureError(f'unsupported {tool} transcript: invalid JSON on line {number}') from e
            if not isinstance(r, dict):
                raise CaptureError(f'unsupported {tool} transcript record')
            kind = r.get('type')
            if tool == 'claude':
                if kind in ('summary', 'ai-title', 'system', 'progress', 'file-history-snapshot', 'queue-operation', 'last-prompt'):
                    continue
                if kind not in ('user', 'assistant'):
                    raise CaptureError(f'unsupported Claude transcript record: {kind}')
                if r.get('isMeta') or r.get('isSidechain') or r.get('isCompactSummary') or r.get('promptSource') == 'system':
                    continue
                m = r.get('message', {})
                role, content, source = kind, m.get('content'), r.get('uuid') or m.get('id')
            else:
                if kind == 'turn_context':
                    model = r.get('payload', {}).get('model')
                    continue
                if kind in ('session_meta', 'compacted', 'event_msg'):
                    continue
                if kind != 'response_item' or not isinstance(r.get('payload'), dict):
                    raise CaptureError(f'unsupported Codex transcript record: {kind}')
                m = r['payload']
                if m.get('type') in ('reasoning', 'function_call', 'function_call_output', 'custom_tool_call', 'custom_tool_call_output', 'web_search_call', 'local_shell_call'):
                    continue
                if m.get('type') != 'message':
                    raise CaptureError(f'unsupported Codex response item: {m.get("type")}')
                if m.get('role') in ('developer', 'system') or m.get('channel') in ('analysis', 'commentary'):
                    continue
                role, content, source = m.get('role'), m.get('content'), m.get('id')
            if role not in ('user', 'assistant'):
                continue
            if isinstance(content, list):
                visible = []
                for part in content:
                    if not isinstance(part, dict):
                        raise CaptureError('unsupported transcript content block')
                    if part.get('type') in ('text', 'input_text', 'output_text'):
                        visible.append(part.get('text', ''))
                    elif part.get('type') not in ('thinking', 'redacted_thinking', 'tool_use', 'tool_result', 'image', 'input_image', 'output_image'):
                        raise CaptureError('unsupported transcript content type: ' + str(part.get('type')))
                content = '\n'.join(visible)
            if not isinstance(content, str):
                raise CaptureError('unsupported transcript message content')
            content = MARKED.sub('', content).strip()
            if not content:
                continue
            # Codex rollout items may lack IDs: append-only line positions are stable in this tested schema.
            source = str(source or ('line:' + str(number)))
            stamp = r.get('timestamp')
            try:
                ts = datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp() if isinstance(stamp, str) else float(stamp or 0)
            except (ValueError, TypeError):
                raise CaptureError('unsupported transcript timestamp')
            out.append(dict(id=digest(tool + ':' + source), speaker=role, content=content, timestamp=ts, model=(m.get('model') or model) if role == 'assistant' else None))
    return out


def hook(client, tool, payload):
    native = payload.get('session_id')
    session = native and client.bound(tool, native)
    if not session:
        return None  # default Private, including new sessions in the same folder
    event, prompt = payload.get('hook_event_name'), payload.get('prompt', '')
    turns = []
    if payload.get('transcript_path'):
        try:
            turns = transcript(tool, payload['transcript_path'])
        except (CaptureError, OSError) as e:
            client.status('capture_error', str(e))
            print('Team Baton capture error: ' + str(e), file=sys.stderr)
        for turn in turns:
            source = turn['id']
            alias = client.db.execute('SELECT id FROM aliases WHERE session=? AND source=?', (session, source)).fetchone()
            if alias:
                turn['id'] = alias[0]
            elif turn['speaker'] == 'user':
                pending = client.db.execute("""SELECT id FROM seen WHERE session=? AND content=? AND speaker='user'
                  AND id LIKE 'prompt:%' AND id NOT IN (SELECT id FROM aliases WHERE session=?) ORDER BY timestamp LIMIT 1""",
                                           (session, turn['content'], session)).fetchone()
                if pending:
                    turn['id'] = pending[0]
                    client.db.execute('INSERT INTO aliases VALUES(?,?,?)', (session, source, turn['id']))
        client.capture(session, turns, 'Claude Code' if tool == 'claude' else 'Codex', branch=payload.get('branch'))
    if event == 'UserPromptSubmit' and prompt and not (turns and turns[-1]['speaker'] == 'user' and turns[-1]['content'] == MARKED.sub('', prompt).strip()):
        # shortcut: clients without turn IDs use the transcript tail; replace when their hooks expose stable prompt IDs.
        tail = ''
        if payload.get('transcript_path'):
            tail = digest(Path(payload['transcript_path']).read_text())
        mid = 'prompt:' + digest(str(payload.get('turn_id') or tail) + '\n' + prompt)
        client.capture(session, [dict(id=mid, speaker='user', content=prompt)], 'Claude Code' if tool == 'claude' else 'Codex', branch=payload.get('branch'))
    if event in ('SessionStart', 'UserPromptSubmit'):
        return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': client.briefing(prompt)}}
    if event == 'Stop':
        client.flush()
    return None


def install_hooks(tool, path, config):
    """Append our definitions and retain unrelated hooks; leave client trust review to the client."""
    path = Path(path)
    d = json.loads(path.read_text()) if path.exists() else {}
    cmd = shlex.join([sys.executable, str(Path(__file__).resolve()), '--config', str(Path(config).resolve()), 'hook', tool])
    hooks = d.setdefault('hooks', {})
    for event in ('SessionStart', 'UserPromptSubmit', 'Stop'):
        entries = hooks.setdefault(event, [])
        entry = {'hooks': [{'type': 'command', 'command': cmd, 'timeout': 10}]}
        if entry not in entries:
            entries.append(entry)
    if path.exists():
        backup = path.with_name(path.name + '.' + uuid.uuid4().hex + '.bak')
        atomic_json(backup, json.loads(path.read_text()))
    atomic_json(path, d)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='explicit project device configuration file')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init'); init.add_argument('--host', required=True); init.add_argument('--project', required=True)
    init.add_argument('--private-network', action='store_true')
    bind = sub.add_parser('bind'); bind.add_argument('tool', choices=['claude', 'codex']); bind.add_argument('session')
    hooks = sub.add_parser('install-hooks'); hooks.add_argument('tool', choices=['claude', 'codex']); hooks.add_argument('path')
    run = sub.add_parser('hook'); run.add_argument('tool', choices=['claude', 'codex'])
    for name in ('context', 'flush', 'watch', 'status'):
        sub.add_parser(name)
    args = parser.parse_args()
    if args.command == 'init':
        cfg = dict(host=validate_host(args.host, args.private_network), project=args.project,
                   token=getpass.getpass('Project device token: '), private_network=args.private_network)
        c = Client(cfg); c.db.close(); atomic_json(args.config, cfg)
        print('Configured. Sessions remain Private until explicitly bound. Run watch in a terminal for retries.')
        return
    if args.command == 'install-hooks':
        install_hooks(args.tool, args.path, args.config)
        print('Hooks added. Review and trust them in your coding client. Sessions remain Private until bound.')
        return
    c = Client(json.loads(Path(args.config).read_text()))
    try:
        if args.command == 'bind':
            print(c.bind(args.tool, args.session))
        elif args.command == 'hook':
            out = hook(c, args.tool, json.load(sys.stdin))
            if out:
                print(json.dumps(out))
        elif args.command == 'context':
            print(c.briefing())
        elif args.command == 'status':
            print(json.dumps({'pending': c.db.execute('SELECT count(*) FROM queue').fetchone()[0],
                              'status': dict(c.db.execute('SELECT k,v FROM status'))}))
        elif args.command == 'watch':
            while True:
                c.flush()
                time.sleep(1)
        else:
            c.flush()
    finally:
        c.db.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except (OSError, ValueError, KeyError, sqlite3.Error) as e:
        print('Team Baton capture error: ' + str(e), file=sys.stderr)
        sys.exit(1)
