#!/usr/bin/env python3
import json, re, sys, urllib.request, urllib.error, shutil, subprocess
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150.0.0.0 Safari/537.36"

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=20) as r:
        data=r.read()
        print(f"[GET] HTTP {r.status} bytes={len(data)} type={r.headers.get('Content-Type')} {url[:100]}")
        return data

def vlc():
    for x in (shutil.which("vlc"),r"C:\Program Files\VideoLAN\VLC\vlc.exe",
              r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"):
        if x and Path(x).exists(): return x

def main():
    jf=Path(sys.argv[1] if len(sys.argv)>1 else "film4k_playlists.json")
    rows=json.loads(jf.read_text(encoding="utf-8"))

    v=None
    for row in rows:
        if str(row.get("url","")).split("?",1)[0].endswith("/v.m3u8"):
            v=row; break
    if not v: raise SystemExit("Khong tim thay v.m3u8 trong JSON")

    body=v["body"]
    m=re.search(r'#EXT-X-MAP:URI="([^"]+)"',body)
    init=m.group(1) if m else None
    segs=[x.strip() for x in body.splitlines()
          if x.strip() and not x.lstrip().startswith("#") and x.strip().startswith("http")]
    if not init or not segs:
        raise SystemExit("Khong tim thay init/media segment trong v.m3u8")

    print("[INIT]",init)
    print("[VIDEO SEGMENT]",segs[0])
    init_b=get(init)
    seg_b=get(segs[0])

    # fMP4 fragmented media: init segment followed by one media fragment.
    out=Path("film4k_real_video_sample.mp4")
    out.write_bytes(init_b+seg_b)
    print(f"[SAVED] {out} bytes={out.stat().st_size}")

    player=vlc()
    if player:
        print("[VLC] opening real video init + first media segment")
        subprocess.Popen([player,str(out.resolve())])
    else:
        print("[VLC] not found; open film4k_real_video_sample.mp4 manually")

if __name__=="__main__":
    main()
