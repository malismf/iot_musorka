<#
Подготовка BinSense к запуску без Docker на Windows. Выполняется один раз:

    powershell -ExecutionPolicy Bypass -File infra\windows\setup.ps1 [-HostAddress 192.168.1.23]

Кладёт PostgreSQL, Mosquitto, Caddy и окружение Python в каталог запуска
(по умолчанию %USERPROFILE%\binsense-run — путь латиницей: PostgreSQL и
Mosquitto плохо переносят кириллицу в путях), создаёт .env, базу и учётную
запись администратора брокера, собирает фронтенд. Готовое при повторном
запуске пропускается. Права администратора не нужны; нужны Python 3.12+,
Node.js, Git for Windows и 7-Zip.

HostAddress — адрес ноутбука, который получат устройства и который попадёт
в ссылки привязки. Без него берётся адрес от DHCP; для мобильного хот-спота
Windows укажите 192.168.137.1.
#>
param(
    [string]$HostAddress = "",
    [string]$RunDir = "$env:USERPROFILE\binsense-run",
    [switch]$RebuildFrontend
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
$P = Get-RunPaths $RunDir
foreach ($dir in $P.Root, $P.Logs, $P.Downloads, $P.MqttData) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

# --- .env ------------------------------------------------------------------
if (-not $HostAddress) { $HostAddress = Get-LanAddress }
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Host "== Создаю .env"
    if (-not (Test-Path -LiteralPath $GitBash)) { throw "нужен Git for Windows ($GitBash)" }
    & $GitBash "$Repo/infra/scripts/init-env.sh" localhost admin@binsense.local $HostAddress
    if ($LASTEXITCODE -ne 0) { throw "init-env.sh завершился с ошибкой" }
    $newEnv = $true
}
if ($newEnv -or $PSBoundParameters.ContainsKey("HostAddress")) {
    # Без Docker сайт отдаётся по HTTP на всех интерфейсах — как DOMAIN=:80 в DEPLOY.md
    Set-DotEnvValue $EnvFile "DOMAIN" ":80"
    Set-DotEnvValue $EnvFile "PUBLIC_URL" "http://$HostAddress"
    Set-DotEnvValue $EnvFile "MQTT_PUBLIC_HOST" $HostAddress
}
$cfg = Read-DotEnv $EnvFile
Write-Host "== Адрес для устройств и ссылок: $($cfg.MQTT_PUBLIC_HOST)"

# --- PostgreSQL ------------------------------------------------------------
if (-not (Test-Path -LiteralPath (Join-Path $P.PgBin "pg_ctl.exe"))) {
    Write-Host "== PostgreSQL"
    $zip = Join-Path $P.Downloads "postgresql.zip"
    Invoke-Download $PgUrl $zip
    & tar.exe -xf $zip -C $P.Root --exclude "pgsql/pgAdmin 4" --exclude "pgsql/doc" --exclude "pgsql/StackBuilder"
    if ($LASTEXITCODE -ne 0) { throw "не удалось распаковать PostgreSQL" }
}
if (-not (Test-Path -LiteralPath (Join-Path $P.PgData "PG_VERSION"))) {
    Write-Host "== Создаю базу"
    $pwFile = Join-Path $P.Root "pgpass.tmp"
    [IO.File]::WriteAllText($pwFile, $cfg.POSTGRES_PASSWORD)
    try {
        & (Join-Path $P.PgBin "initdb.exe") -D $P.PgData -U binsense --pwfile=$pwFile `
            -A scram-sha-256 -E UTF8 --locale=C | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "initdb завершился с ошибкой" }
    } finally {
        Remove-Item -LiteralPath $pwFile -ErrorAction SilentlyContinue
    }
}
$env:PGPASSWORD = $cfg.POSTGRES_PASSWORD
$startedHere = Start-Postgres $P
try {
    $exists = & (Join-Path $P.PgBin "psql.exe") -h 127.0.0.1 -p (Get-PgPort) -U binsense -d postgres -tAc `
        "SELECT 1 FROM pg_database WHERE datname = 'binsense'"
    if ("$exists".Trim() -ne "1") {
        & (Join-Path $P.PgBin "createdb.exe") -h 127.0.0.1 -p (Get-PgPort) -U binsense binsense
        if ($LASTEXITCODE -ne 0) { throw "не удалось создать базу binsense" }
    }
} finally {
    if ($startedHere) { Stop-Postgres $P }
}

# --- Mosquitto -------------------------------------------------------------
$mosquittoExe = Join-Path $P.Mosquitto "mosquitto.exe"
if (-not (Test-Path -LiteralPath $mosquittoExe)) {
    Write-Host "== Mosquitto"
    if (-not (Test-Path -LiteralPath $SevenZip)) { throw "нужен 7-Zip ($SevenZip)" }
    $installer = Join-Path $P.Downloads "mosquitto-install.exe"
    Invoke-Download $MosquittoUrl $installer
    # Установщик требует прав администратора, поэтому просто распаковываем его
    & $SevenZip x $installer "-o$($P.Mosquitto)" -y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "не удалось распаковать Mosquitto" }
}
$dynsec = Join-Path $P.MqttData "dynamic-security.json"
if (-not (Test-Path -LiteralPath $dynsec)) {
    Write-Host "== Учётная запись администратора брокера"
    & (Join-Path $P.Mosquitto "mosquitto_ctrl.exe") dynsec init $dynsec $cfg.MQTT_ADMIN_USER $cfg.MQTT_ADMIN_PASSWORD
    if ($LASTEXITCODE -ne 0) { throw "mosquitto_ctrl dynsec init завершился с ошибкой" }
}

# --- Caddy -----------------------------------------------------------------
if (-not (Test-Path -LiteralPath $P.Caddy)) {
    Write-Host "== Caddy"
    $zip = Join-Path $P.Downloads "caddy.zip"
    Invoke-Download $CaddyUrl $zip
    Expand-Archive -LiteralPath $zip -DestinationPath (Split-Path $P.Caddy) -Force
}

# --- Python ----------------------------------------------------------------
if (-not (Test-Path -LiteralPath $P.Python)) {
    Write-Host "== Окружение Python"
    & python -m venv (Join-Path $P.Root "venv")
    if ($LASTEXITCODE -ne 0) { throw "не удалось создать venv" }
    & $P.Python -m pip install -q --disable-pip-version-check `
        -r (Join-Path $Repo "backend\requirements.txt") pyserial
    if ($LASTEXITCODE -ne 0) { throw "не удалось установить зависимости сервера" }
}

# --- Фронтенд --------------------------------------------------------------
$dist = Join-Path $Repo "frontend\dist\index.html"
if ($RebuildFrontend -or -not (Test-Path -LiteralPath $dist)) {
    Write-Host "== Сборка фронтенда"
    Push-Location (Join-Path $Repo "frontend")
    try {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "npm ci завершился с ошибкой" }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "сборка фронтенда не удалась" }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Готово. Запуск:  powershell -ExecutionPolicy Bypass -File infra\windows\start.ps1"
Write-Host "Администратор: $($cfg.ADMIN_EMAIL), пароль — ADMIN_PASSWORD в .env"
