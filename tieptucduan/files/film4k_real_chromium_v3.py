#!/usr/bin/env python3
import argparse, asyncio, json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Run: pip install playwright && playwright install chromium")
    raise SystemExit(2)

MEDIA_RE = re.compile(r"(?i)(https?://[^\s\"'<>\\]+?(?:\.m3u8|\.mpd|\.mp4|\.m4v|\.webm|\.mkv|\.ts|\.m4s)(?:\?[^\s\"'<>\\]*)?)")
URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.I)
KEYWORDS = (".m3u8",".mpd",".mp4","manifest","playlist","master","source","stream","video","hls","dash")

def uniq(xs):
    out=[]; seen=set()
    for x in xs:
        if x and x not in seen: seen.add(x); out.append(x)
    return out

def kind(url, ct=""):
    u=url.lower(); ct=(ct or "").lower()
    if ".m3u8" in u or "mpegurl" in ct: return "HLS"
    if ".mpd" in u or "dash+xml" in ct: return "DASH"
    if ".mp4" in u or "video/mp4" in ct: return "MP4"
    if ct.startswith("video/"): return "VIDEO"
    return "UNKNOWN"

def extract(text, base=""):
    if not text: return []
    text=text.replace("\\/","/").replace("\\u0026","&")
    out=MEDIA_RE.findall(text)
    for u in URL_RE.findall(text):
        if any(k in u.lower() for k in KEYWORDS): out.append(u.rstrip("),]}"))
    for x in re.findall(r'(?i)["\']([^"\']+\.(?:m3u8|mpd|mp4|m4v|webm)(?:\?[^"\']*)?)["\']', text):
        if base: out.append(urljoin(base,x))
    return uniq(out)

def parse_master(text, base):
    vs=[]; aud=[]; sub=[]
    lines=[x.strip() for x in text.splitlines()]
    for i,line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            a=line.split(":",1)[1]
            res=re.search(r"RESOLUTION=(\d+)x(\d+)",a,re.I)
            bw=re.search(r"(?:AVERAGE-)?BANDWIDTH=(\d+)",a,re.I)
            nxt=next((x for x in lines[i+1:] if x and not x.startswith("#")),"")
            if nxt: vs.append({"url":urljoin(base,nxt),"width":int(res.group(1)) if res else None,
                                "height":int(res.group(2)) if res else None,
                                "bandwidth":int(bw.group(1)) if bw else None})
        elif line.startswith("#EXT-X-MEDIA:"):
            typ=re.search(r"TYPE=([^,]+)",line,re.I); uri=re.search(r'URI="([^"]+)"',line,re.I)
            name=re.search(r'NAME="([^"]+)"',line,re.I); lang=re.search(r'LANGUAGE="([^"]+)"',line,re.I)
            z={"name":name.group(1) if name else None,"language":lang.group(1) if lang else None,
               "url":urljoin(base,uri.group(1)) if uri else None}
            if typ and typ.group(1).upper()=="AUDIO": aud.append(z)
            if typ and typ.group(1).upper()=="SUBTITLES": sub.append(z)
    vs.sort(key=lambda x:(x["height"] or 0,x["bandwidth"] or 0),reverse=True)
    return vs,aud,sub

