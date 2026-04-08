[Setup]
AppName=Modern Archiver
AppVersion=1.0
DefaultDirName={pf}\ModernArchiver
DefaultGroupName=ModernArchiver
OutputDir=Output
OutputBaseFilename=ModernArchiverSetup

[Files]
Source: "dist\ModernArchiver.exe"; DestDir: "{app}"

[Icons]
Name: "{group}\Modern Archiver"; Filename: "{app}\ModernArchiver.exe"
Name: "{commondesktop}\Modern Archiver"; Filename: "{app}\ModernArchiver.exe"

[Run]
Filename: "{app}\ModernArchiver.exe"; Description: "Запустить"; Flags: nowait postinstall