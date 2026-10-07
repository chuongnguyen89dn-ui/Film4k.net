import asyncio, json, base64, hashlib
from pathlib import Path
from playwright.async_api import async_playwright

MOVIE = "https://film4k.net/movie/spider-man-brand-new-day"
CHROME = r"C:\Users\Trinh\AppData\Local\Chromium\Application\chrome.exe"
PROFILE = r"C:\Users\Trinh\AppData\Local\Chromium\User Data"
OUT = Path("film4k_tt_trace.json")

def clean_headers(h):
    # Keep diagnostic headers, but do not export cookies/authorization/session credentials.
    deny = {"cookie", "authorization", "proxy-authorization"}
    return {k:v for k,v in h.items() if k.lower() not in deny}

async def main():
    hits = {}
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            PROFILE,
            executable_path=CHROME,
            headless=False,
            args=["--profile-directory=Default"],
        )
        page = ctx.pages[0]

        def on_request(req):
            if "film4knet.ngaodacopho.workers.dev/tt/" in req.url:
                x = hits.setdefault(req.url, {})
                x["method"] = req.method
                x["resource_type"] = req.resource_type
                x["request_headers"] = clean_headers(req.headers)

        async def on_response(resp):
            if "film4knet.ngaodacopho.workers.dev/tt/" not in resp.url:
                return
            x = hits.setdefault(resp.url, {})
            x["status"] = resp.status
            x["response_headers"] = clean_headers(resp.headers)
            try:
                body = await resp.body()
                x["bytes"] = len(body)
                x["first64_hex"] = body[:64].hex()
                x["sha256_first4096"] = hashlib.sha256(body[:4096]).hexdigest()
                x["looks_png"] = body.startswith(b"\x89PNG\r\n\x1a\n")
                x["looks_mp4"] = (
                    b"ftyp" in body[:64] or b"styp" in body[:64] or
                    b"moof" in body[:256] or b"mdat" in body[:256]
                )
            except Exception as e:
                x["body_error"] = str(e)

        page.on("request", on_request)
        page.on("response", on_response)

        print("[OPEN]", MOVIE)
        await page.goto(MOVIE, wait_until="domcontentloaded", timeout=90000)
        print("[ACTION] In Chromium, start the movie and let it play for 15-20 seconds.")
        print("[WAIT] Capturing /tt/ requests for 45 seconds...")
        await page.wait_for_timeout(45000)

        OUT.write_text(json.dumps(list(hits.values()), ensure_ascii=False, indent=2), encoding="utf-8")

        print("\n=== /tt/ RESULTS ===")
        if not hits:
            print("NO_TT_REQUESTS")
        else:
            for i,(url,x) in enumerate(hits.items(),1):
                print(f"[{i}] status={x.get('status')} bytes={x.get('bytes')} png={x.get('looks_png')} mp4={x.get('looks_mp4')}")
                print("    url:", url[:140] + ("..." if len(url)>140 else ""))
                rh=x.get("request_headers",{})
                for k in ("user-agent","referer","origin","range","accept","sec-fetch-site","sec-fetch-mode","sec-fetch-dest"):
                    if k in rh:
                        print(f"    {k}: {rh[k]}")
        print("\n[SAVED]", OUT.resolve())
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
