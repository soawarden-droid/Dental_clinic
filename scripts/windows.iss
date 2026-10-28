#define AppVersion "0.1.0"
[Setup]
AppId={{97D482A2-09A5-48C8-AF39-3212F094BEA1}
AppName=Faramarz Dental Clinic
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\FaramarzDental
DefaultGroupName=Faramarz Dental Clinic
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=FaramarzDental-Setup-{#AppVersion}
SetupIconFile=..\assets\clinic.ico
UninstallDisplayIcon={app}\faramarz-dental.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
[Files]
Source: "..\dist\faramarz-dental\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Faramarz Dental Clinic"; Filename: "{app}\faramarz-dental.exe"
Name: "{autodesktop}\Faramarz Dental Clinic"; Filename: "{app}\faramarz-dental.exe"
[Run]
Filename: "{app}\faramarz-dental.exe"; Description: "Open Faramarz Dental Clinic"; Flags: nowait postinstall skipifsilent