async def main():
    ap=argparse.ArgumentParser(description="Film4K browser source discovery/validator")
    ap.add_argument("url")
    ap.add_argument("--headed",action="store_true")
    ap.add_argument("--wait",type=int,default=30)
    ap.add_argument("--out",default="film4k_result.json")
    ap.add_argument("--profile",default=".film4k-profile")
    a=ap.parse_args()
    if urlparse(a.url).scheme not in ("http","https"): raise SystemExit("URL must be http/https")

    cand={}; net=[]; title=None
    async with async_playwright() as p:
        chromium_exe = r"C:\Users\Trinh\AppData\Local\Chromium\Application\chrome.exe"
        if not Path(chromium_exe).exists():
            raise SystemExit(f"[ERROR] Chromium not found: {chromium_exe}")
        print("[BROWSER]", chromium_exe)
        real_user_data = r"C:\Users\Trinh\AppData\Local\Chromium\User Data"
        print("[PROFILE]", real_user_data, r"\Default")
        try:
            ctx=await p.chromium.launch_persistent_context(
                user_data_dir=real_user_data,
                executable_path=chromium_exe,
                headless=False,
                viewport=None,
                args=[
                    "--profile-directory=Default",
                    "--start-maximized",
                    "--no-first-run",
                    "--no-default-browser-check"
                ]
            )
        except Exception as e:
            print("[ERROR] Cannot open the real Chromium profile.")
            print("[ACTION] Close ALL blue Chromium windows first, then run this script again.")
            print("[DETAIL]", e)
            raise SystemExit(3)
        # ungoogled-chromium can reject Playwright Target.createTarget when using
        # the real Default profile. Reuse the browser-created tab instead.
        pages = list(ctx.pages)
        if not pages:
            print("[ERROR] Chromium started but exposed no initial tab.")
            print("[ACTION] Open one normal tab in this Chromium profile and retry.")
            raise SystemExit(4)
        page = pages[0]
        print("[INITIAL_TAB]", page.url)
        print("[TARGET]", a.url)
        try:
            await page.bring_to_front()
        except Exception:
            pass

        async def remember(u,src,ct="",headers=None):
            if not u or not u.startswith(("http://","https://")): return
            k=kind(u,ct)
            if k!="UNKNOWN" or any(x in u.lower() for x in KEYWORDS):
                z=cand.setdefault(u,{"url":u,"kind":k,"seen_from":[],"content_type":ct})
                if src not in z["seen_from"]: z["seen_from"].append(src)
                if ct and not z.get("content_type"): z["content_type"]=ct
                if headers:
                    z["request_headers"]={x:y for x,y in headers.items()
                        if x.lower() in ("referer","origin","user-agent","accept","range")}

        async def req(r):
            try:
                if r.resource_type in ("media","xhr","fetch","document"):
                    net.append({"type":r.resource_type,"method":r.method,"url":r.url})
                    await remember(r.url,"request:"+r.resource_type,headers=r.headers)
            except: pass

        async def resp(r):
            try:
                ct=(r.headers.get("content-type") or "").lower()
                await remember(r.url,"response",ct)
                cl=r.headers.get("content-length")
                if ("json" in ct or "javascript" in ct or "mpegurl" in ct or "dash+xml" in ct or "text/" in ct) and (not cl or int(cl)<3000000):
                    try:
                        body=await r.text()
                        for u in extract(body[:3000000],r.url): await remember(u,"body:"+r.url,ct)
                    except: pass
            except: pass

        page.on("request",req); page.on("response",resp)
        print("[OPEN]",a.url)
        try:
            nav = await page.goto(a.url, wait_until="domcontentloaded", timeout=60000)
            print("[NAV_STATUS]", nav.status if nav else "no-response")
            print("[CURRENT_URL]", page.url)
            await page.bring_to_front()
        except Exception as e:
            print("[NAV_ERROR]", e)
            print("[CURRENT_URL]", page.url)
        try: title=await page.title()
        except: pass

        end=time.time()+max(5,a.wait); clicked=set()
        while time.time()<end:
            for fr in page.frames:
                try:
                    await remember(fr.url,"frame")
                    for u in extract(await fr.content(),fr.url): await remember(u,"dom:"+fr.url)
                    vals=await fr.eval_on_selector_all("video,source,iframe",
                        """els=>els.flatMap(e=>[e.src,e.currentSrc,e.getAttribute('src'),e.getAttribute('data-src'),
                        e.getAttribute('data-file'),e.getAttribute('data-url')]).filter(Boolean)""")
                    for u in vals: await remember(urljoin(fr.url,u),"element:"+fr.url)
                    for sel in ("video","button[aria-label*='play' i]","[class*='play' i]","[id*='play' i]"):
                        if (fr.url,sel) in clicked: continue
                        loc=fr.locator(sel).first
                        if await loc.count():
                            try: await loc.click(timeout=700); clicked.add((fr.url,sel))
                            except: pass
                except: pass
            await page.wait_for_timeout(1000)

        for fr in page.frames:
            try:
                for u in await fr.evaluate("()=>performance.getEntriesByType('resource').map(x=>x.name)"):
                    await remember(u,"performance:"+fr.url)
            except: pass

        cookies=await ctx.cookies()
        ua=await page.evaluate("()=>navigator.userAgent")
        validated=[]
        for u,z in list(cand.items()):
            try:
                r=await ctx.request.get(u,headers={"Referer":a.url},timeout=20000)
                ct=r.headers.get("content-type","")
                z.update(status=r.status,content_type=ct or z.get("content_type",""),
                         kind=kind(u,ct),playable_http=200<=r.status<400)
                if z["kind"]=="HLS" and z["playable_http"]:
                    txt=await r.text(); z["is_manifest"]="#EXTM3U" in txt
                    if z["is_manifest"]:
                        vs,aud,sub=parse_master(txt,u); z.update(variants=vs,audio=aud,subtitles=sub)
                        test=vs[0]["url"] if vs else u
                        vr=await ctx.request.get(test,headers={"Referer":a.url},timeout=20000)
                        z["best_variant_status"]=vr.status
                        if 200<=vr.status<400:
                            vt=await vr.text()
                            seg=next((x.strip() for x in vt.splitlines() if x.strip() and not x.startswith("#")),None)
                            if seg:
                                su=urljoin(test,seg)
                                sr=await ctx.request.get(su,headers={"Referer":a.url,"Range":"bytes=0-1023"},timeout=20000)
                                z.update(segment_test_url=su,segment_status=sr.status,segment_ok=sr.status in (200,206))
                validated.append(z)
            except Exception as e:
                z["validation_error"]=str(e); validated.append(z)

        def score(x):
            return (bool(x.get("segment_ok")),bool(x.get("is_manifest")),bool(x.get("playable_http")),
                    {"HLS":4,"DASH":3,"MP4":2,"VIDEO":1}.get(x.get("kind"),0),
                    max([v.get("height") or 0 for v in x.get("variants",[])] or [0]))
        validated.sort(key=score,reverse=True)
        best=validated[0] if validated and any(score(validated[0])[:3]) else None
        result={"page":a.url,"title":title,"user_agent":ua,"best":best,"candidates":validated,
                "cookies":[{k:c[k] for k in ("name","value","domain","path","expires")} for c in cookies],
                "network_sample":net[-500:],"generated_at_unix":int(time.time())}
        Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print("\n=== RESULT ==="); print("TITLE =",title)
        if best:
            print("SOURCE =",best["url"]); print("TYPE =",best.get("kind"))
            if best.get("variants"):
                print("QUALITIES =",",".join(str(v["height"])+"p" for v in best["variants"] if v.get("height")))
                print("BEST =",best["variants"][0]["url"])
            print("HTTP_OK =",best.get("playable_http")); print("SEGMENT_OK =",best.get("segment_ok"))
        else:
            print("SOURCE = NOT VERIFIED")
            print("Use --headed and interact with the normal page/player if required.")
        print("JSON =",a.out)
        await ctx.close()

if __name__=="__main__":
    asyncio.run(main())
