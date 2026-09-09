"""Correct 0.10.30's upstream metadata to match its installed files.

The official py3-none-manylinux_2_28_x86_64 wheel contains a stale CPython tag
and RECORD path. Tasks loads libmediapipe.so through ctypes, not a CPython 3.9
extension. Correct only these known mismatches, then verify every RECORD path.
pip check and actual offline inference remain mandatory.
"""
import base64
import csv
import hashlib
import importlib.metadata
import io
import platform


def main():
  dist = importlib.metadata.distribution('mediapipe')
  if dist.version != '0.10.30' or platform.system() != 'Linux' or platform.machine() != 'x86_64':
    raise RuntimeError('Wheel correction applies only to MediaPipe 0.10.30 Linux x86_64.')
  wheel_relative = next(p for p in dist.files if str(p).endswith('.dist-info/WHEEL'))
  wheel = dist.locate_file(wheel_relative)
  original = wheel.read_text()
  old = 'Tag: cp39-cp39-linux_x86_64'
  new = 'Tag: py3-none-manylinux_2_28_x86_64'
  tag_count = sum(line.startswith('Tag:') for line in original.splitlines())
  if new in original and old not in original and tag_count == 1:
    data = original.encode()
  elif original.count(old) == 1 and new not in original and tag_count == 1:
    data = original.replace(old, new).encode()
    wheel.write_bytes(data)
  else:
    raise RuntimeError('Unexpected upstream wheel metadata; review before changing it.')
  record = wheel.parent / 'RECORD'
  rows = list(csv.reader(io.StringIO(record.read_text())))
  digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
  for row in rows:
    if row[0] == str(wheel_relative):
      row[1:] = ['sha256=' + digest, str(len(data))]
  stale_library = 'mediapipe/tasks/c/libmediapipe_c_lib.cpython-39-x86_64-linux-gnu.so'
  actual_library = 'mediapipe/tasks/c/libmediapipe.so'
  stale_rows = [row for row in rows if row[0] == stale_library]
  actual_rows = [row for row in rows if row[0] == actual_library]
  if len(stale_rows) == 1 and not actual_rows:
    stale_rows[0][0] = actual_library
  elif len(stale_rows) == 1 and len(actual_rows) == 1:
    # pip records the installed archive member but retains the wheel's stale row.
    rows.remove(stale_rows[0])
  elif stale_rows or len(actual_rows) != 1:
    matching = [row[0] for row in rows if 'libmediapipe' in row[0]]
    raise RuntimeError(f'Unexpected MediaPipe native-library RECORD metadata: {matching!r}')
  if not dist.locate_file(actual_library).is_file() or dist.locate_file(stale_library).exists():
    raise RuntimeError('Unexpected MediaPipe native-library installation layout.')
  with record.open('w', newline='') as output:
    csv.writer(output).writerows(rows)
  corrected = importlib.metadata.distribution('mediapipe')
  for relative, recorded_digest, recorded_size in rows:
    path = corrected.locate_file(relative)
    if not path.is_file():
      raise RuntimeError(f'MediaPipe RECORD still names a missing file: {relative}')
    if recorded_size and path.stat().st_size != int(recorded_size):
      raise RuntimeError(f'MediaPipe RECORD size mismatch: {relative}')
    if recorded_digest:
      algorithm, expected = recorded_digest.split('=', 1)
      with path.open('rb') as source:
        file_digest = hashlib.file_digest(source, algorithm).digest()
      actual = base64.urlsafe_b64encode(file_digest).decode().rstrip('=')
      if actual != expected:
        raise RuntimeError(f'MediaPipe RECORD checksum mismatch: {relative}')
  print('Corrected known MediaPipe 0.10.30 wheel metadata; native library bytes unchanged.')


if __name__ == '__main__':
  main()
