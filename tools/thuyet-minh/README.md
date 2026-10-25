# Công cụ tạo thuyết minh tạo sẵn

Tạo tệp MP3 đọc bản tóm tắt ngắn của di sản (năm ngôn ngữ) bằng giọng tự host trên máy dev rồi tải lên máy chủ qua API quản trị.
Tab "Nghe" của web học tập và app phát tệp này kèm tô sáng câu theo mốc thời gian; chưa có tệp thì vẫn dùng giọng thiết bị.
Thư mục này **không vào ảnh Docker** (`.dockerignore`) và `app/` không nhập gì từ đây. Chiều ngược lại thì có: phần dùng chung với giọng đọc tự host của dịch vụ AI
(`POST /v1/tts`, xem README.md ở thư mục gốc) nằm trong `app/giong_doc/` và công cụ nhập lại từ đó, nên các script ở đây tự thêm thư mục gốc repo vào `sys.path`.

| Ngôn ngữ | Máy đọc | Giọng (`voice`) | Giấy phép |
|---|---|---|---|
| Tiếng Việt | [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS) v3 Turbo, ONNX, CPU | `vieneu-mai-anh` (preset "Mai Anh") | Apache-2.0 |
| Anh, Hàn, Trung, Nhật | [MeloTTS](https://github.com/myshell-ai/MeloTTS) (PyTorch CPU, ghim commit `2091453`) | `melo-en-us`, `melo-kr`, `melo-zh`, `melo-jp` | MIT |

Mô hình tải từ Hugging Face về `.cache/hf` lần đầu (vài GB). Âm thanh ra: MP3 mono 80 kbps, âm lượng đưa về −20 dBFS,
~150 ms im lặng đầu tệp, ~350 ms giữa câu; `sentences[].text` là câu **gốc** để hiển thị, còn văn bản đưa vào máy đọc tiếng Việt
đã được chuẩn hóa (số, ngày, đơn vị, thế kỷ La Mã, viết tắt, tên riêng...) bằng `chuan_hoa_vi.py`.

## Tệp

| Tệp | Vai trò |
|---|---|
| `tao_thuyet_minh.py` | Tiến trình chính, chỉ thư viện chuẩn (Python ≥ 3.11 bất kỳ): đăng nhập, lấy danh sách thiếu, gọi máy đọc, tải lên, nhật ký CSV |
| `doc_vieneu.py`, `doc_melo.py`, `chay_viec.py` | Máy đọc chạy trong venv riêng: nạp mô hình một lần, ghép sóng theo câu kèm mốc, ghi MP3 |
| `cai-dat.ps1`, `requirements-*.txt`, `go_symlink_hf.py` | Dựng hai venv bằng uv với phiên bản ghim, tải dữ liệu NLTK/unidic, kéo mô hình, sửa symlink của Hugging Face cache (`go_symlink_hf.py` chỉ còn là lớp mỏng gọi mã trong `app/giong_doc/`) |

Mã dùng chung đã chuyển sang `app/giong_doc/` (test ở `tests/test_giong_doc_*.py`), công cụ nhập lại từ đó:

| Tệp trong `app/giong_doc/` | Vai trò |
|---|---|
| `chuan_hoa_vi.py`, `chia_cau.py`, `chuan_bi.py` | Chuẩn hóa tiếng Việt; tách câu hiển thị và chia mẩu ≤ 250 ký tự cho máy đọc; ghép hai bước thành danh sách câu kèm mẩu (chỉ thư viện chuẩn, nên `tao_thuyet_minh.py` vẫn chạy bằng Python bất kỳ ≥ 3.11) |
| `am_thanh.py` | Ghép sóng theo câu kèm mốc, chuẩn hóa âm lượng, mã hóa MP3 (cần numpy, lameenc) |
| `mo_hinh.py`, `go_symlink_hf.py` | Nạp VieNeu v3 Turbo kể cả cách sửa symlink; công cụ này luôn nạp fp32, còn dịch vụ tự chọn int8 khi CPU có VNNI |
| `mau/vi-du.json`, `mau/kiem-cai-dat.json` | Mục mẫu để chạy cục bộ không mạng |

## Cài đặt (một lần)

Cần [uv](https://docs.astral.sh/uv/) và git. Trong PowerShell:

```powershell
cd tools\thuyet-minh
.\cai-dat.ps1          # dựng moi-truong\vieneu (Python 3.12) và moi-truong\melo (Python 3.11), tải mô hình, nghe thử ra\kiem-cai-dat\cuc-bo
```

Vì sao có bước sửa symlink: onnxruntime 1.31 từ chối tệp dữ liệu ngoài khi snapshot trong Hugging Face cache là symlink;
`go_symlink_hf.py` thay symlink bằng tệp thật (máy đọc tiếng Việt cũng tự làm việc này khi gặp lỗi).

## Chạy

```powershell
python tao_thuyet_minh.py                                   # hỏi tên đăng nhập (mặc định admin.vietnamheritage) và mật khẩu (ô ẩn)
python tao_thuyet_minh.py --dry-run                         # chỉ liệt kê phần còn thiếu
python tao_thuyet_minh.py --languages vi,en --limit 50      # một phần
python tao_thuyet_minh.py --cuc-bo mau\vi-du.json --ra ..\..\ra-thu   # không mạng: đọc mục từ tệp, ghi ra thư mục
```

Tham số khác: `--api` (mặc định `https://34.124.169.74/api/v1`), `--ra` (thư mục cache + nhật ký, mặc định `ra/`),
`--python-vieneu`, `--python-melo`, `--hf-home`, `--ca` (chứng chỉ gốc thêm; TLS luôn được kiểm chứng), `--timeout`.

Mật khẩu chỉ nhập qua ô ẩn, không nhận qua tham số, biến môi trường hay tệp; token chỉ ở trong bộ nhớ. Phiên hết hạn (401) thì đăng nhập lại.
Máy chủ trả 409 (tóm tắt đã đổi sau khi lấy danh sách) thì bỏ qua mục đó và ghi nhật ký; lần chạy sau sẽ tạo lại.

**Chạy lại được:** máy chủ chỉ trả tóm tắt còn thiếu; âm thanh đã tạo nằm ở `ra/am-thanh/<textHash>__<voice>.mp3|.json`
nên tải lên hỏng không phải tạo lại. Mỗi lượt ghi một tệp `ra/nhat-ky/<thời điểm>.csv` (bước tạo / tải lên, kết quả, giây tạo, thời lượng).

## Chạy qua đêm

Khi quản trị viên còn đang duyệt tóm tắt ở nơi khác, cho công cụ chạy không người trông sau một lần nhập mật khẩu:

```powershell
python tao_thuyet_minh.py --lap-den "2026-10-21 08:00" --cho-tep <đường dẫn>\duyet-xong.txt
```

- `--lap-den "YYYY-MM-DD HH:MM"` (giờ máy này): lặp lượt. Lượt vừa rồi có tạo hoặc tải được gì thì làm lượt kế ngay; không có gì thì nghỉ
  `--nghi` phút (mặc định 5) rồi lấy lại danh sách thiếu. Qua giờ chốt thì không bắt đầu mục mới (mục đang làm được làm nốt, âm thanh
  đã tạo vẫn được tải lên), rồi in dòng tóm tắt và thoát. Không có `--lap-den` thì chạy một lượt như trước.
- `--cho-tep TEP` và `--ngon-ngu-sau` (mặc định `ko,zh,ja`): các ngôn ngữ này chỉ được làm khi tệp `TEP` đã có, vì bản tiếng Hàn, Trung,
  Nhật được dịch lại mỗi khi bản tiếng Anh được duyệt, làm trước thì âm thanh sẽ cũ. Mỗi lượt làm theo thứ tự `--languages` (vi, en trước).
  Tạo tệp báo hiệu bằng lệnh bất kỳ khi đã duyệt xong, ví dụ `New-Item <đường dẫn>\duyet-xong.txt`.
- Thoát sớm: khi tệp `TEP` đã có (hoặc không dùng `--cho-tep`) và một lượt đầy đủ không còn tóm tắt nào thiếu thuyết minh.
- Mỗi lượt in một dòng (giờ, số thiếu và số đã tải theo từng ngôn ngữ) và ghi vào cùng một tệp nhật ký CSV của lần chạy. Mất mạng giữa
  chừng thì nghỉ rồi thử lại. Đăng nhập một lần, tự đăng nhập lại khi 401 bằng mật khẩu trong bộ nhớ; không ghi mật khẩu hay token ra đâu.

## Mất bao lâu

Đo trên i5-12450HX (CPU, fp32): tỷ lệ thời gian tạo / thời lượng âm thanh (RTF) ≈ 0,45 với VieNeu và ≈ 0,52 với MeloTTS,
tức một tóm tắt dài 60 giây mất khoảng 30 giây; nạp mô hình lần đầu mỗi lượt 10–30 giây (VieNeu) và 1–2 giây mỗi ngôn ngữ (MeloTTS).
Khoảng 270 di sản × 5 ngôn ngữ ≈ 1.350 tệp, mỗi tệp 30–60 giây âm thanh → ước 6–10 giờ máy, có thể chia nhiều lượt bằng `--languages`/`--limit`.
