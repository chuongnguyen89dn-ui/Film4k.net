#!/usr/bin/env python3
import json, shutil, subprocess, sys
from pathlib import Path

d = Path("film4k_hls_test")
files = [d/"init.mp4"] + sorted(d.glob("seg*.m4s"))
if not all(x.exists() for x in files[:2]):
    raise SystemExit("Khong thay film4k_hls_test\\init.mp4 va seg*.m4s")

ffprobe = shutil.which("ffprobe")
ffmpeg = shutil.which("ffmpeg")

print("=== FILES ===")
for f in files:
    print(f, f.stat().st_size, "bytes")

if ffprobe:
    print("\n=== FFPROBE INIT ===")
    subprocess.run([ffprobe, "-hide_banner", "-v", "error",
                    "-show_entries", "stream=index,codec_name,codec_long_name,codec_type,profile,width,height,pix_fmt,codec_tag_string",
                    "-of", "json", str(files[0])])
else:
    print("\n[FFPROBE] not installed")

# Build one fragmented MP4 from the already-downloaded local init + fragments.
joined = d/"video_fragments.mp4"
with joined.open("wb") as w:
    for f in files:
        w.write(f.read_bytes())
print("\n[JOINED]", joined.resolve(), joined.stat().st_size, "bytes")

if ffprobe:
    print("\n=== FFPROBE JOINED ===")
    subprocess.run([ffprobe, "-hide_banner", "-v", "error",
                    "-show_entries", "format=format_name,duration:stream=index,codec_name,codec_type,profile,width,height,pix_fmt",
                    "-of", "json", str(joined)])

# If ffmpeg exists, remux the local fragmented MP4 without re-encoding.
remux = d/"video_remux.mkv"
if ffmpeg:
    print("\n=== REMUX ===")
    r = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "warning",
                        "-i", str(joined), "-map", "0:v:0", "-c", "copy", str(remux)])
    if r.returncode == 0 and remux.exists():
        print("[REMUX_OK]", remux.resolve(), remux.stat().st_size, "bytes")
        target = remux
    else:
        print("[REMUX_FAIL]")
        target = joined
else:
    print("[FFMPEG] not installed")
    target = joined

vlc = next((x for x in (
    shutil.which("vlc"),
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
) if x and Path(x).exists()), None)

if vlc:
    print("[VLC]", target.resolve())
    subprocess.Popen([vlc, "--play-and-exit", str(target.resolve())])
else:
    print("[VLC] not found")
