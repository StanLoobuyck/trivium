# Builds the Windows installer of Verbatim (Verbatim-Setup-<version>.exe) with Inno Setup.
# Run on Windows from apps/verbatim:  pwsh packaging/windows/build.ps1   (CI: job verbatim-installer)
#
# Stages: uv.exe (pinned), ffmpeg + ffprobe (BtbN GPL build, pinned branch, with its licence), the icon and
# Verbatim's source (no tests, no Mac server, no private files). uv downloads Python and the libraries on the
# user's laptop at the end of the install, so the installer stays small.

$ErrorActionPreference = "Stop"
$UvVersion = "0.13.7"
$FfmpegZip = "ffmpeg-n8.1-latest-win64-gpl-8.1.zip"
# Python comes with the installer: uv-managed Python links its minor version with a junction, and Windows refuses
# to traverse a junction an ordinary user made (os error 448, both test laptops on 2026-11-12).
$PythonTag = "20261026"
$PythonTgz = "cpython-3.12.16+$PythonTag-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$out = Join-Path $root "dist"
$stage = Join-Path $out "stage"
$cache = Join-Path $out "downloads"
Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $stage, $cache, (Join-Path $stage "bin"), (Join-Path $stage "verbatim") | Out-Null

function Fetch($url, $name) {
  $file = Join-Path $cache $name
  if (-not (Test-Path $file)) {
    Write-Host "download $url"
    Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
  }
  return $file
}

# uv
$uvZip = Fetch "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" "uv-$UvVersion.zip"
Expand-Archive $uvZip -DestinationPath (Join-Path $cache "uv") -Force
Copy-Item (Get-ChildItem (Join-Path $cache "uv") -Recurse -Filter uv.exe | Select-Object -First 1).FullName $stage

# Python (python-build-standalone, the build uv itself would download): unpacked into stage\python
$pyTgz = Fetch "https://github.com/astral-sh/python-build-standalone/releases/download/$PythonTag/$($PythonTgz -replace '\+', '%2B')" $PythonTgz
tar -xzf $pyTgz -C $stage
if (-not (Test-Path (Join-Path $stage "python\python.exe"))) { throw "no python\python.exe in $PythonTgz" }

# ffmpeg + ffprobe, with the licence (GPL: the source is at https://github.com/BtbN/FFmpeg-Builds)
$ffZip = Fetch "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/$FfmpegZip" $FfmpegZip
Expand-Archive $ffZip -DestinationPath (Join-Path $cache "ffmpeg") -Force
$ffDir = (Get-ChildItem (Join-Path $cache "ffmpeg") -Directory | Select-Object -First 1).FullName
Copy-Item (Join-Path $ffDir "bin\ffmpeg.exe"), (Join-Path $ffDir "bin\ffprobe.exe") (Join-Path $stage "bin")
Copy-Item (Join-Path $ffDir "LICENSE.txt") (Join-Path $stage "bin\FFMPEG-LICENSE.txt")

# Verbatim's source: what `uv sync` needs to install it, plus the defaults it reads
Copy-Item (Join-Path $PSScriptRoot "verbatim.ico") $stage
foreach ($item in "pyproject.toml", "uv.lock", "README.md", "config.yaml", "courses.yaml", "prompts", "src") {
  Copy-Item -Recurse (Join-Path $root $item) (Join-Path $stage "verbatim")
}
Get-ChildItem (Join-Path $stage "verbatim") -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

# Version from pyproject.toml
$version = (Select-String -Path (Join-Path $root "pyproject.toml") -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value

# Inno Setup: preinstalled on GitHub's Windows images; otherwise install it once (choco install innosetup)
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (choco install innosetup)" }
& $iscc "/DAppVersion=$version" "/DStageDir=$stage" "/O$out" (Join-Path $PSScriptRoot "verbatim.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
Write-Host "built $(Join-Path $out "Verbatim-Setup-$version.exe")"
