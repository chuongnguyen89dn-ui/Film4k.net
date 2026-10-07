import hashlib
import re
import sys
import time
from urllib.parse import urljoin

import requests

BASE_URL = "https://film4k.net"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def ms(start):
    return int((time.monotonic() - start) * 1000)


def solve_gate(session, page_url, html):
    if "Đang kiểm tra" not in html and "/__gate" not in html:
        print("[+] PoW gate: not required")
        return True

    c_m = re.search(r'const c = "([^"]+)"', html)
    p_m = re.search(r'pre = "([^"]+)"', html)
    if not c_m or not p_m:
        print("[!] PoW markers not found")
        return False

    c, pre = c_m.group(1), p_m.group(1)
    want_bytes = len(pre) // 2
    started = time.monotonic()

    for i in range(10_000_000):
        digest = hashlib.sha256(f"{c}:{i}".encode()).digest()
        if all(b == 0 for b in digest[:want_bytes]):
            r = session.post(
                f"{BASE_URL}/__gate",
                json={"c": c, "n": str(i)},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            r.raise_for_status()
            print(f"[+] PoW solved: nonce={i}, total={ms(started)} ms")
            return True

    print(f"[!] PoW failed after {ms(started)} ms")
    return False


def extract_stream(session, slug, page_url):
    timings = {}
    started = time.monotonic()

    t = time.monotonic()
    page = session.get(page_url, timeout=10)
    page.raise_for_status()
    timings["watch_ms"] = ms(t)

    if not solve_gate(session, page_url, page.text):
        return None, None, timings

    t = time.monotonic()
    api_watch = session.get(f"{BASE_URL}/api/watch/{slug}", timeout=10)
    api_watch.raise_for_status()
    timings["api_watch_ms"] = ms(t)

    t = time.monotonic()
    api_ticket = session.post(
        f"{BASE_URL}/api/play-ticket",
        json={"slug": slug},
        timeout=10,
    )
    api_ticket.raise_for_status()
    timings["ticket_ms"] = ms(t)

    combined = api_watch.text + "\n" + api_ticket.text + "\n" + page.text
    matches = re.findall(
        r'https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*|[^\s"\'\\]+\.m3u8[^\s"\'\\]*',
        combined,
    )

    candidates = []
    for raw in matches:
        clean = raw.replace("\\/", "/")
        if not clean.startswith("http"):
            clean = urljoin(BASE_URL, clean)
        if clean not in candidates:
            candidates.append(clean)

    print(f"[*] M3U8 candidates: {len(candidates)}")

    for n, url in enumerate(candidates, 1):
        t = time.monotonic()
        try:
            r = session.get(url, timeout=10)
            elapsed = ms(t)
            print(f"    [{n}] HTTP {r.status_code} {elapsed} ms  {url}")

            if not r.ok:
                continue

            text = r.text
            if "WEBVTT" in text or "subtitle" in url.lower():
                print("        -> subtitle candidate, skipped")
                continue

            if "#EXT-X-STREAM-INF" in text:
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                for idx, line in enumerate(lines):
                    if (
                        line.startswith("#EXT-X-STREAM-INF")
                        and idx + 1 < len(lines)
                        and not lines[idx + 1].startswith("#")
                    ):
                        stream_url = urljoin(url, lines[idx + 1])
                        timings["m3u8_ms"] = elapsed
                        timings["total_ms"] = ms(started)
                        print("        -> master playlist: PASS")
                        return stream_url, url, timings

            if "#EXTINF" in text:
                timings["m3u8_ms"] = elapsed
                timings["total_ms"] = ms(started)
                print("        -> media playlist: PASS")
                return url, url, timings

        except requests.RequestException as exc:
            print(f"        -> request error: {exc}")

    timings["total_ms"] = ms(started)
    return None, None, timings


def validate_stream(session, stream_url, referer):
    print("[*] Validating selected stream...")
    try:
        r = session.get(
            stream_url,
            headers={"Referer": referer, "User-Agent": USER_AGENT},
            timeout=10,
        )
        print(f"    HTTP {r.status_code}, {len(r.content)} bytes")
        if not r.ok:
            return False

        text = r.text
        if "#EXT-X-STREAM-INF" in text or "#EXTINF" in text:
            print("[+] Stream validation: PASS")
            return True

        print("[!] Response is not a recognized HLS playlist")
        return False
    except requests.RequestException as exc:
        print(f"[!] Stream validation failed: {exc}")
        return False


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else input("Nhập slug phim: ").strip()
    if not slug:
        print("[!] Missing slug")
        return 1

    page_url = f"{BASE_URL}/watch/{slug}"
    session = requests.Session()
    session.headers.update(
        {"User-Agent": USER_AGENT, "Referer": page_url}
    )

    print(f"[*] Film4K resolver test: {slug}")
    stream_url, source_playlist, timings = extract_stream(
        session, slug, page_url
    )

    if not stream_url:
        print("[FAIL] Không lấy được stream URL")
        print(f"Timing: {timings}")
        return 2

    print("\n[SUCCESS] Stream URL:")
    print(stream_url)
    print(f"Source playlist: {source_playlist}")

    cookies = "; ".join(
        f"{k}={v}" for k, v in session.cookies.get_dict().items()
    )
    print(f"Cookies: {cookies or '(none)'}")

    valid = validate_stream(session, stream_url, page_url)

    print("\n=== RESULT ===")
    print(f"slug       : {slug}")
    print(f"stream     : {'PASS' if valid else 'FAIL'}")
    for key, value in timings.items():
        print(f"{key:11}: {value} ms")

    return 0 if valid else 3


if __name__ == "__main__":
    raise SystemExit(main())
