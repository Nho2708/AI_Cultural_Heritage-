# Dịch vụ AI của DSVHVN

Dịch vụ nội bộ (Python, FastAPI) mà backend gọi một chiều qua HTTP. Không truy cập cơ sở dữ liệu, không nhận dữ liệu cá nhân.
Gọi mô hình ngôn ngữ để soạn bài học, sinh câu hỏi, tóm tắt và dịch di sản; riêng gợi ý di sản liên quan chỉ dùng scikit-learn
(TF-IDF và cosine), không gọi mô hình ngôn ngữ; giọng đọc tiếng Việt (`/v1/tts`) do chính dịch vụ này tự host bằng VieNeu-TTS, không gọi dịch vụ ngoài. Hai nhà cung cấp mô hình ngôn ngữ, chọn bằng `AI_PROVIDER`:

| `AI_PROVIDER` | Mô hình mặc định | Chi phí | Ghi chú |
|---|---|---|---|
| `anthropic` (mặc định) | `claude-haiku-5-5` (`AI_MODEL`) | trả theo lượt, nạp tiền trước | SDK `anthropic` |
| `gemini` | `gemini-3.8-flash` (`GEMINI_MODEL`) | hạn mức miễn phí của Google AI Studio | REST `generateContent`; bản miễn phí: Google có thể dùng dữ liệu gửi lên, điều khoản yêu cầu người dùng từ 18 tuổi |

| API | Việc | Mô hình | Mức suy nghĩ |
|---|---|---|---|
| `POST /v1/compose-lesson` | Soạn nội dung bài học tiếng Việt đúng cấp 1, 2, 3 của lớp | có | medium |
| `POST /v1/generate-questions` | Sinh câu hỏi 8 dạng theo cấp, độ khó | có | medium |
| `POST /v1/summarize-heritage` | Tóm tắt tiếng Việt (bản ngắn để nghe, bản chi tiết để đọc) | có | low |
| `POST /v1/translate-heritage` | Dịch sang `en`, `ko`, `zh-Hans`, `ja`, có bảng thuật ngữ tên riêng | có | low |
| `POST /v1/rank-related` | Xếp hạng di sản liên quan | không | - |
| `POST /v1/tts` | Đọc chữ tiếng Việt thành MP3 bằng giọng "Mai Anh" tự host (xem mục Giọng đọc tiếng Việt) | không (VieNeu-TTS) | - |
| `GET /health` | Kiểm tra sức khỏe, gồm trạng thái giọng đọc `tts` (không cần khóa) | - | - |

Hợp đồng chi tiết nằm ở phía backend (`docs/bai-hoc-theo-cap.md`, `docs/ngan-hang-cau-hoi.md`, `docs/da-ngon-ngu.md`, `docs/thong-ke-goi-y.md`).

## Cấu trúc

```
app/
  main.py, asgi.py      tạo ứng dụng, kiểm khóa nội bộ, mã tương quan, log JSON
  serve.py              điểm chạy dưới IIS trên máy demo (cổng lấy từ ASPNETCORE_PORT) và trong container (AI_HOST, AI_PORT)
  config.py             cấu hình (pydantic-settings), đọc .env
  api/routes.py         sáu API và /health
  giong_doc/            giọng đọc tiếng Việt: chuẩn hóa chữ, chia mẩu, ghép âm thanh và MP3, nạp VieNeu-TTS, động cơ mỗi lúc một yêu cầu
  schemas/              kiểu yêu cầu, kết quả (JSON camelCase, khớp backend)
  prompts/              prompt tiếng Việt, lược đồ JSON, bảng thuật ngữ tên riêng
  validators/           bộ kiểm đầu ra theo cấp, dạng câu, ngôn ngữ
  services/             ghép prompt, gọi mô hình, kiểm, gọi lại một lần
  llm/                  bộ gọi Claude (client.py), bộ gọi Gemini (gemini.py), chọn theo cấu hình (factory.py), vòng gọi-kiểm-gọi lại (runner.py)
  recommender/rank.py   gợi ý content-based
  rules.py              số liệu quy tắc sao đúng của backend
scripts/                thử gọi thật, đếm token, chạy nối backend, mô hình giả
scripts/trien-khai/     cài site IIS, tạo cấu hình, triển khai lên máy demo (CD gọi)
tests/                  pytest với mô hình giả, không mạng
tools/thuyet-minh/      công cụ tạo thuyết minh tạo sẵn trên máy dev (nhập lại mã dùng chung từ app/giong_doc; app/ không nhập gì từ tools/)
```

## Cài đặt

