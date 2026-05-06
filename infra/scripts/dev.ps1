param(
  [int]$ApiPort = 8000,
  [int]$DesktopPort = 5173,
  [switch]$NoDesktop,
  [switch]$NoWorker,
  [switch]$DryRunWorker
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$PythonExe = Join-Path $RepoRoot ".venv-api\Scripts\python.exe"
$UvicornExe = Join-Path $RepoRoot ".venv-api\Scripts\uvicorn.exe"
$DesktopDir = Join-Path $RepoRoot "apps\desktop"
$ApiDir = Join-Path $RepoRoot "apps\api"
$WorkerSrc = Join-Path $RepoRoot "apps\worker\src"
$DatabasePath = Join-Path $ApiDir "oneradar.db"
$DatabaseUrl = "sqlite+pysqlite:///$($DatabasePath.Replace('\', '/'))"
$WorkerDryRun = if ($DryRunWorker) { "true" } else { "false" }

if (-not (Test-Path $PythonExe)) {
  throw "Missing Python environment: $PythonExe. Create or install the API venv before running dev.ps1."
}

if (-not (Test-Path $UvicornExe)) {
  throw "Missing uvicorn executable: $UvicornExe. Install apps/api dependencies into .venv-api first."
}

if (-not (Test-Path (Join-Path $DesktopDir "package.json"))) {
  throw "Missing desktop package.json under $DesktopDir."
}

Write-Host "OneRadar local development"
Write-Host "API:      http://127.0.0.1:$ApiPort/api"
Write-Host "Desktop:  http://127.0.0.1:$DesktopPort"
Write-Host "Database: $DatabasePath"
Write-Host ""

$jobs = @()

$jobs += Start-Job -Name "oneradar-api" -ArgumentList $ApiDir, $UvicornExe, $DatabaseUrl, $ApiPort -ScriptBlock {
  param($ApiDir, $UvicornExe, $DatabaseUrl, $ApiPort)
  Set-Location $ApiDir
  $env:ONERADAR_DATABASE_URL = $DatabaseUrl
  $env:ONERADAR_FEED_REFRESH_ENABLED = "true"
  & $UvicornExe "app.main:app" "--reload" "--host" "127.0.0.1" "--port" "$ApiPort"
}

if (-not $NoWorker) {
  $jobs += Start-Job -Name "oneradar-worker" -ArgumentList $RepoRoot, $PythonExe, $WorkerSrc, $DatabaseUrl, $WorkerDryRun -ScriptBlock {
    param($RepoRoot, $PythonExe, $WorkerSrc, $DatabaseUrl, $WorkerDryRun)
    Set-Location $RepoRoot
    $env:PYTHONPATH = $WorkerSrc
    $env:ONERADAR_DATABASE_URL = $DatabaseUrl
    $env:ONERADAR_ENABLE_DRY_RUN = $WorkerDryRun
    & $PythonExe "-m" "one_radar_worker"
  }
}

if (-not $NoDesktop) {
  $jobs += Start-Job -Name "oneradar-desktop" -ArgumentList $DesktopDir, $ApiPort, $DesktopPort -ScriptBlock {
    param($DesktopDir, $ApiPort, $DesktopPort)
    Set-Location $DesktopDir
    $env:VITE_ONERADAR_DEFAULT_API_URL = "http://127.0.0.1:$ApiPort/api"
    & npm.cmd "run" "dev" "--" "--host" "127.0.0.1" "--port" "$DesktopPort"
  }
}

try {
  Write-Host "Started jobs: $($jobs.Name -join ', ')"
  Write-Host "Press Ctrl+C to stop all local development processes."
  Write-Host ""

  while ($true) {
    foreach ($job in $jobs) {
      Receive-Job -Job $job
    }

    $failed = $jobs | Where-Object { $_.State -in @("Failed", "Stopped", "Completed") }
    if ($failed) {
      foreach ($job in $failed) {
        Write-Warning "$($job.Name) exited with state $($job.State)."
        Receive-Job -Job $job
      }
      break
    }

    Start-Sleep -Seconds 1
  }
}
finally {
  foreach ($job in $jobs) {
    if ($job.State -eq "Running") {
      Stop-Job -Job $job
    }
    Remove-Job -Job $job -Force
  }
}
