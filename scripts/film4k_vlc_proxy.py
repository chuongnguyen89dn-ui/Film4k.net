#!/usr/bin/env python3
"""Serve the latest verified Film4K session locally for real VLC seek testing."""
import argparse
import json
import re
import threading
import urllib.request
import shutil
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urljoin

SESSION = {}
TRACKS = {}
PORT = 8765

def attrs(line):
    return dict((k, v.strip('"')) for k, v in re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', line))

def rewrite_media(name, item):
    out = []
    seg_index = 0
    for raw in item['body'].splitlines():
        line = raw.strip()
        if line.startswith('#EXT-X-MAP:'):
            a = attrs(line)
            uri = a.get('URI')
            if uri:
                line = line.replace(uri, f'http://127.0.0.1:{PORT}/fetch/{name}/init')
        elif line and not line.startswith('#'):
            line = f'http://127.0.0.1:{PORT}/fetch/{name}/seg/{seg_index}'
            seg_index += 1
        out.append(line)
    return '\n'.join(out) + '\n'

def rewrite_master(item):
    out = []
    for raw in item['body'].splitlines():
        line = raw.strip()
        if line.startswith('#EXT-X-MEDIA:'):
            a = attrs(line)
            uri = a.get('URI')
            if uri:
                if 'TYPE=AUDIO' in line:
                    line = line.replace(uri, f'http://127.0.0.1:{PORT}/audio.m3u8')
                else:
                    # Do not let VLC follow subtitle/alternate rendition URIs
                    # from the original Film4K session through localhost.
                    line = line.replace(uri, f'http://127.0.0.1:{PORT}/video.m3u8')
        elif line and not line.startswith('#') and '.m3u8' in line:
            # Every variant URI in the master is rewritten, regardless of
            # whether VLC's parser associates it with the preceding tag.
            line = f'http://127.0.0.1:{PORT}/video.m3u8'
        out.append(line)
    return '\n'.join(out) + '\n'

def resources(item):
    base=item['url']; init=None; seg=[]
    for raw in item['body'].splitlines():
        line=raw.strip()
        if line.startswith('#EXT-X-MAP:'):
            u=attrs(line).get('URI')
            if u: init=urljoin(base,u)
        elif line and not line.startswith('#') and not line.endswith('.m3u8'):
            seg.append(urljoin(base,line))
    return init,seg

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print('[HTTP]', fmt%args)
    def do_GET(self):
        if self.path=='/master.m3u8':
            body=TRACKS['master'].encode()
            return self.sendb(body,'application/vnd.apple.mpegurl')
        if self.path=='/video.m3u8': return self.sendb(TRACKS['video']['playlist'].encode(),'application/vnd.apple.mpegurl')
        if self.path=='/audio.m3u8': return self.sendb(TRACKS['audio']['playlist'].encode(),'application/vnd.apple.mpegurl')
        m=re.fullmatch(r'/fetch/(video|audio)/(init|seg/(\d+))',self.path)
        if not m: self.send_error(404); return
        kind=m.group(1); key=m.group(2)
        url=TRACKS[kind]['init'] if key=='init' else TRACKS[kind]['segments'][int(m.group(3))]
        headers=dict(SESSION[kind].get('headers',{}))
        # Do NOT send Range for the fMP4 init. The earlier diagnostic showed
        # Range requests can return an image/challenge object instead of init.
        is_init = key == 'init'
        if not is_init:
            headers.setdefault('Range','bytes=0-')
        req=urllib.request.Request(url,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                data=r.read()
                ct=r.headers.get('Content-Type','application/octet-stream')
                status=getattr(r,'status',200)
                cr=r.headers.get('Content-Range')
            print('[UPSTREAM_OK]',kind,key,'http=',status,'bytes=',len(data),'type=',ct)
            if ct.startswith('image/') or data[:8] == b'\x89PNG\r\n\x1a\n':
                print('[UPSTREAM_BAD_MEDIA]',kind,key,'returned image instead of media')
            self.send_response(status if status in (200,206) else 200)
            self.send_header('Content-Type',ct)
            self.send_header('Content-Length',str(len(data)))
            if cr: self.send_header('Content-Range',cr)
            self.end_headers(); self.wfile.write(data)
        except Exception as e:
            print('[UPSTREAM_ERROR]',kind,key,type(e).__name__); self.send_error(502)
    def sendb(self,b,ct):
        self.send_response(200); self.send_header('Content-Type',ct); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--session',type=Path,default=Path('.local/film4k-probe/session.json')); ap.add_argument('--port',type=int,default=8765); a=ap.parse_args()
    global SESSION, PORT; PORT=a.port; SESSION=json.loads(a.session.read_text(encoding='utf-8'))
    TRACKS['master']=rewrite_master(SESSION['master'])
    for kind in ('video','audio'):
        init,segs=resources(SESSION[kind]); TRACKS[kind]={'init':init,'segments':segs,'playlist':rewrite_media(kind,SESSION[kind])}
    url=f'http://127.0.0.1:{a.port}/master.m3u8'
    server=ThreadingHTTPServer(('127.0.0.1',a.port),H)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    print(f'[READY] {url}')
    candidates=[
        shutil.which('vlc'),
        r'C:\\Program Files\\VideoLAN\\VLC\\vlc.exe',
        r'C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe',
    ]
    vlc=next((x for x in candidates if x and Path(x).exists()),None)
    if not vlc:
        raise SystemExit('[VLC_NOT_FOUND] Install VLC or add vlc.exe to PATH')
    print(f'[VLC] launching {vlc}')
    proc=subprocess.Popen([vlc,'--network-caching=1500','--verbose=2',url])
    try:
        while proc.poll() is None:
            time.sleep(1)
    finally:
        server.shutdown()
if __name__=='__main__': main()