Cần Python 3.12 trở lên. Đã chạy trên Python 3.14.7: mọi thư viện ghim trong `requirements.txt` đều có bản dựng sẵn cho 3.14 trên Windows (kể cả numpy, scipy, scikit-learn), không cần trình biên dịch.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt          # chạy dịch vụ
.\.venv\Scripts\python -m pip install -r requirements-dev.txt      # thêm pytest để chạy test
```

Giọng đọc tiếng Việt cần thêm gói riêng, chỉ cài khi chạy `/v1/tts` (CI và máy demo IIS không cài): xem mục Giọng đọc tiếng Việt.

Phiên bản đã ghim: `anthropic 1.13.0`, `fastapi 0.143.0`, `httpx 0.28.1` (bộ gọi Gemini), `uvicorn 0.54.0`, `pydantic 2.14.0`, `pydantic-settings 2.15.0`, `scikit-learn 1.9.1`, `numpy 2.5.3`.

## Đặt khóa

Các biến: `AI_INTERNAL_KEY` (khóa nội bộ giữa backend và dịch vụ này, bắt buộc), `AI_PROVIDER` (`anthropic` hoặc `gemini`), rồi khóa của nhà cung cấp đã chọn:
`ANTHROPIC_API_KEY` và `AI_MODEL` (mặc định `claude-haiku-5-5`), hoặc `GEMINI_API_KEY` (tạo ở aistudio.google.com, mục Get API key; đừng bật thanh toán nếu muốn ở bản miễn phí),
`GEMINI_MODEL` (mặc định `gemini-3.8-flash`) và `GEMINI_THINKING_LEVEL` (mặc định `low`: ở bản miễn phí mức `medium` làm một lần soạn bài quá 40 giây; để rỗng thì theo mức của từng API).
Chọn một trong hai cách (có cả hai thì `.env` trong thư mục dịch vụ thắng; biến môi trường của tiến trình thắng cả hai):

1. Tệp `.env` cạnh `README.md` (sao từ `.env.example`, bỏ dấu `#` ở dòng nào bạn điền; đã nằm trong `.gitignore`), hoặc
2. Tệp `%APPDATA%\DSVHVN\ai-service.env` dùng chung cho mọi bản chạy trên máy (cùng ba dòng `TÊN=giá trị`).

Không đặt `ANTHROPIC_API_KEY` thành biến môi trường người dùng hay hệ thống (sẽ chiếm quyền xác thực của công cụ khác): dịch vụ tự đọc từ tệp và chỉ giữ khóa trong tiến trình.
Thiếu `AI_INTERNAL_KEY` thì dịch vụ không khởi động; thiếu khóa của nhà cung cấp đã chọn thì các API dùng mô hình trả 503 còn `rank-related` vẫn chạy.
`GET /health` cho biết nhà cung cấp, mô hình và đã có khóa hay chưa.
Khóa không bao giờ vào log; log chỉ ghi mã tương quan, API, mô hình, số token, thời gian, kết quả.

## Chạy

```powershell
.\run.ps1                       # http://localhost:8000
.\run.ps1 -Port 8001
# hoặc
.\.venv\Scripts\python -m uvicorn app.asgi:app --host localhost --port 8000
```

Dùng `--host localhost` (không phải `127.0.0.1`): Windows phân giải `localhost` ra `::1` trước, nếu dịch vụ chỉ nghe IPv4 thì lần kết nối đầu của backend mất 1 đến 2 giây
và gợi ý (chỉ chờ 2 giây) rơi vào phương án dự phòng. Kiểm tra: `curl http://localhost:8000/health`.

## Giọng đọc tiếng Việt (`POST /v1/tts`)

Nút Nghe của cấp 1 cần giọng đọc tiếng Việt thật, nên dịch vụ tự tạo giọng bằng [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS) v3 Turbo (Apache-2.0,
ONNX Runtime trên CPU, không cần GPU), giọng preset "Mai Anh" (cùng giọng với thuyết minh tạo sẵn của tóm tắt).

**Hợp đồng.** Khóa nội bộ như các API khác (`X-Internal-Key`). Thân JSON:

```json
{ "text": "Hoàng thành Thăng Long được UNESCO ghi danh ngày 31/7/2010.", "voice": "vieneu-mai-anh" }
```

`text` dài 1 đến 1000 ký tự (không được chỉ có khoảng trắng); `voice` chỉ nhận `vieneu-mai-anh` (mặc định khi bỏ qua).

| Kết quả | Khi nào |
|---|---|
| 200, `Content-Type: audio/mpeg`, thân là MP3 mono 80 kbps, âm lượng chuẩn hóa về khoảng -20 dBFS; tiêu đề `X-Duration-Ms` (thời lượng, mili giây) và `X-Voice` | thành công |
| 401 | thiếu hoặc sai khóa nội bộ |
| 422 (`invalid_request`) | chữ rỗng hoặc quá 1000 ký tự, giọng không hỗ trợ; 422 (`no_speakable_text`) khi chữ chỉ có dấu câu |
| 503 kèm `Retry-After` (giây) | `tts_disabled` (tắt bằng cấu hình), `tts_loading` (đang nạp mô hình), `tts_failed` (nạp hỏng), `tts_busy` (đang sinh yêu cầu khác quá 30 giây) |

