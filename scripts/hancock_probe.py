#!/usr/bin/env python3
"""Diagnose a normal Film4K browsing session; no stealth or challenge bypass.

Only sanitized counts go to stdout. Session URLs and playlists stay in a
git-ignored local bundle. A playlist result is NOT a playback success.
"""
import argparse
import asyncio
import json
import math
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit


def attributes(line):
    return dict((k, v.strip('"')) for k, v in
                re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', line))


def master_tracks(body, base):
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    audio, variants = [], []
    for i, line in enumerate(lines):
        if line.startswith('#EXT-X-MEDIA:'):
            a = attributes(line)
            if a.get('TYPE') == 'AUDIO' and a.get('URI'):
                audio.append({**a, 'url': urljoin(base, a['URI'])})
        elif line.startswith('#EXT-X-STREAM-INF:'):
            if i + 1 >= len(lines) or lines[i + 1].startswith('#'):
                raise ValueError('master_variant_uri_missing')
            variants.append({**attributes(line), 'url': urljoin(base, lines[i + 1])})
    if not variants:
        raise ValueError('master_has_no_variants')
    # Prefer the original AAC-compatible audio group, without changing codecs.
    variant = next((v for v in variants if 'mp4a' in v.get('CODECS', '')), variants[0])
    choices = [a for a in audio if a.get('GROUP-ID') == variant.get('AUDIO')]
    if not choices:
        raise ValueError('matching_audio_group_missing')
    track = next((a for a in choices if a.get('DEFAULT') == 'YES'), choices[0])
    return variant, track


def media_summary(body):
    if not body.lstrip().startswith('#EXTM3U'):
        raise ValueError('not_hls')
    durations, pending, init, end, gaps = [], None, False, False, False
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith('#EXTINF:'):
            if pending is not None:
                raise ValueError('duration_without_segment')
            pending = float(line.split(':', 1)[1].split(',')[0])
            if not math.isfinite(pending) or pending <= 0:
                raise ValueError('invalid_duration')
        elif line.startswith('#EXT-X-MAP:'):
            init = bool(attributes(line).get('URI'))
        elif line == '#EXT-X-ENDLIST':
            end = True
        elif line == '#EXT-X-GAP':
            gaps = True
        elif line and not line.startswith('#'):
            if pending is None:
                raise ValueError('segment_without_duration')
            durations.append(pending)
            pending = None
    if pending is not None or not durations or not init or not end or gaps:
        raise ValueError('incomplete_fmp4_vod_playlist')
    elapsed = sum(durations)

    def index_at(seconds):
        if seconds < 0 or seconds >= elapsed:
            return None
        cursor = 0.0
        for i, duration in enumerate(durations):
            if cursor + duration > seconds:
                return i
            cursor += duration
        return None

    seek_points = {
        'start': index_at(0),
        '30min': index_at(1800),
        'middle': index_at(elapsed / 2),
        'near_end_30s': index_at(max(0, elapsed - 30)),
    }
    return {'segments': len(durations), 'duration_seconds': round(elapsed, 6),
            'index_at_30min_zero_based': seek_points['30min'],
            'seek_points_zero_based': seek_points,
            'init_present': init, 'endlist': end}


def normal_movie_url(value):
    u = urlsplit(value)
    if (u.scheme != 'https' or u.netloc != 'film4k.net' or u.query or u.fragment
            or not re.fullmatch(r'/(movie|watch)/[a-z0-9-]+', u.path)):
        raise argparse.ArgumentTypeError('Use an https://film4k.net/movie/<slug> URL')
    return value


async def probe(args):
    from playwright.async_api import async_playwright
    captured, pending = {}, set()
    ready = asyncio.Event()
    stage = 'launch'
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headed)
        context = await browser.new_context()
        page = await context.new_page()

        async def capture(response):
            if (urlsplit(response.url).hostname != 'film4k.net'
                    or not urlsplit(response.url).path.endswith('.m3u8')
                    or response.status != 200):
                return
            try:
                body = await response.text()
                if not body.lstrip().startswith('#EXTM3U'):
                    return
                # Preserve only same-origin headers needed for this session.
                headers = await response.request.all_headers()
                safe_headers = {k: v for k, v in headers.items()
                                if k.lower() in ('referer', 'user-agent', 'x-f4k-pt')}
                captured[response.url] = {'body': body, 'headers': safe_headers}
                if '#EXT-X-STREAM-INF:' in body:
                    ready.set()
            except Exception:
                return

        def on_response(response):
            task = asyncio.create_task(capture(response))
            pending.add(task)
            task.add_done_callback(pending.discard)

        page.on('response', on_response)
        try:
            stage = 'goto_movie'
            await page.goto(args.url, wait_until='domcontentloaded', timeout=45000)
            stage = 'entry_controls'
            # These controls were observed on the live Hancock page on 2026-10-07.
            for label in ('Enter Film4k', 'UNDERSTOOD'):
                control = page.get_by_text(label, exact=False).first
                try:
                    await control.wait_for(state='visible', timeout=4000)
                    await control.click(timeout=5000)
                except Exception:
                    pass
            if '/movie/' in urlsplit(page.url).path:
                stage = 'open_watch'
                watch_url = args.url.replace('/movie/', '/watch/', 1)
                # Normal-site fallback: the movie page does not always render a
                # clickable Play link in headless Chromium. /watch/<slug> is the
                # canonical player route observed in the interactive session.
                await page.goto(watch_url, wait_until='domcontentloaded', timeout=45000)
                for label in ('Enter Film4k', 'UNDERSTOOD'):
                    control = page.get_by_text(label, exact=False).first
                    try:
                        await control.wait_for(state='visible', timeout=3000)
                        await control.click(timeout=5000)
                    except Exception:
                        pass
            # Reading the master is sufficient even if this browser cannot decode HEVC.
            stage = 'wait_master'
            await asyncio.wait_for(ready.wait(), timeout=args.timeout)
            stage = 'parse_master'
            master_url, master = next((u, x) for u, x in captured.items()
                                      if '#EXT-X-STREAM-INF:' in x['body'])
            video, audio = master_tracks(master['body'], master_url)
            bundle = {'movie': args.url, 'master': {'url': master_url, **master}}
            summary = {'status': 'PLAYLISTS_VERIFIED', 'playback_verified': False}
            for kind, track in (('video', video), ('audio', audio)):
                stage = f'fetch_{kind}_playlist'
                url = track['url']
                if urlsplit(url).netloc != urlsplit(master_url).netloc:
                    raise ValueError('cross_origin_playlist_requires_review')
                item = captured.get(url)
                if item is None:
                    response = await context.request.get(
                        url, headers=master['headers'], timeout=20000, max_redirects=0)
                    if response.status != 200:
                        raise ValueError(f'{kind}_playlist_http_{response.status}')
                    item = {'body': await response.text(), 'headers': master['headers']}
                stage = f'validate_{kind}_playlist'
                summary[kind] = media_summary(item['body'])
                bundle[kind] = {'url': url, **item}
            args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
            private = args.output / 'session.json'
            private.write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
            private.chmod(0o600)
            (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        except Exception as error:
            # Do not print exceptions which may embed session-bound URLs.
            try:
                text = (await page.locator('body').inner_text(timeout=3000))[:20000].lower()
            except Exception:
                text = ''
            blocked = any(s in text for s in ('verify you are human', 'checking your browser',
                                              'access denied', 'error 1010', 'just a moment'))
            path = urlsplit(page.url).path if page.url else ''
            print(json.dumps({'status': 'ACCESS_BLOCKED' if blocked else 'INCOMPLETE',
                              'stage': stage, 'error_type': type(error).__name__,
                              'page_path': path, 'captured_hls_count': len(captured),
                              'master_captured': any('#EXT-X-STREAM-INF:' in x['body'] for x in captured.values()),
                              'playback_verified': False}))
            return 2
        finally:
            if pending:
                await asyncio.gather(*list(pending), return_exceptions=True)
            await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', type=normal_movie_url)
    parser.add_argument('--headed', action='store_true')
    parser.add_argument('--timeout', type=int, default=45)
    parser.add_argument('--output', type=Path, default=Path('.local/film4k-probe'))
    raise SystemExit(asyncio.run(probe(parser.parse_args())))
