# FILM4K — HANDOFF / TIẾP TỤC DỰ ÁN

Ngày ghi: 2026-10-06
Repo: chuongnguyen89dn-ui/Film4k.net
Mục đích: ghi lại **những gì đã thực sự làm, test, lấy được và trạng thái hiện tại** để cuộc chat sau có thể tiếp tục, không phải chỉ lưu tên file.

## 1. Mục tiêu cuối cùng

Film4K phải phát được trên **Nuvio iOS build hiện tại** (Nuvio vẫn giữ cơ chế/player gốc), không phụ thuộc vào việc người dùng mở Chromium cho từng phim.

Luồng mục tiêu:

Phim bất kỳ
→ resolver lấy nguồn/playlist hiện tại
→ video + audio playlist
→ adapter xử lý segment
→ giữ timeline
→ Nuvio phát
→ tua tới mốc bất kỳ bằng segment tương ứng.

**Không coi capture Spider-Man là giải pháp cuối.** Capture chỉ là dữ liệu/test để chứng minh adapter.

---

## 2. Những gì đã TEST và PASS

### 2.1. Test Film4K trên VLC / local

Đã chạy nhiều script/package:

- `film4k_vlc.py`
- `film4k_run.zip`
- `film4k_stream.zip`
- các script HLS/VLC/segment trong thư mục làm việc.

Một run có kết quả:

```
[ACTION] Bam Play...
[BUFFER] Dang chuan bi 5 segment dau...
[video] 5/4356
[PLAY] VLC mo ngay. Tai tiep o nen.
[audio] 286/436
```

Sau đó đã xác nhận bằng thực tế:

**Có hình + có tiếng, tới khoảng 51:20.**

Điều này chứng minh pipeline stream có thể tiếp tục tải segment trong khi VLC phát.

### 2.2. Test Nuvio iOS

Đã đưa test Film4K/Spider-Man qua add-on và Nuvio.

Kết quả người dùng xác nhận:

**Có tiếng + có hình. Timeline khoảng 41 giây.**

Đây là PASS quan trọng nhất của adapter hiện tại:
- Nuvio nhận được output.
- Video có hình.
- Audio có tiếng.

Nhưng **41 giây chưa phải full movie**.

### 2.3. Spider-Man capture

Một bản test có:
- video: **435 segments**
- audio: **436 segments**

Một bản stream/full capture khác ghi nhận:
- video: **4356 segments**
- audio: **436 segments**
- đã phát tới khoảng **51:20** có hình + tiếng.

Hai con số này thuộc các run/test khác nhau; không được trộn thành một playlist duy nhất.

---

## 3. Những gì đã TEST nhưng CHƯA PASS

### 3.1. Full movie + seek

Chưa chứng minh được:
- chạy toàn bộ timeline của phim;
- tua trực tiếp tới giữa phim;
- tua tới gần cuối;
- sau khi tua vẫn có hình + tiếng và tiếp tục phát.

Có một test nhảy tới phút 30 nhưng VLC chỉ hiện:

```
0:00 - 3:01
```

=> playlist test lúc đó chỉ chứa khoảng 3:01, **không đủ để kết luận seek toàn phim**.

### 3.2. On-demand seek

Đã xác định hướng đúng là:
- không tải hàng nghìn segment trước khi VLC/Nuvio mở;
- buffer nhỏ ban đầu;
- mở player sớm;
- segment tiếp theo được lấy theo timeline/on-demand;
- khi seek, lấy segment tương ứng với mốc thời gian.

Nhưng pipeline on-demand + full timeline **chưa được xác nhận PASS**.

---

## 4. Lỗi đã gặp trong quá trình test

Có run bị:

```
urllib.error.URLError: <urlopen error [Errno 11001] getaddrinfo failed>
```

=> lỗi DNS/resolve hostname khi tải segment.

Một số run:
- VLC không hiện vì script chờ tải quá nhiều segment.
- VLC mở nhưng playlist chỉ có 3:01.
- VLC tự dừng sau khi mở.
- Một số script/package trước đó chạy chậm vì tải tuần tự rất nhiều segment.

Kết luận: không dùng kiểu “download toàn bộ phim trước rồi mới mở VLC”.

---

## 5. Kiến trúc adapter đã xác định

Adapter đang hướng tới xử lý output mà Nuvio đã PASS:

**HLS/video + audio → segment adapter → loại wrapper PNG ở đầu response khi cần → trả media/fMP4 phù hợp cho Nuvio.**

Không thay player Nuvio.

Không giả định Nuvio tự phát raw AV01/Film4K.

Điểm đã chứng minh là output sau adapter có thể được Nuvio phát.

---

## 6. Resolver động — PHẦN CHƯA XONG

Mục tiêu:

Không hard-code Spider-Man.

Khi chọn một phim bất kỳ:

```
movie URL/ID
→ lấy source
→ lấy master/manifest
→ chọn video playlist
→ chọn audio playlist
→ map segment
→ adapter
→ Nuvio
```

Đã chọn phim thứ hai để test resolver:

**Hancock**
`https://film4k.net/movie/hancock`

Kết quả hiện tại:

- Không lấy được nguồn Hancock trực tiếp từ môi trường server/web hiện tại.
- Chưa chứng minh được resolver server-side tự lấy manifest/source Hancock.
- Không được biến việc người dùng mở Chromium cho từng phim thành yêu cầu sản phẩm.

