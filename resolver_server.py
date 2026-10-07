import json
import os
from pathlib import Path
from urllib.parse import urljoin

from flask import Flask, jsonify

app = Flask(__name__)
FIXTURE_DIR = Path(os.environ.get("RESOLVER_FIXTURE_DIR", ".local/resolver-fixtures"))


def _parse_media_playlist(body: str, playlist_url: str):
    init_url = None
    segments = []
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("#EXT-X-MAP:"):
            marker = 'URI="'
            if marker in line:
                init_url = urljoin(playlist_url, line.split(marker, 1)[1].split('"', 1)[0])
        elif line and not line.startswith("#"):
            segments.append(urljoin(playlist_url, line))
    if not init_url or not segments:
        raise RuntimeError("fixture playlist missing init or segments")
    return {"init": init_url, "segments": segments}


def _load_fixture(slug: str):
    """Load previously captured, authorized HLS data from local disk.

    Nothing from .local is committed. Expected files:
      .local/resolver-fixtures/<slug>/video.m3u8
      .local/resolver-fixtures/<slug>/audio.m3u8
      .local/resolver-fixtures/<slug>/fixture.json

    fixture.json contains only local test configuration:
      {"video_url":"https://authorized.example/video.m3u8",
       "audio_url":"https://authorized.example/audio.m3u8",
       "headers":{}}
    """
    root = FIXTURE_DIR / slug
    cfg_path = root / "fixture.json"
    video_path = root / "video.m3u8"
    audio_path = root / "audio.m3u8"
    if not (cfg_path.exists() and video_path.exists() and audio_path.exists()):
        raise RuntimeError(f"fixture not found for {slug}: {root}")

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    video_url = cfg.get("video_url")
    audio_url = cfg.get("audio_url")
    if not video_url or not audio_url:
        raise RuntimeError("fixture.json missing video_url/audio_url")

    video_body = video_path.read_text(encoding="utf-8")
    audio_body = audio_path.read_text(encoding="utf-8")
    return {
        "video": {"body": video_body, "url": video_url},
        "audio": {"body": audio_body, "url": audio_url},
        "media": {
            "video": _parse_media_playlist(video_body, video_url),
            "audio": _parse_media_playlist(audio_body, audio_url),
        },
        "headers": cfg.get("headers") or {},
    }


def resolve_authorized_source(slug: str):
    return _load_fixture(slug)


@app.get("/health")
def health():
    return jsonify({"ok": True, "fixture_dir": str(FIXTURE_DIR)})


@app.get("/resolve/<slug>")
def resolve(slug):
    try:
        return jsonify(resolve_authorized_source(slug))
    except Exception as exc:
        return jsonify({"error": "RESOLVE_FAILED", "message": str(exc)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787)
