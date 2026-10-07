import json, re, sys
from pathlib import Path
from urllib.request import Request, urlopen

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "film4k_network_all.json")
OUT = Path("film4k_extracted")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
PNG_SIG = b"\x89PNG\r\n\x1a\n"

def png_end(data):
    if not data.startswith(PNG_SIG):
        return None
    p = 8
    while p + 12 <= len(data):
        n = int.from_bytes(data[p:p+4], "big")
        typ = data[p+4:p+8]
        end = p + 12 + n
        if end > len(data):
            return None
        if typ == b"IEND":
            return end
        p = end
    return None

def boxes(data, limit=512):
    names = []
    for tag in (b"ftyp", b"styp", b"moov", b"moof", b"mdat", b"sidx"):
        i = data[:limit].find(tag)
        if i >= 0:
            names.append(f"{tag.decode()}@{i}")
    return names

def get(url):
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=60) as r:
        return r.status, dict(r.headers.items()), r.read()

rows = json.loads(SRC.read_text(encoding="utf-8"))
candidates = []
for x in rows:
    u = x.get("url","")
    if "film4knet.ngaodacopho.workers.dev/tt/" in u and int(x.get("bytes") or 0) > 100000:
        candidates.append(x)

if not candidates:
    raise SystemExit("Khong tim thay Worker response lon trong JSON.")

OUT.mkdir(exist_ok=True)
print("[FOUND]", len(candidates), "large Worker responses")

for idx, x in enumerate(candidates[:4], 1):
    url = x["url"]
    print(f"\n[{idx}] downloading {url[:100]}...")
    status, hdr, data = get(url)
    print(" HTTP", status, "bytes=", len(data), "type=", hdr.get("Content-Type"))
    pe = png_end(data)
    print(" PNG IEND offset:", pe)

    if pe is None:
        print(" Not a complete PNG prefix.")
        continue

    tail = data[pe:]
    print(" tail bytes:", len(tail))
    print(" tail first64:", tail[:64].hex())
    print(" MP4 boxes:", ", ".join(boxes(tail)) or "NONE")

    # Also search shortly after IEND in case padding/metadata exists.
    window = tail[:4096]
    hits = []
    for tag in (b"ftyp", b"styp", b"moov", b"moof", b"mdat"):
        pos = window.find(tag)
        if pos >= 0:
            hits.append((pos, tag))
    if hits:
        start = max(0, min(p for p,_ in hits) - 4)
        payload = tail[start:]
        name = OUT / f"payload_{idx}.bin"
        name.write_bytes(payload)
        print(" SAVED candidate media:", name, "bytes=", len(payload), "start=", start)
    else:
        name = OUT / f"tail_{idx}.bin"
        name.write_bytes(tail[:65536])
        print(" No MP4 box in first 4096 tail bytes; saved diagnostic:", name)

print("\n[DONE] folder:", OUT.resolve())
