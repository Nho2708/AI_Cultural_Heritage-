<#
.SYNOPSIS
  Cài đặt một lần phần Dịch vụ AI trên máy demo QUANG-NHO: Python 3.14 cho mọi tài khoản, site IIS 127.0.0.1:8090, quyền, runner GitHub.

.DESCRIPTION
  Chạy bằng PowerShell 7 mở bằng "Run as Administrator", SAU cai-dat-may-demo.ps1 của repo backend (cây C:\dsvhvn, ARR, runner API/web).
  Chạy lại nhiều lần vẫn đúng (mỗi bước kiểm rồi mới làm). Không mở cổng tường lửa: site chỉ nghe 127.0.0.1, chỉ API trên cùng máy gọi.

  Sau script này:
    1. pwsh scripts\trien-khai\tao-cau-hinh-ai.ps1          (không cần quản trị: tạo cau-hinh\ai.env)
    2. Gộp vào main (CD tự triển khai) hoặc chạy tay: pwsh scripts\trien-khai\trien-khai-ai.ps1 -ThuMucGoi .
    3. Repo backend: pwsh scripts\trien-khai\tao-cau-hinh-may-demo.ps1 rồi chạy lại CD của backend để API gọi AI thật.

.PARAMETER BoQuaPython
  Không cài Python (đã có C:\Program Files\Python314\python.exe hoặc tự cài).
.PARAMETER BoQuaRunner
  Không cài runner GitHub cho repo AI.
#>
#Requires -Version 7.0
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [switch]$BoQuaPython,
    [switch]$BoQuaRunner
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3.0

$goc = 'C:\dsvhvn'
$tenPool = 'DSVHVN AI'
$tenSite = 'DSVHVN AI'
$binding = 'http/127.0.0.1:8090:'
$thuAi = Join-Path $goc 'ai'
$pythonMay = 'C:\Program Files\Python314\python.exe'
$repoAi = 'Nho2708/AI_Cultural_Heritage-'
$thuRunner = 'C:\actions-runner\ai'
$appcmd = Join-Path $env:windir 'System32\inetsrv\appcmd.exe'

function Write-Buoc([string]$noiDung) {
    Write-Host ''
    Write-Host "== $noiDung" -ForegroundColor Cyan
}

function Invoke-Native([string]$tep, [string[]]$thamSo, [switch]$ChoPhepLoi) {
    $kq = & $tep @thamSo 2>&1
    $ma = $LASTEXITCODE
    $global:LASTEXITCODE = 0
    if ($ma -ne 0 -and -not $ChoPhepLoi) { throw "$([System.IO.Path]::GetFileName($tep)) $($thamSo -join ' ') lỗi (mã $ma): $($kq -join ' ')" }
    return [pscustomobject]@{ Ma = $ma; DauRa = ($kq -join "`n") }
}

function Grant([string]$duongDan, [string]$nguoi, [string]$quyen, [switch]$KhongKeThua) {
    $dich = if ($KhongKeThua) { $quyen } else { "(OI)(CI)$quyen" }
    [void](Invoke-Native icacls @($duongDan, '/grant', "${nguoi}:${dich}"))
}

function Test-IisCoTen([string]$loai, [string]$ten) {
    $r = Invoke-Native $appcmd @('list', $loai, $ten, '/text:name') -ChoPhepLoi
    return ($r.Ma -eq 0 -and $r.DauRa.Trim().Length -gt 0)
}

# ---------------------------------------------------------------- kiểm tiền điều kiện
Write-Buoc 'Kiểm điều kiện của máy'
if (-not (Test-Path $appcmd)) { throw 'Chưa bật IIS (không thấy appcmd.exe).' }
if (-not (Test-Path "$env:ProgramFiles\IIS\Asp.Net Core Module\V2\aspnetcorev2.dll")) {
    throw 'Thiếu ASP.NET Core Module V2 (cài .NET Hosting Bundle): site AI dùng module này để chạy Python.'
}
if (-not (Test-Path (Join-Path $goc 'cau-hinh'))) { throw "Chưa có $goc\cau-hinh. Chạy cai-dat-may-demo.ps1 của repo backend trước." }
Write-Host 'Đủ IIS, ASP.NET Core Module V2 và cây C:\dsvhvn.'

