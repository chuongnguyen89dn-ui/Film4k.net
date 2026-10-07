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


def print_http_diagnostic(label, response):
    print(f"[DIAG] {label}: HTTP {response.status_code}")
    print(f"       Server      : {response.headers.get('Server', '(none)')}")
    print(f"       Content-Type: {response.headers.get('Content-Type', '(none)')}")
    print(f"       Retry-After : {response.headers.get('Retry-After', '(none)')}")
    print(f"       Location    : {response.headers.get('Location', '(none)')}")
    print(f"       Length      : {len(response.content)} bytes")
    body = re.sub(r"\\s+", " ", response.text[:500]).strip()
    print(f"       Body[500]   : {body}")


def run_diagnostics(session, slug, page_url):
    print("[*] Running Film4K HTTP diagnostics...")
    targets = [
        ("homepage", BASE_URL + "/"),
        ("watch", page_url),
        ("api_watch", f"{BASE_URL}/api/watch/{slug}"),
    ]
    for label, url in targets:
        try:
            t = time.monotonic()
            if label == "api_watch":
                r = session.get(url, timeout=10, headers={"Referer": page_url, "User-Agent": USER_AGENT})
            else:
                r = session.get(url, timeout=10, headers={"Referer": page_url, "User-Agent": USER_AGENT})
            print_http_diagnostic(label, r)
            print(f"       Time        : {ms(t)} ms")
        except requests.RequestException as exc:
            print(f"[DIAG] {label}: REQUEST ERROR: {exc}")


def extract_hls_from_api(session, slug, page_url):
    """Try Film4K's direct /api/watch endpoint before the Cloudflare watch page."""
    timings = {}
    started = time.monotonic()

    t = time.monotonic()
    try:
        r = session.get(
            f"{BASE_URL}/api/watch/{slug}",
            timeout=10,
            headers={"User-Agent": USER_AGENT, "Referer": page_url},
        )
        timings["api_watch_ms"] = ms(t)
        print(f"    [/api/watch] HTTP {r.status_code} {timings['api_watch_ms']} ms")
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"    [/api/watch] unavailable: {exc}")
        return None, None, timings

    movie = data.get("movie") or {}
    hls_path = movie.get("hlsUrl")
    if not hls_path:
        print("    [/api/watch] no movie.hlsUrl")
        return None, None, timings

    hls_url = urljoin(BASE_URL, str(hls_path).replace("\\/", "/"))
    print(f"    [hlsUrl] {hls_url}")

    candidates = [hls_url]
    t = time.monotonic()
    try:
        r = session.get(
            hls_url,
            timeout=10,
            headers={"User-Agent": USER_AGENT, "Referer": page_url},
        )
        elapsed = ms(t)
        timings["hls_ms"] = elapsed
        print(f"    [/api/hls] HTTP {r.status_code} {elapsed} ms")
        if r.ok:
            text = r.text
            if "#EXT-X-STREAM-INF" in text:
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                for i, line in enumerate(lines):
                    if (
                        line.startswith("#EXT-X-STREAM-INF")
                        and i + 1 < len(lines)
                        and not lines[i + 1].startswith("#")
                    ):
                        stream_url = urljoin(hls_url, lines[i + 1])
                        timings["total_ms"] = ms(started)
                        print("        -> API HLS master: PASS")
                        return stream_url, hls_url, timings
            if "#EXTINF" in text:
                timings["total_ms"] = ms(started)
                print("        -> API HLS media playlist: PASS")
                return hls_url, hls_url, timings
            print("        -> /api/hls returned non-HLS content")
        else:
            print_http_diagnostic("/api/hls", r)
    except requests.RequestException as exc:
        print(f"    [/api/hls] request error: {exc}")

    # Keep the original resolver path as fallback, including PoW.
    print("[*] Falling back to /watch + PoW resolver...")
    stream_url, source, fallback_timings = extract_stream(session, slug, page_url)
    timings.update({f"fallback_{k}": v for k, v in fallback_timings.items()})
    timings["total_ms"] = ms(started)
    return stream_url, source, timings


def extract_stream(session, slug, page_url):
    timings = {}
    started = time.monotonic()

    watch_attempts = 3
    page = None
    watch_errors = []
    t = time.monotonic()

    for attempt in range(1, watch_attempts + 1):
        try:
            page = session.get(
                page_url,
                timeout=10,
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": page_url,
                    "Cache-Control": "no-cache",
                },
            )
            print(f"    [/watch attempt {attempt}] HTTP {page.status_code}")
            if page.ok:
                break
            watch_errors.append(f"attempt {attempt}: HTTP {page.status_code}")
        except requests.RequestException as exc:
            watch_errors.append(f"attempt {attempt}: {exc}")
            print(f"    [/watch attempt {attempt}] ERROR {exc}")

        if attempt < watch_attempts:
            time.sleep(1.5 * attempt)

    timings["watch_ms"] = ms(t)

    if page is None or not page.ok:
        print("[FAIL] /watch unavailable after retries")
        for error in watch_errors:
            print(f"    {error}")
        if page is not None:
            print_http_diagnostic("/watch final response", page)
        run_diagnostics(session, slug, page_url)
        return None, None, timings

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
