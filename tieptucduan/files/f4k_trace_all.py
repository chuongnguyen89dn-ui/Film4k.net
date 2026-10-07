import asyncio, json, hashlib
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

MOVIE = "https://film4k.net/movie/spider-man-brand-new-day"
CHROME = r"C:\Users\Trinh\AppData\Local\Chromium\Application\chrome.exe"
PROFILE = r"C:\Users\Trinh\AppData\Local\Chromium\User Data"
OUT = Path("film4k_network_all.json")

# Do not export browser credentials/session secrets.
DENY = {"cookie", "authorization", "proxy-authorization"}

def clean(h):
    return {k:v for k,v in h.items() if k.lower() not in DENY}

def interesting(url, ctype, rtype):
    u = url.lower()
    c = (ctype or "").lower()
    return (
        rtype in {"media", "xhr", "fetch"} or
        any(x in u for x in (".m3u8", ".mpd", ".m4s", ".mp4", "/hls/", "/api/watch", "/api/title", "/tt/")) or
        any(x in c for x in ("video/", "audio/", "mpegurl", "dash+xml", "octet-stream"))
    )

async def main():
    rows = {}
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            PROFILE, executable_path=CHROME, headless=False,
            args=["--profile-directory=Default"],
        )
        page = ctx.pages[0]

        def req_cb(req):
            key = id(req)
            rows[key] = {
                "url": req.url,
                "method": req.method,
                "resource_type": req.resource_type,
                "request_headers": clean(req.headers),
            }

        async def resp_cb(resp):
            req = resp.request
            key = id(req)
            x = rows.setdefault(key, {
                "url": req.url, "method": req.method,
                "resource_type": req.resource_type,
                "request_headers": clean(req.headers),
            })
            h = clean(resp.headers)
            x["status"] = resp.status
            x["response_headers"] = h
            ctype = h.get("content-type","")
            if not interesting(req.url, ctype, req.resource_type):
                return
            try:
                body = await resp.body()
                x["bytes"] = len(body)
                x["first64_hex"] = body[:64].hex()
                x["sha256_first4096"] = hashlib.sha256(body[:4096]).hexdigest()
                x["looks_png"] = body.startswith(b"\x89PNG\r\n\x1a\n")
                x["looks_mp4"] = any(b in body[:512] for b in (b"ftyp", b"styp", b"moof", b"mdat"))
                x["looks_hls"] = b"#EXTM3U" in body[:4096]
            except Exception as e:
                x["body_error"] = str(e)

        page.on("request", req_cb)
        page.on("response", resp_cb)

        print("[OPEN]", MOVIE)
        await page.goto(MOVIE, wait_until="domcontentloaded", timeout=90000)
        print("[ACTION] Bam PLAY va de phim chay 20-30 giay.")
        print("[CAPTURE] Dang ghi TOAN BO network trong 60 giay...")
        await page.wait_for_timeout(60000)

        result = []
        for x in rows.values():
            ctype = x.get("response_headers",{}).get("content-type","")
            if interesting(x.get("url",""), ctype, x.get("resource_type","")):
                result.append(x)

        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        print("\n=== INTERESTING NETWORK ===")
        for i,x in enumerate(result,1):
            host = urlparse(x.get("url","")).netloc
            print(
                f"[{i:03}] {x.get('resource_type','?'):6} "
                f"{x.get('status','?')} bytes={x.get('bytes','?')} "
                f"png={x.get('looks_png','?')} mp4={x.get('looks_mp4','?')} "
                f"hls={x.get('looks_hls','?')} {host}"
            )
            print("      ", x.get("url","")[:180])
        print("\n[SAVED]", OUT.resolve())
        print("[COUNT]", len(result))
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
