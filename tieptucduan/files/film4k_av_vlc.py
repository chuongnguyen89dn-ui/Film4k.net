import asyncio, re, subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from playwright.async_api import async_playwright

MOVIE="https://film4k.net/movie/spider-man-brand-new-day"
CHROME=r"C:\Users\Trinh\AppData\Local\Chromium\Application\chrome.exe"
PROFILE=r"C:\Users\Trinh\AppData\Local\Chromium\User Data"
VLC=Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe")
OUT=Path("film4k_av_clean")
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
PNG=b"\x89PNG\r\n\x1a\n"

def png_end(b):
    if not b.startswith(PNG): return 0
    p=8
    while p+12<=len(b):
        n=int.from_bytes(b[p:p+4],"big"); typ=b[p+4:p+8]; e=p+12+n
        if e>len(b): return 0
        if typ==b"IEND": return e
        p=e
    return 0

def clean_get(url):
    with urlopen(Request(url,headers={"User-Agent":UA,"Accept":"*/*"}),timeout=120) as r: b=r.read()
    p=png_end(b)
    return b[p:] if p else b

def parse(body):
    init=None; seg=[]; dur=[]
    for s in body.splitlines():
        s=s.strip()
        if s.startswith("#EXT-X-MAP:"):
            m=re.search(r'URI="([^"]+)"',s)
            if m:init=m.group(1)
        elif s.startswith("#EXTINF:"):
            try:dur.append(float(s.split(":",1)[1].split(",",1)[0]))
            except:dur.append(20.0)
        elif s and not s.startswith("#") and "workers.dev/tt/" in s: seg.append(s)
    return init,seg,dur

async def main():
    bodies={}
    async with async_playwright() as p:
        ctx=await p.chromium.launch_persistent_context(PROFILE,executable_path=CHROME,headless=False,args=["--profile-directory=Default"])
        page=ctx.pages[0]
        async def got(r):
            if re.search(r"/(master|v|a[0-9]+)\.m3u8$",r.url):
                try:bodies[r.url]=(await r.body()).decode("utf-8","replace")
                except:pass
        page.on("response",got)
        await page.goto(MOVIE,wait_until="domcontentloaded",timeout=90000)
        print("[ACTION] Bam Play, de chay 20 giay...")
        await page.wait_for_timeout(35000)
        await ctx.close()

    master=next((b for u,b in bodies.items() if u.endswith("/master.m3u8")),None)
    video=next((b for u,b in bodies.items() if u.endswith("/v.m3u8")),None)
    if not master or not video: raise SystemExit("Chua bat du master/video. Chay lai va bam Play.")

    preferred=[]
    for line in master.splitlines():
        if "#EXT-X-MEDIA:TYPE=AUDIO" in line:
            m=re.search(r'URI="([^"]+)"',line)
            if m:
                name=m.group(1).split("/")[-1]
                score=0 if ("ViE" in line or 'LANGUAGE="vi"' in line) else 1
                preferred.append((score,name))
    preferred.sort()
    audio=None; aname=None
    for _,name in preferred:
        x=next((b for u,b in bodies.items() if u.endswith("/"+name)),None)
        if x: audio=x; aname=name; break
    if not audio:
        for u,b in bodies.items():
            if re.search(r"/a[0-9]+\.m3u8$",u): audio=b; aname=u.rsplit("/",1)[-1]; break
    if not audio: raise SystemExit("Chua bat audio playlist.")

    OUT.mkdir(exist_ok=True)
    def build(body,prefix,n=4):
        init,segs,durs=parse(body)
        if not init or not segs: raise RuntimeError(prefix+" thieu init/segment")
        (OUT/f"{prefix}_init.mp4").write_bytes(clean_get(init))
        lines=["#EXTM3U","#EXT-X-VERSION:7","#EXT-X-TARGETDURATION:23","#EXT-X-MEDIA-SEQUENCE:0",f'#EXT-X-MAP:URI="{prefix}_init.mp4"']
        for i,u in enumerate(segs[:n]):
            fn=f"{prefix}_{i:02}.m4s"; (OUT/fn).write_bytes(clean_get(u))
            lines += [f"#EXTINF:{(durs[i] if i<len(durs) else 20):.3f},",fn]
            print("[OK]",fn)
        lines += ["#EXT-X-ENDLIST",""]
        (OUT/f"{prefix}.m3u8").write_text("\n".join(lines),encoding="utf-8")

    build(video,"video")
    print("[AUDIO]",aname)
    build(audio,"audio")
    master_local = '#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",NAME="Audio",DEFAULT=YES,AUTOSELECT=YES,URI="audio.m3u8"\n#EXT-X-STREAM-INF:BANDWIDTH=30000000,CODECS="hev1.2.4.L150.B0,mp4a.40.2",AUDIO="aud"\nvideo.m3u8\n'
    pl=OUT/"master.m3u8"; pl.write_text(master_local,encoding="utf-8")
    print("[READY]",pl.resolve())
    if VLC.exists(): subprocess.Popen([str(VLC),str(pl.resolve())])
    else: print("Mo VLC:",pl.resolve())

asyncio.run(main())
