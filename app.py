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
    page_url = f"{BASE_URL}/watch/{slug}"
    session.headers.update(
        {"User-Agent": USER_AGENT, "Referer": page_url}
    )

    try:
        # Primary resolver path verified by the standalone Film4K test:
        # /api/watch -> /api/play-ticket -> /api/hls/<token>/master.m3u8
        t0 = time.monotonic()
        api_watch = session.get(
            f"{BASE_URL}/api/watch/{slug}",
            timeout=8,
            headers={"User-Agent": USER_AGENT, "Referer": page_url},
        )
        watch_ms = int((time.monotonic() - t0) * 1000)
        api_watch.raise_for_status()

        data = api_watch.json()
        movie = data.get("movie") or {}
        hls_path = movie.get("hlsUrl")
        if not hls_path:
            print(f"[film4k] no hlsUrl slug={slug}")
            return None, None

        t0 = time.monotonic()
        api_ticket = session.post(
            f"{BASE_URL}/api/play-ticket",
            json={"slug": slug},
            timeout=8,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": page_url,
                "Content-Type": "application/json",
            },
        )
        ticket_ms = int((time.monotonic() - t0) * 1000)
        api_ticket.raise_for_status()

        hls_url = urljoin(BASE_URL, str(hls_path).replace("\\/", "/"))

        t0 = time.monotonic()
        master = session.get(
            hls_url,
            timeout=8,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": page_url,
                "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
            },
        )
        hls_ms = int((time.monotonic() - t0) * 1000)
        master.raise_for_status()

        text = master.text
        real_stream_url = None

        if "#EXT-X-STREAM-INF" in text:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for idx, line in enumerate(lines):
                if (
                    line.startswith("#EXT-X-STREAM-INF")
                    and idx + 1 < len(lines)
                    and not lines[idx + 1].startswith("#")
                ):
                    real_stream_url = urljoin(hls_url, lines[idx + 1])
                    break
        elif "#EXTINF" in text:
            real_stream_url = hls_url

        if not real_stream_url:
            print(f"[film4k] HLS master did not contain a playable playlist slug={slug}")
            return None, None

        cookies_str = "; ".join(
            f"{k}={v}" for k, v in session.cookies.get_dict().items()
        )

        total_ms = int((time.monotonic() - started) * 1000)
        print(
            f"[film4k] resolver slug={slug} "
            f"api_watch={watch_ms}ms ticket={ticket_ms}ms "
            f"hls={hls_ms}ms total={total_ms}ms"
        )

        cache_put(slug, real_stream_url, cookies_str)
        return real_stream_url, cookies_str

    except requests.RequestException as exc:
        print(f"[film4k] resolver request failed slug={slug} error={exc}")
        return None, None
    except (ValueError, KeyError, TypeError) as exc:
        print(f"[film4k] resolver response invalid slug={slug} error={exc}")
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
