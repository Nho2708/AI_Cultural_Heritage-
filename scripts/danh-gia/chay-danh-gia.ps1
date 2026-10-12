# Chạy đánh giá gợi ý trên backend tạm: dựng backend trên CƠ SỞ DỮ LIỆU TẠM, chạy các script đo, tắt backend, XÓA cơ sở dữ liệu tạm.
#
# Dùng:
#   pwsh -File scripts/danh-gia/chay-danh-gia.ps1                              # đo cả hai phần
#   pwsh -File scripts/danh-gia/chay-danh-gia.ps1 -Phan goi-y-ca-nhan -Out D:\tam\danh-gia
#   pwsh -File scripts/danh-gia/chay-danh-gia.ps1 -Phan khong -GiuBackend      # chỉ bật backend tạm và giữ lại (chạy tay các script, xem dữ liệu)
#   pwsh -File scripts/danh-gia/chay-danh-gia.ps1 -DonDep -Database dsvhvn_tam_danhgia_202610131200 -MaTienTrinh 1234
#
# An toàn (bắt buộc):
#   - Chuỗi kết nối, chế độ email, chế độ AI, nơi lưu tệp và cổng đều được ĐÈ bằng biến môi trường của tiến trình con, nên User Secrets
#     (trỏ vào cơ sở dữ liệu thật, SMTP thật, AI thật) không có tác dụng: email chỉ ghi log, AI giả lập, tệp lưu cục bộ.
#   - Tên cơ sở dữ liệu phải bắt đầu bằng "dsvhvn_tam_danhgia_"; script từ chối mọi tên khác và từ chối cổng của các backend khác.
#   - Mật khẩu quản trị lấy từ User Secrets (khóa Seed:AdminPassword) hoặc biến ADMIN_PASSWORD, chỉ đi vào tiến trình con bằng biến môi trường,
#     không in và không ghi ra tệp.
#   - Xong (kể cả lỗi) thì tắt backend theo mã tiến trình và xóa cơ sở dữ liệu tạm, rồi kiểm lại bằng truy vấn rằng không còn.
#
# Kết quả: báo cáo Markdown và JSON số liệu thô trong thư mục -Out (mặc định %TEMP%\dsvhvn-danhgia-<giờ>); không đưa vào git.
[CmdletBinding()]
param(
    [ValidateSet('tat-ca', 'di-san-lien-quan', 'goi-y-ca-nhan', 'khong')]
    [string] $Phan = 'tat-ca',
    [string] $Out,
    [int] $Port = 5090,
    [string] $Database,
    [string] $BackendDir,
    [switch] $GiuBackend,
    [switch] $DonDep,
    [int] $MaTienTrinh = 0,
    [string[]] $ThamSoDiSan = @(),
    [string[]] $ThamSoHocSinh = @()
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$localDb = '(localdb)\MSSQLLocalDB'
$prefix = 'dsvhvn_tam_danhgia_'
$forbiddenPorts = @(5080, 8080, 8081, 8082, 8090)
$stamp = Get-Date -Format 'yyyyMMddHHmm'

function Step([string] $text) { Write-Host "`n== $text" -ForegroundColor Cyan }

function Invoke-Sql([string] $query) {
    $out = & sqlcmd -S $localDb -d master -h -1 -W -b -Q "SET NOCOUNT ON; $query" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "sqlcmd lỗi: $out" }
    return ($out | Out-String).Trim()
}