`GET /health` luôn trả 200 và thêm `"tts": "off" | "loading" | "ready" | "error"`. Nạp hỏng (ví dụ chưa tải được mô hình vì mất mạng) thì dịch vụ vẫn chạy
bình thường, `/v1/tts` trả 503, và yêu cầu kế tiếp sau 60 giây tự thử nạp lại.

**Cách làm.** Chữ được chuẩn hóa như một thuyết minh viên sẽ đọc (số, ngày, đơn vị, thế kỷ La Mã, viết tắt...: `app/giong_doc/chuan_hoa_vi.py`), tách câu và chia mẩu
không quá 250 ký tự (`chia_cau.py`), mỗi mẩu qua mô hình, ghép lại với khoảng lặng ngắn giữa các câu rồi chuẩn hóa âm lượng và mã hóa MP3 (`am_thanh.py`).
Một lúc chỉ sinh một yêu cầu (khóa), việc sinh chạy trong luồng riêng nên không chặn các API khác. Mô hình nạp ở luồng nền khi khởi động, dịch vụ nhận yêu cầu ngay.

**Cấu hình** (biến môi trường hoặc `.env`):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `GIONG_DOC_BAT` | `0` | `1` để bật. Ảnh Docker đặt sẵn `1`; máy demo IIS và CI không cài gói giọng đọc nên để tắt |
| `GIONG_DOC_LUONG` | `2` | số luồng tính của ONNX Runtime và OMP (máy chủ e2-standard-2 có 2 vCPU) |
| `GIONG_DOC_DO_CHINH_XAC` | `auto` | `auto`: int8 khi CPU có VNNI (Linux đọc cờ `avx512_vnni` hoặc `avx_vnni` trong `/proc/cpuinfo`), không thì fp32; hoặc ép `int8` / `fp32`. int8 nhanh hơn nhưng trên CPU không có VNNI thì tiếng bị méo. Hệ điều hành khác Linux không đọc được cờ nên `auto` chọn fp32 |

