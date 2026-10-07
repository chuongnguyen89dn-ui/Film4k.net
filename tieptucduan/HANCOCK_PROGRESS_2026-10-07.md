# Hancock — kiểm tra tiếp ngày 07/10/2026

## Kết quả thực tế trong phiên này

- Mở URL phim Hancock bằng cloud browser, bấm Enter Film4k, đóng thông báo cộng đồng rồi bấm Phát.
- Trang phim và trang `/watch/hancock` mở được, không yêu cầu đăng nhập trong lần thử này.
- Player báo `no level with compatible codecs found in manifest` với hai codec:
  `hev1.1.4.L150.B0,mp4a.40.2` và `hev1.1.4.L150.B0,ec-3`.
- Trang báo `Playback failed — no variant this browser can decode (HEVC-only stream)`.
- Điều này cho thấy player đã tới bước kiểm tra codec của manifest. KHÔNG chứng minh audio/video segment đã tải hay phim đã phát.
- Video DOM chỉ cung cấp URL blob. Công cụ cloud browser hiện tại không xuất được network response/playlist; vì vậy chưa lấy được bundle nguồn Hancock trong phiên này.

## Mã mới

`scripts/hancock_probe.py`: bộ kiểm tra dùng Playwright thông thường, không stealth, không sửa fingerprint, không giải CAPTCHA. Chờ master response, giữ đúng nhóm audio, lấy playlist media trong cùng context, kiểm tra init + ENDLIST + durations, rồi xuất bundle cục bộ.

Không cần browser giải mã HEVC để kiểm tra playlist. Tuy nhiên truy cập và lấy playlist bằng script mới CHƯA được kiểm chứng trực tiếp; browser tương tác thành công không bảo đảm headless sẽ thành công.

Lệnh chạy ở môi trường Python có quyền truy cập trang bình thường:

```sh
python -m pip install playwright
python -m playwright install chromium
python scripts/hancock_probe.py https://film4k.net/movie/hancock
```

`PLAYLISTS_VERIFIED` chỉ xác nhận cấu trúc các playlist, KHÔNG phải PASS playback/full-movie/seek. Khi chưa đủ dữ liệu, script trả mã thoát 2. Bundle `.local/film4k-probe/session.json` có URL/header phiên nên không đưa lên repo; summary chỉ chứa số lượng và thời lượng.

Kiểm tra offline:

```sh
python -m unittest discover -s tests -v
```

Test đối chiếu capture Spider-Man thật: 435 video segment, 8700.523 giây, chỉ số video ở phút 30 là 89 (đếm từ 0). Đây KHÔNG phải kết quả Hancock.

## Còn thiếu

1. Chạy probe trên môi trường triển khai dự kiến và kiểm chứng bundle Hancock mới.
2. Xác định tuổi thọ nguồn từ quan sát thực tế, chưa gán TTL 1–2 giờ.
3. Adapter đầy đủ timeline + xử lý PNG cho init/segment + test seek trên Nuvio.

Chưa thay đổi add-on đang chạy, chưa deploy, chưa quét toàn site.
