import json, re, sys, subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "film4k_network_all.json")
OUT = Path("film4k_vlc_clean")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
VLC = Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe")
PNG = b"\x89PNG\r\n\x1a\n"

def png_end(b):
    if not b.startswith(PNG): return 0
    p=8
    while p+12 <= len(b):
        n=int.from_bytes(b[p:p+4],"big")
        typ=b[p+4:p+8]
        e=p+12+n
        if e>len(b): return 0
        if typ==b"IEND": return e
        p=e
    return 0

def get(url):
    with urlopen(Request(url,headers={"User-Agent":UA,"Accept":"*/*"}),timeout=90) as r:
        return r.read()

rows=json.loads(SRC.read_text(encoding="utf-8"))
vrow=next((x for x in rows if x.get("url","").endswith("/v.m3u8")),None)
if not vrow:
    raise SystemExit("Khong tim thay v.m3u8 trong JSON.")

vurl=vrow["url"]
# Fetching the Film4K playlist outside the browser may require its play-ticket,
# so use the playlist body from a companion capture if present; otherwise fail clearly.
playlist_file=Path("film4k_playlists.json")
body=None
if playlist_file.exists():
    try:
        p=json.loads(playlist_file.read_text(encoding="utf-8"))
        seq=p if isinstance(p,list) else p.get("playlists",[])
        for x in seq:
            if isinstance(x,dict) and str(x.get("url","")).endswith("/v.m3u8"):
                body=x.get("body") or x.get("text")
                if body: break
    except Exception:
        pass

# If old playlist capture is absent, derive Worker URLs directly from current trace.
# Preserve trace order; first small Worker item is normally init, larger items are fragments.
workers=[x["url"] for x in rows if "film4knet.ngaodacopho.workers.dev/tt/" in x.get("url","")]
if not workers:
    raise SystemExit("Khong co Worker URL trong trace.")

OUT.mkdir(exist_ok=True)
local=[]

print("[DOWNLOAD/CLEAN]")
for i,u in enumerate(workers[:8]):
    raw=get(u)
    pe=png_end(raw)
    clean=raw[pe:] if pe else raw
    if not any(t in clean[:512] for t in (b"ftyp",b"styp",b"moov",b"moof",b"sidx",b"mdat")):
        print(f"[SKIP {i}] not MP4 after PNG, raw={len(raw)}, png_end={pe}")
        continue
    fn=OUT / ("init.mp4" if not local else f"seg{len(local):02}.m4s")
    fn.write_bytes(clean)
    local.append(fn)
    print(f"[OK] {fn.name}: raw={len(raw)} png={pe} clean={len(clean)}")

if len(local)<2:
    raise SystemExit("Chua du init/segment MP4 sach de test VLC.")

# Build a short local HLS. First cleaned object is treated as init; remaining as media fragments.
m3u = [
    "#EXTM3U",
    "#EXT-X-VERSION:7",
    "#EXT-X-TARGETDURATION:23",
    "#EXT-X-MEDIA-SEQUENCE:0",
    '#EXT-X-MAP:URI="init.mp4"',
]
for fn in local[1:]:
    m3u += ["#EXTINF:20.000,", fn.name]
m3u += ["#EXT-X-ENDLIST", ""]
pl=OUT/"video.m3u8"
pl.write_text("\n".join(m3u),encoding="utf-8")
print("[PLAYLIST]", pl.resolve())

if VLC.exists():
    print("[VLC] opening...")
    subprocess.Popen([str(VLC), str(pl.resolve()), "--play-and-exit"])
else:
    print("[VLC_NOT_FOUND] Open manually:", pl.resolve())
