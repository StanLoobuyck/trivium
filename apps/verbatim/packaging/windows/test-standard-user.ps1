# CI: install as an ordinary Windows user (no administrator), as people really do. GitHub's runner is an admin,
# and Windows trusts junctions an admin makes; for an ordinary user uv-managed Python failed with os error 448
# (2026-11-12, two real laptops) while every admin test passed.
# Run from apps/verbatim after build.ps1:  pwsh packaging/windows/test-standard-user.ps1

param([string]$Installer = "")
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$setup = if ($Installer) { $Installer } else { (Get-ChildItem (Join-Path $root "dist") -Filter "Verbatim-Setup-*.exe" | Select-Object -First 1).FullName }

$name = "verbatimuser"
$password = "Vb-" + [guid]::NewGuid().ToString("N").Substring(0, 16) + "!"
net user $name $password /add /y | Out-Null
if ($LASTEXITCODE -ne 0) { throw "could not create the test user" }
$cred = New-Object System.Management.Automation.PSCredential($name, (ConvertTo-SecureString $password -AsPlainText -Force))
$admins = net localgroup Administrators
if ($admins -match "^$name$") { throw "test user is an administrator" }

# A folder the test user can read: the installer and a log from the user's side.
$share = "C:\verbatim-test"
New-Item -ItemType Directory -Force $share | Out-Null
Copy-Item $setup (Join-Path $share "setup.exe")
icacls $share /grant "${name}:(OI)(CI)M" | Out-Null

Write-Host "== install as the ordinary user '$name'"
$t = Get-Date
$p = Start-Process (Join-Path $share "setup.exe") -Credential $cred -LoadUserProfile -WorkingDirectory $share -PassThru `
  -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/WHISPER=fast", "/TASKS=", "/LOG=$share\setup.log"
$p.WaitForExit()
Write-Host "exit $($p.ExitCode) after $([math]::Round(((Get-Date) - $t).TotalSeconds)) s"

$app = "C:\Users\$name\AppData\Local\Programs\Verbatim"
$log = Join-Path $app "install.log"
if (Test-Path $log) { Get-Content $log -Tail 25 } else { Write-Host "no install.log"; Get-Content "$share\setup.log" -Tail 30 -ErrorAction SilentlyContinue }
if ($p.ExitCode -ne 0) { throw "installer failed for an ordinary user" }
foreach ($f in "python\python.exe", "verbatim\.venv\Scripts\pythonw.exe") {
  if (-not (Test-Path (Join-Path $app $f))) { throw "missing $f for an ordinary user" }
}
if (Test-Path "C:\Users\$name\AppData\Roaming\uv\python") { throw "uv installed its own Python after all" }
Write-Host "ok: installed for an ordinary user, with the bundled Python"

net user $name /delete | Out-Null
