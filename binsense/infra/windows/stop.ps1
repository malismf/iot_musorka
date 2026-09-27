<#
Остановка BinSense, запущенного infra\windows\start.ps1:

    powershell -ExecutionPolicy Bypass -File infra\windows\stop.ps1
#>
param([string]$RunDir = "$env:USERPROFILE\binsense-run")
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"
$P = Get-RunPaths $RunDir

if (Test-Path -LiteralPath $P.Pids) {
    $pids = (Get-Content -LiteralPath $P.Pids -Raw | ConvertFrom-Json).PSObject.Properties
    foreach ($entry in $pids) {
        if (Get-Process -Id $entry.Value -ErrorAction SilentlyContinue) {
            # /T — вместе с дочерними: python.exe из venv запускает настоящий интерпретатор
            & taskkill.exe /PID $entry.Value /T /F | Out-Null
            Write-Host ("  {0,-10} остановлен" -f $entry.Name)
        }
    }
    Remove-Item -LiteralPath $P.Pids
}

& (Join-Path $P.PgBin "pg_ctl.exe") status -D $P.PgData | Out-Null
if ($LASTEXITCODE -eq 0) {
    Stop-Postgres $P
    Write-Host "  postgres   остановлен"
}
