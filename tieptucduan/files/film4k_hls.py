#!/usr/bin/env python3
import json,re,sys,urllib.request,subprocess,shutil
from pathlib import Path
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150.0.0.0 Safari/537.36"

def get(u):
    q=urllib.request.Request(u,headers={"User-Agent":UA,"Accept":"*/*"})
    with urllib.request.urlopen(q,timeout=30) as r:
        b=r.read()
        print("[GET]",r.status,len(b),"bytes",r.headers.get("Content-Type"))
        return b

j=Path(sys.argv[1] if len(sys.argv)>1 else "film4k_playlists.json")
rows=json.loads(j.read_text(encoding="utf-8"))
v=next((x for x in rows if str(x.get("url","")).split("?",1)[0].endswith("/v.m3u8")),None)
if not v: raise SystemExit("Khong tim thay v.m3u8")
body=v["body"]
m=re.search(r'#EXT-X-MAP:URI="([^"]+)"',body)
urls=[x.strip() for x in body.splitlines() if x.strip().startswith("https://")]
if not m or not urls: raise SystemExit("Khong tim thay init/segment")
out=Path("film4k_hls_test"); out.mkdir(exist_ok=True)
(out/"init.mp4").write_bytes(get(m.group(1)))
lines=["#EXTM3U","#EXT-X-VERSION:7","#EXT-X-TARGETDURATION:20","#EXT-X-MEDIA-SEQUENCE:0",
       '#EXT-X-MAP:URI="init.mp4"']
for i,u in enumerate(urls[:3]):
    n=f"seg{i}.m4s"; (out/n).write_bytes(get(u))
    lines += ["#EXTINF:20.0,",n]
lines += ["#EXT-X-ENDLIST"]
pl=out/"video.m3u8"; pl.write_text("\n".join(lines)+"\n",encoding="utf-8")
print("[READY]",pl.resolve())
for x in (shutil.which("vlc"),r"C:\Program Files\VideoLAN\VLC\vlc.exe"):
    if x and Path(x).exists():
        subprocess.Popen([x,str(pl.resolve())]); break
