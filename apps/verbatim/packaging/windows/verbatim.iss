; Verbatim for Windows — Inno Setup script. Built by packaging/windows/build.ps1 (CI: job verbatim-installer).
;
; Small installer: uv, Python 3.12, ffmpeg and Verbatim's source. At the end uv downloads the libraries once
; (a few hundred MB). Two questions: where the lectures go, and which local Whisper model is the backup.
; Per user, no administrator rights (Program Files would need them).
;
; Silent install (CI test): Verbatim-Setup.exe /VERYSILENT /LECTURES="C:\path" /WHISPER=fast

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef StageDir
  #define StageDir "stage"
#endif

[Setup]
AppId={{6B1C3E52-9A0B-4D4E-9F3A-5B7D2E8C1A40}
AppName=Verbatim
AppVersion={#AppVersion}
AppPublisher=Trivium
AppPublisherURL=https://stanloobuyck.github.io/trivium/
DefaultDirName={localappdata}\Programs\Verbatim
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=Verbatim-Setup-{#AppVersion}
SetupIconFile={#StageDir}\verbatim.ico
UninstallDisplayIcon={app}\verbatim.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
nl.LecturesTitle=Waar bewaar je je lessen?
nl.LecturesDesc=Transcripts, ondertitels en notities komen in deze map.
nl.LecturesPrompt=Kies een map (je kan er gewoon op klikken in Verkenner):
nl.WhisperTitle=Omzetten op deze laptop
nl.WhisperDesc=Verbatim gebruikt Groq (gratis, snel). Lukt dat niet, bv. zonder internet, dan zet je laptop de les zelf om.
nl.WhisperPrompt=Welk model voor op je laptop? Het wordt pas gedownload als het echt nodig is.
nl.WhisperAccurate=Nauwkeurig (aanbevolen): 1,6 GB, ongeveer 30 tot 50 minuten voor een les van 2 uur
nl.WhisperFast=Snel: 0,5 GB, ongeveer twee keer sneller, maar meer fouten
nl.Downloading=Python en de onderdelen van Verbatim downloaden (eenmalig, enkele minuten)…
nl.Configuring=Verbatim instellen…
nl.StartWithWindows=Start Verbatim met Windows (in het systeemvak, rechtsonder)
nl.OpenNow=Verbatim nu openen
nl.Failed=Verbatim kon niet volledig geïnstalleerd worden. Kijk of je internet hebt en probeer opnieuw. Lukt het niet, stuur dan dit bestand door:%n%n%1
en.LecturesTitle=Where should your lectures go?
en.LecturesDesc=Transcripts, subtitles and notes are saved in this folder.
en.LecturesPrompt=Choose a folder (you can open it in Explorer any time):
en.WhisperTitle=Transcribing on this laptop
en.WhisperDesc=Verbatim uses Groq (free, fast). When that can't, e.g. without internet, your laptop transcribes the lecture itself.
en.WhisperPrompt=Which model for your laptop? It's only downloaded when it's really needed.
en.WhisperAccurate=Accurate (recommended): 1.6 GB, about 30 to 50 minutes for a 2-hour lecture
en.WhisperFast=Fast: 0.5 GB, about twice as fast, but more mistakes
en.Downloading=Downloading Python and Verbatim's parts (once, a few minutes)…
en.Configuring=Setting up Verbatim…
en.StartWithWindows=Start Verbatim with Windows (in the notification area, bottom right)
en.OpenNow=Open Verbatim now
en.Failed=Verbatim couldn't be installed completely. Check your internet connection and try again. If it still fails, send this file:%n%n%1

[Tasks]
Name: "autostart"; Description: "{cm:StartWithWindows}"

[InstallDelete]
; An update replaces Verbatim's code completely (files removed from Verbatim mustn't linger); .venv stays.
Type: filesandordirs; Name: "{app}\verbatim\src"
Type: filesandordirs; Name: "{app}\verbatim\prompts"

[Files]
Source: "{#StageDir}\uv.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\verbatim.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion recursesubdirs
Source: "{#StageDir}\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs
Source: "{#StageDir}\verbatim\*"; DestDir: "{app}\verbatim"; Flags: ignoreversion recursesubdirs; Excludes: ".venv\*,__pycache__\*,*.pyc"

[Icons]
Name: "{userprograms}\Verbatim"; Filename: "{app}\verbatim\.venv\Scripts\pythonw.exe"; Parameters: "-I -m lecture.cli app"; WorkingDir: "{app}\verbatim"; IconFilename: "{app}\verbatim.ico"
Name: "{userstartup}\Verbatim"; Filename: "{app}\verbatim\.venv\Scripts\pythonw.exe"; Parameters: "-I -m lecture.cli app --no-browser"; WorkingDir: "{app}\verbatim"; IconFilename: "{app}\verbatim.ico"; Tasks: autostart

[Run]
; uv sync and setup-simple run in CurStepChanged (below): their output goes to {app}\install.log and a failure stops here.
Filename: "{app}\verbatim\.venv\Scripts\pythonw.exe"; Parameters: "-I -m lecture.cli app"; WorkingDir: "{app}\verbatim"; Description: "{cm:OpenNow}"; Flags: postinstall nowait skipifsilent
; An update from inside Verbatim (/RELAUNCH=1): open it again once the new version is in place
Filename: "{app}\verbatim\.venv\Scripts\pythonw.exe"; Parameters: "-I -m lecture.cli app"; WorkingDir: "{app}\verbatim"; Flags: nowait; Check: IsRelaunch

[UninstallDelete]
; The environment uv made (not in [Files]). Lectures, keys and settings stay: they are the user's.
Type: filesandordirs; Name: "{app}\verbatim\.venv"

[Code]
var
  LecturesPage: TInputDirWizardPage;
  WhisperPage: TInputOptionWizardPage;

function ParamOr(const Name, Default: String): String;
begin
  Result := ExpandConstant('{param:' + Name + '|' + Default + '}');
end;

procedure InitializeWizard;
begin
  LecturesPage := CreateInputDirPage(wpSelectTasks, CustomMessage('LecturesTitle'), CustomMessage('LecturesDesc'),
    CustomMessage('LecturesPrompt'), False, '');
  LecturesPage.Add('');
  LecturesPage.Values[0] := ParamOr('LECTURES', ExpandConstant('{userdocs}\Verbatim'));

  WhisperPage := CreateInputOptionPage(LecturesPage.ID, CustomMessage('WhisperTitle'), CustomMessage('WhisperDesc'),
    CustomMessage('WhisperPrompt'), True, False);
  WhisperPage.Add(CustomMessage('WhisperAccurate'));
  WhisperPage.Add(CustomMessage('WhisperFast'));
  if CompareText(ParamOr('WHISPER', 'accurate'), 'fast') = 0 then
    WhisperPage.SelectedValueIndex := 1
  else
    WhisperPage.SelectedValueIndex := 0;
end;

function IsRelaunch: Boolean;
begin
  Result := ParamOr('RELAUNCH', '0') = '1';
end;

function LecturesDir(Param: String): String;
begin
  Result := LecturesPage.Values[0];
end;

function WhisperChoice(Param: String): String;
begin
  if WhisperPage.SelectedValueIndex = 1 then
    Result := 'fast'
  else
    Result := 'accurate';
end;

{ An NVIDIA GPU (its driver brings nvidia-smi): the CUDA build of local Whisper; otherwise the light CPU one. }
function WhisperExtra(Param: String): String;
begin
  if FileExists(ExpandConstant('{sys}\nvidia-smi.exe')) then
    Result := 'local'
  else
    Result := 'whisper-cpu';
end;

procedure ExitProcess(uExitCode: Integer); external 'ExitProcess@kernel32.dll stdcall';

{ Runs a program hidden, with its output appended to install.log. True when it exits with 0. }
function RunLogged(const Exe, Params, Status: String): Boolean;
var
  Code: Integer;
  Log: String;
begin
  Log := ExpandConstant('{app}\install.log');
  WizardForm.StatusLabel.Caption := Status;
  SaveStringToFile(Log, #13#10 + '> ' + Exe + ' ' + Params + #13#10, True);
  { A Python of the user's own may have set PYTHONPATH/PYTHONHOME globally: our Python would load its library
    and crash ("SRE module mismatch", 2026-11-12). Cleared for these steps; the shortcuts use python -I. }
  Result := Exec(ExpandConstant('{cmd}'), '/S /C "set "PYTHONPATH=" & set "PYTHONHOME=" & "' + Exe + '" ' + Params
    + ' >> "' + Log + '" 2>&1"', '',
    SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
  SaveStringToFile(Log, '< exit ' + IntToStr(Code) + #13#10, True);
end;

function Sync(const Extra: String): Boolean;
begin
  { Our own Python (see build.ps1): uv makes the environment with it and downloads no Python of its own. }
  Result := RunLogged(ExpandConstant('{app}\uv.exe'), 'sync --frozen --no-dev --no-managed-python --no-python-downloads'
    + ' --python "' + ExpandConstant('{app}\python\python.exe') + '" --project "'
    + ExpandConstant('{app}\verbatim') + '" --extra ' + Extra, CustomMessage('Downloading'));
end;

procedure Fail;
begin
  SuppressibleMsgBox(FmtMessage(CustomMessage('Failed'), [ExpandConstant('{app}\install.log')]), mbCriticalError, MB_OK, IDOK);
  ExitProcess(2);
end;

{ After the files are copied: the environment (Python + libraries), then the settings. With an NVIDIA GPU the CUDA
  build first; when that fails (e.g. a download of 1.5 GB breaking off) the light CPU build still works. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  Ok: Boolean;
begin
  if CurStep <> ssPostInstall then
    exit;
  Ok := Sync(WhisperExtra(''));
  if (not Ok) and (WhisperExtra('') = 'local') then
    Ok := Sync('whisper-cpu');
  if not Ok then
    Fail;
  if not RunLogged(ExpandConstant('{app}\verbatim\.venv\Scripts\python.exe'), '-I -m lecture.cli setup-simple "'
      + LecturesDir('') + '" --whisper ' + WhisperChoice(''), CustomMessage('Configuring')) then
    Fail;
end;

