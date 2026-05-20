[Setup]
AppName=Motorcycle Forensic Data Visualizer
AppVersion=1.3.2
AppPublisher=Thijs Ribbers HAN University
DefaultDirName={pf}\Motorcycle Forensic Data Visualizer
DefaultGroupName=Motorcycle Forensic Data Visualizer
OutputDir=installer_output
OutputBaseFilename=MotorcycleForensicDataVisualizer-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\Motorcycle Forensic Data Visualizer.exe
MinVersion=10.0

[Files]
Source: "dist\Motorcycle Forensic Data Visualizer\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Motorcycle Forensic Data Visualizer"; Filename: "{app}\Motorcycle Forensic Data Visualizer.exe"
Name: "{group}\Uninstall Motorcycle Forensic Data Visualizer"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Motorcycle Forensic Data Visualizer"; Filename: "{app}\Motorcycle Forensic Data Visualizer.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\Motorcycle Forensic Data Visualizer.exe"; Description: "Launch Motorcycle Forensic Data Visualizer"; Flags: nowait postinstall skipifsilent