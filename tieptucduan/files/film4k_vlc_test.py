#!/usr/bin/env python3
import json, os, shutil, subprocess, sys
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150.0.0.0 Safari/537.36"

def find_vlc():
    for x in (
        shutil.which("vlc"),
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ):
        if x and Path(x).exists():
            return x
    raise SystemExit("Khong tim thay VLC")

def find_segment(obj):
    best = obj.get("best") if isinstance(obj, dict) else None
    if isinstance(best, dict):
        for k in ("segment_test_url", "segment_url"):
            if best.get(k):
                return best[k]
    for k in ("segment_test_url", "segment_url"):
        if isinstance(obj, dict) and obj.get(k):
            return obj[k]
    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                r = walk(x)
                if r: return r
        elif isinstance(v, list):
            for x in v:
                r = walk(x)
                if r: return r
        elif isinstance(v, str) and "workers.dev/" in v and v.startswith("http"):
            return v
    return walk(obj)

def main():
    jf = Path(sys.argv[1] if len(sys.argv) > 1 else "film4k_result.json")
    if not jf.exists():
        raise SystemExit(f"Khong thay {jf}")
    data = json.loads(jf.read_text(encoding="utf-8"))
    seg = find_segment(data)
    if not seg:
        raise SystemExit("Khong tim thay CDN segment trong JSON")

    vlc = find_vlc()
    print("[VLC]", vlc)
    print("[SEGMENT]", seg)
    print("[TEST] VLC mo truc tiep CDN segment voi User-Agent da PASS HTTP 206")
    subprocess.Popen([
        vlc,
        "--http-user-agent=" + UA,
        "--network-caching=1000",
        seg,
    ])

if __name__ == "__main__":
    main()