**Vì vậy resolver động = CHƯA PASS.**

---

## 7. Quét toàn site

Đã phân biệt rõ:

### Playback
Không nên phụ thuộc vào việc crawl toàn site trước.

Nên:
`chọn phim → resolve nguồn → phát on-demand`

### Crawler/catalog
Có thể dùng riêng nếu muốn:
- quét toàn site;
- tạo catalog;
- cache metadata/source.

Không được coi crawler toàn site là điều kiện bắt buộc để playback.

---

## 8. Deploy / add-on test

Đã có test Film4K trong add-on/manifest YouTube Khoai.

Đã kiểm tra deploy và có run được xác nhận LIVE.

Trong lịch sử công việc có ghi:
- commit test: **a25a8fe**
- hoàn tất khoảng **22:51 giờ VN**
- test Film4K adapter chạy trên `khoai-nuvio-addon`.

Sau deploy, người dùng xác nhận test có:
**hình + tiếng, 41 giây.**

---

## 9. File/script đã tạo hoặc dùng

Các file liên quan trong môi trường làm việc gồm nhóm:

- `f4k.py`
- `f4k_extract.py`
- `f4k_trace.py`
- `f4k_trace_all.py`
- `film4k.py`
- `film4k_all_in_one.py`
- `film4k_all_in_one_vlc.py`
- `film4k_all_in_one_vlc_v2.py`
- `film4k_av_vlc_package.zip`
- `film4k_chrome_capture.py`
- `film4k_chromium_blue.py`
- `film4k_diagnostic_fixed.py`
- `film4k_diagnostic_once.py`
- `film4k_full_vlc.zip`
- `film4k_hls.py`
- `film4k_media_trace.json`
- `film4k_media_trace.py`
- `film4k_real_chromium.py`
- `film4k_real_chromium_v2.py`
- `film4k_real_chromium_v3.py`
- `film4k_real_chromium_v4.py`
- `film4k_real_chromium_v5.py`
- `film4k_run.zip`
- `film4k_seek.zip`
- `film4k_seek_full_timeline.zip`
- `film4k_segment_direct_test.py`
- `film4k_stream.zip`
- `film4k_tt_trace.json`
- `film4k_vlc_clean_test.py`
- `film4k_vlc_real_segment.py`
- `film4k_vlc_test.py`
- `film4k_vplaylist_probe.py`

Các file capture/network quan trọng đã xuất hiện:
- `film4k_result.json`
- `film4k_result(1).json`
- `film4k_result(2).json`
- `film4k_result(3).json`
- `film4k_network_all.json`
- `film4k_playlists.json`

**Lưu ý:** capture/network có thể chứa ticket/token/session. Không public nguyên trạng nếu chưa làm sạch.

---

## 10. Những dữ liệu kỹ thuật đã lấy được

Từ capture/network đã xác định được các thành phần cần quan tâm:

- HLS manifest
- `v.m3u8`
- audio `a0.m3u8`
- video segments
- audio segments
- Worker/CDN segment URL
- request/header liên quan đến nguồn Film4K.

Có capture ghi nhận request/header `x-f4k-pt`.

Điểm này quan trọng để tiếp tục nghiên cứu resolver, nhưng **không được đưa token/session thật vào repo public**.

---

## 11. Trạng thái bàn giao chính xác

### PASS
- Film4K pipeline có thể lấy media.
- VLC/local đã có hình + tiếng.
- Stream test đã phát tới khoảng 51:20.
- Nuvio iOS build đã phát được test Spider-Man có hình + tiếng.
- Adapter output đã chứng minh tương thích với Nuvio trong test 41 giây.

### CHƯA PASS
- Full movie.
- Full timeline.
- Seek toàn phim.
- Seek giữa/cuối phim.
- Resolver động cho phim chưa capture.
- Hancock tự resolve server-side.
- Playback production cho “phim bất kỳ”.

### Không được làm
- Không hard-code Spider-Man rồi gọi là resolver tổng quát.
- Không bắt người dùng mở Chromium cho từng phim.
- Không public token/cookie/play-ticket/session capture.
- Không đổi player Nuvio khi adapter hiện tại đã có PASS.

---

## 12. Việc tiếp theo phải làm

**Ưu tiên 1:** hoàn thiện adapter full timeline + seek bằng nguồn đã được lấy hợp lệ.

**Ưu tiên 2:** resolver động cho phim thứ hai (Hancock) hoặc một phim mới khác, nhưng phải chứng minh được:
- không cần user mở Chromium;
- lấy được video + audio playlist;
- tạo timeline đầy đủ;
- segment được phục vụ on-demand.

**Ưu tiên 3:** test một phim chưa capture trước:
`Play → hình + tiếng → chạy lâu → seek giữa → seek gần cuối`.

Chỉ sau khi bước này PASS mới coi Film4K playback là hoàn chỉnh.

---

## 13. Kết luận bàn giao

**Không phải dự án thất bại.** Phần khó nhất đã có bằng chứng: **Nuvio iOS build đã phát được output Film4K sau adapter (hình + tiếng).**

Nhưng **chưa hoàn thành sản phẩm**.

Điểm nghẽn hiện tại là:
**resolver động + full timeline + seek**, không phải player Nuvio.

Người tiếp tục dự án phải bắt đầu từ phần này, không quay lại xây player từ đầu và không quay lại hard-code Spider-Man.
