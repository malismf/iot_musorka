<#
Запуск BinSense без Docker на Windows (после setup.ps1):

    powershell -ExecutionPolicy Bypass -File infra\windows\start.ps1

Наружу, на всех интерфейсах, слушают только веб (порт 80, Caddy) и брокер
(1883, Mosquitto). PostgreSQL и API — на 127.0.0.1. Логи — в logs\ каталога
запуска, остановка — stop.ps1.
#>
param(
    [string]$RunDir = "$env:USERPROFILE\binsense-run",
    [int]$HttpPort = 80
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
$P = Get-RunPaths $RunDir

if (Test-Path -LiteralPath $P.Pids) {
    $alive = (Get-Content -LiteralPath $P.Pids -Raw | ConvertFrom-Json).PSObject.Properties |
        Where-Object { Get-Process -Id $_.Value -ErrorAction SilentlyContinue }
    if ($alive) { throw "BinSense уже запущен ($($alive.Name -join ', ')). Сначала stop.ps1" }
}

# Окружение сервисов: .env плюс адреса внутри этой машины
$cfg = Read-DotEnv $EnvFile
foreach ($key in $cfg.Keys) {
    # TZ=Europe/Moscow C-библиотека Windows не понимает и сдвигает местное время
    if ($key -ne "TZ") { Set-Item -Path "env:$key" -Value $cfg[$key] }
}
$env:DATABASE_URL = "postgresql://binsense:$($cfg.POSTGRES_PASSWORD)@127.0.0.1:5432/binsense"
$env:MQTT_HOST = "127.0.0.1"
$env:MQTT_PORT = "1883"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:BINSENSE_WEB_ROOT = Join-Path $Repo "frontend\dist"
$env:BINSENSE_HTTP_PORT = "$HttpPort"

$pids = [ordered]@{}
function Start-Worker([string]$Name, [string]$Exe, [string[]]$Arguments, [string]$WorkDir) {
    $proc = Start-Process -FilePath $Exe -ArgumentList (ConvertTo-ArgumentList $Arguments) `
        -WorkingDirectory $WorkDir `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $P.Logs "$Name.out.log") `
        -RedirectStandardError (Join-Path $P.Logs "$Name.log")
    $pids[$Name] = $proc.Id
    Write-Host ("  {0,-10} PID {1}" -f $Name, $proc.Id)
}

Write-Host "== PostgreSQL (127.0.0.1:5432)"
$null = Start-Postgres $P

Write-Host "== Сервисы"
# Конфиг брокера — тот же, что в Docker, с путями этой машины
$data = $P.MqttData.Replace("\", "/")
$plugin = $P.Mosquitto.Replace("\", "/") + "/mosquitto_dynamic_security.dll"
$conf = Get-Content -LiteralPath (Join-Path $Repo "infra\mosquitto\mosquitto.conf") -Raw -Encoding UTF8
$conf = $conf.Replace("/usr/lib/mosquitto_dynamic_security.so", $plugin)
$conf = $conf.Replace("/mosquitto/data/", "$data/")
# журнал брокера — в stderr, его пишет в logs\mosquitto.log сам start.ps1
$conf = $conf.Replace("log_dest stdout", "log_dest stderr")
$confFile = Join-Path $P.Root "mosquitto.conf"
[IO.File]::WriteAllText($confFile, $conf, (New-Object Text.UTF8Encoding $false))
Start-Worker "mosquitto" (Join-Path $P.Mosquitto "mosquitto.exe") @("-c", $confFile) $P.Mosquitto

$backend = Join-Path $Repo "backend"
# aiomqtt не работает с ProactorEventLoop, который uvicorn выбирает на Windows
Start-Worker "api" $P.Python @("-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1",
    "--port", "8000", "--proxy-headers", "--loop", "asyncio:SelectorEventLoop") $backend
Start-Worker "ingestor" $P.Python @("-m", "app.ingestor") $backend
Start-Worker "bot" $P.Python @("-m", "app.bot") $backend
Start-Worker "caddy" $P.Caddy @("run", "--config", (Join-Path $PSScriptRoot "Caddyfile"),
    "--adapter", "caddyfile") $P.Root

$pids | ConvertTo-Json | Set-Content -LiteralPath $P.Pids -Encoding UTF8

Write-Host "== Жду API"
$ok = $false
for ($i = 0; $i -lt 60 -and -not $ok; $i++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$HttpPort/api/health" -TimeoutSec 2
        $ok = $health.status -eq "ok"
    } catch { }
}
if (-not $ok) { throw "API не ответил за минуту, см. logs\api.log" }

$hostAddr = $cfg.MQTT_PUBLIC_HOST
$web = if ($HttpPort -eq 80) { "http://$hostAddr" } else { "http://${hostAddr}:$HttpPort" }
Write-Host ""
Write-Host "BinSense запущен:"
Write-Host "  веб:     $web   (на этой машине — http://localhost)"
Write-Host "  брокер:  ${hostAddr}:1883"
Write-Host "  логи:    $($P.Logs)"
Write-Host "Остановка: powershell -ExecutionPolicy Bypass -File infra\windows\stop.ps1"
