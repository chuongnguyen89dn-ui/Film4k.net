#!/usr/bin/env python3
"""
Attach to a user-started Chrome via CDP and observe Film4K player network traffic.

1) Close all Chrome windows.
2) Start Chrome yourself with:
   chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\film4k-debug"
3) In that Chrome, browse to Film4K normally and complete any normal site verification.
4) Run:
   python film4k_chrome_capture.py "https://film4k.net/movie/spider-man-brand-new-day"
5) Press Play in Chrome when instructed.

This tool observes traffic already accessible to your browser session.
It does not bypass CAPTCHA, DRM, authentication, or access controls.
"""
import argparse, asyncio, json, re, time
from pathlib import Path
from urllib.parse import urljoin

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Install: pip install playwright")
    raise SystemExit(2)

def classify(url, ct=""):
    u=(url or "").lower()
    c=(ct or "").lower().split(";")[0].strip()
    if ".m3u8" in u or c in ("application/vnd.apple.mpegurl","application/x-mpegurl"):
        return "HLS"
    if ".mpd" in u or c == "application/dash+xml":
        return "DASH"
    if re.search(r"\.mp4(?:$|\?)",u) or c == "video/mp4":
        return "MP4"
    if c.startswith("video/"):
        return "VIDEO"
    return None

def hls_info(text, base):
    variants=[]; audio=[]; subtitles=[]
    lines=[x.strip() for x in text.splitlines()]
    for i,line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            attrs=line.split(":",1)[1]
            res=re.search(r"RESOLUTION=(\d+)x(\d+)",attrs,re.I)
            bw=re.search(r"(?:AVERAGE-)?BANDWIDTH=(\d+)",attrs,re.I)
            nxt=next((x for x in lines[i+1:] if x and not x.startswith("#")),"")
            if nxt:
                variants.append({
                    "url":urljoin(base,nxt),
                    "width":int(res.group(1)) if res else None,
                    "height":int(res.group(2)) if res else None,
                    "bandwidth":int(bw.group(1)) if bw else None
                })
        elif line.startswith("#EXT-X-MEDIA:"):
            typ=re.search(r"TYPE=([^,]+)",line,re.I)
            uri=re.search(r'URI="([^"]+)"',line,re.I)
            name=re.search(r'NAME="([^"]+)"',line,re.I)
            lang=re.search(r'LANGUAGE="([^"]+)"',line,re.I)
            z={"name":name.group(1) if name else None,
               "language":lang.group(1) if lang else None,
               "url":urljoin(base,uri.group(1)) if uri else None}
            if typ and typ.group(1).upper()=="AUDIO": audio.append(z)
            if typ and typ.group(1).upper()=="SUBTITLES": subtitles.append(z)
    variants.sort(key=lambda x:(x["height"] or 0,x["bandwidth"] or 0),reverse=True)
    return variants,audio,subtitles

