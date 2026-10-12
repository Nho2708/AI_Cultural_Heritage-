<#
.SYNOPSIS
  Triển khai Dịch vụ AI lên máy demo: thay mã, dựng lại môi trường Python khi danh sách gói đổi, kiểm sức khoẻ, tự trả bản trước khi hỏng.

.DESCRIPTION
  Workflow CD chỉ gọi script này; khi runner tắt vẫn triển khai tay được bằng đúng script, kể cả từ thư mục repo:
    pwsh scripts/trien-khai/trien-khai-ai.ps1 -ThuMucGoi <thư mục gói hoặc thư mục repo>

  Site IIS "DSVHVN AI" (cổng 8090, chỉ 127.0.0.1) do cai-dat-may-demo-ai.ps1 tạo; ASP.NET Core Module chạy
  .venv\Scripts\python.exe -m app.serve theo web.config. Bí mật ở <GocMay>\cau-hinh\ai.env (tao-cau-hinh-ai.ps1).

  Các bước:
    1. Kiểm gói, Python gốc 3.14 dùng chung cho mọi tài khoản, tệp ai.env.
    2. Giữ bản đang chạy ở ai-truoc (kể cả .venv).
    3. Đặt app_offline.htm để dừng tiến trình Python.
    4. Chép mã mới, web.config, requirements.txt.
    5. requirements.txt đổi (so mã băm) hoặc chưa có .venv thì dựng lại .venv và cài gói.
    6. Gỡ app_offline.htm, gọi địa chỉ sức khoẻ tới khi trả 200.
    7. Hỏng ở bước 3-6: trả bản trước, gỡ app_offline.htm, thoát mã 1.

.PARAMETER ThuMucGoi
  Thư mục chứa app\ và requirements.txt; web.config ở gốc gói hoặc ở scripts\trien-khai\ (khi trỏ vào repo).
.PARAMETER GocMay
  Gốc triển khai, mặc định C:\dsvhvn (có ai\, ai-truoc\, cau-hinh\, nhat-ky\).
.PARAMETER PythonGoc
  python.exe 3.14 cài cho mọi tài khoản. Bỏ trống thì lấy biến DSVHVN_PYTHON, rồi C:\Program Files\Python314\python.exe.
.PARAMETER KiemSucKhoeUrl
  Địa chỉ kiểm sức khoẻ sau khi thay bản, mặc định http://127.0.0.1:8090/health.
.PARAMETER ThoiGianChoGiay
  Số giây tối đa chờ địa chỉ sức khoẻ trả 200, mặc định 180 (lần đầu sau khi dựng .venv Python nạp gói chậm).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ThuMucGoi,
    [string]$GocMay = 'C:\dsvhvn',
    [string]$PythonGoc,
    [string]$KiemSucKhoeUrl = 'http://127.0.0.1:8090/health',
    [int]$ThoiGianChoGiay = 180
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3.0

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$script:SoBuoc = 0
function Write-Buoc([string]$noiDung) {
    $script:SoBuoc++
    Write-Host ''
    Write-Host ("[{0}] {1}" -f $script:SoBuoc, $noiDung) -ForegroundColor Cyan
}

function Invoke-Robocopy([string]$nguon, [string]$dich, [string[]]$them) {
    # Mã thoát 0-7 là thành công, từ 8 là lỗi.
    $a = @($nguon, $dich, '/MIR', '/R:5', '/W:2', '/NFL', '/NDL', '/NJH', '/NJS', '/NP') + $them
    & robocopy @a | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy từ '$nguon' sang '$dich' lỗi (mã $LASTEXITCODE)." }
    $global:LASTEXITCODE = 0
}

function Invoke-Native([string]$tep, [string[]]$thamSo) {
    & $tep @thamSo
    if ($LASTEXITCODE -ne 0) { throw "$([System.IO.Path]::GetFileName($tep)) $($thamSo -join ' ') lỗi (mã $LASTEXITCODE)." }
}

function Test-SucKhoe([string]$url) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
        return ($r.StatusCode -eq 200)
    } catch {
        $script:LoiSucKhoe = $_.Exception.Message
        return $false
    }
}

