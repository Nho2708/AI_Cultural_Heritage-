# Dựng hai môi trường máy đọc cho công cụ tạo thuyết minh (chạy trên máy dev, không vào ảnh Docker):
#   moi-truong\vieneu  (Python 3.12: VieNeu-TTS v3 Turbo, onnxruntime)
#   moi-truong\melo    (Python 3.11: MeloTTS ghim ở một commit, PyTorch CPU)
# rồi tải dữ liệu NLTK/unidic, nạp thử hai máy đọc để kéo mô hình về .cache\hf và áp cách sửa symlink của Hugging Face.
# Cần: uv (https://docs.astral.sh/uv/), git. Dùng: .\cai-dat.ps1 [-ChiMoiTruong]   (bỏ bước nạp thử mô hình)
param([switch]$ChiMoiTruong)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:HF_HOME = Join-Path $PSScriptRoot ".cache\hf"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
if (-not (Test-Path -LiteralPath $uv)) { Write-Error "Chưa có uv. Cài: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`"" }

function Dung-MoiTruong([string]$Ten, [string]$PhienBanPython, [string]$TepYeuCau) {
    $thuMuc = Join-Path $PSScriptRoot "moi-truong\$Ten"
    Write-Host "== $Ten (Python $PhienBanPython) -> $thuMuc"
    & $uv venv --python $PhienBanPython --seed $thuMuc
    if ($LASTEXITCODE -ne 0) { throw "uv venv $Ten thất bại" }
    $python = Join-Path $thuMuc "Scripts\python.exe"
    & $uv pip install --python $python -r $TepYeuCau
    if ($LASTEXITCODE -ne 0) { throw "cài gói cho $Ten thất bại" }
    return $python
}

$pyVieneu = Dung-MoiTruong "vieneu" "3.12" "requirements-vieneu.txt"
$pyMelo = Dung-MoiTruong "melo" "3.11" "requirements-melo.txt"

Write-Host "== Dữ liệu NLTK (g2p tiếng Anh) và từ điển unidic (tiếng Nhật)"
& $pyMelo -c "import nltk; [nltk.download(t, quiet=True) for t in ('averaged_perceptron_tagger_eng', 'cmudict')]"
& $pyMelo -m unidic download

if ($ChiMoiTruong) { Write-Host "Xong (chưa nạp thử mô hình)."; exit 0 }

Write-Host "== Nạp thử hai máy đọc: tải mô hình về $env:HF_HOME (vài GB, chỉ lần đầu) và sửa symlink của Hugging Face cache"
$ra = Join-Path $PSScriptRoot "ra\kiem-cai-dat"
& $pyVieneu -X utf8 tao_thuyet_minh.py --cuc-bo mau\kiem-cai-dat.json --ra $ra --python-vieneu $pyVieneu --python-melo $pyMelo --hf-home $env:HF_HOME
if ($LASTEXITCODE -ne 0) { throw "nạp thử máy đọc thất bại, xem thông báo phía trên" }
& $pyVieneu go_symlink_hf.py $env:HF_HOME
Write-Host "Xong. Nghe thử trong $ra\cuc-bo rồi chạy: python tao_thuyet_minh.py"
