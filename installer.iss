#define MyAppName "Saber Accounting"
#define MyAppVersion "2.9.23"
#define MyAppPublisher "Saber for Audit"

[Setup]
AppId={{4C848D44-EF69-47C0-86F1-5A5AA3C34E8D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\Saber Accounting
DefaultGroupName=Saber Accounting
DisableProgramGroupPage=yes
OutputDir=installer-output
OutputBaseFilename=SaberAccountingSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\SaberAccounting.exe
UninstallDisplayName={#MyAppName} {#MyAppVersion}
; Close a running copy before upgrading. Company data lives in the user's
; SaberAccounting folder and is never touched by install, upgrade or uninstall.
CloseApplications=yes
RestartApplications=no

[Tasks]
; Off by default: backups are made from Backup & Restore when the user asks. Tick it to start a daily background backup of every company and year with Windows.
Name: "autobackup"; Description: "Start automatic daily backups with Windows (all companies and years)"; Flags: unchecked

[Files]
; The application is built with PyInstaller --onedir, so the program lives in
; dist\SaberAccounting\ (SaberAccounting.exe plus its _internal support files).
; Package the whole folder; SaberAccounting.exe lands at {app}\SaberAccounting.exe.
Source: "dist\SaberAccounting\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\SaberAccountingBackup.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "Assets\Saber_for_Audit_logo.png"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "Assets\fonts\Amiri-OFL.txt"; DestDir: "{app}\assets\fonts"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Saber Accounting"; Filename: "{app}\SaberAccounting.exe"
Name: "{autodesktop}\Saber Accounting"; Filename: "{app}\SaberAccounting.exe"
Name: "{commonstartup}\Saber Accounting Backups"; Filename: "{app}\SaberAccountingBackup.exe"; WorkingDir: "{app}"; Tasks: autobackup; Check: FileExists(ExpandConstant('{app}\SaberAccountingBackup.exe'))

[Run]
Filename: "{app}\SaberAccounting.exe"; Description: "Open Saber Accounting"; Flags: nowait postinstall skipifsilent