# ---------------------------------------------------------------- kiểm đầu vào
Write-Buoc 'Kiểm gói, Python và cấu hình'
$ThuMucGoi = (Resolve-Path -LiteralPath $ThuMucGoi).Path
$goiApp = Join-Path $ThuMucGoi 'app'
$goiReq = Join-Path $ThuMucGoi 'requirements.txt'
$goiWebConfig = @((Join-Path $ThuMucGoi 'web.config'), (Join-Path $ThuMucGoi 'scripts\trien-khai\web.config')) |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not (Test-Path -LiteralPath (Join-Path $goiApp 'serve.py'))) { throw "Gói không có app\serve.py: $ThuMucGoi" }
if (-not (Test-Path -LiteralPath $goiReq)) { throw "Gói không có requirements.txt: $ThuMucGoi" }
if (-not $goiWebConfig) { throw "Gói không có web.config (ở gốc hoặc scripts\trien-khai\): $ThuMucGoi" }

if (-not $PythonGoc) {
    $PythonGoc = @($env:DSVHVN_PYTHON, 'C:\Program Files\Python314\python.exe') |
        Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $PythonGoc -or -not (Test-Path -LiteralPath $PythonGoc)) {
    throw 'Không thấy Python 3.14 cài cho mọi tài khoản (C:\Program Files\Python314\python.exe). Chạy cai-dat-may-demo-ai.ps1 bằng quyền quản trị.'
}
$banPython = (& $PythonGoc -c 'import sys; print("%d.%d" % sys.version_info[:2])').Trim()
if ($banPython -ne '3.14') { throw "Cần Python 3.14, $PythonGoc là $banPython." }
Write-Host "Python gốc: $PythonGoc ($banPython)"

$ai = Join-Path $GocMay 'ai'
$aiTruoc = Join-Path $GocMay 'ai-truoc'
$tepEnv = Join-Path $GocMay 'cau-hinh\ai.env'
$appOffline = Join-Path $ai 'app_offline.htm'
$venv = Join-Path $ai '.venv'
$pythonVenv = Join-Path $venv 'Scripts\python.exe'
$tepBam = Join-Path $venv 'requirements.sha256'
if (-not (Test-Path -LiteralPath $ai)) { throw "Chưa có $ai. Chạy cai-dat-may-demo-ai.ps1 bằng quyền quản trị." }
if (-not (Test-Path -LiteralPath $tepEnv) -or (Get-Item -LiteralPath $tepEnv).Length -eq 0) {
    throw "Chưa có $tepEnv (hoặc tệp rỗng). Chạy scripts\trien-khai\tao-cau-hinh-ai.ps1 trước."
}

$phienBan = Join-Path $ThuMucGoi 'phien-ban.txt'
if (Test-Path -LiteralPath $phienBan) {
    Write-Host 'Phiên bản trong gói:'
    Get-Content -LiteralPath $phienBan | ForEach-Object { Write-Host "  $_" }
}

$bamMoi = (Get-FileHash -LiteralPath $goiReq -Algorithm SHA256).Hash
$bamCu = if (Test-Path -LiteralPath $tepBam) { (Get-Content -LiteralPath $tepBam -Raw).Trim() } else { '' }
$canDungVenv = (-not (Test-Path -LiteralPath $pythonVenv)) -or ($bamCu -ne $bamMoi)
$coBanTruoc = Test-Path -LiteralPath (Join-Path $ai 'app\serve.py')
$daDatOffline = $false
$daThayBan = $false

