"""Synthetic Team Baton storage, auth, outage and provider failure release gates."""
import copy
import http.client
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

os.environ['MINDBATON_AI'] = '0'
import server
import ai
import team
import team_client


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.auth = sqlite3.connect(':memory:', isolation_level=None, check_same_thread=False)
        self.auth.execute('CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT)')
        self.store = team.Team(self.auth, self.tmp.name, threading.RLock())
        self.p = self.store.create(1, 'Synthetic project')
        self.host = self.store.access(self.p['id'], owner={'via': 'session', 'account': 1})
        self.joined, self.token, self.member = self.enroll(self.p['id'])

    def tearDown(self):
        self.store.close()
        self.auth.close()
        self.tmp.cleanup()

    def enroll(self, pid, name='Maya'):
        invite = self.store.invite(pid)
        joined = self.store.join({'code': invite['code'], 'name': name}, name)
        self.store.approve(pid, joined['request'], True)
        token = self.store.poll(joined['poll'])['token']
        return joined, token, self.store.access(pid, token)

    def upload(self, who=None, content='Queue durability discovery', version=1, mid='same', session='same', timestamp=1):
        return self.store.upload(who or self.member, dict(session_id=session, messages=[dict(message_id=mid,
            revision=version, speaker='assistant', content=content, timestamp=timestamp)]))

    def test_project_isolation_identical_ids(self):
        p2 = self.store.create(2, 'Other project')
        _, token, other = self.enroll(p2['id'], 'Rui')
        self.upload(content='quillbeam isolated discovery')
        self.upload(other, content='driftwren different discovery')
        self.assertNotIn('quillbeam', json.dumps(self.store.context(other)))
        self.assertNotIn('driftwren', json.dumps(self.store.context(self.member)))
        with self.assertRaises(team.Error):
            self.store.access(p2['id'], self.token)
        with self.assertRaises(team.Error):
            self.store.access(self.p['id'], token)
        self.assertNotEqual(self.store.db(other), self.store.db(self.member))

    def test_short_invites_format_normalization_and_collisions(self):
        other = self.store.create(2, 'Other project')
        with patch('team.secrets.choice', side_effect=list('ABC234ABC234DEF567')):
            first = self.store.invite(self.p['id'])
            second = self.store.invite(other['id'])
        self.assertEqual(first['code'], 'ABC-234')
        self.assertEqual(second['code'], 'DEF-567')
        for code in ('abc-234', 'ABC234', 'abc234'):
            joined = self.store.join({'code': code, 'name': 'Rui'}, 'formats')
            self.assertEqual(joined['project'], self.p['id'])
        self.assertNotIn(first['code'], str(self.auth.execute('SELECT invite_hash FROM team_projects').fetchall()))
        for _ in range(10):
            code = self.store.invite(self.p['id'])['code']
            self.assertRegex(code, r'^[A-HJ-NP-Z2-9]{3}-[A-HJ-NP-Z2-9]{3}$')
            self.assertTrue(any(c.isdigit() for c in code))
            self.assertTrue(any(c.isalpha() for c in code))
        self.assertIsNone(self.store.invite(self.p['id'], False)['code'])

    def test_short_invites_reject_symbols_and_limit_attempts(self):
        for code in ('ABC_234', 'AB-234', 'ABC--234', 'ABC 234', 'ABC@23', 'ABC2345',
                     'ＡBC234', 'ßBC234', 'ABC234\nXYZ', 'long-old-invite-code'):
            with self.subTest(code=code), self.assertRaises(team.Error) as caught:
                self.store.join({'code': code, 'name': 'Rui'}, 'invalid')
            self.assertEqual(caught.exception.status, 400)
        for _ in range(30):
            with self.assertRaises(team.Error):
                self.store.join({'code': '@', 'name': 'Rui'}, 'limited')
        with self.assertRaises(team.Error) as caught:
            self.store.join({'code': 'ABC234', 'name': 'Rui'}, 'limited')
        self.assertEqual(caught.exception.status, 429)

    def test_project_health_is_read_only_and_reports_sharing_states(self):
        self.upload(content='Synthetic shared discovery')
        old = self.store.publish(self.host, {'kind': 'progress', 'content': 'Old report'})
        self.store.publish(self.host, {'kind': 'correction', 'content': 'Corrected report', 'replaces': old['id']})
        db = self.store.db(self.host)
        revision = self.store.meta(db, 'revision')
        summary = self.store.project_summary(self.p)
        self.assertEqual(summary['health']['state'], 'running')
        self.assertEqual(summary['counts'], {'conversations': 1, 'updates': 1, 'people': 2})
        self.assertEqual(self.store.meta(db, 'revision'), revision)
        provider, model = ai.team_models()[0]
        self.store.settings(self.host, {'settings': {'external': True, 'provider': provider, 'model': model, 'budget': 0}})
        db.execute("INSERT INTO jobs(session,revision,first_changed,due,status,error) VALUES('fixture',1,0,0,'pending','budget exhausted')")
        self.assertEqual(self.store.project_summary(self.p)['health']['state'], 'attention')
        self.store.settings(self.host, {'archived': True})
        self.assertEqual(self.store.project_summary(self.p)['health']['state'], 'paused')

    def test_project_health_does_not_recreate_missing_or_bad_storage(self):
        other = self.store.create(2, 'Broken project')
        self.store.dbs.pop(other['id']).close()
        path = Path(self.tmp.name, 'projects', other['id'], 'project.db')
        path.unlink()
        summary = self.store.project_summary(other)
        self.assertEqual(summary['health']['state'], 'unavailable')
        self.assertFalse(path.exists())
        with self.assertRaises(team.Error) as caught:
            self.store.db({'project': other['id']})
        self.assertEqual(caught.exception.status, 503)
        self.assertIsNone(self.store.next_job())
        self.assertFalse(path.exists())
        self.assertNotIn(self.tmp.name, json.dumps(summary))
        path.write_bytes(b'not a SQLite database')
        self.assertEqual(self.store.project_summary(other)['health']['state'], 'unavailable')
        self.assertEqual(self.store.project_summary(self.p)['health']['state'], 'running')

    def test_invites_rotation_expiry_and_approval(self):
        old = self.store.invite(self.p['id'])
        self.store.invite(self.p['id'])
        with self.assertRaises(team.Error):
            self.store.join({'code': old['code'], 'name': 'Rui'}, 'ip')
        new = self.store.invite(self.p['id'])
        self.auth.execute('UPDATE team_projects SET invite_until=0')
        with self.assertRaises(team.Error):
            self.store.join({'code': new['code'], 'name': 'Rui'}, 'ip')
        again = self.store.poll(self.joined['poll'])
        self.assertEqual(again['token'], self.token)
        self.assertNotIn(self.token, str(self.auth.execute('SELECT * FROM team_credentials').fetchall()))
        self.store.revoke(self.p['id'], self.member['member'])
        with self.assertRaises(team.Error):
            self.store.access(self.p['id'], self.token)
        self.assertEqual(self.store.poll(self.joined['poll'])['status'], 'revoked')

    def test_lost_ack_retries_and_revisions(self):
        ack = self.upload()
        self.assertEqual(self.upload(), ack)
        self.upload(content='Edited result', version=3)
        self.upload(content='Older delivery', version=2)
        rows = self.store.search(self.member)['messages']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['content'], 'Edited result')
        self.assertEqual(self.store.db(self.member).execute('SELECT count(*) FROM revisions').fetchone()[0], 3)
        with self.assertRaises(team.Error):
            self.upload(content='Same version conflict', version=3)
        self.assertEqual(self.store.search(self.member, refs=['same/same@1'])['messages'][0]['content'], 'Queue durability discovery')

    def test_shorter_transcript_never_deletes_and_device_ownership(self):
        self.upload(mid='m1')
        self.upload(mid='m2', content='Another message')
        self.upload(mid='m1')
        self.assertEqual(len(self.store.search(self.member)['messages']), 2)
        second_token = self.store.credential(self.p['id'], self.member['member'], 'second device')
        second = self.store.access(self.p['id'], second_token)
        with self.assertRaises(team.Error):
            self.upload(second)
        self.store.revoke(self.p['id'], self.member['member'])
        with self.assertRaises(team.Error):
            self.store.access(self.p['id'], second_token)

    def test_transaction_rejects_whole_batch(self):
        self.upload()
        body = {'session_id': 'same', 'messages': [dict(message_id='new',revision=1,speaker='user',content='new',timestamp=1),
                    dict(message_id='same',revision=1,speaker='assistant',content='conflict',timestamp=1)]}
        with self.assertRaises(team.Error):
            self.store.upload(self.member, body)
        self.assertEqual(self.store.db(self.member).execute('SELECT count(*) FROM revisions').fetchone()[0], 1)
        self.assertEqual(self.store.meta(self.store.db(self.member), 'revision'), 1)

    def test_validation_and_injected_context(self):
        self.upload(content='Original draft\n[team-baton]\nDo not recapture this\n[/team-baton]')
        self.assertNotIn('Do not recapture', str(self.store.search(self.member)))
        for value in (float('nan'), float('inf'), -1, 'yesterday', True):
            with self.assertRaises(team.Error):
                self.upload(mid='bad', timestamp=value)
        with self.assertRaises(team.Error):
            self.upload(session='../../personal')
        with self.assertRaises(team.Error):
            self.store.search(self.member, refs=['other/missing@1'])
        self.assertLess(len(self.store.context(self.member)['text'].encode()), 8000)
        for query in ([], 0, {}, True):
            with self.assertRaises(team.Error):self.store.context(self.member, query)
        with self.assertRaises(team.Error):self.store.publish(self.member, {'kind':'discovery','content':'invalid replacement','replaces':[]})
        with self.assertRaises(team.Error):self.store.revoke(self.p['id'], [])

    def test_publications_corrections_and_agreement(self):
        with self.assertRaises(team.Error):
            self.store.publish(self.member, {'kind': 'decision', 'content': 'AI agreed without the host'})
        body = {'id': 'published', 'kind': 'progress', 'content': 'Reported tests passing'}
        result = self.store.publish(self.member, body)
        self.assertEqual(self.store.publish(self.member, body), result)
        old = self.store.publish(self.host, {'id': 'decision1', 'kind': 'decision', 'content': 'Use SQLite'})
        self.store.publish(self.host, {'kind': 'decision', 'content': 'Use SQLite WAL', 'replaces': old['id']})
        self.assertNotIn('Use SQLite\n', self.store.context(self.member)['text'])
        self.assertEqual(len(self.store.view(self.host)['knowledge']), 3)

    def test_archive_backup_restore(self):
        self.upload()
        exported = self.store.export(self.host)
        self.store.backup(self.host)
        saved = next((Path(self.tmp.name) / 'project_backups').glob('*.json'))
        self.assertEqual(json.loads(saved.read_text()), exported)
        restored = self.store.restore(3, exported)
        self.assertNotEqual(restored['id'], self.p['id'])
        owner = self.store.access(restored['id'], owner={'via': 'session', 'account': 3})
        self.assertIn('Queue durability discovery', self.store.context(owner)['text'])
        with self.assertRaises(team.Error):
            self.store.access(restored['id'], self.token)
        self.assertFalse(self.store.view(owner)['settings']['external'])
        self.store.settings(self.host, {'archived': True})
        with self.assertRaises(team.Error):
            self.upload(mid='new')
        self.assertIn('Queue durability', self.store.context(self.member)['text'])
        corrupt = copy.deepcopy(exported); corrupt['tables']['messages'][0]['bogus'] = 1
        count = self.auth.execute('SELECT count(*) FROM team_projects').fetchone()[0]
        with self.assertRaises(team.Error):
            self.store.restore(3, corrupt)
        self.assertEqual(self.auth.execute('SELECT count(*) FROM team_projects').fetchone()[0], count)

    def enable_processing(self):
        self.store.settings(self.host, {'settings': {'external': True, 'provider': 'OpenAI', 'model': 'gpt-6-luna', 'budget': 1}})
        self.store.db(self.host).execute('UPDATE jobs SET due=0')

    def summary(self):
        return json.dumps({'summary': 'Queue is durable', 'sources': ['same/same@1'],
                           'items': [{'kind': 'decision', 'content': 'Reported SQLite choice', 'sources': ['same/same@1']}]})

    def test_ai_is_opt_in_batching_and_budget(self):
        self.upload()
        self.assertIsNone(self.store.next_job())
        self.enable_processing()
        db = self.store.db(self.host)
        job = self.store.next_job()
        self.assertEqual(job['revision'], 1)
        self.assertGreater(db.execute('SELECT estimate FROM usage').fetchone()[0], 0)
        self.assertGreater(self.store.view(self.host)['usage_estimate'], 0)
        self.store.finish_job(job, self.summary())
        self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0], 'done')
        self.assertEqual(db.execute('SELECT kind,origin FROM knowledge').fetchone()[:], ('proposal','unverified AI'))
        self.upload(version=2, content='New message revision')
        self.store.settings(self.host, {'settings': {'external': True, 'provider': 'OpenAI', 'model': 'gpt-6-luna', 'budget': 0}})
        db.execute('UPDATE jobs SET due=0')
        self.assertIsNone(self.store.next_job())
        self.assertIn('budget exhausted', db.execute('SELECT error FROM jobs').fetchone()[0])
        self.assertIn('New message revision', self.store.context(self.member)['text'])

    def test_ai_invalid_failure_and_stale_result(self):
        self.upload(); self.enable_processing()
        job = self.store.next_job()
        self.store.finish_job(job, '{invalid')
        db = self.store.db(self.host)
        self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0], 'pending')
        self.assertFalse(db.execute('SELECT 1 FROM summaries').fetchone())
        db.execute('UPDATE jobs SET due=0')
        job = self.store.next_job()
        self.upload(version=2, content='newer discovery')
        self.store.finish_job(job, self.summary())
        self.assertFalse(db.execute('SELECT 1 FROM summaries').fetchone())
        self.assertEqual(db.execute('SELECT revision,status FROM jobs').fetchone()[:], (self.store.meta(db,'revision'), 'pending'))

    def test_summary_cache_separates_identical_ids_in_different_sessions(self):
        self.upload(session='one'); self.upload(session='two', content='Different session')
        self.enable_processing()
        first = self.store.next_job(); second = self.store.next_job()
        self.assertNotEqual(first['key'], second['key'])

    def test_restore_preserves_source_graph_and_summaries(self):
        self.upload(); self.enable_processing()
        self.store.finish_job(self.store.next_job(), self.summary())
        self.store.publish(self.member, {'kind':'discovery', 'content':'Evidence-backed report', 'sources':['same/same@1']})
        restored=self.store.restore(4,self.store.export(self.host))
        who=self.store.access(restored['id'],owner={'via':'session','account':4})
        self.assertIn('Queue is durable',self.store.context(who)['text'])
        self.assertEqual(self.store.search(who,refs=['same/same@1'])['messages'][0]['content'],'Queue durability discovery')
        self.assertEqual(len(self.store.view(who)['knowledge']),2)

    def test_batching_has_one_minute_maximum(self):
        with patch.object(team.time,'time',return_value=100): self.upload()
        with patch.object(team.time,'time',return_value=140): self.upload(mid='later')
        job=self.store.db(self.host).execute('SELECT first_changed,due FROM jobs').fetchone()
        self.assertEqual(job[:],(100,155))
        with patch.object(team.time,'time',return_value=154): self.upload(mid='latest')
        self.assertEqual(self.store.db(self.host).execute('SELECT due FROM jobs').fetchone()[0],160)

    def test_host_restart_recovers_interrupted_job(self):
        self.upload(); self.enable_processing(); self.store.next_job()
        self.store.close()
        self.store = team.Team(self.auth, self.tmp.name, threading.RLock())
        db = self.store.db(self.store.access(self.p['id'], self.token))
        self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0], 'pending')
        self.assertIn('Queue durability', self.store.context(self.member)['text'])


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = dict(host='http://127.0.0.1:3004', project='a'*32, token='tb_device')
        self.client = team_client.Client(self.cfg, root=self.tmp.name)
        self.sid = self.client.bind('codex', 'explicit-session')
        self.turn = dict(id='visible', speaker='assistant', content='A completed visible response', timestamp=1)

    def tearDown(self):
        self.client.db.close(); self.tmp.cleanup()

    def test_private_default_and_scoped_cache(self):
        self.assertIsNone(self.client.bound('codex', 'new-session'))
        self.assertIsNone(team_client.hook(self.client, 'codex', {'session_id': 'new-session','hook_event_name':'Stop'}))
        second = team_client.Client(dict(self.cfg, token='tb_other'), root=self.tmp.name)
        self.assertNotEqual(self.client.scope, second.scope)
        self.assertEqual(second.db.execute('SELECT count(*) FROM queue').fetchone()[0], 0)
        second.db.close()
        with self.assertRaises(team_client.CaptureError):
            team_client.validate_host('http://mindbaton.example.com')

    def test_queue_restart_lost_ack_and_storage_full(self):
        self.client.capture(self.sid, [self.turn], 'Codex')
        self.client.db.close()
        self.client = team_client.Client(self.cfg, root=self.tmp.name)
        self.assertEqual(self.client.db.execute('SELECT count(*) FROM queue').fetchone()[0], 1)
        deliveries = []
        def fail(path, body, timeout=3):
            deliveries.append(body)
            raise OSError('lost acknowledgement')
        with patch.object(self.client, 'request', fail): self.assertFalse(self.client.flush())
        self.client.status('retry_at', 0)
        def accept(path, body, timeout=3):
            deliveries.append(body)
            return {'accepted': [{'message_id':m['message_id'], 'revision':m['revision']} for m in body['messages']]}
        with patch.object(self.client, 'request', accept): self.assertTrue(self.client.flush())
        self.assertEqual(deliveries[0], deliveries[1])
        self.client.max_bytes = 1
        with self.assertRaises(team_client.CaptureError):
            self.client.capture(self.sid, [dict(self.turn,id='new')], 'Codex')
        self.assertFalse(self.client.db.execute("SELECT 1 FROM seen WHERE id='new'").fetchone())

    def test_dated_outage_briefing_and_feedback_exclusion(self):
        with patch.object(self.client, 'request', return_value={'text':'[team-baton]\nsource\n[/team-baton]'}):
            self.client.briefing('task')
        with patch.object(self.client, 'request', side_effect=OSError('offline')):
            self.assertIn('cached at', self.client.briefing('task'))
        self.client.capture(self.sid, [dict(self.turn,content='Original\n[team-baton]\nexclude\n[/team-baton]')], 'Codex')
        body = self.client.db.execute('SELECT body FROM queue').fetchone()[0]
        self.assertNotIn('exclude', body)
        self.client.status('stopped','revoked')
        self.assertIn('revoked',self.client.briefing())
        with self.assertRaises(team_client.CaptureError): self.client.flush()

    def test_model_metadata_changes_create_revisions(self):
        self.client.capture(self.sid,[self.turn],'Codex','synthetic-model-one')
        self.client.capture(self.sid,[self.turn],'Codex','synthetic-model-two')
        bodies=[json.loads(r[0]) for r in self.client.db.execute('SELECT body FROM queue')]
        self.assertEqual([b['messages'][0]['revision'] for b in bodies],[1,2])
        self.assertEqual(bodies[-1]['messages'][0]['model'],'synthetic-model-two')

    def test_retrieval_deadline_and_hook_prompt_dedup(self):
        release=threading.Event()
        class SlowOpener:
            def open(self,*args,**kwargs):
                release.wait(1)
                raise OSError('slow host')
        try:
            with patch.object(team_client.urllib.request,'build_opener',return_value=SlowOpener()):
                with self.assertRaises(TimeoutError):self.client.request('context',timeout=0.02)
                self.assertFalse(release.is_set())
        finally:release.set()
        path=Path(self.tmp.name)/'current.jsonl'
        path.write_text(json.dumps({'type':'response_item','timestamp':'2026-10-17T12:00:00Z','payload':
            {'type':'message','role':'user','content':[{'type':'input_text','text':'Already recorded prompt'}]}})+'\n')
        with patch.object(self.client,'briefing',return_value='synthetic briefing'):
            team_client.hook(self.client,'codex',{'session_id':'explicit-session','hook_event_name':'UserPromptSubmit',
                                                'prompt':'Already recorded prompt','transcript_path':str(path)})
        self.assertEqual(self.client.db.execute('SELECT count(*) FROM seen').fetchone()[0],1)

    def test_large_batches_fit_host_request_limit(self):
        turns=[dict(id='message'+str(i),speaker='assistant',content='x'*60000,timestamp=i) for i in range(25)]
        self.client.capture(self.sid,turns,'Codex')
        bodies=[r[0] for r in self.client.db.execute('SELECT body FROM queue')]
        self.assertGreater(len(bodies),1)
        self.assertTrue(all(len(b.encode())<1_000_000 for b in bodies))
        self.assertEqual(sum(len(json.loads(b)['messages']) for b in bodies),25)

    def test_hooks_merge_idempotently_and_adapters(self):
        path = Path(self.tmp.name) / 'hooks.json'
        path.write_text(json.dumps({'hooks':{'Stop':[{'hooks':[{'command':'existing hook','type':'command'}]}]}}))
        team_client.install_hooks('codex', path, Path(self.tmp.name)/'config.json')
        team_client.install_hooks('codex', path, Path(self.tmp.name)/'config.json')
        d=json.loads(path.read_text())
        self.assertEqual(len(d['hooks']['Stop']),2)
        self.assertEqual(d['hooks']['Stop'][0]['hooks'][0]['command'],'existing hook')
        fixtures = Path(__file__).parent / 'fixtures'
        for tool in ('codex','claude'):
            turns=team_client.transcript(tool, fixtures / (tool+'-team.jsonl'))
            self.assertEqual([t['speaker'] for t in turns],['user','assistant'])
            self.assertNotIn('secret reasoning',json.dumps(turns))
            self.assertNotIn('injected briefing',json.dumps(turns))
        bad=Path(self.tmp.name)/'bad.jsonl';bad.write_text('{"type":"future_wire_format"}\n')
        with self.assertRaisesRegex(team_client.CaptureError,'unsupported Codex'):
            team_client.transcript('codex',bad)


