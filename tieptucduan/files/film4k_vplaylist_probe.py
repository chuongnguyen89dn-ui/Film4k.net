#!/usr/bin/env python3
import argparse
import urllib.request
import urllib.error, asyncio, json, re, time
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

        media_trace = []
        playlist_bodies = []
        async def trace_response(resp):
            try:
                u = resp.url
                req = resp.request
                rt = req.resource_type
                ct = (resp.headers.get("content-type") or "").lower()
                path = u.split("?", 1)[0].lower()
                media_ext = any(path.endswith(x) for x in (".m3u8", ".m4s", ".mp4", ".ts", ".aac", ".m4a", ".webm"))
                media_ct = any(x in ct for x in ("mpegurl", "video/", "audio/", "mp2t", "mp4", "octet-stream"))
                if media_ext or media_ct or rt == "media":
                    media_trace.append({
                        "status": resp.status,
                        "resource_type": rt,
                        "content_type": ct,
                        "url": u,
                    })
                    print(f"[MEDIA] {resp.status} {rt:8} {ct[:32]:32} {u}", flush=True)

                    # Capture the exact child HLS playlist body already returned
                    # to the normal page. No extra endpoint guessing.
                    if resp.status == 200 and path.endswith(".m3u8"):
                        try:
                            body = await resp.text()
                            playlist_bodies.append({"url": u, "body": body})
                            if path.endswith("/v.m3u8"):
                                print("\n=== V.M3U8 BODY ===")
                                print(body[:12000])
                                print("=== END V.M3U8 ===\n")
                        except Exception as e:
                            print(f"[PLAYLIST_BODY_ERROR] {type(e).__name__}: {e}")
            except Exception:
                pass

        page.on("response", trace_response)
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
                u0=r.url.lower()
                # Only inspect API/manifest bodies. Static JS/CSS can contain
                # library example strings that look like media URLs.
                if ("json" in ct or "mpegurl" in ct or "dash+xml" in ct or
                    "/api/" in u0 or u0.endswith(".m3u8") or u0.endswith(".mpd")) and (not cl or int(cl)<3000000):
                    try:
                        body=await r.text()
                        for u in extract(body[:3000000],r.url):
                            await remember(u,"body:"+r.url,ct)
                    except: pass
            except: pass

        page.on("request",req); page.on("response",resp)

        # Keep the movie page as the primary target. Observe popups, but never
        # replace/navigate the movie page because an ad opened another tab.
        async def attach_extra(pg):
            try:
                pg.on("request", req)
                pg.on("response", resp)
                print("[POPUP]", pg.url)
            except Exception:
                pass

        def on_new_page(pg):
            asyncio.create_task(attach_extra(pg))

        ctx.on("page", on_new_page)
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

        print("[CAPTURE] Automatic Film4K discovery active.")
        slug = urlparse(a.url).path.rstrip("/").split("/")[-1]
        # Give the title page a moment to load its source catalogue, then open
        # Film4K's own watch route. No synthetic click/ad interaction is used.
        await asyncio.sleep(3)
        watch_url = f"https://film4k.net/watch/{slug}"
        if "/watch/" not in urlparse(page.url).path:
            print("[WATCH]", watch_url)
            try:
                nav2 = await page.goto(watch_url, wait_until="domcontentloaded", timeout=60000)
                print("[WATCH_STATUS]", nav2.status if nav2 else "no-response")
            except Exception as e:
                print("[WATCH_ERROR]", e)

        # End as soon as the real watch API has emitted a master HLS source.
        end=time.time()+max(8,a.wait)
        last_beat=0
        while time.time()<end:
            active = [
                z for z in cand.values()
                if "/api/hls/" in (z.get("url") or "").lower()
                and (z.get("url") or "").lower().endswith("/master.m3u8")
                and any("/api/watch/" in s for s in (z.get("seen_from") or []))
            ]
            if active:
                await asyncio.sleep(1.5)
                break
            left=int(end-time.time())
            if time.time()-last_beat >= 5:
                print("[WAIT] discovering active source...", max(0,left), "s")
                last_beat=time.time()
            await asyncio.sleep(0.25)

        print("[CAPTURE_DONE] Captured",len(cand),"candidates.")
        cookies=await ctx.cookies()
        ua=await page.evaluate("()=>navigator.userAgent")
        validated=[]

        def priority(z):
            u=(z.get("url") or "").lower()
            seen=" ".join(z.get("seen_from") or []).lower()
            ct=(z.get("content_type") or "").lower()
            s=0
            if "/api/hls/" in u and u.endswith("/master.m3u8"): s+=1000
            elif u.endswith("/master.m3u8"): s+=800
            elif u.endswith(".m3u8"): s+=500
            elif u.endswith(".mpd"): s+=400
            if "request:" in seen or "response" in seen: s+=200
            if "body:https://film4k.net/api/" in seen: s+=150
            if "mpegurl" in ct or "dash+xml" in ct: s+=100
            if "/assets/" in u or u.endswith(".js") or u.endswith(".css"): s-=2000
            if "time.akamai.com" in u: s-=5000
            return s

        likely=sorted(cand.values(),key=priority,reverse=True)
        # Validate only master manifests. Child playlists are validated through
        # their master, so there is no reason to test dozens of candidates.
        likely=[
            z for z in likely
            if priority(z)>0
            and "/api/hls/" in (z.get("url") or "").lower()
            and (z.get("url") or "").lower().endswith("/master.m3u8")
        ]
        # Deduplicate by URL and prefer the active /api/watch source first.
        dedup=[]; seen_master=set()
        for z in likely:
            if z["url"] not in seen_master:
                seen_master.add(z["url"]); dedup.append(z)
        likely=dedup[:12]
        print("[VALIDATE]",len(likely),"master sources")

        for i,z0 in enumerate(likely,1):
            z=dict(z0)
            u=z["url"]
            try:
                hdr={"User-Agent":ua}
                rh=z.get("request_headers") or {}
                ref=rh.get("referer") or rh.get("Referer") or page.url
                hdr["Referer"]=ref
                r=await ctx.request.get(u,headers=hdr,timeout=5000)
                ct=r.headers.get("content-type","")
                z.update(status=r.status,content_type=ct or z.get("content_type",""),
                         kind=kind(u,ct),playable_http=200<=r.status<400)
                txt=await r.text()
                if z["kind"]=="HLS":
                    z["is_manifest"]="#EXTM3U" in txt
                    if z["is_manifest"]:
                        vs,aud,sub=parse_master(txt,u)
                        z.update(variants=vs,audio=aud,subtitles=sub)
                        # Prefer a video variant; otherwise first non-comment URI.
                        test=vs[0]["url"] if vs else next(
                            (urljoin(u,x.strip()) for x in txt.splitlines()
                             if x.strip() and not x.lstrip().startswith("#")),None)
                        if test:
                            vr=await ctx.request.get(test,headers=hdr,timeout=5000)
                            z["best_variant_url"]=test
                            z["best_variant_status"]=vr.status
                            if 200<=vr.status<400:
                                vt=await vr.text()
                                seg=next((x.strip() for x in vt.splitlines()
                                          if x.strip() and not x.lstrip().startswith("#")),None)
                                if seg:
                                    su=urljoin(test,seg)
                                    sr=await ctx.request.get(su,headers={**hdr,"Range":"bytes=0-1023"},timeout=5000)
                                    z.update(segment_test_url=su,segment_status=sr.status,
                                             segment_ok=sr.status in (200,206))
                elif z["kind"]=="DASH":
                    z["is_manifest"]="<MPD" in txt or "<mpd" in txt
                print(f"[VALIDATE {i}/{len(likely)}]",z.get("kind"),z.get("status"),
                      "manifest=",z.get("is_manifest"),"segment=",z.get("segment_ok"))
            except Exception as e:
                z["validation_error"]=str(e)
            validated.append(z)

        def score(x):
            variants=x.get("variants") or []
            height=max([v.get("height") or 0 for v in variants] or [0])
            width=max([v.get("width") or 0 for v in variants] or [0])
            bandwidth=max([v.get("bandwidth") or 0 for v in variants] or [0])
            audio=x.get("audio") or []
            subs=x.get("subtitles") or []
            vie_audio=any((t.get("language") or "").lower() in ("vie","vi") or
                          "vie" in (t.get("name") or "").lower() or
                          "vietnam" in (t.get("name") or "").lower() for t in audio)
            vie_sub=any((t.get("language") or "").lower() in ("vie","vi") or
                        "vietnam" in (t.get("name") or "").lower() for t in subs)
            active=any("/api/watch/" in s for s in (x.get("seen_from") or []))
            return (bool(x.get("segment_ok")),bool(x.get("is_manifest")),
                    height,width,vie_audio,vie_sub,active,bandwidth)
        validated.sort(key=score,reverse=True)
        best=validated[0] if validated and any(score(validated[0])[:3]) else None
        result={"page":a.url,"title":title,"user_agent":ua,"best":best,"sources":validated,
                "generated_at_unix":int(time.time())}
        Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print("\n=== RESULT ==="); print("TITLE =",title)
        if best:
            print("SOURCE =",best["url"]); print("TYPE =",best.get("kind"))
            if best.get("variants"):
                print("QUALITIES =",",".join(str(v["height"])+"p" for v in best["variants"] if v.get("height")))
                print("BEST =",best["variants"][0]["url"])
            aud=best.get("audio") or []; sub=best.get("subtitles") or []
            print("AUDIO =", ", ".join(filter(None,[x.get("name") for x in aud])) or "none")
            print("SUBTITLES =", ", ".join(filter(None,[x.get("name") for x in sub])) or "none")
            print("HTTP_OK =",best.get("playable_http")); print("SEGMENT_OK =",best.get("segment_ok"))
        else:
            print("SOURCE = NOT VERIFIED")
            print("Use --headed and interact with the normal page/player if required.")
        print("JSON =",a.out)

        if best:
            print("\n=== DIRECT CLIENT DIAGNOSTIC ===")
            master = best.get("url")
            variant = best.get("best_variant_url")
            if not variant and best.get("variants"):
                variant = best["variants"][0].get("url")
            referer = f"https://film4k.net/watch/{slug}"

            def direct_probe(label, target, headers):
                if not target:
                    print(f"[DIRECT] {label}: missing URL")
                    return False
                req = urllib.request.Request(target, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=8) as r:
                        body = r.read(2048)
                        status = getattr(r, "status", None)
                        is_hls = b"#EXTM3U" in body
                        print(f"[DIRECT] {label}: HTTP {status} HLS={is_hls}")
                        return bool(status and 200 <= status < 300 and is_hls)
                except urllib.error.HTTPError as e:
                    print(f"[DIRECT] {label}: HTTP {e.code}")
                    return False
                except Exception as e:
                    print(f"[DIRECT] {label}: ERROR {type(e).__name__}: {e}")
                    return False

            # One decisive test only: can the actual CDN media segment be
            # fetched by an independent client, without Chromium cookies/session?
            segment = best.get("segment_test_url")

            def direct_segment_probe(label, target, headers):
                if not target:
                    print(f"[DIRECT] {label}: missing URL")
                    return False
                h = dict(headers)
                h["Range"] = "bytes=0-4095"
                req = urllib.request.Request(target, headers=h)
                try:
                    with urllib.request.urlopen(req, timeout=8) as r:
                        body = r.read(4096)
                        status = getattr(r, "status", None)
                        ctype = r.headers.get("Content-Type", "")
                        ok = bool(status in (200, 206) and len(body) > 0)
                        print(f"[DIRECT] {label}: HTTP {status} bytes={len(body)} type={ctype!r}")
                        return ok
                except urllib.error.HTTPError as e:
                    print(f"[DIRECT] {label}: HTTP {e.code}")
                    return False
                except Exception as e:
                    print(f"[DIRECT] {label}: ERROR {type(e).__name__}: {e}")
                    return False

            print("\n=== DIRECT CDN SEGMENT TEST ===")
            seg_bare = direct_segment_probe("segment / bare", segment, {})
            seg_ua = False
            if not seg_bare:
                seg_ua = direct_segment_probe("segment / UA", segment, {"User-Agent": ua})

            print("\n=== DIAGNOSIS ===")
            if seg_bare or seg_ua:
                print("DIRECT_SEGMENT = PASS")
                print("NEXT = build direct VLC playlist from the CDN path")
            else:
                print("DIRECT_SEGMENT = FAIL")
                print("NEXT = CDN is also session/access-bound; do not retry master/Referer tests")
        try:
            Path("film4k_media_trace.json").write_text(
                json.dumps(media_trace, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[MEDIA_TRACE] {len(media_trace)} entries -> film4k_media_trace.json")
            Path("film4k_playlists.json").write_text(
                json.dumps(playlist_bodies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[PLAYLISTS] {len(playlist_bodies)} entries -> film4k_playlists.json")
        except Exception as e:
            print(f"[MEDIA_TRACE_ERROR] {e}")

        await ctx.close()

if __name__=="__main__":
    asyncio.run(main())