**Cài gói giọng đọc** (sau `requirements.txt`; `--no-deps` là bắt buộc, lý do ghi ở đầu `requirements-giong.txt`):

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install --no-deps -r requirements-giong.txt
$env:GIONG_DOC_BAT = "1"; $env:HF_HOME = "D:\mo-hinh"        # mô hình ~530 MB tải về HF_HOME ở lần chạy đầu (cần Internet)
.\run.ps1
```

Nạp mô hình mất khoảng 10 đến 20 giây, RAM đỉnh khoảng 1 GB. Hugging Face cache dùng symlink mà ONNX Runtime 1.31 từ chối, nên khi gặp lỗi đó
dịch vụ tự thay symlink bằng tệp thật (`go_symlink_hf.py`); cần đặt `HF_HOME`. Trong ảnh Docker, `HF_HOME=/srv/mo-hinh` là volume để lần triển khai sau không tải lại mô hình.
Thời gian sinh tính theo thời lượng âm thanh: đo trên máy dev 2 luồng, một câu ngắn khoảng 1 giây, đoạn 9 giây âm thanh khoảng 5 đến 8 giây; máy chủ 2 vCPU dự kiến chậm hơn
2 đến 3 lần, nên phía gọi nên cho thời gian chờ hàng chục giây và lưu lại tệp đã tạo.

## Cấu hình backend

Trong `appsettings` hoặc biến môi trường của backend:

```
Ai:Mode     = Remote
Ai:BaseUrl  = http://localhost:8000
```

Khóa nội bộ không ghi vào appsettings, đặt bằng User Secrets (cùng giá trị với `AI_INTERNAL_KEY`):

```powershell
dotnet user-secrets set "Ai:InternalKey" "<giá trị AI_INTERNAL_KEY>" --project src/DSVHVN.Api
```

hoặc biến môi trường `Ai__InternalKey`. Thời gian chờ và thử lại do backend quyết định (`Ai:AttemptTimeoutSeconds` 45 giây, `Ai:HeritageAttemptTimeoutSeconds` 90 giây, `Ai:MaxRetries` 2).

## Mã phản hồi (đúng cách backend phân loại)

Backend coi 5xx, 408, 429 và lỗi mạng là lỗi thử lại được; 400, 401, 403, 422 là lỗi không thử lại.

| Mã | `errorCode` | Khi nào |
|---|---|---|
| 200 | | Đầu ra đã qua bộ kiểm |
| 401 | `invalid_internal_key` | Thiếu hoặc sai `X-Internal-Key` (so khớp hằng thời gian, kiểm trước khi đọc nội dung) |
| 422 | `invalid_request`, `type_not_allowed_at_level`, `insufficient_material`, `missing_source`, `same_language`, `duplicate_heritage` | Đầu vào sai lược đồ hoặc không làm được từ tư liệu đã gửi |
| 422 | `model_refused` | Mô hình từ chối nội dung (`stop_reason` = `refusal`); gọi lại cũng vậy nên không thử lại |
| 502 | `invalid_model_output` | Đầu ra sai lược đồ riêng của cấp, dạng câu, ngôn ngữ sau khi đã gọi lại một lần; hoặc bị cắt do hết `max_tokens` hai lần |
| 502 / 503 | `llm_unavailable`, `llm_rate_limited`, `llm_unreachable` | Nhà cung cấp mô hình lỗi 5xx, 429, quá tải hoặc không kết nối được |
| 503 | `llm_not_configured`, `llm_not_ready`, `llm_billing` | Thiếu khóa, khóa hoặc mô hình không dùng được, hết số dư tài khoản |
| 504 | `llm_timeout` | Mô hình không trả lời kịp |
| 500 | `internal_error` | Lỗi ngoài dự kiến (chỉ ghi kiểu lỗi, không ghi nội dung) |

Mọi phản hồi lỗi có dạng `{ errorCode, message, correlationId, details? }` và trả lại `X-Correlation-Id` (không có thì dịch vụ tự sinh).

## Kiểm đầu ra

Đầu ra mô hình dùng structured outputs (lược đồ JSON riêng cho từng cấp, từng dạng câu, có hay không có tóm tắt), rồi dịch vụ tự kiểm lại trước khi trả:

- **Soạn bài**: số từ nằm trong khung của cấp (cấp 1: 150 đến 250, cấp 2: 300 đến 500, cấp 3: 600 đến 900, dung sai 8%); cấp 1 câu ngắn, 3 đến 6 bước câu chuyện mỗi bước tối đa 50 từ kèm ảnh có sẵn; cấp 2 từ 3 đến 8 mốc có năm, ảnh và chú thích; cấp 3 từ 1 đến 3 đoạn trích nguyên văn (là chuỗi con của nội dung di sản) kèm nguồn, câu hỏi gợi suy nghĩ; 3 đến 7 ý chính; ảnh và sự kiện chỉ lấy trong danh sách đã gửi; tiếng Việt có dấu.
- **Sinh câu**: tám dạng kiểm đúng quy tắc cấu trúc của backend (số phương án, đúng một đáp án đúng, chỗ trống `___`, số mục sắp xếp theo cấp, mệnh đề không cùng Đúng hay cùng Sai, đoạn tư liệu tối đa 150 từ...), ảnh phải thuộc thư viện ảnh của đúng di sản, không trùng câu; dạng nào tư liệu không đủ (thiếu ảnh, thiếu chữ) thì không đưa vào lược đồ. Chỉ một phần số câu đạt thì gọi lại để bù phần thiếu; sau lần gọi lại vẫn có câu đạt thì trả các câu đó (backend nhận ít câu hơn yêu cầu), không có câu nào thì 502.
- **Tóm tắt**: bản ngắn khoảng 80 đến 120 từ một đoạn, bản chi tiết khoảng 250 đến 400 từ, văn bản thuần (ký hiệu Markdown nếu sót thì bỏ).
- **Dịch**: đủ mã giai đoạn, sự kiện, ảnh; đúng chữ viết của ngôn ngữ đích (Hangul, chữ Hán giản thể không lẫn phồn thể, kana); giữ số tiêu đề Markdown; tên riêng đúng bảng thuật ngữ (`app/prompts/glossary.py`, hơn 50 mục địa danh, di sản, triều đại).

Sai thì gọi lại đúng một lần (kèm danh sách lỗi cụ thể, tính cả token của hai lần vào `usage`), vẫn sai thì trả 502. Tổng thời gian một yêu cầu bị chặn trong khoảng 43 giây (soạn bài, sinh câu) hoặc 88 giây (tóm tắt, dịch) để vừa thời gian chờ của backend; còn ít thời gian thì không gọi lại.

## Chi phí ước tính

Haiku 5.5 (prompt tối đa 100 nghìn token): **0,10 USD / 1 triệu token vào, 0,50 USD / 1 triệu token ra**; đọc từ bộ nhớ đệm 0,1 lần, ghi bộ nhớ đệm 1,25 lần giá vào. System prompt của từng API được đặt `cache_control`.
Token suy nghĩ tính vào token ra. Ước tính cho một lần gọi với một di sản cỡ vài trăm từ (số liệu thô, chưa đo bằng lời gọi thật):

| Việc | Token vào | Token ra | Chi phí |
|---|---|---|---|
| Soạn một bài | khoảng 4 nghìn | khoảng 3 nghìn | khoảng 0,002 USD |
| Sinh 10 câu | khoảng 5 nghìn | khoảng 6 nghìn | khoảng 0,004 USD |
| Tóm tắt một di sản | khoảng 1,5 nghìn | khoảng 1,5 nghìn | dưới 0,001 USD |
| Dịch một di sản sang một ngôn ngữ (kèm tóm tắt) | khoảng 4 nghìn | khoảng 4 nghìn | khoảng 0,0025 USD |
| Dịch và tóm tắt đủ bốn ngôn ngữ | | | khoảng 0,011 USD |

Gọi lại do đầu ra sai nhân đôi chi phí của lần đó. Xem số thật: log mỗi lời gọi có `inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`.

### Số đo thật với Gemini (12/10/2026, `gemini-3.8-flash`, bản miễn phí, mức suy nghĩ `low`)

| Việc | Thời gian | Token vào | Token ra (kể cả suy nghĩ) | Kết quả |
|---|---|---|---|---|
| Soạn bài cấp 1, 2, 3 | 13 đến 33 giây | khoảng 1,6 nghìn | 0,9 đến 1,8 nghìn | đạt bộ kiểm ngay lần đầu |
| Sinh 6 câu cấp 1, 2, 3 | 16 đến 31 giây | 2,6 đến 5,5 nghìn | 1,2 đến 1,6 nghìn | cấp 2 phải gọi lại một lần, được 5/6 câu |
| Tóm tắt một di sản | 6 giây | khoảng 1 nghìn | khoảng 0,5 nghìn | đạt |
| Dịch một di sản (kèm tóm tắt) | 9 đến 15 giây | khoảng 1,9 nghìn | 1 đến 1,4 nghìn | đạt ở en, ko, zh-Hans |

Bản miễn phí thỉnh thoảng trả 503 ("high demand") hoặc 429 (vượt số lượt mỗi phút), hoặc trả lời chậm quá thời gian chờ: dịch vụ trả 503/504 để backend tự gọi lại (tối đa 2 lần).
Chi phí bằng 0 trong hạn mức miễn phí.

Hạn mức miễn phí tính theo **từng mô hình**: `gemini-3.8-flash` chỉ có **20 lượt mỗi ngày** (đặt lại vào nửa đêm giờ Thái Bình Dương), nên dịch vụ tự chuyển sang
`GEMINI_FALLBACK_MODELS` (mặc định `gemini-3.5-flash,gemini-3.5-flash-lite`) khi mô hình chính hết lượt. Xem lượt đã dùng ở https://ai.dev/rate-limit.

Chạy nối qua backend (`scripts/chay-noi-backend.py`, backend `Ai:Mode=Remote` trên cơ sở dữ liệu tạm, 12/10/2026, mô hình chính đã hết lượt nên chạy bằng mô hình dự phòng):
dịch và tóm tắt một di sản sang 4 ngôn ngữ trong 29 giây; soạn bài cấp 1, 2, 3 trong 13 đến 19 giây; sinh 6 câu mỗi cấp trong khoảng 5 giây, đúng dạng của cấp;
gợi ý cho khách dùng kết quả của dịch vụ (không dự phòng); khóa nội bộ sai bị từ chối 401. Một điểm chưa đạt: bài cấp 1 có 139 từ, dưới khung 150 đến 250
(backend chỉ cảnh báo, giáo viên vẫn lưu được).

Độ dài bài soạn (13/10/2026): mô hình hay viết ngắn hơn mục tiêu, nhất là bản nhẹ (`gemini-3.5-flash-lite` viết 130 đến 145 từ khi được yêu cầu 200).
Dịch vụ nay báo mục tiêu lùi vào trong khung ít nhất 10% (`rules.target_words`), kèm số câu tương ứng, và không báo dung sai 8% cho mô hình;
lần đầu kiểm số từ đúng khung, bài hơi ngắn hoặc hơi dài được gọi lại kèm góp ý "viết thêm khoảng N từ", còn bản đó vẫn đạt dung sai thì giữ làm dự phòng
khi lần gọi lại hỏng hoặc quá giờ. Đo lại trên bản nhẹ: cấp 1 ngắn 214 từ, cấp 1 vừa 233 từ, cấp 2 vừa 369 từ, đều đạt ngay lần đầu; cấp 3 vừa trên bản nhẹ
chỉ được 546 từ sau khi gọi lại (khung 600 đến 900) nên báo lỗi; mô hình chính `gemini-3.8-flash` đạt cấp 3 ngay lần đầu ở lần đo 12/10.
Thử lại: `scripts\thu-that.py --only compose --levels 1 --lengths SHORT,MEDIUM`.

## Triển khai lên máy demo

Máy demo `QUANG-NHO` chạy dịch vụ dưới IIS: site **DSVHVN AI** chỉ nghe `127.0.0.1:8090` (không mở ra mạng ngoài, chỉ API trên cùng máy gọi),
ASP.NET Core Module chạy `.venv\Scripts\python.exe -m app.serve` theo `scripts/trien-khai/web.config`, app pool luôn chạy nên khởi động cùng máy.
Mã nằm ở `C:\dsvhvn\ai` (bản trước ở `C:\dsvhvn\ai-truoc`), khoá ở `C:\dsvhvn\cau-hinh\ai.env` (web.config trỏ tới qua `AI_ENV_FILE`), nhật ký `C:\dsvhvn\nhat-ky\ai_*.log`.

| Bước | Lệnh | Quyền |
|---|---|---|
| 1. Cài một lần: Python 3.14 cho mọi tài khoản (chép từ gói NuGet chính thức của python.org vào `C:\Program Files\Python314`, kiểm chữ ký; không dùng bộ cài vì bộ cài thất bại khi máy đã có cùng phiên bản cài cho riêng người dùng), app pool và site IIS, quyền, runner GitHub `may-demo-ai` | `pwsh -File scripts\trien-khai\cai-dat-may-demo-ai.ps1` | Quản trị, sau `cai-dat-may-demo.ps1` của repo backend |
| 2. Tạo `ai.env` từ `%APPDATA%\DSVHVN\ai-service.env` (chỉ biến `AI_*`, `GEMINI_*`, `ANTHROPIC_*`; đối chiếu khoá nội bộ với API, không in giá trị) | `pwsh -File scripts\trien-khai\tao-cau-hinh-ai.ps1` | Người dùng |
| 3. Triển khai: Pull Request có CI đạt thì workflow "Tự động gộp" gộp vào `main` (không cần người duyệt), CI trên `main` đạt thì workflow CD tự chạy; chạy tay từ thư mục repo khi runner tắt | `pwsh -File scripts\trien-khai\trien-khai-ai.ps1 -ThuMucGoi .` | Người dùng hoặc runner |
| 4. Cho API gọi dịch vụ thật: `Ai:Mode=Remote`, `Ai:BaseUrl=http://127.0.0.1:8090` | Repo backend: `tao-cau-hinh-may-demo.ps1` rồi chạy lại CD của backend | Người dùng |

