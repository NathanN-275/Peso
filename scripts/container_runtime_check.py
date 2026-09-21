"""Offline application-image smoke gate; this is not real-clip model equivalence."""
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, '/app')


def command(*args):
  result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=120)
  return result.stdout


def inspect(path):
  return json.loads(command('ffprobe', '-v', 'error', '-select_streams', 'v:0',
    '-show_streams', '-of', 'json', str(path)))['streams'][0]


def main():
  assert os.getuid() == 10001 and os.getgid() == 10001
  for module in ['app.main', 'app.jobs.analysis_worker', 'rtmlib', 'onnxruntime']:
    importlib.import_module(module)
  assert importlib.metadata.version('mediapipe') == '0.10.30'
  assert importlib.metadata.version('protobuf') == '6.33.5'
  assert command('ffmpeg', '-version').startswith('ffmpeg version 9.0.1')
  for tool in ['pip', 'setuptools', 'wheel']:
    assert shutil.which(tool) is None, f'Unexpected runtime executable: {tool}'
    assert importlib.util.find_spec(tool) is None, f'Unexpected runtime module: {tool}'
    try:
      importlib.metadata.version(tool)
    except importlib.metadata.PackageNotFoundError:
      pass
    else:
      raise AssertionError(f'Unexpected runtime build tool: {tool}')
  assert not Path('/usr/share/python-wheels').exists()

  import cv2
  import numpy as np
  from app.analysis.pose_estimator import MediaPipePoseBackend, PoseEstimatorConfig
  from app.analysis.side_squat.quality_preflight import SideSquatQualityPreflight, QualityPreflightThresholds
  from app.services.analyzed_video_renderer import render_analyzed_video
  from app.services.video_assets import create_video_thumbnail, compress_video_for_playback

  frame = cv2.imread('/checks/pose.jpg')
  assert frame is not None
  poses = []
  for complexity in (0, 1, 2):
    backend = MediaPipePoseBackend(PoseEstimatorConfig(model_complexity=complexity))
    try:
      # The official MediaPipe test image proves positive native inference. It
      # cannot establish video tracking equivalence or product accuracy.
      pose = backend.process(frame, 0)
      assert pose is not None and len(pose) == 33, f'No 33-point pose from model {complexity}'
      poses.append(pose)
      backend.process(frame, 0)  # duplicate source timestamp must be accepted
    finally:
      backend.close()
  backend = MediaPipePoseBackend(PoseEstimatorConfig(model_complexity=1))
  try:
    assert backend.process(np.zeros((240, 320, 3), dtype=np.uint8), 0) is None
  finally:
    backend.close()

  with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / 'source.mp4'
    command('ffmpeg', '-y', '-loop', '1', '-i', '/checks/pose.jpg', '-t', '1',
      '-vf', 'scale=320:240', '-r', '10', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source))
    assert inspect(source)['codec_name'] == 'h264'
    rotated = root / 'rotated.mp4'
    command('ffmpeg', '-y', '-display_rotation', '90', '-i', str(source), '-c', 'copy', str(rotated))
    assert any(abs(item.get('rotation', 0)) == 90 for item in inspect(rotated).get('side_data_list', []))
    playback = compress_video_for_playback(rotated, root / 'playback.mp4')
    info = inspect(playback)
    assert info['codec_name'] == 'h264' and info['height'] > info['width']
    thumbnail = create_video_thumbnail(rotated, root / 'thumbnail.jpg', at_seconds=0)
    thumbnail_frame = cv2.imread(str(thumbnail))
    assert thumbnail_frame is not None and thumbnail_frame.shape[0] > thumbnail_frame.shape[1]
    preflight = SideSquatQualityPreflight(QualityPreflightThresholds(sample_count=3)).evaluate_file(source, exercise_type='squat')
    assert preflight['sampledFrameMetadata']['sampledFrameCount'] > 0
    result = {'poseFrames': [{'time': 0, 'keypoints': [{'name': name, **point, 'confidence': point['visibility']} for name, point in poses[1].items()]}]}
    export = render_analyzed_video(source_path=rotated, output_path=root / 'export.mp4', result_json=result)
    exported = inspect(export)
    assert exported['codec_name'] == 'h264' and exported['height'] > exported['width']
    for extension, codec in [('mov', 'mpeg4'), ('mkv', 'mpeg4')]:
      sample = root / f'upload.{extension}'
      command('ffmpeg', '-y', '-i', str(source), '-c:v', codec, str(sample))
      assert inspect(sample)['width'] == 320
    webm = compress_video_for_playback(Path('/checks/upload.webm'), root / 'webm-playback.mp4')
    assert inspect(webm)['codec_name'] == 'h264'
  print(json.dumps({'offline': True, 'uid': os.getuid(), 'gid': os.getgid(), 'pose_models': 3,
    'checks': ['API and worker imports', 'positive and missing pose', 'quality preflight',
      'H.264', 'ffprobe', 'rotation', 'thumbnail', 'analyzed export', 'MOV/MKV/WebM uploads']}))


if __name__ == '__main__':
  main()
