<#
.SYNOPSIS
  Tạo C:\dsvhvn\cau-hinh\ai.env cho Dịch vụ AI trên máy demo từ tệp khoá của máy dev (không in giá trị nào).

.DESCRIPTION
  Không cần quyền quản trị. Đọc %APPDATA%\DSVHVN\ai-service.env, chỉ giữ các biến của dịch vụ (AI_*, GEMINI_*, ANTHROPIC_*),
  ghi đè nội dung tệp đích nhưng giữ nguyên quyền của tệp (cai-dat-may-demo-ai.ps1 cấp quyền đọc cho app pool "DSVHVN AI").
  Kiểm khoá nội bộ có trùng Ai:InternalKey trong appsettings.Production.json của API không (so sánh, không in).
  Chạy lại mỗi khi đổi khoá (ví dụ sau khi đổi khoá Gemini), rồi chạy lại triển khai hoặc tái chế app pool để dịch vụ đọc lại.

.PARAMETER TepNguon
  Tệp khoá của máy dev, mặc định %APPDATA%\DSVHVN\ai-service.env.
.PARAMETER TepDich
  Mặc định C:\dsvhvn\cau-hinh\ai.env.
.PARAMETER CauHinhApi
  appsettings.Production.json của API để đối chiếu khoá nội bộ, mặc định C:\dsvhvn\cau-hinh\appsettings.Production.json.
#>
[CmdletBinding()]
param(
    [string]$TepNguon = (Join-Path $env:APPDATA 'DSVHVN\ai-service.env'),
    [string]$TepDich = 'C:\dsvhvn\cau-hinh\ai.env',
    [string]$CauHinhApi = 'C:\dsvhvn\cau-hinh\appsettings.Production.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3.0
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

if (-not (Test-Path -LiteralPath $TepNguon)) { throw "Không thấy $TepNguon." }
$thuMucDich = Split-Path -Parent $TepDich
if (-not (Test-Path -LiteralPath $thuMucDich)) { throw "Chưa có $thuMucDich. Chạy cai-dat-may-demo.ps1 (repo backend) bằng quyền quản trị." }

$giaTri = [ordered]@{}
foreach ($dong in Get-Content -LiteralPath $TepNguon -Encoding UTF8) {
    $t = $dong.Trim()
    if (-not $t -or $t.StartsWith('#')) { continue }
    if ($t -notmatch '^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }
    $ten = $Matches[1].ToUpperInvariant()
    $gia = $Matches[2].Trim().Trim('"').Trim("'")
    if (-not ($ten.StartsWith('AI_') -or $ten.StartsWith('GEMINI_') -or $ten.StartsWith('ANTHROPIC_'))) { continue }
    # Máy demo tự đặt AI_ENV_FILE trong web.config; không chép biến này.
    if ($ten -eq 'AI_ENV_FILE') { continue }
    $giaTri[$ten] = $gia
}
if (-not $giaTri.Contains('AI_INTERNAL_KEY') -or -not $giaTri['AI_INTERNAL_KEY']) { throw "Tệp nguồn thiếu AI_INTERNAL_KEY." }

$nhaCungCap = if ($giaTri.Contains('AI_PROVIDER') -and $giaTri['AI_PROVIDER']) { $giaTri['AI_PROVIDER'].ToLowerInvariant() } else { 'anthropic' }
$khoaMoHinh = if ($nhaCungCap -eq 'gemini') { 'GEMINI_API_KEY' } else { 'ANTHROPIC_API_KEY' }
if (-not $giaTri.Contains($khoaMoHinh) -or -not $giaTri[$khoaMoHinh]) {
    Write-Warning "Tệp nguồn chưa có $khoaMoHinh cho nhà cung cấp '$nhaCungCap': dịch vụ chạy được nhưng các API dùng mô hình trả 503."
}

if (Test-Path -LiteralPath $CauHinhApi) {
    $api = Get-Content -LiteralPath $CauHinhApi -Raw -Encoding UTF8 | ConvertFrom-Json
    $khoaApi = if ($api.PSObject.Properties['Ai'] -and $api.Ai.PSObject.Properties['InternalKey']) { [string]$api.Ai.InternalKey } else { '' }
    if (-not $khoaApi) {
        Write-Warning 'appsettings.Production.json của API chưa có Ai:InternalKey.'
    } elseif ($khoaApi -cne $giaTri['AI_INTERNAL_KEY']) {
        Write-Warning 'AI_INTERNAL_KEY khác Ai:InternalKey của API: API sẽ bị dịch vụ AI trả 401. Chạy lại tao-cau-hinh-may-demo.ps1 (repo backend) hoặc sửa tệp nguồn.'
    } else {
        Write-Host 'Khoá nội bộ trùng với cấu hình API.'
    }
}

$dongGhi = New-Object System.Collections.Generic.List[string]
$dongGhi.Add('# Sinh bởi tao-cau-hinh-ai.ps1 từ tệp khoá của máy dev. Không đưa tệp này vào repo.')
foreach ($k in $giaTri.Keys) { $dongGhi.Add("$k=$($giaTri[$k])") }
# Ghi đè nội dung, giữ quyền của tệp đã có (không xoá rồi tạo lại).
[System.IO.File]::WriteAllText($TepDich, (($dongGhi -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))

$mo = if ($nhaCungCap -eq 'gemini') {
    if ($giaTri.Contains('GEMINI_MODEL') -and $giaTri['GEMINI_MODEL']) { $giaTri['GEMINI_MODEL'] } else { 'mặc định của dịch vụ' }
} else {
    if ($giaTri.Contains('AI_MODEL') -and $giaTri['AI_MODEL']) { $giaTri['AI_MODEL'] } else { 'mặc định của dịch vụ' }
}
Write-Host "Đã ghi $TepDich ($($giaTri.Count) biến: $(@($giaTri.Keys) -join ', '))."
Write-Host "Nhà cung cấp: $nhaCungCap, mô hình: $mo."