Mỗi lần triển khai: giữ bản đang chạy, đặt `app_offline.htm` để dừng Python, chép mã mới, dựng lại `.venv` chỉ khi `requirements.txt` đổi (so mã băm),
gỡ `app_offline.htm` rồi chờ `/health` trả 200 (tối đa 180 giây); hỏng thì tự trả bản trước. CI có bước cài riêng `requirements.txt` rồi nạp `app.asgi`
để bắt gói chạy bị thiếu (test vẫn qua nhờ gói dev nên không tự phát hiện được).
Đổi khoá (ví dụ khoá Gemini mới): sửa `%APPDATA%\DSVHVN\ai-service.env`, chạy lại bước 2 rồi bước 3.
Hạn mức miễn phí của Gemini tính theo dự án Google, nên máy dev và máy demo dùng chung một khoá thì dùng chung 20 lượt mỗi ngày cho mỗi mô hình.

## Triển khai lên máy chủ Google Cloud

Máy chủ Google Cloud chạy dịch vụ trong container (ảnh dựng từ `Dockerfile`: Python 3.14, `requirements.txt` cộng `requirements-giong.txt` và `app/`, bật sẵn giọng đọc
(`GIONG_DOC_BAT=1`, mô hình trong volume `/srv/mo-hinh`), người dùng không phải root, nghe `0.0.0.0:8000` trong container, máy chủ chỉ mở ra `127.0.0.1:8090`). Khóa không nằm trong ảnh: Docker Compose
nạp `/opt/dsvhvn/cau-hinh/ai.env` do `deploy/google-cloud/tao-cau-hinh-may-chu.ps1` của repo backend sinh (chỉ khóa của nhà cung
cấp đang dùng, khóa nội bộ riêng của máy chủ). Biến repo `GCP_DEPLOY=true` thì CD dựng ảnh, đẩy lên Artifact Registry rồi chạy
`/opt/dsvhvn/bin/trien-khai.sh ai <mã commit>` trên máy chủ (kiểm `/health`, hỏng thì trả bản trước). Cách cài máy chủ và vận hành:
`deploy/google-cloud/README.md` của repo backend. Job `docker` trong CI dựng ảnh và chạy thử container.

