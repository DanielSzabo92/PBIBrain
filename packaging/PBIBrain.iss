#define AppName "PBIBrain"
#define AppVersion "0.1.0"
#define AppPublisher "PBIBrain"
#define AppExeName "PBIBrain.exe"

[Setup]
AppId={{56E0B6CE-016E-434A-9CB2-F9D813720E87}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\PBIBrain
DefaultGroupName=PBIBrain
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=PBIBrain-Setup-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\branding\pbibrain.ico

[Files]
Source: "..\dist\PBIBrain\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\runtime\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\PBIBrain"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\PBIBrain"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2..."; Flags: runhidden waituntilterminated; Check: not IsWebView2Installed; AfterInstall: VerifyWebView2Installed
Filename: "{app}\{#AppExeName}"; Description: "Open PBIBrain"; Flags: nowait postinstall skipifsilent

[Code]
function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and
      (Trim(Version) <> '') and (CompareText(Trim(Version), '0.0.0.0') <> 0)) or
    (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and
      (Trim(Version) <> '') and (CompareText(Trim(Version), '0.0.0.0') <> 0));
end;

procedure VerifyWebView2Installed();
begin
  if not IsWebView2Installed then
    RaiseException('Microsoft Edge WebView2 Runtime could not be installed. Check your internet connection and run PBIBrain Setup again.');
end;