function Remove-TempDatabase([string] $name) {
    if (-not $name.StartsWith($prefix) -or $name -notmatch '^[A-Za-z0-9_]{1,100}$') { throw "Từ chối xóa cơ sở dữ liệu '$name': tên không bắt đầu bằng $prefix." }
    Invoke-Sql "IF DB_ID(N'$name') IS NOT NULL BEGIN ALTER DATABASE [$name] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [$name]; END" | Out-Null
    $left = Invoke-Sql "SELECT COUNT(*) FROM sys.databases WHERE name LIKE N'${prefix}%'"
    Write-Host "Còn lại cơ sở dữ liệu '$prefix%': $(($left -split "`n")[-1])"
}

function Stop-Backend([int] $processId) {
    if ($processId -gt 0 -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
        & taskkill /PID $processId /T /F 2>&1 | Out-Null
        Write-Host "Đã tắt backend (mã tiến trình $processId)."
    }
}

if ($DonDep) {
    if (-not $Database) { throw 'Cần -Database khi dùng -DonDep.' }
    Stop-Backend $MaTienTrinh
    Remove-TempDatabase $Database
    return
}

# ---- Kiểm môi trường ----
Step 'Kiểm công cụ và cổng'
foreach ($tool in 'dotnet', 'sqlcmd', 'sqllocaldb') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Không thấy lệnh '$tool' trong PATH." }
}
if ($forbiddenPorts -contains $Port) { throw "Cổng $Port thuộc backend khác, chọn cổng khác." }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Cổng $Port đang bị dùng: chọn cổng khác bằng -Port." }
if (-not $Database) { $Database = "$prefix$stamp" }
if (-not $Database.StartsWith($prefix) -or $Database -notmatch '^[A-Za-z0-9_]{1,100}$') { throw "Tên cơ sở dữ liệu phải bắt đầu bằng $prefix (chỉ chữ không dấu, số, gạch dưới)." }

$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Chưa có môi trường ảo: py -3.14 -m venv .venv rồi pip install -r requirements-dev.txt (xem README)." }

if (-not $BackendDir) {
    foreach ($candidate in '..\BE_Cultural_Heritage-', '..\..\BE_Cultural_Heritage-') {
        $path = Join-Path $repo $candidate
        if (Test-Path (Join-Path $path 'src\DSVHVN.Api')) { $BackendDir = (Resolve-Path $path).Path; break }
    }
}
if (-not $BackendDir -or -not (Test-Path (Join-Path $BackendDir 'src\DSVHVN.Api'))) { throw 'Không thấy thư mục backend: truyền -BackendDir.' }
$apiProject = Join-Path $BackendDir 'src\DSVHVN.Api'

# Mật khẩu quản trị: User Secrets của backend (không in), hoặc biến ADMIN_PASSWORD.
$adminPassword = $env:ADMIN_PASSWORD
if (-not $adminPassword) {
    $csproj = Get-ChildItem $apiProject -Filter *.csproj | Select-Object -First 1
    $secretId = ([xml](Get-Content $csproj.FullName -Raw)).Project.PropertyGroup.UserSecretsId | Where-Object { $_ } | Select-Object -First 1
    $secretFile = Join-Path $env:APPDATA "Microsoft\UserSecrets\$secretId\secrets.json"
    if ($secretId -and (Test-Path $secretFile)) {
        $adminPassword = (Get-Content $secretFile -Raw -Encoding utf8 | ConvertFrom-Json).'Seed:AdminPassword'
    }
}
if (-not $adminPassword) { throw 'Không có mật khẩu quản trị: đặt Seed:AdminPassword trong User Secrets của backend hoặc biến môi trường ADMIN_PASSWORD.' }

$work = Join-Path $env:TEMP ("dsvhvn-danhgia-" + (Get-Date -Format 'yyyyMMddHHmmss'))
if (-not $Out) { $Out = Join-Path $work 'ket-qua' }
New-Item -ItemType Directory -Force $work, $Out | Out-Null
$publishDir = Join-Path $work 'backend'
$beOut = Join-Path $work 'backend.out'
$beErr = Join-Path $work 'backend.err'
$backend = $null
$exit = 0
$envNames = 'ConnectionStrings__Default', 'ASPNETCORE_ENVIRONMENT', 'ASPNETCORE_URLS', 'Database__InitMode', 'Email__Mode', 'Ai__Mode', 'Ai__BaseUrl',
    'Storage__Provider', 'Seed__AdminPassword', 'Seed__HeritageData__ProvincesFile', 'Seed__HeritageData__HeritagesFile'

try {
    Step 'Dựng backend (bản phát hành vào thư mục tạm, không đụng thư mục bin của backend)'
    & dotnet publish $apiProject -c Release -o $publishDir -nologo -v quiet
    if ($LASTEXITCODE -ne 0) { throw 'dotnet publish thất bại.' }

    Step "Chạy backend trên cơ sở dữ liệu tạm $Database (cổng $Port, email chế độ Log, AI giả lập)"
    & sqllocaldb start MSSQLLocalDB 2>&1 | Out-Null
    $env:ConnectionStrings__Default = "Server=$localDb;Database=$Database;Trusted_Connection=True;TrustServerCertificate=True"
    $env:ASPNETCORE_ENVIRONMENT = 'Development'
    $env:ASPNETCORE_URLS = "http://localhost:$Port"
    $env:Database__InitMode = 'Migrate'
    $env:Email__Mode = 'Log'
    $env:Ai__Mode = 'Simulated'
    $env:Ai__BaseUrl = ''
    $env:Storage__Provider = 'Local'
    $env:Seed__AdminPassword = $adminPassword
    $env:Seed__HeritageData__ProvincesFile = (Join-Path $BackendDir 'seed-data\provinces.json')
    $env:Seed__HeritageData__HeritagesFile = (Join-Path $BackendDir 'seed-data\seed-dot-1.json')
    $backend = Start-Process -FilePath 'dotnet' -ArgumentList "`"$(Join-Path $publishDir 'DSVHVN.Api.dll')`"" `
        -WorkingDirectory $publishDir -RedirectStandardOutput $beOut -RedirectStandardError $beErr -WindowStyle Hidden -PassThru
    foreach ($name in $envNames) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
    Write-Host "Mã tiến trình backend: $($backend.Id). Log: $beOut"
    $end = (Get-Date).AddSeconds(300)
    $ready = $false
    while ((Get-Date) -lt $end -and -not $ready) {
        if ($backend.HasExited) { throw "Backend thoát sớm, xem log: $beOut và $beErr" }
        try { $ready = (Invoke-WebRequest "http://localhost:$Port/api/v1/public/languages" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $ready) { throw 'Hết thời gian chờ backend sẵn sàng.' }
    Write-Host 'Backend sẵn sàng.'

    $env:BASE = "http://localhost:$Port"
    $env:API_LOG = $beOut
    $env:ADMIN_PASSWORD = $adminPassword
    if ($Phan -in 'tat-ca', 'di-san-lien-quan') {
        Step 'Di sản liên quan: precision@3 (hai cách xếp)'
        & $python -X utf8 (Join-Path $PSScriptRoot 'do-di-san-lien-quan.py') --out $Out @ThamSoDiSan
        if ($LASTEXITCODE -ne 0) { throw "do-di-san-lien-quan.py thất bại (mã $LASTEXITCODE)." }
    }
    if ($Phan -in 'tat-ca', 'goi-y-ca-nhan') {
        Step 'Học sinh ảo và gợi ý cá nhân hóa'
        & $python -X utf8 (Join-Path $PSScriptRoot 'hoc-sinh-ao.py') --out $Out @ThamSoHocSinh
        if ($LASTEXITCODE -ne 0) { throw "hoc-sinh-ao.py thất bại (mã $LASTEXITCODE)." }
    }
    Write-Host "`nKết quả nằm trong: $Out"
}
catch {
    Write-Host "LỖI: $($_.Exception.Message)" -ForegroundColor Red
    $exit = 1
}
finally {
    foreach ($name in $envNames + 'BASE', 'API_LOG', 'ADMIN_PASSWORD') { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
    $adminPassword = $null
    if ($GiuBackend -and $backend) {
        Write-Host "`nGiữ backend chạy (mã tiến trình $($backend.Id), cổng $Port) và cơ sở dữ liệu $Database."
        Write-Host "Dọn: pwsh -File scripts/danh-gia/chay-danh-gia.ps1 -DonDep -Database $Database -MaTienTrinh $($backend.Id)"
    }
    else {
        if ($backend) { Stop-Backend $backend.Id }
        try { Remove-TempDatabase $Database } catch { Write-Host "Không xóa được cơ sở dữ liệu tạm: $($_.Exception.Message)" -ForegroundColor Red; $exit = 1 }
    }
}
exit $exit