## Chạy test

```powershell
.\.venv\Scripts\python -m pytest
```

Test dùng mô hình giả và SDK giả (kể cả máy đọc giả phát sóng hình sin cho `/v1/tts`, không nhập `vieneu`), không mạng, không cần khóa thật; `lameenc` (trong `requirements-dev.txt`) mã hóa MP3 thật trong test: khóa nội bộ, lược đồ vào, đầu ra hợp lệ và sai của từng API, gọi lại, `max_tokens`, từ chối, lỗi 429, 5xx, mạng, quá giờ của nhà cung cấp, bảng thuật ngữ, gợi ý, cấu hình, log không lộ khóa.

## Thử với mô hình thật và nối backend

```powershell
.\.venv\Scripts\python scripts\dem-token.py                     # chỉ Claude: đếm token vào, kiểm lược đồ được nhà cung cấp chấp nhận (không sinh chữ)
.\.venv\Scripts\python scripts\thu-that.py                      # theo AI_PROVIDER: mỗi API dùng mô hình chạy với dữ liệu mẫu, in token và chi phí
.\.venv\Scripts\python scripts\thu-that.py --only compose --levels 2 --max-calls 10
```

Hai script cùng ghi một sổ đếm lời gọi (`--ledger`, `--max-calls`, mặc định 60) để không vượt hạn mức khi thử.

