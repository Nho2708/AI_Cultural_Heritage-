# Dịch vụ AI của DSVHVN

Dịch vụ nội bộ (Python, FastAPI) mà backend gọi một chiều qua HTTP. Không truy cập cơ sở dữ liệu, không nhận dữ liệu cá nhân.
Gọi Claude (mặc định `claude-haiku-5-5`) để soạn bài học, sinh câu hỏi, tóm tắt và dịch di sản; riêng gợi ý di sản liên quan
chỉ dùng scikit-learn (TF-IDF và cosine), không gọi mô hình ngôn ngữ.

| API | Việc | Mô hình | Mức suy nghĩ |
|---|---|---|---|
| `POST /v1/compose-lesson` | Soạn nội dung bài học tiếng Việt đúng cấp 1, 2, 3 của lớp | có | medium |
| `POST /v1/generate-questions` | Sinh câu hỏi 8 dạng theo cấp, độ khó | có | medium |
| `POST /v1/summarize-heritage` | Tóm tắt tiếng Việt (bản ngắn để nghe, bản chi tiết để đọc) | có | low |
| `POST /v1/translate-heritage` | Dịch sang `en`, `ko`, `zh-Hans`, `ja`, có bảng thuật ngữ tên riêng | có | low |
| `POST /v1/rank-related` | Xếp hạng di sản liên quan | không | - |
| `GET /health` | Kiểm tra sức khỏe (không cần khóa) | - | - |

Hợp đồng chi tiết nằm ở phía backend (`docs/bai-hoc-theo-cap.md`, `docs/ngan-hang-cau-hoi.md`, `docs/da-ngon-ngu.md`, `docs/thong-ke-goi-y.md`).

## Cấu trúc

```
app/
  main.py, asgi.py      tạo ứng dụng, kiểm khóa nội bộ, mã tương quan, log JSON
  config.py             cấu hình (pydantic-settings), đọc .env
  api/routes.py         năm API và /health
  schemas/              kiểu yêu cầu, kết quả (JSON camelCase, khớp backend)
  prompts/              prompt tiếng Việt, lược đồ JSON, bảng thuật ngữ tên riêng
  validators/           bộ kiểm đầu ra theo cấp, dạng câu, ngôn ngữ
  services/             ghép prompt, gọi mô hình, kiểm, gọi lại một lần
  llm/                  bộ gọi Claude (client.py) và vòng gọi-kiểm-gọi lại (runner.py)
  recommender/rank.py   gợi ý content-based
  rules.py              số liệu quy tắc sao đúng của backend
scripts/                thử gọi thật, đếm token, chạy nối backend, mô hình giả
tests/                  pytest với mô hình giả, không mạng
```

## Cài đặt

Cần Python 3.12 trở lên. Đã chạy trên Python 3.14.7: mọi thư viện ghim trong `requirements.txt` đều có bản dựng sẵn cho 3.14 trên Windows (kể cả numpy, scipy, scikit-learn), không cần trình biên dịch.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt          # chạy dịch vụ
.\.venv\Scripts\python -m pip install -r requirements-dev.txt      # thêm pytest để chạy test
```

Phiên bản đã ghim: `anthropic 1.13.0`, `fastapi 0.143.0`, `uvicorn 0.54.0`, `pydantic 2.14.0`, `pydantic-settings 2.15.0`, `scikit-learn 1.9.1`, `numpy 2.5.3`.

## Đặt khóa

Ba biến: `ANTHROPIC_API_KEY` (khóa nhà cung cấp mô hình), `AI_INTERNAL_KEY` (khóa nội bộ giữa backend và dịch vụ này), `AI_MODEL` (mặc định `claude-haiku-5-5`).
Chọn một trong hai cách (có cả hai thì `.env` trong thư mục dịch vụ thắng; biến môi trường của tiến trình thắng cả hai):

1. Tệp `.env` cạnh `README.md` (sao từ `.env.example`, đã nằm trong `.gitignore`), hoặc
2. Tệp `%APPDATA%\DSVHVN\ai-service.env` dùng chung cho mọi bản chạy trên máy (cùng ba dòng `TÊN=giá trị`).

Không đặt `ANTHROPIC_API_KEY` thành biến môi trường người dùng hay hệ thống (sẽ chiếm quyền xác thực của công cụ khác): dịch vụ tự đọc từ tệp và chỉ giữ khóa trong tiến trình.
Thiếu `AI_INTERNAL_KEY` thì dịch vụ không khởi động; thiếu `ANTHROPIC_API_KEY` thì các API dùng mô hình trả 503 còn `rank-related` vẫn chạy.
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

## Chạy test

```powershell
.\.venv\Scripts\python -m pytest
```

Test dùng mô hình giả và SDK giả, không mạng, không cần khóa thật: khóa nội bộ, lược đồ vào, đầu ra hợp lệ và sai của từng API, gọi lại, `max_tokens`, từ chối, lỗi 429, 5xx, mạng, quá giờ của nhà cung cấp, bảng thuật ngữ, gợi ý, cấu hình, log không lộ khóa.

## Thử với Claude thật và nối backend

```powershell
.\.venv\Scripts\python scripts\dem-token.py                     # đếm token vào, kiểm lược đồ được nhà cung cấp chấp nhận (không sinh chữ)
.\.venv\Scripts\python scripts\thu-that.py                      # mỗi API dùng mô hình chạy với dữ liệu mẫu, in token và chi phí
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
