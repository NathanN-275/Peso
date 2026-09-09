"""Exercise two-user database/storage ownership only on permanent peso-staging.

The owner credential is read from a protected local JSON file produced by
`supabase projects api-keys --project-ref iseqgaewjpjcxrndibep --output json`.
No credential or password is printed. Created users/objects are tracked and
cleaned in finally; unrelated staging data is never selected or changed.
"""
import argparse
import base64
import json
from pathlib import Path
import secrets
import urllib.error
import urllib.request
import uuid

PROJECT = 'iseqgaewjpjcxrndibep'
BASE = f'https://{PROJECT}.supabase.co'


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--keys-file', type=Path, required=True)
  parser.add_argument('--report', type=Path, required=True)
  args = parser.parse_args()
  keys = json.loads(args.keys_file.read_text())
  owner = next(k['api_key'] for k in keys if k.get('name') == 'service_role')
  anon = next(k['api_key'] for k in keys if k.get('name') == 'anon')
  for key, role in [(owner, 'service_role'), (anon, 'anon')]:
    claims = json.loads(base64.urlsafe_b64decode(key.split('.')[1] + '=='))
    if claims.get('ref') != PROJECT or claims.get('role') != role:
      raise RuntimeError('Refusing credentials outside the Student boundary.')

  def request(path, *, method='GET', token=None, body=None, binary=False, allow_error=False):
    key = anon if token else owner
    headers = {'apikey': key, 'Authorization': 'Bearer ' + (token or owner)}
    if body is not None:
      headers['Content-Type'] = 'video/mp4' if binary else 'application/json'
      data = body if binary else json.dumps(body).encode()
    else:
      data = None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
      with urllib.request.urlopen(req, timeout=25) as response:
        data = response.read()
        return response.status, json.loads(data) if data and response.headers.get('Content-Type','').startswith('application/json') else data
    except urllib.error.HTTPError as error:
      if allow_error:
        return error.code, None
      raise RuntimeError(f'Student isolation request failed: {method} {path.split("?")[0]} ({error.code})') from None

  users = []
  objects = []
  run = uuid.uuid4().hex
  report = {'project': PROJECT, 'run': run, 'checks': [], 'cleanup': []}
  try:
    for suffix in ['a', 'b']:
      email = f'peso-student-{run}-{suffix}@example.test'
      password = secrets.token_urlsafe(32)
      _, user = request('/auth/v1/admin/users', method='POST', body={
        'email': email, 'password': password, 'email_confirm': True,
        'app_metadata': {'student_isolation_test': run},
      })
      record = {'id': user['id']}
      users.append(record)
      _, session = request('/auth/v1/token?grant_type=password', method='POST', body={'email': email, 'password': password})
      record['token'] = session['access_token']
    report['user_ids'] = [u['id'] for u in users]
    for user, other in [(users[0], users[1]), (users[1], users[0])]:
      video_id = str(uuid.uuid4())
      object_path = f"{user['id']}/student-isolation-{run}.mp4"
      request('/rest/v1/videos', method='POST', body={
        'id': video_id, 'user_id': user['id'], 'storage_path': object_path,
        'source_type': 'camera_roll', 'exercise_type': 'squat', 'view_type': 'side', 'status': 'uploaded',
      })
      _, own = request(f'/rest/v1/videos?id=eq.{video_id}&select=id', token=user['token'])
      _, foreign = request(f'/rest/v1/videos?id=eq.{video_id}&select=id', token=other['token'])
      assert len(own) == 1 and foreign == [], 'Cross-owner database read was not isolated'
      status, _ = request(f'/rest/v1/videos?id=eq.{video_id}', method='PATCH', token=other['token'], body={'exercise_type': 'forbidden'}, allow_error=True)
      assert status in (200, 204, 401, 403), 'Unexpected database update response'
      _, saved = request(f'/rest/v1/videos?id=eq.{video_id}&select=exercise_type', token=user['token'])
      assert saved[0]['exercise_type'] == 'squat', 'Cross-owner database update succeeded'
      status, _ = request(f'/rest/v1/videos?id=eq.{video_id}', method='DELETE', token=other['token'], allow_error=True)
      assert status in (200, 204, 401, 403), 'Unexpected database delete response'
      _, saved = request(f'/rest/v1/videos?id=eq.{video_id}&select=id', token=user['token'])
      assert len(saved) == 1, 'Cross-owner database deletion succeeded'
      # Service seeds an owned opaque object; this is an RLS check, not media admission.
      request('/storage/v1/object/videos/' + object_path, method='POST', body=b'student-isolation-fixture', binary=True)
      objects.append(object_path)
      status, data = request('/storage/v1/object/authenticated/videos/' + object_path, token=user['token'])
      assert status == 200 and data == b'student-isolation-fixture'
      status, _ = request('/storage/v1/object/authenticated/videos/' + object_path, token=other['token'], allow_error=True)
      assert status in (400, 401, 403, 404), 'Cross-owner storage read succeeded'
      status, _ = request('/storage/v1/object/videos', method='DELETE', token=other['token'], body={'prefixes': [object_path]}, allow_error=True)
      assert status in (200, 204, 401, 403), 'Unexpected storage delete response'
      status, _ = request('/storage/v1/object/authenticated/videos/' + object_path, token=user['token'])
      assert status == 200, 'Cross-owner storage deletion succeeded'
      report['checks'].append({'owner': user['id'], 'database_read_update_delete': 'isolated', 'storage_read_delete': 'isolated'})
  finally:
    # Storage objects do not cascade when auth users are deleted.
    if objects:
      request('/storage/v1/object/videos', method='DELETE', body={'prefixes': objects})
    for user in users:
      if user.get('token'):
        request('/auth/v1/logout?scope=global', method='POST', token=user['token'])
      request('/auth/v1/admin/users/' + user['id'], method='DELETE')
      _, rows = request(f"/rest/v1/videos?user_id=eq.{user['id']}&select=id")
      assert rows == [], 'Test user rows were not cleaned up'
      report['cleanup'].append({'user': user['id'], 'sessions_revoked': True, 'user_deleted': True, 'rows_removed': True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))
  print(json.dumps(report))


if __name__ == '__main__':
  main()
