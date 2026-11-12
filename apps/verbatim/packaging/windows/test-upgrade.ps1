# CI: update an existing install the way the Update button does. Installs the newest published release (as a
# user has it), sets it up like a user (a key, the fast Whisper model, a leftover code file), then runs the newly
# built installer with the arguments from updates.installer_args and checks what a user would notice.
# Run from apps/verbatim after build.ps1 (needs GH_TOKEN for the GitHub API):  pwsh packaging/windows/test-upgrade.ps1
# The old Verbatim is running during the update (tray / started with Windows). -From picks the old release;
# -Manual runs the new installer like a double-click instead of the Update button (no reopen): the G14 case
# (2026-11-12), 0.2.1 running while 0.2.2 replaced its environment, gave "Access is denied (os error 5)".
param([string]$From = "", [switch]$Manual)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$new = Get-ChildItem (Join-Path $root "dist") -Filter "Verbatim-Setup-*.exe" | Select-Object -First 1
$app = Join-Path $env:LOCALAPPDATA "Programs\Verbatim"
$py = Join-Path $app "verbatim\.venv\Scripts\python.exe"
$lectures = Join-Path $env:RUNNER_TEMP "Lessen upgrade"
$tmp = Join-Path $env:RUNNER_TEMP "upgrade"
New-Item -ItemType Directory -Force $tmp | Out-Null

function Wait-Installed($proc, $what) {
  if ($proc.ExitCode -ne 0) { Get-Content "$tmp\setup.log" -Tail 40 -ErrorAction SilentlyContinue; throw "$what failed ($($proc.ExitCode))" }
}

# Start as a user of the old version: the install test before this one (and a first -From run) left settings written
# by the new version, which an old version can't always read (0.2.2 crashed on an empty notes list, 2026-11-12).
# Uninstalling keeps the user's settings on purpose, so clear them here; this is a throwaway CI machine.
Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force
foreach ($d in @("$env:USERPROFILE\.config\lecture-transcriber", "$env:USERPROFILE\.cache\lecture-transcriber")) {
  if ($env:CI -and (Test-Path $d)) { Remove-Item -Recurse -Force $d }
}

Write-Host "== install the published version"
$releases = gh api "repos/StanLoobuyck/trivium/releases?per_page=30" | ConvertFrom-Json
$old = $releases | Where-Object { $_.tag_name -like "verbatim-v*" -and -not $_.draft -and (-not $From -or $_.tag_name -eq $From) } | Select-Object -First 1
if (-not $old) { if ($From) { throw "release $From not found" }; Write-Host "no published release yet: nothing to update from"; exit 0 }
$oldExe = Join-Path $tmp "old.exe"
gh release download $old.tag_name --repo StanLoobuyck/trivium --pattern "Verbatim-Setup-*.exe" --output $oldExe --clobber
if ($LASTEXITCODE -ne 0) { throw "downloading $($old.tag_name) failed" }
$p = Start-Process $oldExe -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$tmp\setup.log", "/LECTURES=`"$lectures`"", "/WHISPER=fast", "/TASKS=" -Wait -PassThru
Wait-Installed $p "installing $($old.tag_name)"
$oldVersion = & $py -I -c "from lecture import updates; print(updates.current_version())"
if ("verbatim-v$oldVersion" -ne $old.tag_name) { throw "installed $oldVersion, expected $($old.tag_name)" }
Write-Host "installed $($old.tag_name)"

Write-Host "== use it like a user"
& $py -c @"
from lecture import settings, config
settings.set_key('groq', 'gsk_' + 'u' * 40)
settings.finish_welcome()
print('ok:', config.load_config().stt.local.model, settings.key_status()['groq'])
"@
if ($LASTEXITCODE -ne 0) { throw "setting up the old version failed" }
$stale = Join-Path $app "verbatim\src\lecture\removed_in_new_version.py"
Set-Content $stale "raise SystemExit('stale code')"

function Wait-Api {
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep 1
    try { return Invoke-RestMethod "http://127.0.0.1:7861/api/setup" } catch {}
  }
  Get-Content (Join-Path $env:USERPROFILE ".cache\lecture-transcriber\app.log") -Tail 40 -ErrorAction SilentlyContinue | Out-Host
  return $null
}

Write-Host "== start the old Verbatim, as the shortcut does (keeps .venv\Scripts\pythonw.exe open)"
$running = Start-Process (Join-Path $app "verbatim\.venv\Scripts\pythonw.exe") -ArgumentList "-I", "-m", "lecture.cli", "app", "--no-browser" -WorkingDirectory (Join-Path $app "verbatim") -PassThru
if (-not (Wait-Api)) { throw "the old Verbatim didn't start" }

$updArgs = & $py -c "from lecture import updates, config; print('\n'.join(updates.installer_args(config.load_config())))"
if ($LASTEXITCODE -ne 0) { throw "installer_args failed" }
if ($Manual) {
  Write-Host "== update with $($new.Name), as a double-click does"
  $updArgs = @($updArgs | Where-Object { $_ -notlike "/RELAUNCH=*" })
} else {
  Write-Host "== update with $($new.Name), as the Update button starts it"
}
# Quoted like Python's subprocess does it (updates.start uses Popen with a list).
$line = (@($updArgs) + "/LOG=$tmp\setup.log" | ForEach-Object { if ($_ -match " ") { "`"$_`"" } else { $_ } }) -join " "
Write-Host "arguments: $line"
$t = Get-Date
# Not -Wait: that also waits for the Verbatim the installer reopens, which keeps running.
$p = Start-Process $new.FullName -ArgumentList $line -PassThru
$p.WaitForExit()
Wait-Installed $p "updating"
Write-Host "updated in $([math]::Round(((Get-Date) - $t).TotalSeconds)) s"
Get-Content (Join-Path $app "install.log") -Tail 60
if (-not $running.HasExited) { throw "the old Verbatim still runs after the update" }

Write-Host "== what the user would notice"
if (Test-Path $stale) { throw "old code left behind" }
& $py -c @"
from lecture import settings, config, updates
c = config.load_config()
assert c.app.simple and c.app.welcomed, 'welcome would show again'
assert c.stt.local.model == 'small', 'Whisper choice lost: ' + c.stt.local.model
assert settings.key_status()['groq'], 'Groq key lost'
assert str(c.paths.jobs_dir).endswith('Lessen upgrade\\jobs'), c.paths.jobs_dir
print('ok: settings kept, version', updates.current_version())
"@
if ($LASTEXITCODE -ne 0) { throw "settings after the update" }

$want = $new.BaseName.Substring("Verbatim-Setup-".Length)
if ($Manual) {
  Write-Host "ok: no reopen expected (silent double-click install)"
} else {
  $s = Wait-Api
  if (-not $s) { throw "Verbatim didn't reopen after the update" }
  if ($s.version -ne $want) { throw "running $($s.version), expected $want" }
  Write-Host "ok: Verbatim reopened by itself, version $($s.version)"
}

Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process (Join-Path $app "unins000.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES" -Wait | Out-Null