class ProviderTests(unittest.TestCase):
    def test_project_provider_selection_and_host_budget(self):
        import ai
        from unittest.mock import MagicMock
        reply=MagicMock()
        reply.__enter__.return_value=reply
        reply.read.return_value=json.dumps({'choices':[{'message':{'content':'{"summary":"Synthetic"}'}}],
            'usage':{'prompt_tokens':10,'completion_tokens':10}}).encode()
        with patch.object(ai,'keys',return_value={'OPENAI_KEY':'synthetic','GEMINI_KEY':'synthetic'}), \
             patch.object(ai,'enabled',return_value=True), patch.object(ai,'spend',return_value={'usd':0}), \
             patch.object(ai,'MONTH_CAP',1), patch.object(ai,'_spent') as spent, \
             patch.object(ai.urllib.request,'urlopen',return_value=reply) as network:
            self.assertEqual(ai.team_chat('Synthetic prompt','OpenAI','gpt-6-luna'),'{"summary":"Synthetic"}')
            request=network.call_args.args[0]
            self.assertEqual(json.loads(request.data)['model'],'gpt-6-luna')
            self.assertEqual(network.call_count,1)
            spent.assert_called_once()
        with patch.object(ai,'keys',return_value={'OPENAI_KEY':'synthetic'}),patch.object(ai,'enabled',return_value=True), \
             patch.object(ai,'spend',return_value={'usd':0}),patch.object(ai,'MONTH_CAP',0), \
             patch.object(ai.urllib.request,'urlopen') as network:
            self.assertIsNone(ai.team_chat('Synthetic prompt','OpenAI','gpt-6-luna'))
            network.assert_not_called()
        with patch.object(ai,'keys',return_value={'OPENAI_KEY':'synthetic','GEMINI_KEY':'synthetic'}), \
             patch.object(ai,'enabled',return_value=True),patch.object(ai.urllib.request,'urlopen',side_effect=TimeoutError) as network:
            self.assertIsNone(ai.team_chat('Synthetic prompt','Gemini',ai.PROVIDERS[0][3]))
            self.assertEqual(network.call_count,1,'selected provider failure must not try a paid fallback')


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'MINDBATON_TEAM':'1'});self.env.start()
        server.open_data(self.tmp.name)
        self.srv=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=self.srv.serve_forever,daemon=True).start()
        _, h, _=self.call('POST','/api/auth/setup',{'username':'maya','password':'synthetic-password'})
        self.cookie=h['Set-Cookie'].split(';')[0]
        _,_,p=self.call('POST','/team/projects',{'name':'Synthetic HTTP project'},cookie=self.cookie)
        self.pid=p['id']
        _,_,d=self.call('POST',self.path('devices'),{'name':'Codex'},cookie=self.cookie)
        self.token=d['token']

    def tearDown(self):
        self.srv.shutdown();self.srv.server_close();server.TEAM.close()
        for g in server.GRAPHS.values():g.db.close()
        server.GRAPHS.clear();server.AUTH.close();server.AUTH=None;server.TEAM=None
        self.env.stop();self.tmp.cleanup()

    def path(self,action):return '/team/'+self.pid+'/'+action

    def call(self,method,path,body=None,cookie=None,token=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.srv.server_port,timeout=5)
        hdr={'Content-Type':'application/json',**(headers or {})}
        if cookie:hdr['Cookie']=cookie
        if token:hdr['Authorization']='Bearer '+token
        conn.request(method,path,json.dumps(body) if body is not None else None,hdr)
        r=conn.getresponse();data=r.read();out=(r.status,dict(r.getheaders()),json.loads(data) if data else {})
        conn.close();return out

    def test_project_list_health_stays_host_scoped(self):
        status, _, data = self.call('GET', '/team/projects', cookie=self.cookie)
        self.assertEqual(status, 200)
        self.assertGreater(data['checked_at'], 0)
        self.assertEqual([p['id'] for p in data['projects']], [self.pid])
        self.assertEqual(data['projects'][0]['health']['state'], 'running')
        self.assertEqual(self.call('GET', '/team/projects', token=self.token)[0], 403)

    def test_project_token_cannot_reach_personal_or_admin(self):
        for path in ('/graph','/export','/mcp','/api/accounts','/team/projects'):
            self.assertEqual(self.call('GET',path,token=self.token)[0],403,path)
        self.assertEqual(self.call('GET',self.path('view'),token=self.token)[0],200)
        for action in ('invite','approve','revoke','settings','backup','export'):
            self.assertEqual(self.call('POST',self.path(action),{},token=self.token)[0],403,action)
        self.assertEqual(self.call('GET',self.path('view'),token=self.token,headers={'X-Forwarded-Proto':'https','Host':'mindbaton.example.com'})[0],200)
        self.assertEqual(self.call('GET',self.path('view'),token=self.token,headers={'Host':'192.0.2.9'})[0],403)

    def test_discovery_preserves_transport_and_origin_checks_without_project_lock(self):
        self.assertEqual(self.call('GET', '/team/discovery')[2], {'state': 'disabled', 'hosts': []})
        class FakeDiscovery:
            def scan(inner):
                self.assertFalse(server.LOCK._is_owned())
                return {'state': 'ready', 'hosts': []}
            def close(inner):
                pass
        server.TEAM.discovery = FakeDiscovery()
        self.assertEqual(self.call('GET', '/team/discovery')[0], 200)
        for code, expected in ((None, 400), ('', 400), ('ZZZ-999', 403)):
            self.assertEqual(self.call('POST', '/team/join', {'code': code, 'name': 'Discovery guest'})[0], expected)
        invite = server.TEAM.invite(self.pid)
        status, _, joined = self.call('POST', '/team/join', {'code': invite['code'], 'name': 'Discovery guest', 'kind': 'browser'})
        self.assertEqual(status, 200)
        self.assertEqual(self.call('POST', '/team/poll', {'poll': joined['poll']})[2]['status'], 'pending')
        self.assertEqual(self.call('GET', self.path('view'))[0], 403)
        self.assertEqual(self.call('GET', '/team/discovery', headers={'Origin': 'https://other.example'})[0], 403)
        self.assertEqual(self.call('GET', '/team/discovery', headers={'Host': '192.0.2.9'})[0], 403)
        with patch.dict(os.environ, {'MINDBATON_TEAM': '0'}):
            self.assertEqual(self.call('GET', '/team/discovery')[0], 404)

    def test_mixed_coding_clients_and_real_host_outage(self):
        fixtures=Path(__file__).parent/'fixtures'
        root=Path(self.tmp.name)/'clients'
        base='http://127.0.0.1:'+str(self.srv.server_port)
        first_cfg=dict(host=base,project=self.pid,token=self.token)
        first=team_client.Client(first_cfg,root=root)
        self.addCleanup(lambda:first.db.close())
        first.bind('codex','synthetic-codex-session')
        first.capture(first.bound('codex','synthetic-codex-session'),team_client.transcript('codex',fixtures/'codex-team.jsonl'),'Codex')
        original=first.request
        def lost_ack(path,body=None,timeout=3):
            original(path,body,timeout)
            raise OSError('connection dropped after server commit')
        with patch.object(first,'request',lost_ack):self.assertFalse(first.flush())
        count=server.TEAM.db(server.TEAM.access(self.pid,self.token)).execute('SELECT count(*) FROM revisions').fetchone()[0]
        self.assertEqual(count,2)
        first.db.close()
        first=team_client.Client(first_cfg,root=root)
        first.status('retry_at',0);self.assertTrue(first.flush())
        self.assertEqual(server.TEAM.db(server.TEAM.access(self.pid,self.token)).execute('SELECT count(*) FROM revisions').fetchone()[0],2)
        # A separately approved Claude device receives Codex's discovery before its next prompt.
        _,_,invite=self.call('POST',self.path('invite'),{},cookie=self.cookie)
        _,_,request=self.call('POST','/team/join',{'code':invite['code'],'name':'Rui','kind':'device'})
        self.call('POST',self.path('approve'),{'request':request['request'],'allow':True},cookie=self.cookie)
        _,_,approved=self.call('POST','/team/poll',{'poll':request['poll']})
        second=team_client.Client(dict(host=base,project=self.pid,token=approved['token']),root=root)
        self.addCleanup(second.db.close)
        second.bind('claude','synthetic-claude-session')
        out=team_client.hook(second,'claude',{'session_id':'synthetic-claude-session','hook_event_name':'UserPromptSubmit','prompt':'Use the queue discovery'})
        self.assertIn('queue persists uploads',out['hookSpecificOutput']['additionalContext'])
        turns=team_client.transcript('claude',fixtures/'claude-team.jsonl')
        turns[-1]['content']='Claude discovery: context caches must be separated by credential.'
        second.capture(second.bound('claude','synthetic-claude-session'),turns,'Claude Code')
        self.assertTrue(second.flush())
        self.assertIn('separated by credential',first.briefing())
        port=self.srv.server_port
        self.srv.shutdown();self.srv.server_close()
        first.capture(first.bound('codex','synthetic-codex-session'),[dict(id='offline',speaker='assistant',content='Offline reported progress remains pending',timestamp=2)],'Codex')
        self.assertFalse(first.flush())
        self.assertIn('Context outdated',first.briefing())
        with server.LOCK:server.open_data(self.tmp.name)
        self.srv=ThreadingHTTPServer(('127.0.0.1',port),server.Handler)
        threading.Thread(target=self.srv.serve_forever,daemon=True).start()
        first.status('retry_at',0);self.assertTrue(first.flush())
        self.assertIn('Offline reported progress',second.briefing())
        first.db.close()

    def test_browser_join_approval_cookie_and_project_mcp(self):
        _,_,invite=self.call('POST',self.path('invite'),{},cookie=self.cookie)
        _,_,joined=self.call('POST','/team/join',{'code':invite['code'],'name':'Rui','kind':'browser'})
        self.call('POST',self.path('approve'),{'request':joined['request'],'allow':True},cookie=self.cookie)
        _,h,result=self.call('POST','/team/poll',{'poll':joined['poll']})
        self.assertNotIn('token',result)
        self.assertIn('Path=/team/'+self.pid+'/',h['Set-Cookie'])
        cookie=h['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('GET',self.path('view'),cookie=cookie)[0],200)
        self.assertEqual(self.call('GET',self.path('view'),cookie=self.cookie+'; '+cookie)[0],200)
        self.assertEqual(self.call('GET','/graph',cookie=cookie)[0],401)
        status,_,res=self.call('POST',self.path('mcp'),{'jsonrpc':'2.0','id':1,'method':'tools/list'},token=self.token)
        self.assertEqual(status,200)
        self.assertEqual({t['name'] for t in res['result']['tools']},{'project_context','project_search','project_publish','project_handoff'})
        self.assertEqual(self.call('POST',self.path('publish'),{'kind':'proposal','content':'Cross-client discovery'},token=self.token)[0],200)
        self.assertIn('Cross-client discovery',str(self.call('GET',self.path('context'),cookie=cookie)[2]))
        self.assertEqual(self.call('POST',self.path('publish'),{'kind':'proposal','content':'CSRF'},cookie=cookie,headers={'Origin':'https://foreign.example.com'})[0],403)


if __name__=='__main__':unittest.main()
