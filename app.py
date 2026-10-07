import hashlib
import os
import re
import threading
import time
from urllib.parse import urljoin
from flask import Flask, abort, jsonify, request
import requests

app = Flask(__name__)

BASE_URL = "https://film4k.net"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SECRET_KEY = os.environ.get("API_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("API_SECRET_KEY is not configured")

STREAM_CACHE_TTL = 30
stream_cache = {}
stream_cache_lock = threading.Lock()


def cache_get(slug):
    now = time.monotonic()
    with stream_cache_lock:
        item = stream_cache.get(slug)
        if not item:
            return None
        if now - item["created"] > STREAM_CACHE_TTL:
            stream_cache.pop(slug, None)
            return None
        return item["stream_url"], item["cookies"]


def cache_put(slug, stream_url, cookies):
    with stream_cache_lock:
        stream_cache[slug] = {
            "created": time.monotonic(),
            "stream_url": stream_url,
            "cookies": cookies,
        }


def get_fresh_stream(slug):
    started = time.monotonic()
    session = requests.Session()
    session.headers.update(
        {"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/watch/{slug}"}
    )

    try:
        t0 = time.monotonic()
        res = session.get(f"{BASE_URL}/watch/{slug}", timeout=8)
        gate_ms = int((time.monotonic() - t0) * 1000)

        if "Đang kiểm tra" in res.text or "/__gate" in res.text:
            c_m = re.search(r'const c = "([^"]+)"', res.text)
            p_m = re.search(r'pre = "([^"]+)"', res.text)
            if c_m and p_m:
                c, pre = c_m.group(1), p_m.group(1)
                want_bytes = len(pre) // 2
                solved = False
                for i in range(5_000_000):
                    if all(
                        b == 0
                        for b in hashlib.sha256(f"{c}:{i}".encode()).digest()[:want_bytes]
                    ):
                        gate_resp = session.post(
                            f"{BASE_URL}/__gate",
                            json={"c": c, "n": str(i)},
                            headers={"Content-Type": "application/json"},
                            timeout=5,
                        )
                        gate_resp.raise_for_status()
                        solved = True
                        break
                if not solved:
                    print(f"[film4k] PoW not solved slug={slug}")
                    return None, None

        t0 = time.monotonic()
        api_watch = session.get(f"{BASE_URL}/api/watch/{slug}", timeout=5)
        api_watch.raise_for_status()
        watch_ms = int((time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        api_ticket = session.post(
            f"{BASE_URL}/api/play-ticket",
            json={"slug": slug},
            timeout=5,
        )
        api_ticket.raise_for_status()
        ticket_ms = int((time.monotonic() - t0) * 1000)

        combined = api_watch.text + "\n" + api_ticket.text + "\n" + res.text
        m3u8_matches = re.findall(
            r'https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*|[^\s"\'\\]+\.m3u8[^\s"\'\\]*',
            combined,
        )

        candidate_urls = []
        for raw in m3u8_matches:
            clean = raw.replace("\\/", "/")
            if not clean.startswith("http"):
                clean = urljoin(BASE_URL, clean)
            if clean not in candidate_urls:
                candidate_urls.append(clean)

        real_stream_url = None
        m3u8_ms = 0
        for url in candidate_urls:
            try:
                t0 = time.monotonic()
                resp = session.get(url, timeout=5)
                m3u8_ms += int((time.monotonic() - t0) * 1000)
                resp.raise_for_status()
                text = resp.text

                if "WEBVTT" in text or "subtitle" in url.lower():
                    continue

                if "#EXT-X-STREAM-INF" in text:
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    for idx, line in enumerate(lines):
                        if (
                            line.startswith("#EXT-X-STREAM-INF")
                            and idx + 1 < len(lines)
                            and not lines[idx + 1].startswith("#")
                        ):
                            real_stream_url = urljoin(url, lines[idx + 1])
                            break
                    if real_stream_url:
                        break
                elif "#EXTINF" in text:
                    real_stream_url = url
                    break
            except requests.RequestException as exc:
                print(f"[film4k] m3u8 failed slug={slug} url={url} error={exc}")
                continue

        cookies_str = "; ".join(
            f"{k}={v}" for k, v in session.cookies.get_dict().items()
        )

        total_ms = int((time.monotonic() - started) * 1000)
        print(
            f"[film4k] resolver slug={slug} gate={gate_ms}ms "
            f"watch={watch_ms}ms ticket={ticket_ms}ms m3u8={m3u8_ms}ms "
            f"total={total_ms}ms candidates={len(candidate_urls)}"
        )

        if not real_stream_url:
            return None, None

        cache_put(slug, real_stream_url, cookies_str)
        return real_stream_url, cookies_str

    except requests.RequestException as exc:
        print(f"[film4k] resolver request failed slug={slug} error={exc}")
        return None, None
    except Exception as exc:
        print(f"[film4k] resolver failed slug={slug} error={exc}")
        return None, None


@app.route("/stream/movie/<slug>.json")
def nuvio_stream(slug):
    client_key = request.args.get("key")
    if not client_key or client_key != SECRET_KEY:
        abort(403)

    cached = cache_get(slug)
    if cached:
        stream_url, cookies = cached
        print(f"[film4k] cache hit slug={slug}")
    else:
        stream_url, cookies = get_fresh_stream(slug)

    if not stream_url:
        return jsonify({"streams": []})

    return jsonify(
        {
            "streams": [
                {
                    "title": "Film4K - Full HD (Auto Token)",
                    "url": stream_url,
                    "behaviorHints": {
                        "notWebReady": True,
                        "proxyHeaders": {
                            "request": {
                                "Referer": f"{BASE_URL}/watch/{slug}",
                                "User-Agent": USER_AGENT,
                                "Cookie": cookies,
                            }
                        },
                    },
                }
            ]
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
