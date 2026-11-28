param(
  [string]$PythonVersion,
  [switch]$Recreate
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$venvPath = Join-Path $root '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'

function Fail([string]$message) {
  Write-Host "Problem: $message" -ForegroundColor Red
  exit 1
}

function Probe-Python([string]$exe, [string[]]$prefix) {
  try {
    $result = & $exe @prefix -c 'import sys; print(sys.version_info.major, sys.version_info.minor)' 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $numbers = [string]($result | Select-Object -Last 1)
    if ($numbers -notmatch '^3 (\d+)$') { return $null }
    $minor = [int]$Matches[1]
    if ($minor -lt 11) { return $null }
    return [pscustomobject]@{ Exe = $exe; Prefix = $prefix; Version = "3.$minor" }
  } catch {
    return $null
  }
}

function Pick-Python {
  if ($PythonVersion -and $PythonVersion -notmatch '^3\.(1[1-9]|[2-9]\d)$') {
    Fail 'PythonVersion aise dein: -PythonVersion 3.14'
  }
  $versions = if ($PythonVersion) { @($PythonVersion) } else { @('3.13', '3.12', '3.11', '3.14') }

  # uv and the Windows py launcher can locate installed versions that are not on PATH.
  if (Get-Command uv.exe -ErrorAction SilentlyContinue) {
    foreach ($version in $versions) {
      try {
        $found = & uv.exe python find $version --no-python-downloads 2>$null
        if ($LASTEXITCODE -eq 0 -and $found) {
          $candidate = Probe-Python ([string]($found | Select-Object -Last 1)).Trim() @()
          if ($candidate -and $candidate.Version -eq $version) { return $candidate }
        }
      } catch { }
    }
  }
  if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    foreach ($version in $versions) {
      $candidate = Probe-Python 'py.exe' @("-$version")
      if ($candidate -and $candidate.Version -eq $version) { return $candidate }
    }
  }
  foreach ($name in @('python.exe', 'python3.exe', 'python')) {
    foreach ($command in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
      $candidate = Probe-Python $command.Source @()
      if ($candidate -and (!$PythonVersion -or $candidate.Version -eq $PythonVersion)) { return $candidate }
    }
  }
  return $null
}

Write-Host 'Drishti Python setup' -ForegroundColor Cyan

if ($Recreate -and (Test-Path -LiteralPath $venvPath)) {
  $resolved = [IO.Path]::GetFullPath($venvPath)
  if ($resolved -ne [IO.Path]::GetFullPath((Join-Path $root '.venv'))) { Fail 'Environment path verify nahi hua.' }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

if (Test-Path -LiteralPath $venvPython) {
  $existing = Probe-Python $venvPython @()
  if (-not $existing) { Fail 'Existing .venv Python nahi chal raha. .\setup-venv.ps1 -Recreate chalayein.' }
  if ($PythonVersion -and $existing.Version -ne $PythonVersion) {
    Fail "Existing .venv Python $($existing.Version) hai. Version badalne ke liye -Recreate -PythonVersion $PythonVersion chalayein."
  }
  Write-Host "Existing .venv: Python $($existing.Version)" -ForegroundColor Green
} else {
  $selected = Pick-Python
  if (-not $selected) { Fail 'Python 3.11+ nahi mila. Installed Python check karein; zarurat ho to -PythonVersion 3.14 dein.' }
  Write-Host "Python $($selected.Version) mila: $($selected.Exe)" -ForegroundColor Green
  & $selected.Exe @($selected.Prefix) -m venv $venvPath
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) { Fail '.venv banana fail hua.' }
}

Write-Host 'Python packages install ho rahe hain...' -ForegroundColor Cyan
& $venvPython -m pip install -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Fail 'Python package installation fail hui. Upar ka error dekhein.' }
Write-Host 'Python setup complete.' -ForegroundColor Green
