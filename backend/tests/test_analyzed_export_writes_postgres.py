from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import threading
import time
import unittest
from uuid import uuid4

import test_video_revocation_postgres as fixture
import test_generated_media_writes_postgres as generated


@unittest.skipUnless(fixture.DATABASE_URL, 'Dedicated local analyzed-export database is not configured.')
class AnalyzedExportWritesPostgresTest(unittest.TestCase):
  connect=classmethod(fixture.VideoRevocationPostgresTest.connect.__func__)
  setUpClass=classmethod(fixture.VideoRevocationPostgresTest.setUpClass.__func__)
  setUp=fixture.VideoRevocationPostgresTest.setUp
  sql=fixture.VideoRevocationPostgresTest.sql
  video=fixture.VideoRevocationPostgresTest.video
  legacy_video_fields=fixture.VideoRevocationPostgresTest.legacy_video_fields
  revoke=fixture.VideoRevocationPostgresTest.rpc
  finish=fixture.VideoRevocationPostgresTest.finalize
  wait_blocked=fixture.VideoRevocationPostgresTest.wait_blocked
  run_sql=generated.GeneratedMediaWritesPostgresTest.run_sql

  def make(self, owner=None, variant='pose', *, video=None, analysis=None, result=None):
    from psycopg.types.json import Jsonb
    owner=owner or self.user;video=video or self.video(owner=owner)
    if analysis is None:
      analysis=uuid4();result=result or {'poseFrames':[{'time':0,'keypoints':[]}],'reps':2}
      self.run_sql('insert into public.analysis_results(id,video_id,model_version,result_json) values(%s,%s,%s,%s)',
                   (analysis,video,'export-fixture',Jsonb(result)))
    row=self.sql('select model_version,result_json from public.analysis_results where id=%s',(analysis,))[0]
    source=self.sql('select coalesce(playback_path,storage_path) as path from public.videos where id=%s',(video,))[0]['path']
    attempt=uuid4();path=f'{owner}/exports/{video}-{analysis}-{variant}-{attempt}-h264-v1.mp4'
    return (attempt,owner,video,'videos',path,source,analysis,row['model_version'],Jsonb(row['result_json']),variant,80,1000000000,1000000000)

  def admit(self,args,connection=None,role='service_role'):
    return self.run_sql('select * from public.admit_private_media_export_write('+','.join(['%s']*13)+')',args,connection,role)

  def observe(self,args,connection=None):
    return self.run_sql('select public.observe_private_media_generated_write_success('+','.join(['%s']*12)+') as observed',
      (args[0],args[1],args[2],'analyzed_export',args[3],args[4],args[5],'video/mp4',args[10],None,None,None),connection)[0]['observed']

  def publish(self,args,ttl=3600,connection=None,role='service_role'):
    return self.run_sql('select * from public.publish_private_media_export(%s,%s,%s)',(args[0],args[1],ttl),connection,role)

  def read(self,args,connection=None,role='service_role', expected=True):
    return self.run_sql('select * from public.read_private_media_export(%s,%s,%s,%s,%s)',
      (args[1],args[2],args[9],args[3],args[6] if expected else None),connection,role)

  def completed(self,args):
    self.admit(args);self.assertTrue(self.observe(args));return self.publish(args)[0]

  def test_snapshot_admission_success_and_publication_are_separate(self):
    args=self.make();row=self.admit(args)[0]
    self.assertEqual(row['attempt_id'],args[0]);self.assertEqual(row['storage_path'],args[4])
    self.assertEqual(row['analysis_id'],args[6]);self.assertEqual(row['analysis_model_version'],args[7])
    digest=self.sql("select encode(sha256(convert_to(result_json::text,'UTF8')),'hex') as hash from public.analysis_results where id=%s",(args[6],))[0]['hash']
    self.assertEqual(row['analysis_snapshot_hash'],digest)
    self.assertEqual(row['state'],'dispatching');self.assertIsNone(row['published_at']);self.assertEqual(self.read(args),[])
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
    self.assertTrue(self.observe(args));self.assertEqual(self.read(args),[])
    published=self.publish(args)[0];self.assertEqual(published['state'],'succeeded')
    self.assertEqual(self.read(args),[published]);self.assertGreater(published['cache_expires_at'],published['published_at'])

  def test_repeated_dispatch_or_rebound_attempt_is_denied(self):
    args=self.make();self.admit(args)
    with self.assertRaises(self.psycopg.errors.UniqueViolation):self.admit(args)
    changed=list(self.make());changed[0]=args[0]
    changed[4]=f'{changed[1]}/exports/{changed[2]}-{changed[6]}-{changed[9]}-{args[0]}-h264-v1.mp4'
    with self.assertRaises(self.psycopg.errors.UniqueViolation):self.admit(tuple(changed))

  def test_exact_rendered_snapshot_source_type_key_size_and_owner_are_required(self):
    from psycopg.types.json import Jsonb
    args=self.make()
    changes={0:None,1:self.other,2:uuid4(),3:'Bad/bucket',4:args[4]+'different',5:args[5]+'different',
             6:uuid4(),7:'different-model',8:Jsonb({'reps':99}),9:'clean',10:0,11:0,12:None}
    for index,value in changes.items():
      changed=list(args);changed[index]=value
      with self.subTest(index=index),self.assertRaises(self.psycopg.Error):self.admit(tuple(changed))
    self.assertEqual(self.sql('select attempt_id from public.private_media_generated_writes'),[])

  def test_in_place_result_update_changes_fingerprint_and_invalidates_old_cache(self):
    from psycopg.types.json import Jsonb
    args=self.make();first=self.completed(args)
    self.run_sql('update public.analysis_results set result_json=%s where id=%s',(Jsonb({'reps':9}),args[6]))
    self.assertEqual(self.read(args),[])
    stale=list(args);stale[0]=uuid4();stale[4]=f'{args[1]}/exports/{args[2]}-{args[6]}-pose-{stale[0]}-h264-v1.mp4'
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(tuple(stale))
    fresh=self.make(video=args[2],analysis=args[6]);second=self.completed(fresh)
    self.assertEqual(first['analysis_id'],second['analysis_id'])
    self.assertNotEqual(first['analysis_snapshot_hash'],second['analysis_snapshot_hash'])
    self.assertNotEqual(first['storage_path'],second['storage_path'])
    self.assertEqual(len(self.sql('select attempt_id from public.private_media_generated_writes')),2)

  def test_analysis_change_after_upload_observation_denies_publication(self):
    args=self.make();self.admit(args);self.observe(args)
    self.run_sql("update public.analysis_results set result_json='{}'::jsonb where id=%s",(args[6],))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
    row=self.sql('select state,published_at from public.private_media_generated_writes')[0]
    self.assertEqual(row,{'state':'succeeded','published_at':None})

  def test_latest_analysis_selection_is_deterministic_when_timestamps_tie(self):
    from psycopg.types.json import Jsonb
    args=self.make();self.completed(args)
    another=uuid4();same_time=self.sql('select created_at from public.analysis_results where id=%s',(args[6],))[0]['created_at']
    self.run_sql('insert into public.analysis_results(id,video_id,model_version,result_json,created_at) values(%s,%s,%s,%s,%s)',
      (another,args[2],'second-model',Jsonb({'reps':3}),same_time))
    winner=max(args[6],another)
    if winner!=args[6]:
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.read(args)
    latest=self.make(video=args[2],analysis=winner);self.completed(latest)
    self.assertEqual(self.read(latest,expected=False)[0]['analysis_id'],winner)

  def test_playback_generation_change_invalidates_cache_even_with_same_analysis(self):
    args=self.make();self.completed(args)
    new=generated.GeneratedMediaWritesPostgresTest.make_args(self,'playback',video=args[2])
    generated.GeneratedMediaWritesPostgresTest.admit(self,new)
    generated.GeneratedMediaWritesPostgresTest.observe(self,new)
    generated.GeneratedMediaWritesPostgresTest.publish(self,new)
    self.run_sql("update public.analysis_jobs set status='completed',lease_owner=null,lease_expires_at=null where id=%s",(new[9],))
    self.assertEqual(self.read(args),[])
    fresh=self.make(video=args[2],analysis=args[6]);self.assertEqual(fresh[5],new[5]);self.completed(fresh)
    self.assertEqual(self.read(fresh)[0]['source_path'],new[5])

  def test_publication_replay_does_not_extend_cache_lifetime(self):
    args=self.make();first=self.completed(args)
    self.assertEqual(self.publish(args,7200),[first])

  def test_publication_cannot_be_extended_cleared_or_combined_with_observation(self):
    args=self.make();self.admit(args)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql("update public.private_media_generated_writes set state='succeeded',observed_at=clock_timestamp(),published_at=clock_timestamp(),cache_expires_at=clock_timestamp()+interval '1 hour' where attempt_id=%s",(args[0],))
    self.observe(args);self.publish(args)
    for change in ("cache_expires_at=cache_expires_at+interval '1 minute'",'published_at=null,cache_expires_at=null',"published_at='infinity'"):
      with self.subTest(change=change),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.run_sql('update public.private_media_generated_writes set '+change+' where attempt_id=%s',(args[0],))

  def test_expired_publication_is_not_resolved_and_still_stays_charged(self):
    args=self.make();self.admit(args);self.observe(args);self.publish(args,1)
    threading.Event().wait(1.05)
    self.assertEqual(self.read(args),[])
    self.assertEqual(self.sql('select sum(size_bytes) as charged from public.private_media_generated_writes')[0]['charged'],80)

  def test_missing_foreign_unsaved_pruned_expired_or_active_analysis_denies_export(self):
    for denial in ('foreign','unsaved','pruned','expired','active','missing'):
      args=self.make();changed=list(args)
      if denial=='foreign':changed[1]=self.other
      elif denial=='unsaved':self.run_sql("update public.videos set is_saved=false,save_state='pending' where id=%s",(args[2],))
      elif denial=='pruned':self.run_sql("update public.videos set storage_state='pruned' where id=%s",(args[2],))
      elif denial=='expired':self.run_sql("update public.videos set expires_at=clock_timestamp()-interval '1 second' where id=%s",(args[2],))
      elif denial=='active':self.run_sql("insert into public.analysis_jobs(video_id,status) values(%s,'queued')",(args[2],))
      else:self.sql('delete from public.videos where id=%s',(args[2],))
      with self.subTest(denial=denial),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(tuple(changed))

  def test_late_success_after_owner_deletion_and_metadata_loss_is_not_publication(self):
    args=self.make();self.admit(args)
    self.run_sql('select * from public.begin_private_media_owner_deletion(%s)',(self.user,))
    self.sql('delete from auth.users where id=%s',(self.user,))
    self.assertTrue(self.observe(args))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
    self.assertEqual(self.sql('select user_id,video_id,state,published_at from public.private_media_generated_writes'),
      [{'user_id':self.user,'video_id':args[2],'state':'succeeded','published_at':None}])

  def test_revocation_snapshots_include_unpublished_export_and_cannot_finish(self):
    args=self.make();self.admit(args);self.observe(args)
    task=self.revoke([args[2]],delete=True)[0]
    self.assertIn(args[4],task['storage_paths']);self.assertIn(f'{self.user}/exports/{args[2]}-',task['export_prefixes'])
    self.assertFalse(self.finish(task))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)

  def test_saved_deletion_stays_pending_for_an_observed_published_export(self):
    args=self.make();self.completed(args)
    task=self.run_sql('select * from public.revoke_saved_lifts(%s,%s)',(self.user,[args[2]]))[0]['task']
    self.assertFalse(self.finish(task))
    self.assertIsNone(self.sql('select completed_at from public.saved_lift_deletion_receipts')[0]['completed_at'])

  def test_snapshot_identity_cannot_change_and_nonexport_rows_cannot_publish_export_fields(self):
    args=self.make();self.admit(args)
    for change in ("analysis_snapshot_hash=repeat('a',64)",'analysis_id=gen_random_uuid()',"variant='barbell'","analysis_model_version='other'"):
      with self.subTest(change=change),self.assertRaises(self.psycopg.Error):self.run_sql('update public.private_media_generated_writes set '+change)
    other=generated.GeneratedMediaWritesPostgresTest.make_args(self,'thumbnail_backfill')
    generated.GeneratedMediaWritesPostgresTest.admit(self,other);generated.GeneratedMediaWritesPostgresTest.observe(self,other)
    with self.assertRaises(self.psycopg.Error):
      self.run_sql("update public.private_media_generated_writes set published_at=clock_timestamp(),cache_expires_at=clock_timestamp()+interval '1 hour' where attempt_id=%s",(other[0],))

  def test_export_variants_have_independent_immutable_cache_entries(self):
    first=self.make();self.completed(first)
    for variant in ('barbell','pose-barbell'):
      args=self.make(video=first[2],analysis=first[6],variant=variant);self.completed(args)
      self.assertEqual(self.read(args)[0]['variant'],variant)
    self.assertEqual(self.read(first)[0]['storage_path'],first[4])

  def test_source_and_other_generated_admissions_include_export_bytes(self):
    args=self.make();self.completed(args)
    gen=generated.GeneratedMediaWritesPostgresTest.make_args(self,'thumbnail_backfill')
    generated.GeneratedMediaWritesPostgresTest.admit(self,gen,limits=(160,160))
    with self.assertRaises(self.psycopg.errors.RaiseException):
      generated.GeneratedMediaWritesPostgresTest.reserve_source(self,size=1,user_limit=160)
    more=list(self.make());more[11:]=[160,160]
    with self.assertRaises(self.psycopg.errors.RaiseException):self.admit(tuple(more))

  def test_concurrent_exports_cannot_overbook_global_storage(self):
    args=[]
    for owner in (self.user,self.other,self.user):
      row=list(self.make(owner));row[11:]=[1000,160];args.append(tuple(row))
    def attempt(row):
      try:self.admit(row);return True
      except self.psycopg.errors.RaiseException:return False
    with ThreadPoolExecutor(3) as pool:results=list(pool.map(attempt,args))
    self.assertEqual(sum(results),2)
    self.assertEqual(self.sql('select sum(size_bytes) as bytes from public.private_media_generated_writes')[0]['bytes'],160)

  def test_service_only_invoker_functions_have_fixed_search_paths(self):
    args=self.make()
    queries=[('select * from public.admit_private_media_export_write('+','.join(['%s']*13)+')',args),
             ('select * from public.publish_private_media_export(%s,%s,%s)',(args[0],args[1],3600)),
             ('select * from public.read_private_media_export(%s,%s,%s,%s,%s)',(args[1],args[2],args[9],args[3],None)),
             ('select public.lock_private_media_export_resource(%s,%s)',(args[1],args[2]))]
    for role in ('anon','authenticated','public_probe'):
      for query,values in queries:
        with self.subTest(role=role),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.run_sql(query,values,role=role)
    names=['admit_private_media_export_write','publish_private_media_export','read_private_media_export',
           'lock_private_media_export_resource','assert_private_media_export_write']
    rows=self.sql('select prosecdef,proconfig from pg_proc where proname=any(%s)',(names,))
    self.assertEqual(len(rows),5)
    self.assertTrue(all(not row['prosecdef'] and 'search_path=""' in row['proconfig'] for row in rows))

  def test_owner_deletion_wait_before_admission_denies_any_new_export(self):
    args=self.make()
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(1) as pool:
      holder.execute('set local role service_role');holder.execute('select * from public.begin_private_media_owner_deletion(%s)',(self.user,))
      waiting.execute('set local role service_role');future=pool.submit(self.admit,args,waiting)
      self.wait_blocked(waiting.info.backend_pid,holder.info.backend_pid);holder.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=4)
    self.assertEqual(self.sql('select attempt_id from public.private_media_generated_writes'),[])

  def test_published_cache_cannot_be_resolved_after_owner_deletion(self):
    args=self.make();self.completed(args)
    self.run_sql('select * from public.begin_private_media_owner_deletion(%s)',(self.user,))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.read(args)

  def test_capacity_wait_rechecks_video_deadline_before_committing_an_export_attempt(self):
    args=self.make();expiry=datetime.now(timezone.utc)+timedelta(milliseconds=450)
    self.run_sql('update public.videos set expires_at=%s where id=%s',(expiry,args[2]))
    with self.connect() as capacity,self.connect() as waiting,ThreadPoolExecutor(1) as pool:
      capacity.execute("select pg_advisory_xact_lock(hashtextextended('peso:upload-capacity',0))")
      waiting.execute('set local role service_role');future=pool.submit(self.admit,args,waiting)
      self.wait_blocked(waiting.info.backend_pid,capacity.info.backend_pid)
      threading.Event().wait(max(0,(expiry-datetime.now(timezone.utc)).total_seconds()+.05));capacity.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=4)
    self.assertEqual(self.sql('select attempt_id from public.private_media_generated_writes'),[])

  def test_admission_before_revocation_is_retained_after_actual_lock_wait(self):
    args=self.make()
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(1) as pool:
      holder.execute('set local role service_role');self.admit(args,holder)
      waiting.execute('set local role service_role')
      future=pool.submit(self.run_sql,'select * from public.revoke_video_media(%s,%s,true)',(self.user,[args[2]]),waiting)
      self.wait_blocked(waiting.info.backend_pid,holder.info.backend_pid);holder.commit()
      task=future.result(timeout=4)[0];waiting.commit()
    self.assertIn(args[4],task['storage_paths']);self.assertFalse(self.finish(task))

  def test_busy_analysis_update_fails_without_dispatch_or_lock_cycle(self):
    args=self.make()
    with self.connect() as holder:
      holder.execute('select id from public.analysis_results where id=%s for update',(args[6],))
      start=time.monotonic()
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):self.admit(args)
      self.assertLess(time.monotonic()-start,1.5)
    self.assertEqual(self.sql('select attempt_id from public.private_media_generated_writes'),[])

  def test_unicode_whitespace_and_unsafe_legacy_sources_cannot_authorize_export(self):
    for suffix in ('\u00a0','\u2003','\n','/../wrong.mp4','\\wrong.mp4'):
      args=list(self.make());args[5]+=suffix
      self.legacy_video_fields(args[2],{'playback_path':args[5]})
      with self.subTest(suffix=suffix),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(tuple(args))
    self.assertEqual(self.sql('select attempt_id from public.private_media_generated_writes'),[])
