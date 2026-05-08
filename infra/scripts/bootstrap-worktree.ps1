param(
  [switch]$NoPython,
  [switch]$NoDesktop,
  [switch]$CopyPrivate,
  [string]$SourceRepoRoot = "E:\OneRadar"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$ApiDir = Join-Path $RepoRoot "apps\api"
$WorkerDir = Join-Path $RepoRoot "apps\worker"
$DesktopDir = Join-Path $RepoRoot "apps\desktop"
$VenvDir = Join-Path $RepoRoot ".venv-api"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "OneRadar worktree bootstrap"
Write-Host "Repo: $RepoRoot"
Write-Host ""

if (-not $NoPython) {
  if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating Python venv: $VenvDir"
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
      & py -3.11 -m venv $VenvDir
    } else {
      & python -m venv $VenvDir
    }
  }

  Write-Host "Installing API and worker dependencies into .venv-api"
  & $PythonExe -m pip install --upgrade pip
  & $PythonExe -m pip install -e "$ApiDir[dev]" -e "$WorkerDir[dev]"
}

if (-not $NoDesktop) {
  if (-not (Test-Path (Join-Path $DesktopDir "package.json"))) {
    throw "Missing desktop package.json under $DesktopDir."
  }

  Write-Host "Installing desktop dependencies"
  Push-Location $DesktopDir
  try {
    & npm.cmd install
  }
  finally {
    Pop-Location
  }
}

if ($CopyPrivate) {
  $ResolvedSource = Resolve-Path $SourceRepoRoot
  if ($ResolvedSource.Path -eq $RepoRoot.Path) {
    Write-Host "CopyPrivate skipped because SourceRepoRoot is the current repo."
  } else {
    $SourceEnv = Join-Path $ResolvedSource ".env.production.local"
    $TargetEnv = Join-Path $RepoRoot ".env.production.local"
    if ((Test-Path $SourceEnv) -and -not (Test-Path $TargetEnv)) {
      Copy-Item -LiteralPath $SourceEnv -Destination $TargetEnv
      Write-Host "Copied .env.production.local from source repo."
    }

    $SourcePrivate = Join-Path $ResolvedSource "infra\private"
    $TargetPrivate = Join-Path $RepoRoot "infra\private"
    if ((Test-Path $SourcePrivate) -and -not (Test-Path $TargetPrivate)) {
      Copy-Item -LiteralPath $SourcePrivate -Destination $TargetPrivate -Recurse
      Write-Host "Copied infra/private from source repo."
    }
  }
}

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Run local stack: rtk pwsh -File infra/scripts/dev.ps1"
