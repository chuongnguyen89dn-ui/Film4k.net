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

---
# 14. NHẬT KÝ TEST — LỆNH ĐÃ CHẠY / CÁI GÌ ĐÃ THU ĐƯỢC

Phần này ghi cụ thể để người khác biết đã chạy cái gì, chạy bằng lệnh nào, nhìn thấy gì và kết luận gì.

## TEST A — Capture nguồn Film4K

### Lệnh đã chạy
~~~bat
C:\Users\Trinh\Downloads>python film4k_run.zip
~~~

### Log
~~~text
[ACTION] Bam Play. Cho phim chay khoang 20 giay...
[CAPTURED] video + a0.m3u8
[VIDEO] 435 segments
[video] 2/435
~~~

### Kết quả sau đó
~~~text
socket.gaierror: [Errno 11001] getaddrinfo failed
urllib.error.URLError: <urlopen error [Errno 11001] getaddrinfo failed>
~~~

Kết luận: đã lấy được video playlist + audio playlist a0.m3u8; video test có 435 segment. Downloader tuần tự sau đó gặp lỗi DNS 11001.

## TEST B — Stream mode, mở VLC sớm

### Lệnh
~~~bat
C:\Users\Trinh\Downloads>python film4k_stream.zip
~~~

### Log
~~~text
[ACTION] Bam Play...
[BUFFER] Dang chuan bi 5 segment dau...
[video] 5/4356
[PLAY] VLC mo ngay. Tai tiep o nen.
[audio] 286/436
~~~

### Kết quả thực tế
Người dùng xác nhận **có hình + có tiếng và phát tới khoảng 51:20**.

Run này ghi nhận 4356 video segment và 436 audio segment.

Kết luận: mô hình buffer nhỏ → mở VLC → tải tiếp ở nền đã hoạt động trong test.

## TEST C — Seek / nhảy tới phút 30

### Log
~~~text
[ACTION] Bam Play. Script se test nhay thang toi phut 30.
[video] segment 88/435
[video] segment 89/435
[video] segment 90/435
[video] segment 91/435
[video] segment 92/435
~~~

VLC mở nhưng chỉ hiện:

~~~text
0:00 - 3:01
~~~

Kết luận: **seek toàn phim CHƯA PASS**. Playlist test lúc đó chỉ có khoảng 3:01 nên không thể dùng nó để chứng minh tua tới phút 30/cuối phim.

## TEST D — VLC load lâu / tự dừng

Đã gặp:
- VLC không hiện ngay vì script chờ tải quá nhiều segment.
- Có run mở VLC nhưng playlist chỉ có 3:01.
- Có run VLC tự dừng.
- Download tuần tự nhiều segment quá chậm.

Kết luận: không dùng kiểu tải toàn bộ phim trước rồi mới mở player.

Kiến trúc cần là:
~~~text
init + buffer nhỏ
→ mở VLC/Nuvio
→ lấy segment tiếp theo on-demand
→ seek = lấy segment tương ứng timeline
~~~

## TEST E — Nuvio iOS build

Nguồn Film4K/Spider-Man được đưa qua add-on test rồi mở bằng **Nuvio iOS build hiện tại**.

Kết quả người dùng xác nhận:
**có hình + có tiếng**, timeline khoảng **0:00–0:41**.

Kết luận: **adapter output → Nuvio đã PASS ở test ngắn**.

Chưa chứng minh full movie hoặc seek.

## TEST F — Deploy add-on

Film4K test được đưa vào add-on/manifest YouTube Khoai.

Lịch sử deploy ghi:
- commit: a25a8fe
- khoảng 22:51 giờ VN
- service: khoai-nuvio-addon

Sau deploy, test Film4K trên Nuvio cho hình + tiếng / 41 giây.

## TEST G — Network/source capture

Các dữ liệu đã thu được:
- film4k_network_all.json
- film4k_playlists.json
- film4k_result.json
- film4k_result(1).json
- film4k_result(2).json
- film4k_result(3).json

Đã xác định/quan sát:
- HLS manifest
- v.m3u8
- audio a0.m3u8
- video segments
- audio segments
- Worker/CDN segment URL
- request/header x-f4k-pt

Các capture này là dữ liệu phân tích; không public token/session thật.

## TEST H — Hancock, phim chưa capture

URL:
~~~text
https://film4k.net/movie/hancock
~~~

Mục tiêu: chứng minh resolver làm được với phim khác, không hard-code Spider-Man.

Kết quả: môi trường server/web hiện tại chưa lấy được source Hancock trực tiếp.

Trạng thái:
**Hancock resolver = CHƯA PASS.**

Không biến việc người dùng phải mở Chromium cho từng phim thành yêu cầu sản phẩm.

# 15. BẢNG KẾT QUẢ

| Test | Lệnh / nguồn | Kết quả | Trạng thái |
|---|---|---|---|
| Capture | python film4k_run.zip | video + a0.m3u8; 435 video segment; sau đó DNS 11001 | PARTIAL |
| Stream | python film4k_stream.zip | VLC mở sớm; 4356 video + 436 audio; hình + tiếng tới ~51:20 | PASS test stream |
| Seek | script seek, nhảy phút 30 | VLC chỉ hiện 0:00–3:01 | CHƯA PASS |
| Nuvio | add-on → Nuvio iOS build | hình + tiếng, 41 giây | PASS test ngắn |
| Full movie | cùng pipeline | chưa chứng minh toàn phim | CHƯA PASS |
| Seek giữa/cuối | cùng pipeline | chưa chứng minh | CHƯA PASS |
| Hancock resolver | URL Hancock | chưa tự lấy source | CHƯA PASS |
| Deploy | khoai-nuvio-addon | LIVE, commit a25a8fe | PASS deploy |

# 16. KHÔNG ĐƯỢC HIỂU NHẦM

435 và 4356 là số segment của **hai run/test khác nhau**.

41 giây là test Nuvio ngắn.

51:20 là kết quả stream test VLC/local.

3:01 là playlist seek-test bị ngắn, không phải thời lượng thật của phim.

Trạng thái chính xác:
~~~text
Adapter media → Nuvio: ĐÃ CHỨNG MINH PASS
Full timeline: CHƯA PASS
Seek toàn phim: CHƯA PASS
Resolver phim bất kỳ: CHƯA PASS
~~~

# 17. LỆNH TIẾP TỤC TEST

Các lệnh đã dùng và có log:
~~~bat
python film4k_run.zip
python film4k_stream.zip
~~~

Khi tiếp tục, phải kiểm tra theo thứ tự:

1. VLC/Nuvio mở nhanh bằng buffer nhỏ.
2. Timeline phải là toàn phim, không phải 3:01/41 giây.
3. Tua tới giữa phim và xác nhận hình + tiếng.
4. Tua gần cuối phim và xác nhận hình + tiếng.
5. Sau khi 4 điểm trên PASS mới test Hancock/phim chưa capture để chứng minh resolver động.

**Ghi chú về độ chính xác:** phần này chỉ ghi các lệnh và kết quả đã xuất hiện rõ trong lịch sử hiện có; không tự bịa tên lệnh cho những run mà lịch sử chỉ còn log.
