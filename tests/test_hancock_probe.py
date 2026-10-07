import json
import unittest
from pathlib import Path
from scripts.hancock_probe import master_tracks, media_summary


class PlaylistTests(unittest.TestCase):
    def test_real_capture(self):
        path = Path(__file__).resolve().parents[1] / 'tieptucduan/files/film4k_playlists.json'
        data = json.loads(path.read_text())
        master = next(x for x in data if '#EXT-X-STREAM-INF:' in x['body'])
        video, audio = master_tracks(master['body'], master['url'])
        self.assertIn('mp4a', video['CODECS'])
        self.assertEqual(video['AUDIO'], audio['GROUP-ID'])
        v = next(x for x in data if x['url'] == video['url'])
        result = media_summary(v['body'])
        self.assertEqual(result['segments'], 435)
        self.assertAlmostEqual(result['duration_seconds'], 8700.523, places=3)
        self.assertEqual(result['index_at_30min_zero_based'], 89)
        seek = result['seek_points_zero_based']
        self.assertEqual(seek['start'], 0)
        self.assertIsNotNone(seek['middle'])
        self.assertGreater(seek['middle'], seek['30min'])
        self.assertIsNotNone(seek['near_end_30s'])
        self.assertGreater(seek['near_end_30s'], seek['middle'])
        self.assertLess(seek['near_end_30s'], result['segments'])

    def test_clip_and_gap_are_not_full_vod(self):
        body = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:20,\na.m4s\n'
        with self.assertRaises(ValueError):
            media_summary(body)
        with self.assertRaises(ValueError):
            media_summary(body + '#EXT-X-GAP\n#EXT-X-ENDLIST\n')

    def test_preserve_group_and_resolve_relative_uris(self):
        body = ('#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="English, stereo",'
                'DEFAULT=YES,URI="a1.m3u8"\n'
                '#EXT-X-STREAM-INF:CODECS="hev1,mp4a.40.2",AUDIO="aac"\nv.m3u8\n')
        video, audio = master_tracks(body, 'https://film4k.net/api/hls/example/master.m3u8')
        self.assertEqual(audio['NAME'], 'English, stereo')
        self.assertEqual(audio['url'], 'https://film4k.net/api/hls/example/a1.m3u8')


if __name__ == '__main__':
    unittest.main()