# ---------------------------------------------------------------- 1. Python cho mọi tài khoản
Write-Buoc 'Python 3.14 cho mọi tài khoản'
# Python của người dùng nằm trong hồ sơ cá nhân: runner (NETWORK SERVICE) và app pool không đọc được, nên cần bản cài cho cả máy.
if (Test-Path -LiteralPath $pythonMay) {
    Write-Host "Đã có $pythonMay."
} elseif ($BoQuaPython) {
    Write-Warning "Bỏ qua cài Python (-BoQuaPython) nhưng chưa có $pythonMay; trien-khai-ai.ps1 sẽ cần -PythonGoc."
} else {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Không thấy winget. Cài Python 3.14 (64-bit, "Install for all users") rồi chạy lại với -BoQuaPython.' }
    Write-Host 'Cài Python.Python.3.14 bằng winget (phạm vi máy)...'
    $r = Invoke-Native winget @('install', '--id', 'Python.Python.3.14', '--exact', '--scope', 'machine', '--silent',
        '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity') -ChoPhepLoi
    if (-not (Test-Path -LiteralPath $pythonMay)) { throw "winget không cài được Python vào $pythonMay (mã $($r.Ma)): $($r.DauRa)" }
    Write-Host "Đã cài $pythonMay."
}
if (Test-Path -LiteralPath $pythonMay) {
    $ban = (& $pythonMay -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])').Trim()
    Write-Host "Phiên bản: $ban"
}

# ---------------------------------------------------------------- 2. thư mục
Write-Buoc 'Thư mục'
foreach ($t in @('ai', 'ai-truoc')) { New-Item -ItemType Directory -Force -Path (Join-Path $goc $t) | Out-Null }
Write-Host "Đã có $goc\ai và $goc\ai-truoc."

# ---------------------------------------------------------------- 3. IIS
Write-Buoc 'App pool và site IIS (chỉ 127.0.0.1:8090)'
if (-not (Test-IisCoTen 'apppool' $tenPool)) {
    [void](Invoke-Native $appcmd @('add', 'apppool', "/name:$tenPool"))
    Write-Host "Đã tạo app pool '$tenPool'."
}
# Không dùng .NET; luôn chạy để lần gọi AI đầu tiên không phải chờ Python khởi động.
[void](Invoke-Native $appcmd @('set', 'apppool', $tenPool, '/managedRuntimeVersion:', '/startMode:AlwaysRunning',
    '/processModel.idleTimeout:00:00:00', '/autoStart:true'))
if (-not (Test-IisCoTen 'site' $tenSite)) {
    [void](Invoke-Native $appcmd @('add', 'site', "/name:$tenSite", "/bindings:$binding", "/physicalPath:$thuAi"))
    Write-Host "Đã tạo site '$tenSite'."
} else {
    [void](Invoke-Native $appcmd @('set', 'site', $tenSite, "/bindings:$binding"))
    [void](Invoke-Native $appcmd @('set', 'vdir', "$tenSite/", "/physicalPath:$thuAi"))
    Write-Host "Đã cập nhật site '$tenSite'."
}
[void](Invoke-Native $appcmd @('set', 'app', "$tenSite/", "/applicationPool:$tenPool", '/preloadEnabled:true'))
[void](Invoke-Native $appcmd @('start', 'site', $tenSite) -ChoPhepLoi)