try {
    # ------------------------------------------------------------ 2. giữ bản trước
    Write-Buoc 'Giữ bản đang chạy'
    if ($coBanTruoc) {
        New-Item -ItemType Directory -Force -Path $aiTruoc | Out-Null
        Invoke-Robocopy $ai $aiTruoc @('/XF', 'app_offline.htm', '/XD', '__pycache__')
        Write-Host "Đã giữ bản đang chạy ở $aiTruoc."
    } else {
        Write-Host 'Lần triển khai đầu tiên: chưa có bản trước để giữ.'
    }

    # ------------------------------------------------------------ 3. dừng tiến trình
    Write-Buoc 'Dừng dịch vụ (app_offline.htm)'
    $trangOffline = '<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>Đang cập nhật</title></head><body><p>Dịch vụ AI đang được cập nhật.</p></body></html>'
    [System.IO.File]::WriteAllText($appOffline, $trangOffline, (New-Object System.Text.UTF8Encoding($false)))
    $daDatOffline = $true
    # Chờ tiến trình Python thoát để nhả khoá tệp trong .venv.
    Start-Sleep -Seconds 5

    # ------------------------------------------------------------ 4. thay mã
    Write-Buoc 'Chép mã mới'
    $daThayBan = $true
    Invoke-Robocopy $goiApp (Join-Path $ai 'app') @('/XD', '__pycache__')
    Copy-Item -LiteralPath $goiReq -Destination (Join-Path $ai 'requirements.txt') -Force
    Copy-Item -LiteralPath $goiWebConfig -Destination (Join-Path $ai 'web.config') -Force
    if (Test-Path -LiteralPath $phienBan) { Copy-Item -LiteralPath $phienBan -Destination (Join-Path $ai 'phien-ban.txt') -Force }
    Get-ChildItem -LiteralPath $ai -Filter 'index.html' -File -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-Host 'Đã chép app\, requirements.txt, web.config.'

    # ------------------------------------------------------------ 5. môi trường Python
    Write-Buoc 'Môi trường Python (.venv)'
    if ($canDungVenv) {
        Write-Host $(if ($bamCu) { 'requirements.txt đã đổi: dựng lại .venv.' } else { 'Chưa có .venv: dựng mới.' })
        if (Test-Path -LiteralPath $venv) { Remove-Item -LiteralPath $venv -Recurse -Force }
        Invoke-Native $PythonGoc @('-m', 'venv', $venv)
        Invoke-Native $pythonVenv @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '--no-warn-script-location',
            '-r', (Join-Path $ai 'requirements.txt'))
        [System.IO.File]::WriteAllText($tepBam, $bamMoi, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host 'Đã cài gói.'
    } else {
        Write-Host 'requirements.txt không đổi: giữ .venv.'
    }

    # ------------------------------------------------------------ 6. khởi động lại và kiểm sức khoẻ
    Write-Buoc "Khởi động lại và kiểm sức khoẻ ($KiemSucKhoeUrl, tối đa $ThoiGianChoGiay giây)"
    Remove-Item -LiteralPath $appOffline -Force -ErrorAction SilentlyContinue
    $daDatOffline = $false
    $han = (Get-Date).AddSeconds($ThoiGianChoGiay)
    $script:LoiSucKhoe = ''
    $khoe = $false
    do {
        if (Test-SucKhoe $KiemSucKhoeUrl) { $khoe = $true; break }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $han)
    if (-not $khoe) {
        throw "Địa chỉ sức khoẻ không trả 200 trong $ThoiGianChoGiay giây. Lỗi cuối: $($script:LoiSucKhoe). Xem nhật ký $GocMay\nhat-ky\ai_*.log"
    }
    $tt = (Invoke-WebRequest -Uri $KiemSucKhoeUrl -UseBasicParsing -TimeoutSec 10).Content | ConvertFrom-Json
    Write-Host ("Dịch vụ AI đã khoẻ: nhà cung cấp {0}, mô hình {1}, có khoá: {2}" -f $tt.provider, $tt.model, $tt.llmConfigured) -ForegroundColor Green
    if (-not $tt.llmConfigured) { Write-Warning 'Chưa có khoá mô hình trong ai.env: các nút AI sẽ báo dịch vụ bận.' }

    # Nhật ký stdout của module IIS: giữ 14 ngày.
    Get-ChildItem -LiteralPath (Join-Path $GocMay 'nhat-ky') -Filter 'ai_*.log' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | Remove-Item -Force -ErrorAction SilentlyContinue

    Write-Host ''
    Write-Host 'Triển khai Dịch vụ AI thành công.' -ForegroundColor Green
}
catch {
    Write-Host ''
    Write-Host "TRIỂN KHAI HỎNG: $($_.Exception.Message)" -ForegroundColor Red

    # ------------------------------------------------------------ 7. trả bản trước
    if ($daDatOffline -or $daThayBan) {
        if (-not $daDatOffline) {
            [System.IO.File]::WriteAllText($appOffline, 'Đang trả bản trước', (New-Object System.Text.UTF8Encoding($false)))
            Start-Sleep -Seconds 5
        }
        try {
            if ($daThayBan -and $coBanTruoc -and (Test-Path -LiteralPath $aiTruoc)) {
                Invoke-Robocopy $aiTruoc $ai @('/XF', 'app_offline.htm')
                Write-Host 'Đã trả ai-truoc về ai (kể cả .venv).' -ForegroundColor Yellow
            } elseif ($daThayBan) {
                Write-Host 'Không có bản trước để trả (lần triển khai đầu tiên).' -ForegroundColor Yellow
            } else {
                Write-Host 'Chưa thay bản chạy nên bản cũ còn nguyên.' -ForegroundColor Yellow
            }
        } catch {
            Write-Host "Không trả được bản trước: $($_.Exception.Message)" -ForegroundColor Red
        }
        Remove-Item -LiteralPath $appOffline -Force -ErrorAction SilentlyContinue
    }
    exit 1
}
