# CI: install Verbatim silently with the built installer and check that it works on a clean Windows.
# Run from apps/verbatim after build.ps1:  pwsh packaging/windows/test-install.ps1

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$setup = Get-ChildItem (Join-Path $root "dist") -Filter "Verbatim-Setup-*.exe" | Select-Object -First 1
$lectures = Join-Path $env:RUNNER_TEMP "Mijn lessen"
$app = Join-Path $env:LOCALAPPDATA "Programs\Verbatim"
$py = Join-Path $app "verbatim\.venv\Scripts\python.exe"
$pyw = Join-Path $app "verbatim\.venv\Scripts\pythonw.exe"

# Like a laptop with an older Python of its own that set PYTHONPATH/PYTHONHOME globally (2026-11-12): a broken
# re.py there must not reach Verbatim's Python, neither during the install nor in the app.
$foreign = Join-Path $env:RUNNER_TEMP "foreign-python-lib"
New-Item -ItemType Directory -Force $foreign | Out-Null
Set-Content (Join-Path $foreign "re.py") "raise SystemExit('foreign PYTHONPATH reached Verbatim')"
$env:PYTHONPATH = $foreign

Write-Host "== install $($setup.Name) ($([math]::Round($setup.Length / 1MB, 1)) MB)"
$t = Get-Date
$p = Start-Process $setup.FullName -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$env:RUNNER_TEMP\setup.log", "/LECTURES=`"$lectures`"", "/WHISPER=fast", "/TASKS=" -Wait -PassThru
Write-Host "exit $($p.ExitCode) after $([math]::Round(((Get-Date) - $t).TotalSeconds)) s"
if ($p.ExitCode -ne 0) { Get-Content "$env:RUNNER_TEMP\setup.log" -Tail 40; throw "installer failed" }
foreach ($f in "uv.exe", "bin\ffmpeg.exe", "bin\ffprobe.exe", "verbatim\.venv\Scripts\pythonw.exe") {
  if (-not (Test-Path (Join-Path $app $f))) { throw "missing $f" }
}
if (-not (Test-Path (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Verbatim.lnk"))) { throw "no Start menu shortcut" }
Write-Host "venv size: $([math]::Round((Get-ChildItem (Join-Path $app 'verbatim\.venv') -Recurse | Measure-Object Length -Sum).Sum / 1MB)) MB"

Write-Host "== settings written by the installer"
& $py -I -c @"
from lecture import config, oscompat
import shutil, sys
c = config.load_config()
assert c.app.simple and c.stt.providers == ['groq', 'local'] and c.stt.local.model == 'small', c
assert c.stt.local.device == 'auto' and not c.termfix.enabled
assert str(c.paths.jobs_dir).endswith('Mijn lessen\\jobs'), c.paths.jobs_dir
assert config.load_courses() == []
oscompat.prepare_windows_app()
ff = shutil.which('ffmpeg')
assert ff and ff.lower().startswith(r'$app'.lower()), ff
print('ok:', c.paths.jobs_dir, ff)
"@
if ($LASTEXITCODE -ne 0) { throw "settings check failed" }

Write-Host "== local Whisper (small) on the processor"
& $py -I -c @"
import subprocess, tempfile, pathlib
from lecture import config, oscompat
from lecture.providers.local_whisper import LocalWhisper
oscompat.prepare_windows_app()
wav = pathlib.Path(tempfile.mkdtemp()) / 'tone.wav'
subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=5', str(wav)], check=True)
w = LocalWhisper(config.load_config())
r = w.transcribe(wav, 5.0, 'nl', '')
print('ok:', w.device, r.response['x_local'])
assert w.device == 'cpu'
"@
if ($LASTEXITCODE -ne 0) { throw "local Whisper failed" }

Write-Host "== the app (no console), as the Start menu shortcut starts it"
$proc = Start-Process $pyw -ArgumentList "-I", "-m", "lecture.cli", "app", "--no-browser", "--port", "7871" -WorkingDirectory (Join-Path $app "verbatim") -PassThru
try {
  $ok = $false
  for ($i = 0; $i -lt 60 -and -not $ok; $i++) {
    Start-Sleep 1
    try { $s = Invoke-RestMethod "http://127.0.0.1:7871/api/setup"; $ok = $true } catch {}
  }
  if (-not $ok) {
    $log = Join-Path $env:USERPROFILE ".cache\lecture-transcriber\app.log"
    if (Test-Path $log) { Get-Content $log -Tail 60 } else { Write-Host "no app.log" }
    throw "the app didn't answer"
  }
  $log = Join-Path $env:USERPROFILE ".cache\lecture-transcriber\app.log"
  if (-not (Test-Path $log)) { throw "no app.log written" }
  if (-not $s.simple -or $s.welcomed -or -not $s.worker) { throw "unexpected state: $($s | ConvertTo-Json -Depth 2 -Compress)" }
  $page = Invoke-WebRequest "http://127.0.0.1:7871/" -UseBasicParsing
  if ($page.Content -notmatch "<title>Verbatim</title>") { throw "no Verbatim page" }
  Write-Host "ok: simple mode, worker running, page served"
} finally {
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

$env:PYTHONPATH = $null
Write-Host "== install.log, and the NVIDIA build (the installer picks it when nvidia-smi exists)"
if (-not (Select-String -Path (Join-Path $app "install.log") -Pattern "< exit 0" -Quiet)) { throw "no install.log with the steps" }
$t = Get-Date
& (Join-Path $app "uv.exe") sync --frozen --no-dev --no-managed-python --no-python-downloads --python (Join-Path $app "python\python.exe") --project (Join-Path $app "verbatim") --extra local
if ($LASTEXITCODE -ne 0) { throw "the CUDA build doesn't install on Windows" }
& $py -I -c "import ctranslate2, nvidia.cublas, nvidia.cudnn; from lecture.providers.local_whisper import preload_cuda_libraries; print('ok: CUDA build installed,', preload_cuda_libraries())"
if ($LASTEXITCODE -ne 0) { throw "the CUDA build doesn't import" }
Write-Host "in $([math]::Round(((Get-Date) - $t).TotalSeconds)) s"

Write-Host "== uninstall keeps the lectures folder"
New-Item -ItemType Directory -Force $lectures | Out-Null
$un = Start-Process (Join-Path $app "unins000.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES" -Wait -PassThru
# The uninstaller restarts itself from a temporary copy, so -Wait returns early: wait for the result.
for ($i = 0; $i -lt 60 -and (Test-Path (Join-Path $app "verbatim\.venv")); $i++) { Start-Sleep 2 }
if (Test-Path (Join-Path $app "verbatim\.venv")) { throw "environment left behind" }
if (-not (Test-Path $lectures)) { throw "lectures folder removed" }
Write-Host "ok: uninstalled ($($un.ExitCode)), lectures kept"