Khi chưa gọi được Claude (hết số dư, không mạng) mà vẫn cần kiểm đường đi backend, dịch vụ, backend:

```powershell
.\.venv\Scripts\python scripts\chay-mo-hinh-gia.py --port 8000   # dịch vụ với mô hình giả, đầu ra hợp lệ dựng từ chính yêu cầu
# backend: Ai__Mode=Remote, Ai__BaseUrl=http://localhost:8000, Email__Mode=Log, cơ sở dữ liệu tạm
$env:ADMIN_PASSWORD = "<mật khẩu quản trị của backend tạm>"; $env:API_LOG = "<tệp log của backend>"; $env:BASE = "http://localhost:5090"
.\.venv\Scripts\python scripts\chay-noi-backend.py              # xuất bản di sản, dịch, tạo lớp, soạn bài, sinh câu, gợi ý cho khách
```

## Đánh giá mô hình

Bộ script trong `scripts/danh-gia/` đo phần **gợi ý** của hệ thống. Không gọi mô hình ngôn ngữ, không cần học sinh thật, không đụng cơ sở dữ liệu thật.

| Script | Đo gì |
|---|---|
| `do-di-san-lien-quan.py` | **Di sản liên quan.** precision@3 của hai cách xếp, "chỉ thuộc tính" (tắt phần giống chữ) và "thuộc tính + TF-IDF" (đúng như `app/recommender/rank.py`), trên 20 di sản của backend, so với bộ nhãn do hai người gán. Chỉ tiêu: ≥ 0,5. Cũng in độ đồng thuận giữa hai người gán (Jaccard, kappa của Cohen). |
| `hoc-sinh-ao.py` | **Học sinh ảo và gợi ý cá nhân hóa.** Dựng trường, lớp ở cả 3 cấp (mỗi lớp 10 bài học đã xuất bản và 10 bài kiểm tra), khoảng 180 em ảo mỗi mức nhiễu (3 mức nhiễu: nhầm 10%, 15%, 20% ở di sản đã vững) mỗi em làm 2 bài, cộng 5 lớp em chưa có lượt nào mỗi cấp; đọc "Gợi ý cho em" từ backend rồi đo: hit@3 di sản yếu so với 3 đường cơ sở ("quiz chưa làm theo hạn đóng", "bài mới nhất của lớp", "bài ngẫu nhiên của lớp") và phần "di sản nên ôn" so với 2 đường cơ sở; độ khó khớp mức của em; tác động của khối lớp với em chưa có lượt nào; gợi ý đúng lớp (chỉ tiêu 100%). |
| `chay-danh-gia.ps1` | Dựng backend tạm, chạy hai script trên, tắt backend, xóa cơ sở dữ liệu tạm. |
| `danh_gia_chung.py`, `cau_hoi_mau.py`, `backend_api.py` | Hàm thuần (precision@k, hit@k, đường cơ sở, mô phỏng có hạt giống), dựng câu hỏi mẫu từ dữ liệu di sản, gọi API. Có test trong `tests/`. |

Tham số mô phỏng (xác suất đúng ở di sản yếu: 25% câu 4 phương án, 50% câu đúng/sai; ba mức nhiễu; hạt giống; số em, số bài, số câu) nằm ở **đầu `hoc-sinh-ao.py`**, in ra đầu báo cáo **trước khi đo**. Đổi tham số là đo lại từ đầu và ghi vào báo cáo.

### Chạy (khuyến nghị: một lệnh)

Cần .NET SDK 9, SQL Server LocalDB, `sqlcmd` trong PATH, môi trường ảo `.venv` đã cài `requirements-dev.txt`, và backend (thư mục `BE_Cultural_Heritage-` cạnh repo này, hoặc truyền `-BackendDir`).

```powershell
pwsh -File scripts/danh-gia/chay-danh-gia.ps1                                    # đo cả hai phần, kết quả ở %TEMP%\dsvhvn-danhgia-<giờ>\ket-qua
pwsh -File scripts/danh-gia/chay-danh-gia.ps1 -Phan di-san-lien-quan -Out D:\tam\dg
pwsh -File scripts/danh-gia/chay-danh-gia.ps1 -Phan goi-y-ca-nhan -ThamSoHocSinh "--kieu-han-dong=cung-ngay"
pwsh -File scripts/danh-gia/chay-danh-gia.ps1 -Phan goi-y-ca-nhan -ThamSoHocSinh "--thu-nho"   # cỡ nhỏ (khoảng 1 phút) để thử đường đi
```