# ---------------------------------------------------------------- 4. quyền
Write-Buoc 'Quyền'
$identity = "IIS AppPool\$tenPool"
Grant $thuAi $identity 'RX'
Grant (Join-Path $goc 'nhat-ky') $identity 'M'
# Chỉ cho app pool AI đọc đúng tệp ai.env, không đọc các bí mật khác trong cau-hinh.
$tepEnv = Join-Path $goc 'cau-hinh\ai.env'
if (-not (Test-Path -LiteralPath $tepEnv)) {
    [System.IO.File]::WriteAllText($tepEnv, '', (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Đã tạo $tepEnv rỗng (tao-cau-hinh-ai.ps1 sẽ ghi nội dung)."
}
Grant $tepEnv $identity 'R' -KhongKeThua
Write-Host "App pool '$tenPool': đọc/chạy $thuAi, ghi nhat-ky, đọc cau-hinh\ai.env."

# ---------------------------------------------------------------- 5. runner GitHub cho repo AI
Write-Buoc 'Runner GitHub tự host cho repo AI'
if ($BoQuaRunner) {
    Write-Host 'Bỏ qua (-BoQuaRunner).'
} elseif (Test-Path (Join-Path $thuRunner '.runner')) {
    Write-Host "Runner đã cấu hình ở $thuRunner, bỏ qua."
} else {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Không thấy gh (GitHub CLI) trong PATH.' }
    $networkService = ([System.Security.Principal.SecurityIdentifier]::new([System.Security.Principal.WellKnownSidType]::NetworkServiceSid, $null)).Translate([System.Security.Principal.NTAccount]).Value
    New-Item -ItemType Directory -Force -Path $thuRunner | Out-Null
    $thuTai = $null
    try {
        if (-not (Test-Path (Join-Path $thuRunner 'config.cmd'))) {
            $thuTai = Join-Path ([System.IO.Path]::GetTempPath()) ('runner-' + [guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $thuTai | Out-Null
            $banPh = (& gh release view --repo actions/runner --json tagName,body,assets) | ConvertFrom-Json
            $tai = $banPh.assets | Where-Object { $_.name -match '^actions-runner-win-x64-\d+\.\d+\.\d+\.zip$' } | Select-Object -First 1
            if (-not $tai) { throw 'Không tìm thấy gói actions-runner win-x64 trong bản phát hành mới nhất.' }
            Write-Host "Tải $($tai.name) ($($banPh.tagName))..."
            & gh release download $banPh.tagName --repo actions/runner --pattern $tai.name --dir $thuTai
            if ($LASTEXITCODE -ne 0) { throw 'Tải runner lỗi.' }
            $zip = Join-Path $thuTai $tai.name
            if ($banPh.body -match 'BEGIN SHA win-x64 -->\s*([0-9a-fA-F]{64})\s*<!--') {
                $mong = $Matches[1].ToLowerInvariant()
                $thuc = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
                if ($mong -ne $thuc) { throw "SHA-256 của gói runner không khớp (mong $mong, thực tế $thuc)." }
                Write-Host 'SHA-256 khớp với ghi chú phát hành.'
            } else {
                Write-Warning 'Ghi chú phát hành không có SHA-256 của win-x64, không kiểm được.'
            }
            Expand-Archive -LiteralPath $zip -DestinationPath $thuRunner -Force
        }
        Grant $thuRunner $networkService 'M'
        $token = (& gh api -X POST "repos/$repoAi/actions/runners/registration-token" --jq .token)
        if ($LASTEXITCODE -ne 0 -or -not $token) { throw "Không lấy được mã đăng ký runner cho $repoAi (kiểm tra 'gh auth status')." }
        Push-Location $thuRunner
        try {
            & .\config.cmd --unattended --url "https://github.com/$repoAi" --token $token --name 'may-demo-ai' --labels may-demo `
                --work _work --runasservice --windowslogonaccount 'NT AUTHORITY\NETWORK SERVICE' --replace | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "config.cmd của runner lỗi (mã $LASTEXITCODE)." }
        } finally { Pop-Location }
        Write-Host "Đã đăng ký runner may-demo-ai cho $repoAi và chạy làm dịch vụ."
    } finally {
        if ($thuTai) { Remove-Item -LiteralPath $thuTai -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

# ---------------------------------------------------------------- 6. trạng thái
Write-Buoc 'Trạng thái'
$tt = Invoke-Native $appcmd @('list', 'site', $tenSite, '/text:state') -ChoPhepLoi
$bang = @(
    [pscustomobject]@{ Thanhphan = "Site $tenSite"; Gia = '127.0.0.1:8090'; TrangThai = $tt.DauRa.Trim() },
    [pscustomobject]@{ Thanhphan = 'Python cho mọi tài khoản'; Gia = $pythonMay; TrangThai = $(if (Test-Path -LiteralPath $pythonMay) { 'có' } else { 'chưa có' }) },
    [pscustomobject]@{ Thanhphan = 'Tệp cau-hinh\ai.env'; Gia = $tepEnv; TrangThai = $(if ((Get-Item -LiteralPath $tepEnv).Length -gt 0) { 'có nội dung' } else { 'rỗng' }) }
)
$bang += foreach ($dv in @(Get-Service -Name 'actions.runner.*' -ErrorAction SilentlyContinue)) {
    [pscustomobject]@{ Thanhphan = 'Runner'; Gia = $dv.Name; TrangThai = [string]$dv.Status }
}
$bang | Format-Table -AutoSize

Write-Host 'Việc tiếp theo (không cần quản trị):' -ForegroundColor Cyan
Write-Host '  1. pwsh scripts\trien-khai\tao-cau-hinh-ai.ps1'
Write-Host '  2. pwsh scripts\trien-khai\trien-khai-ai.ps1 -ThuMucGoi .   (hoặc gộp vào main để CD tự triển khai)'
Write-Host '  3. Repo backend: pwsh scripts\trien-khai\tao-cau-hinh-may-demo.ps1, rồi chạy lại CD của backend.'
