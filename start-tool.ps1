param(
  [switch]$Setup,
  [switch]$DownloadModels,
  [switch]$PrepareDemo,
  [switch]$Check,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$venvPython = Join-Path $root '.venv\Scripts\python.exe'

function Fail([string]$message) {
  Write-Host "Problem: $message" -ForegroundColor Red
  exit 1
}
function Run([string]$label, [scriptblock]$action) {
  Write-Host "`n$label" -ForegroundColor Cyan
  & $action
  if ($LASTEXITCODE -ne 0) { Fail "$label failed. See the message above." }
}
function Has-Command([string]$name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

Write-Host 'Drishti Tool startup' -ForegroundColor Cyan
Write-Host "Project: $root"

if (Has-Command 'py.exe') {
  $systemPython = 'py.exe'
  $pythonArgs = @('-3')
} elseif (Has-Command 'python.exe') {
  $systemPython = 'python.exe'
  $pythonArgs = @()
} else {
  Fail 'Python 3.11+ nahi mila. Python install karein aur terminal dobara kholein.'
}
if (-not (Has-Command 'node.exe') -or -not (Has-Command 'npm.cmd')) {
  Fail 'Node.js aur npm nahi mile. Node.js 18+ install karein.'
}
$pythonVersion = & $systemPython @pythonArgs -c 'import sys; print("%d.%d" % sys.version_info[:2]); sys.exit(0 if sys.version_info >= (3,11) else 1)'
if ($LASTEXITCODE -ne 0) { Fail "Python $pythonVersion mila; 3.11+ chahiye." }
$nodeVersion = (& node.exe -p 'process.versions.node.split(".")[0]').Trim()
if ([int]$nodeVersion -lt 18) { Fail "Node.js $nodeVersion mila; 18+ chahiye." }
Write-Host "Python $pythonVersion | Node $(node.exe --version)" -ForegroundColor Green

if ($Setup) {
  if (-not (Test-Path -LiteralPath $venvPython)) {
    Run 'Python environment bana rahe hain' { & $systemPython @pythonArgs -m venv .venv }
  }
  Run 'Python packages install ho rahe hain' { & $venvPython -m pip install -r requirements.txt }
  Run 'Website packages install ho rahe hain' { & npm.cmd ci }
}

if (-not (Test-Path -LiteralPath $venvPython)) { Fail 'Python setup missing. .\start-tool.ps1 -Setup chalayein.' }
if (-not (Test-Path -LiteralPath (Join-Path $root 'node_modules\vite'))) { Fail 'Website packages missing. .\start-tool.ps1 -Setup chalayein.' }
if (-not (Has-Command 'ffmpeg.exe') -or -not (Has-Command 'ffprobe.exe')) {
  Write-Host 'Note: FFmpeg/FFprobe nahi mile. DVR conversion aur kuch video checks kaam nahi karenge.' -ForegroundColor Yellow
}
if ($Setup -or $DownloadModels) {
  Run 'AI models download/check ho rahe hain' { & $venvPython scripts/download_models.py }
}
if ($PrepareDemo) {
  Run 'Demo video prepare ho raha hai' { & $venvPython scripts/prepare_demo_feeds.py }
}

Run 'Dependency check' { & $venvPython scripts/doctor.py }
if ($Check) {
  Write-Host "`nChecks complete. Start ke liye .\start-tool.ps1 chalayein." -ForegroundColor Green
  exit 0
}

$args = @('scripts/run_tool.py')
if ($NoBrowser) { $args += '--no-browser' }
Write-Host "`nStarting local services. Band karne ke liye Ctrl+C dabayein." -ForegroundColor Cyan
& $venvPython @args
exit $LASTEXITCODE