Script `chay-danh-gia.ps1` tự làm theo thứ tự: publish backend vào thư mục tạm; tạo cơ sở dữ liệu LocalDB tên `dsvhvn_tam_danhgia_<giờ>`; chạy backend ở cổng 5090; chạy các script đo; tắt backend; **xóa cơ sở dữ liệu tạm** rồi kiểm lại bằng truy vấn rằng không còn.
Để không chạm vào dữ liệu thật dù User Secrets của backend đang trỏ vào cơ sở dữ liệu thật, gửi thư thật và gọi AI thật, script **đè** bằng biến môi trường của tiến trình con: `ConnectionStrings__Default` (cơ sở dữ liệu tạm), `Email__Mode=Log`, `Ai__Mode=Simulated`, `Storage__Provider=Local`, `ASPNETCORE_ENVIRONMENT=Development`, `ASPNETCORE_URLS=http://localhost:<cổng>`.
Script từ chối tên cơ sở dữ liệu không bắt đầu bằng `dsvhvn_tam_danhgia_` và các cổng 5080, 8080, 8081, 8082, 8090. Mật khẩu quản trị lấy từ User Secrets của backend (khóa `Seed:AdminPassword`) hoặc biến `ADMIN_PASSWORD`, chỉ đi vào tiến trình con, không in và không ghi ra tệp.
Giữ backend để xem dữ liệu: thêm `-GiuBackend`, dọn sau bằng `-DonDep -Database <tên> -MaTienTrinh <mã>`. Gọi `pwsh` (PowerShell 7), không dùng Windows PowerShell 5.

### Chạy tay các script

Khi đã có một backend tạm (cơ sở dữ liệu tạm, `Email__Mode=Log`, `Ai__Mode=Simulated`) ở cổng 5090:

```powershell
$env:BASE = "http://localhost:5090"; $env:API_LOG = "<tệp log của backend>"; $env:ADMIN_PASSWORD = "<mật khẩu quản trị của backend tạm>"
.\.venv\Scripts\python scripts\danh-gia\do-di-san-lien-quan.py --out D:\tam\dg
.\.venv\Scripts\python scripts\danh-gia\hoc-sinh-ao.py --out D:\tam\dg
```

`hoc-sinh-ao.py` có thêm `--hoc-sinh-moi-lop`, `--hoc-sinh-chua-lam`, `--lop-chua-lam`, `--kieu-han-dong khac-nhau|cung-ngay`, `--luong`, `--hat`, `--thu-nho`. Mỗi lần chạy tạo một trường mới trong cơ sở dữ liệu nên chạy lại trên cùng backend là được.

### Kết quả nằm ở đâu

Báo cáo Markdown tiếng Việt (bảng) và JSON số liệu thô nằm trong thư mục `-Out` / `--out` (mặc định dưới `%TEMP%`): `di-san-lien-quan.md`, `di-san-lien-quan.json`, `hoc-sinh-ao.md`, `hoc-sinh-ao.json`. **Không đưa vào git.**

### Bộ nhãn di sản liên quan phải do hai người gán

Tệp `scripts/danh-gia/nhan-di-san-lien-quan.json` liệt kê 20 di sản với các danh sách nhãn **để trống**: script không bịa nhãn. Cách làm:

1. Hai thành viên, **độc lập và không xem nhãn của nhau**, mỗi người điền `nhanNguoi1` / `nhanNguoi2` cho từng di sản: 3 đến 5 mã (`id`) di sản liên quan, chọn trong 20 di sản của danh sách, không chọn chính nó. Không xem kết quả xếp hạng của dịch vụ trước khi gán. Ghi tên vào `nguoiGan1`, `nguoiGan2`.
2. Đối chiếu chỗ lệch, điền danh sách đã thống nhất vào `thongNhat` (3 đến 5 mã). Nếu mời được một giáo viên thì cho gán thêm theo cùng cách trên một bản sao tệp và đưa vào bước thống nhất.
3. Chạy `chay-danh-gia.ps1 -Phan di-san-lien-quan`. Khi chưa có nhãn, báo cáo nói rõ "không có số precision@3" và chỉ in ba di sản đứng đầu của hai cách; có nhãn thì tính precision@3 theo danh sách thống nhất, theo từng người gán, và đồng thuận (Jaccard, kappa).
4. Chỉ commit tệp nhãn khi nhãn do người thật gán. Tệp sai cấu trúc (mã lạ, trùng, tự chọn chính nó, không đủ 3 đến 5 mã) làm script dừng với mã thoát 2.

### Giới hạn cần biết khi đọc số

- Gợi ý của backend chỉ trả mã và tiêu đề quiz, bài học (không trả di sản của chúng); di sản của từng quiz, bài học được lấy từ kế hoạch dựng lớp của chính script.
- Kết quả phụ thuộc cách dựng lớp (10 bài mỗi lớp, mỗi bài 4 di sản, mỗi di sản xuất hiện trong 2 bài) và cách backend xếp quiz theo hạn đóng trước độ khó (xem tùy chọn `--kieu-han-dong`).
- Các đường cơ sở ngẫu nhiên được tính bằng giá trị kỳ vọng chính xác, không rút mẫu.
