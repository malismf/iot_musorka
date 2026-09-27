# Общее для setup.ps1, start.ps1 и stop.ps1: версии, пути, работа с .env.

$Repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$EnvFile = Join-Path $Repo ".env"

$PgUrl = "https://get.enterprisedb.com/postgresql/postgresql-16.4-1-windows-x64-binaries.zip"
$MosquittoUrl = "https://mosquitto.org/files/binary/win64/mosquitto-2.1.2-install-windows-x64.exe"
$CaddyUrl = "https://github.com/caddyserver/caddy/releases/download/v2.11.4/caddy_2.11.4_windows_amd64.zip"
$SevenZip = "C:\Program Files\7-Zip\7z.exe"
$GitBash = "C:\Program Files\Git\bin\bash.exe"

function Get-RunPaths([string]$RunDir) {
    [ordered]@{
        Root      = $RunDir
        Logs      = Join-Path $RunDir "logs"
        Downloads = Join-Path $RunDir "downloads"
        PgBin     = Join-Path $RunDir "pgsql\bin"
        PgData    = Join-Path $RunDir "pgdata"
        Mosquitto = Join-Path $RunDir "mosquitto"
        MqttData  = Join-Path $RunDir "mosquitto-data"
        Caddy     = Join-Path $RunDir "caddy\caddy.exe"
        Python    = Join-Path $RunDir "venv\Scripts\python.exe"
        Pids      = Join-Path $RunDir "pids.json"
    }
}

function Read-DotEnv([string]$Path) {
    $map = [ordered]@{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $map[$Matches[1]] = $Matches[2] }
    }
    return $map
}

function Set-DotEnvValue([string]$Path, [string]$Key, [string]$Value) {
    $text = [IO.File]::ReadAllText($Path)
    $pattern = "(?m)^" + [regex]::Escape($Key) + "=.*$"
    if ([regex]::IsMatch($text, $pattern)) {
        $text = [regex]::Replace($text, $pattern, { param($m) "$Key=$Value" })
    } else {
        $text += "$Key=$Value`n"
    }
    [IO.File]::WriteAllText($Path, $text, (New-Object Text.UTF8Encoding $false))
}

# Адрес ноутбука в локальной сети: сначала адрес от DHCP (роутер), иначе любой,
# кроме loopback и 169.254.* (адаптер без сети).
function Get-LanAddress {
    $all = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" }
    $dhcp = $all | Where-Object { $_.PrefixOrigin -eq "Dhcp" } | Select-Object -First 1
    if ($dhcp) { return $dhcp.IPAddress }
    return ($all | Select-Object -First 1).IPAddress
}

# 5432 часто занят уже установленной службой PostgreSQL — тогда PG_PORT в .env
function Get-PgPort {
    if (Test-Path -LiteralPath $EnvFile) {
        $value = (Read-DotEnv $EnvFile).PG_PORT
        if ($value) { return [int]$value }
    }
    return 5432
}

function ConvertTo-ArgumentList([string[]]$Arguments) {
    $Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
}

# Запуск PostgreSQL. Вывод pg_ctl start нельзя читать конвейером: postgres
# наследует дескрипторы, и PowerShell ждёт конца вывода вечно. Поэтому pg_ctl
# работает в своём скрытом окне, а ждём только его самого.
function Start-Postgres($P) {
    & (Join-Path $P.PgBin "pg_ctl.exe") status -D $P.PgData | Out-Null
    if ($LASTEXITCODE -eq 0) { return $false }
    $arguments = ConvertTo-ArgumentList @("start", "-w", "-D", $P.PgData,
        "-l", (Join-Path $P.Logs "postgres.log"), "-o", "-h 127.0.0.1 -p $(Get-PgPort)")
    $proc = Start-Process -FilePath (Join-Path $P.PgBin "pg_ctl.exe") -ArgumentList $arguments `
        -WindowStyle Hidden -PassThru
    $null = $proc.Handle  # без этого ExitCode после выхода бывает пустым
    $proc.WaitForExit()
    if ($proc.ExitCode -ne 0) { throw "PostgreSQL не запустился, см. logs\postgres.log" }
    return $true
}

function Stop-Postgres($P) {
    & (Join-Path $P.PgBin "pg_ctl.exe") stop -w -D $P.PgData -m fast | Out-Null
}

function Invoke-Download([string]$Url, [string]$Target) {
    if (Test-Path -LiteralPath $Target) { return }
    Write-Host "  скачиваю $Url"
    & curl.exe -fsSL --retry 3 -o $Target $Url
    if ($LASTEXITCODE -ne 0) { throw "не удалось скачать $Url" }
}
