$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = "C:\Users\PC\miniconda3\python.exe"

if (-not $env:DATABASE_URL) {
    if (Test-Path ".env") {
        Get-Content ".env" | ForEach-Object {
            if ($_ -match '^\s*DATABASE_URL=(.+)$') { $env:DATABASE_URL = $matches[1].Trim().Trim('"') }
        }
    }
}
if (-not $env:DATABASE_URL) { Write-Host "Set DATABASE_URL in infigobot/.env"; exit 1 }

Write-Host "Applying schema..."
& $py "$Root\scripts\apply_sql.py" "$Root\scripts\schema.sql"
& $py "$Root\scripts\seed_infigo_kb.py"
Write-Host "Done."
