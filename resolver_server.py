from flask import Flask, jsonify

app = Flask(__name__)


def resolve_authorized_source(slug: str):
    """Return HLS data from a source you are authorized to resolve.

    Expected result:
    {
      "video": {"body": "...m3u8...", "url": "..."},
      "audio": {"body": "...m3u8...", "url": "..."},
      "media": {
        "video": {"init": "...", "segments": ["...", "..."]},
        "audio": {"init": "...", "segments": ["...", "..."]}
      },
      "headers": {}
    }
    """
    raise RuntimeError("source resolver not implemented")


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.get("/resolve/<slug>")
def resolve(slug):
    try:
        return jsonify(resolve_authorized_source(slug))
    except Exception as exc:
        return jsonify({
            "error": "RESOLVE_FAILED",
            "message": str(exc),
        }), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787)
