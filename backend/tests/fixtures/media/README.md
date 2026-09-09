# Generated media fixture

`portrait-vp9.webm` is a one-second synthetic FFmpeg test pattern for the offline
upload-format smoke check. It contains no user footage and is not pose evidence.

Regenerate with:

```sh
ffmpeg -y -f lavfi -i testsrc2=size=64x96:rate=5 -t 1 -c:v libvpx-vp9 portrait-vp9.webm
```
