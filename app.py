from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import re
from urllib.parse import urljoin
from flask import Flask, abort, jsonify, request
import requests

app = Flask(__name__)

BASE_URL = "https://film4k.net"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
    " like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SECRET_KEY = os.environ.get("API_SECRET_KEY", "chuoi_bi_mat_cua_rieng_ban")


def get_fresh_stream(slug):
  session = requests.Session()
  session.headers.update(
      {"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/watch/{slug}"}
  )
  try:
    res = session.get(f"{BASE_URL}/watch/{slug}", timeout=8)
    if "Đang kiểm tra" in res.text or "/__gate" in res.text:
      c_m = re.search(r'const c = "([^"]+)"', res.text)
      p_m = re.search(r'pre = "([^"]+)"', res.text)
      if c_m and p_m:
        c, pre = c_m.group(1), p_m.group(1)
        want_bytes = len(pre) // 2
        for i in range(5_000_000):
          if all(
              b == 0
              for b in hashlib.sha256(f"{c}:{i}".encode()).digest()
              [:want_bytes]
          ):
            session.post(
                f"{BASE_URL}/__gate",
                json={"c": c, "n": str(i)},
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            break

    api_watch = session.get(f"{BASE_URL}/api/watch/{slug}", timeout=5)
    api_ticket = session.post(
        f"{BASE_URL}/api/play-ticket", json={"slug": slug}, timeout=5
    )
    session.post(f"{BASE_URL}/api/view", json={"slug": slug}, timeout=5)
    watch_page = session.get(f"{BASE_URL}/watch/{slug}", timeout=5)

    combined = api_watch.text + "\n" + api_ticket.text + "\n" + watch_page.text
    m3u8_matches = re.findall(
        r'https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*|[^\s"\'\\]+\.m3u8[^\s"\'\\]*',
        combined,
    )
    candidate_urls = [
        urljoin(BASE_URL, r.replace("\\/", "/"))
        if not r.startswith("http")
        else r.replace("\\/", "/")
        for r in m3u8_matches
    ]

    real_stream_url = None
    for url in candidate_urls:
      try:
        resp = session.get(url, timeout=5)
        if "#EXT-X-STREAM-INF" in resp.text:
          lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
          for idx, l in enumerate(lines):
            if (
                l.startswith("#EXT-X-STREAM-INF")
                and idx + 1 < len(lines)
                and not lines[idx + 1].startswith("#")
            ):
              real_stream_url = urljoin(url, lines[idx + 1])
              break
          if real_stream_url:
            break
        elif "#EXTINF" in resp.text:
          real_stream_url = url
          break
      except:
        continue

    cookies_str = "; ".join(
        [f"{k}={v}" for k, v in session.cookies.get_dict().items()]
    )
    return real_stream_url, cookies_str
  except:
    return None, None


@app.route("/stream/movie/<slug>.json")
def nuvio_stream(slug):
    client_key = request.args.get("key")
    if client_key != SECRET_KEY:
      abort(403)

    stream_url, cookies = get_fresh_stream(slug)
    if not stream_url:
      return jsonify({"streams": []})

    return jsonify({
        "streams": [{
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
        }]
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
