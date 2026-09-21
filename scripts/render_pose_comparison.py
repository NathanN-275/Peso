"""Render private old/new pose evidence for human review, never auto-promote."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--video', type=Path, required=True)
  parser.add_argument('--legacy', type=Path, required=True)
  parser.add_argument('--candidate', type=Path, required=True)
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  import cv2
  import numpy as np
  from app.services.analyzed_video_renderer import _draw_pose_overlay

  reports = [json.loads(path.read_text()) for path in (args.legacy, args.candidate)]
  if reports[0].get('backend') != 'legacy' or reports[0].get('mediapipe_version') != '0.10.21':
    raise RuntimeError('Legacy report must come from MediaPipe 0.10.21.')
  if reports[1].get('backend') != 'candidate' or reports[1].get('mediapipe_version') != '0.10.30':
    raise RuntimeError('Candidate report must come from MediaPipe 0.10.30.')
  if reports[0].get('candidate_image_reference') != reports[1].get('candidate_image_reference'):
    raise RuntimeError('Comparison reports must name the same immutable candidate image.')
  if reports[0]['source_sha256'] != reports[1]['source_sha256']:
    raise RuntimeError('Cannot compare different source clips.')
  cap = cv2.VideoCapture(str(args.video))
  cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
  fps = cap.get(cv2.CAP_PROP_FPS)
  width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
  scale = min(1, 720 / max(width, height))
  width, height = int(width * scale) // 2 * 2, int(height * scale) // 2 * 2
  args.output.parent.mkdir(parents=True, exist_ok=True)
  encoder = subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24',
    '-s',f'{width * 2}x{height + 48}','-r',str(fps),'-i','-','-an','-c:v','libx264',
    '-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(args.output)],stdin=subprocess.PIPE)
  positions = [0, 0]
  index = 0
  try:
    while True:
      ok, frame = cap.read()
      if not ok:
        break
      frame = cv2.resize(frame, (width, height))
      panels=[]
      for side, report in enumerate(reports):
        samples=report['frames']
        while positions[side]+1 < len(samples) and samples[positions[side]+1]['source_frame_index'] <= index:
          positions[side]+=1
        pose = samples[positions[side]]['landmarks']
        panel=frame.copy()
        if pose:
          _draw_pose_overlay(cv2, panel, {'keypoints': [{'name': name, **point, 'confidence': point['visibility']} for name,point in pose.items()]}, 'side', None)
        title=np.zeros((48,width,3),dtype=np.uint8)
        label=('Original 0.10.21' if side==0 else 'Candidate 0.10.30') + (' - GAP' if not pose else '')
        cv2.putText(title,label,(8,29),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1,cv2.LINE_AA)
        panels.append(np.vstack([title,panel]))
      encoder.stdin.write(np.hstack(panels).tobytes())
      index+=1
  finally:
    cap.release()
    encoder.stdin.close()
    code=encoder.wait(timeout=120)
    if code:
      raise RuntimeError('Comparison encoding failed.')
  print(args.output)


if __name__ == '__main__':
  main()
