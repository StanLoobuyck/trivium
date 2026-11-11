# CI: update an existing install the way the Update button does. Installs the newest published release (as a
# user has it), sets it up like a user (a key, the fast Whisper model, a leftover code file), then runs the newly
# built installer with the arguments from updates.installer_args and checks what a user would notice.
# Run from apps/verbatim after build.ps1 (needs GH_TOKEN for the GitHub API):  pwsh packaging/windows/test-upgrade.ps1

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

Write-Host "== install the published version"
$releases = gh api "repos/StanLoobuyck/trivium/releases?per_page=30" | ConvertFrom-Json
$old = $releases | Where-Object { $_.tag_name -like "verbatim-v*" -and -not $_.draft } | Select-Object -First 1
if (-not $old) { Write-Host "no published release yet: nothing to update from"; exit 0 }
$oldExe = Join-Path $tmp "old.exe"
gh release download $old.tag_name --repo StanLoobuyck/trivium --pattern "Verbatim-Setup-*.exe" --output $oldExe
$p = Start-Process $oldExe -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=$tmp\setup.log", "/LECTURES=`"$lectures`"", "/WHISPER=fast", "/TASKS=" -Wait -PassThru
Wait-Installed $p "installing $($old.tag_name)"
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

Write-Host "== update with $($new.Name), as the Update button starts it"
$updArgs = & $py -c "from lecture import updates, config; print('\n'.join(updates.installer_args(config.load_config())))"
if ($LASTEXITCODE -ne 0) { throw "installer_args failed" }
# Quoted like Python's subprocess does it (updates.start uses Popen with a list).
$line = (@($updArgs) + "/LOG=$tmp\setup.log" | ForEach-Object { if ($_ -match " ") { "`"$_`"" } else { $_ } }) -join " "
Write-Host "arguments: $line"
$t = Get-Date
# Not -Wait: that also waits for the Verbatim the installer reopens, which keeps running.
$p = Start-Process $new.FullName -ArgumentList $line -PassThru
$p.WaitForExit()
Wait-Installed $p "updating"
Write-Host "updated in $([math]::Round(((Get-Date) - $t).TotalSeconds)) s"

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
$ok = $false
for ($i = 0; $i -lt 60 -and -not $ok; $i++) {
  Start-Sleep 1
  try { $s = Invoke-RestMethod "http://127.0.0.1:7861/api/setup"; $ok = $true } catch {}
}
if (-not $ok) {
  Get-Content (Join-Path $env:USERPROFILE ".cache\lecture-transcriber\app.log") -Tail 40 -ErrorAction SilentlyContinue
  throw "Verbatim didn't reopen after the update"
}
if ($s.version -ne $want) { throw "running $($s.version), expected $want" }
Write-Host "ok: Verbatim reopened by itself, version $($s.version)"

Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process (Join-Path $app "unins000.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES" -Wait | Out-Null
