"""Linux-only bounded image normalizer; stdin/stdout contain image bytes only."""
from __future__ import annotations

import os
import resource
import sys


def main() -> None:
  codecs = {'jpeg': 'mjpeg', 'png': 'png', 'webp': 'webp'}
  if len(sys.argv) != 2 or sys.argv[1] not in codecs or not sys.platform.startswith('linux'):
    raise SystemExit(2)
  resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
  resource.setrlimit(resource.RLIMIT_CPU, (2, 3))
  resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
  resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024, 512 * 1024))
  # No shell, credentials, network/file media URLs, audio or additional frames.
  os.execv('/usr/bin/ffmpeg', [
    'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
    '-max_alloc', '67108864',
    '-threads', '1', '-filter_threads', '1', '-filter_complex_threads', '1',
    '-protocol_whitelist', 'pipe', '-f', 'image2pipe', '-c:v', codecs[sys.argv[1]], '-i', 'pipe:0',
    '-map', '0:v:0', '-frames:v', '1', '-an', '-sn', '-dn', '-map_metadata', '-1', '-map_chapters', '-1',
    '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,sidedata=mode=delete',
    '-threads', '1', '-c:v', 'mjpeg', '-flags:v', '+bitexact', '-q:v', '3', '-f', 'image2pipe', 'pipe:1',
  ])


if __name__ == '__main__':
  main()