async def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", default="")
    ap.add_argument("--cdp", default="http://127.0.0.1:9222")
    ap.add_argument("--wait", type=int, default=60)
    ap.add_argument("--out", default="film4k_result.json")
    a=ap.parse_args()

    seen={}
    async with async_playwright() as pw:
        try:
            browser=await pw.chromium.connect_over_cdp(a.cdp)
        except Exception as e:
            print("[ERROR] Cannot attach to Chrome:", e)
            print('Start Chrome with --remote-debugging-port=9222 first.')
            raise SystemExit(3)

        if not browser.contexts:
            raise SystemExit("[ERROR] Chrome has no browser context")
        ctx=browser.contexts[0]
        pages=[p for p in ctx.pages if p.url.startswith("http")]
        if not pages:
            raise SystemExit("[ERROR] Open Film4K in the attached Chrome first.")

        page=next((p for p in pages if "film4k.net" in p.url), pages[-1])
        print("[ATTACHED]", page.url)

        async def record_response(resp):
            try:
                ct=resp.headers.get("content-type","")
                k=classify(resp.url,ct)
                if not k: return
                z=seen.setdefault(resp.url,{"url":resp.url,"type":k,"content_type":ct,"status":resp.status})
                z["status"]=resp.status
                req=resp.request
                z["request_headers"]={x:y for x,y in req.headers.items()
                    if x.lower() in ("referer","origin","user-agent","accept","range")}
                if k=="HLS" and 200 <= resp.status < 400:
                    try:
                        body=await resp.text()
                        if body.lstrip().startswith("#EXTM3U"):
                            z["verified_manifest"]=True
                            vs,aud,sub=hls_info(body,resp.url)
                            z["variants"]=vs; z["audio"]=aud; z["subtitles"]=sub
                    except Exception as e:
                        z["body_error"]=str(e)
                elif k=="DASH" and 200 <= resp.status < 400:
                    try:
                        body=await resp.text()
                        z["verified_manifest"]=("<MPD" in body[:5000] or "<mpd" in body[:5000].lower())
                    except: pass
            except: pass

        # Register on all current pages. New popup/tab is also handled.
        registered=set()
        def reg(pg):
            if id(pg) in registered: return
            registered.add(id(pg))
            pg.on("response",record_response)
        for pg in ctx.pages: reg(pg)
        ctx.on("page",reg)

        if a.url and a.url not in page.url:
            print("[INFO] Navigate in Chrome to:",a.url)
        print("[ACTION] If the movie page is open, press Play now.")
        print(f"[CAPTURE] Observing for {a.wait} seconds...")

        # Also poll performance entries so already-started resources can be noticed.
        end=time.time()+a.wait
        while time.time()<end:
            for pg in list(ctx.pages):
                try:
                    for fr in pg.frames:
                        try:
                            entries=await fr.evaluate("""() => performance.getEntriesByType('resource').map(x=>x.name)""")
                            for u in entries:
                                k=classify(u,"")
                                if k:
                                    seen.setdefault(u,{"url":u,"type":k,"seen_via":"performance"})
                        except: pass
                except: pass
            await asyncio.sleep(1)

        # Validate only actual media candidates in the SAME Chrome context.
        items=[]
        referer=page.url
        for u,z in list(seen.items()):
            try:
                r=await ctx.request.get(u,headers={"Referer":referer},timeout=20000)
                ct=r.headers.get("content-type","")
                real=classify(u,ct)
                z["validation_status"]=r.status
                z["validation_content_type"]=ct
                z["type"]=real or z.get("type")
                z["http_ok"]=200 <= r.status < 400
                if z["type"]=="HLS" and z["http_ok"]:
                    txt=await r.text()
                    z["verified_manifest"]=txt.lstrip().startswith("#EXTM3U")
                    if z["verified_manifest"]:
                        vs,aud,sub=hls_info(txt,u)
                        z["variants"]=vs; z["audio"]=aud; z["subtitles"]=sub
                        test=vs[0]["url"] if vs else u
                        vr=await ctx.request.get(test,headers={"Referer":referer},timeout=20000)
                        z["variant_status"]=vr.status
                        if 200 <= vr.status < 400:
                            vt=await vr.text()
                            seg=next((x for x in (q.strip() for q in vt.splitlines())
                                      if x and not x.startswith("#")),None)
                            if seg:
                                su=urljoin(test,seg)
                                sr=await ctx.request.get(su,headers={"Referer":referer,"Range":"bytes=0-1023"},timeout=20000)
                                z["segment_url"]=su
                                z["segment_status"]=sr.status
                                z["segment_ok"]=sr.status in (200,206)
                if z["type"]=="DASH" and z["http_ok"]:
                    txt=await r.text()
                    z["verified_manifest"]="<mpd" in txt[:10000].lower()
            except Exception as e:
                z["validation_error"]=str(e)
            items.append(z)

        def score(z):
            return (bool(z.get("segment_ok")),
                    bool(z.get("verified_manifest")),
                    bool(z.get("http_ok")),
                    {"HLS":4,"DASH":3,"MP4":2,"VIDEO":1}.get(z.get("type"),0),
                    max([v.get("height") or 0 for v in z.get("variants",[])] or [0]))
        items.sort(key=score,reverse=True)
        best=items[0] if items and (items[0].get("verified_manifest") or items[0].get("http_ok")) else None

        result={
            "page":page.url,
            "title":await page.title(),
            "best":best,
            "sources":items,
            "generated_at":int(time.time())
        }
        Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")

        print("\n=== RESULT ===")
        print("TITLE =",result["title"])
        if best:
            print("SOURCE =",best["url"])
            print("TYPE =",best.get("type"))
            print("MANIFEST_OK =",best.get("verified_manifest"))
            if best.get("variants"):
                print("QUALITIES =",",".join(f'{v["height"]}p' for v in best["variants"] if v.get("height")))
                print("BEST =",best["variants"][0]["url"])
            print("SEGMENT_OK =",best.get("segment_ok"))
        else:
            print("SOURCE = NOT FOUND")
        print("JSON =",a.out)

        # Disconnect only. Do not close user's Chrome.
        await browser.close()

if __name__=="__main__":
    asyncio.run(main())
