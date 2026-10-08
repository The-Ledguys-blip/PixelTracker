#define AppName "PixelTracker"
#define AppVersion "3.0.18"
#define AppPublisher "PixelTracker"
#define AppExeName "PixelTracker.exe"

[Setup]
AppId={{4DF480CF-428E-4FC6-B03D-0C71D27AC9C7}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion} Beta
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=PixelTracker_V3.0.18_Beta_Windows11_Setup
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Bureaubladsnelkoppeling maken"; GroupDescription: "Extra snelkoppelingen:"; Flags: unchecked

[Files]
Source: "..\dist\PixelTracker-Windows\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{#AppName} starten"; Flags: nowait postinstall skipifsilent
