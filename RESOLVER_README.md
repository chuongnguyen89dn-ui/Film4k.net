# Local HLS Resolver API

Run on Windows:

```bat
cd C:\Users\Trinh\Downloads\Film4k_repo
python -m pip install -r resolver-requirements.txt
python resolver_server.py
```

Health check:

```bat
curl http://127.0.0.1:8787/health
```

Expected:

```json
{"ok":true}
```

The endpoint `GET /resolve/<slug>` is the contract consumed by the Khoai Film4K adapter. Implement `resolve_authorized_source()` only for a media source you are authorized to access.
