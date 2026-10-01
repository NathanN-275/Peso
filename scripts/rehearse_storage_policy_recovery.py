#!/usr/bin/env python3
"""Synthetic local RLS test. Creates/removes its own networkless Docker database.

No connection URL, hosted target, credential, host mount, or real backup input.
"""
from pathlib import Path
import json
import hashlib
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
OWNER = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
ACK = "set peso.recovery_target = 'isolated-storage-policy-rehearsal';\n"


def main():
    if not __debug__:
        raise RuntimeError('Run without Python optimization; assertions must be enabled')
    container = None
    assertions = 0

    def docker(*args, input=None):
        return subprocess.run(['docker', *args], input=input, text=True,
                              capture_output=True, timeout=45)

    def sql(query, role=None, user=OWNER, failure=None):
        nonlocal assertions
        if role:
            assert role in ('authenticated', 'anon', 'service_role')
            assert user in (OWNER, OTHER, '')
            query = f"set role {role}; set request.jwt.claim.sub = '{user}';\n" + query
        result = docker('exec', '-i', container, 'psql', '-X', '-qAt',
                        '-U', 'postgres', '-d', 'peso_storage_recovery_test',
                        '-v', 'ON_ERROR_STOP=1', input=query)
        if failure:
            assert result.returncode != 0 and failure in result.stderr, 'Expected database rejection missing'
            assertions += 1
        else:
            assert result.returncode == 0, f'Unexpected synthetic local SQL failure: {result.stderr.strip()}'
        return result.stdout.strip()

    def expect(query, value, **kwargs):
        nonlocal assertions
        assert sql(query, **kwargs) == str(value), 'Unexpected access result'
        assertions += 1

    try:
        created = docker('run', '--detach', '--rm', '--pull=never', '--network=none',
                         '--label', 'peso.test=storage-policy-recovery',
                         '--name', 'peso-storage-recovery-' + uuid.uuid4().hex[:12],
                         '--tmpfs', '/var/lib/postgresql/data:rw',
                         '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
                         '-e', 'POSTGRES_DB=peso_storage_recovery_test', 'postgres:17')
        assert created.returncode == 0, 'Unable to create isolated local database'
        container = created.stdout.strip()
        assert re.fullmatch('[a-f0-9]{64}', container), 'Unexpected container identity'
        inspected = docker('inspect', container)
        info = json.loads(inspected.stdout)[0]
        assert info['HostConfig']['NetworkMode'] == 'none'
        assert not info['HostConfig']['PortBindings'] and not info['HostConfig']['Binds']
        assertions += 2
        for _ in range(60):
            # The image starts a socket-only temporary server during initdb.
            # TCP becomes available only after initialization has completed.
            if docker('exec', container, 'pg_isready', '-h', '127.0.0.1',
                      '-U', 'postgres', '-d', 'peso_storage_recovery_test').returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('Local database startup timed out')
        sql((ROOT / 'scripts/fixtures/storage_policy_recovery.sql').read_text())
        restore = (ROOT / 'supabase/recovery/restore_pre_cutover_storage_policies.sql').read_text()
        count = "select count(*) from pg_policies where schemaname='storage' and tablename='objects';"
        sql(restore, failure='Explicit isolated recovery target acknowledgement required')
        expect(count, 0)
        sql('alter table storage.objects disable row level security;')
        sql(ACK + restore, failure='storage.objects with RLS enabled is required')
        expect(count, 0)
        sql('alter table storage.objects enable row level security;')
        sql("create policy unexpected on storage.objects for select to anon using (true);")
        sql(ACK + restore, failure='Target must have no existing Storage object policies')
        expect(count, 1)
        sql('drop policy unexpected on storage.objects;')
        sql('alter function storage.extension(text) rename to extension_unavailable;')
        sql(ACK + restore, failure='does not exist')
        expect(count, 0)
        sql('alter function storage.extension_unavailable(text) rename to extension;')
        sql(ACK + restore)
        expect(count, 8)
        definitions_query = """select coalesce(jsonb_agg(to_jsonb(p) order by policyname), '[]'::jsonb)
          from pg_policies p where schemaname='storage' and tablename='objects';"""
        definitions = sql(definitions_query)
        sql(ACK + restore, failure='Target must have no existing Storage object policies')
        expect(count, 8)
        expect(definitions_query, definitions)
        expect("select count(*) from pg_policies where schemaname='storage' and roles=array['authenticated']::name[] and permissive='PERMISSIVE';", 8)

        for bucket, extension in (('videos', 'mp4'), ('profile-avatars', 'png')):
            path = f'{OWNER}/source.{extension}'
            foreign = f'{OTHER}/source.{extension}'
            insert = f"insert into storage.objects(bucket_id,name) values ('{bucket}','{path}');"
            sql(insert, role='authenticated')
            expect(f"select count(*) from storage.objects where bucket_id='{bucket}';", 1, role='authenticated')
            expect(f"with changed as (update storage.objects set metadata='{{\"checked\":true}}' where bucket_id='{bucket}' returning id) select count(*) from changed;", 1, role='authenticated')
            for role, user in (('authenticated', OTHER), ('authenticated', ''), ('anon', OWNER)):
                expect('select count(*) from storage.objects;', 0, role=role, user=user)
                for verb in ('update storage.objects set metadata=null', 'delete from storage.objects'):
                    expect(f'with changed as ({verb} returning id) select count(*) from changed;', 0, role=role, user=user)
                sql(f"insert into storage.objects(bucket_id,name) values ('{bucket}','{OWNER}/denied.{extension}');", role=role, user=user, failure='row-level security')
            sql(f"update storage.objects set name='{foreign}' where bucket_id='{bucket}';", role='authenticated', failure='row-level security')
            sql(f"update storage.objects set bucket_id='saved-lift-exports' where bucket_id='{bucket}';", role='authenticated', failure='row-level security')
            expect(f"with changed as (delete from storage.objects where bucket_id='{bucket}' returning id) select count(*) from changed;", 1, role='authenticated')
            expect('select count(*) from storage.objects;', 0)

        for extension in ('mp4', 'mov', 'm4v', 'webm'):
            sql(f"insert into storage.objects(bucket_id,name) values ('videos','{OWNER}/clip.{extension}');", role='authenticated')
        expect('select count(*) from storage.objects;', 4, role='authenticated')
        for name in (f'{OWNER}/bad.exe', f'{OWNER}/bad.MP4', 'root.mp4', f'{OTHER}/foreign.mp4'):
            sql(f"insert into storage.objects(bucket_id,name) values ('videos','{name}');", role='authenticated', failure='row-level security')
        sql(f"update storage.objects set name='{OWNER}/renamed.exe' where name='{OWNER}/clip.mp4';", role='authenticated', failure='row-level security')
        sql(f"insert into storage.objects(bucket_id,name,owner_id) values ('videos','{OTHER}/spoof.mp4','{OWNER}');", role='authenticated', failure='row-level security')
        sql(f"insert into storage.objects(bucket_id,name) values ('saved-lift-exports','{OWNER}/export.zip');", role='authenticated', failure='row-level security')
        sql(f"insert into storage.objects(bucket_id,name) values ('saved-lift-exports','{OWNER}/export.zip');", role='service_role')
        expect("select count(*) from storage.objects where bucket_id='saved-lift-exports';", 0, role='authenticated')
        expect('select count(*) from storage.objects;', 5, role='service_role')
        print(f'PASS: {assertions} local isolation, restore, and RLS assertions; synthetic data only.')
        print('Restored policy definitions SHA-256: ' + hashlib.sha256(definitions.encode()).hexdigest())
    finally:
        if container:
            removed = docker('rm', '--force', '--volumes', container)
            if removed.returncode != 0:
                raise RuntimeError('Local test container cleanup failed')
            print('Removed the disposable local database and its synthetic data.')


if __name__ == '__main__':
    main()
