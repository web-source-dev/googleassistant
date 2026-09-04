; Google Assistant Windows installer
#define MyAppName "Google Assistant"
#ifndef MyAppVersion
#define MyAppVersion "34.5.07"
#endif
#ifndef MyVersionInfoVersion
#define MyVersionInfoVersion "34.5.7.0"
#endif
#define MyAppPublisher "Google Assistant"
#define MyAppExeName "GoogleAssistant.exe"

[Setup]
AppId={{8E4C2A19-7B6F-4D31-9E5A-1C8F0B4A7D22}
AppName={#MyAppName}
AppVerName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyVersionInfoVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
UninstallDisplayName={#MyAppName}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\release
OutputBaseFilename=GoogleAssistant
AllowNoIcons=yes
CloseApplications=force
RestartApplications=no
UsePreviousAppDir=yes
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "autostart"; Description: "Start Google Assistant when I sign in to Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\dist\GoogleAssistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "silent-update.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "silent-update.cmd"; DestDir: "{commonappdata}\GoogleAssistant"; Flags: ignoreversion
Source: "register-update-task.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "GoogleAssistant"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register-update-task.ps1"""; Flags: runhidden
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Google Assistant now"; Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExeName} /T"; Flags: runhidden; RunOnceId: "StopGoogleAssistant"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /F /TN ""GoogleAssistantSilentUpdate"""; Flags: runhidden; RunOnceId: "RemoveGoogleAssistantUpdate"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{commonappdata}\GoogleAssistant"
