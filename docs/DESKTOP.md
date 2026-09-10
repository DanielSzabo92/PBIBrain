# PBIBrain for Windows

Use the installer, then open **PBIBrain** from Start. No Python, Node, DLL search, or terminal setup is required.

1. Enter a project name.
2. Choose the folder containing the `.pbip` file, or paste its full path into **Project folder**.
3. Select **Scan**.

PBIBrain stores its graph, project config, and scan state inside that project folder in `.pbibrain`. Move or back up the project folder to keep the result.

The installed app includes LadybugDB and its OpenSSL runtime. It requires Windows 10/11 x64 and Microsoft Edge WebView2. The installer checks for WebView2 and installs Microsoft's Evergreen runtime automatically when it is missing. That fallback needs an internet connection; installation works offline when WebView2 is already present.

## Agent access

The desktop installer also includes `PBIBrain-Agent.exe`. Agents may use it from the project folder, for example:

```powershell
& "$env:LOCALAPPDATA\Programs\PBIBrain\PBIBrain-Agent.exe" --project . status --json
```

The GUI is the only setup path for people. The agent executable is for automation and reads the same `.pbibrain` state.

## Reproducible release build

On a Windows x64 release machine with Python 3.11 and Node.js installed, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build-desktop.ps1
```

The build downloads verified native dependencies, creates `dist\PBIBrain-Portable-x64.zip`, and creates `dist\installer\PBIBrain-Setup-x64.exe` when Inno Setup 6 is installed. It does not alter machine PATH or install runtime DLLs globally.

Before creating the ZIP, the build runs `scripts/check-frozen-desktop.py`: the packaged agent scans a temporary PBIP, exits, then reopens its native graph in a new process. Missing packaged Python modules or native libraries fail the build.

For desktop validation, enter the full project path directly when the Windows folder dialog is not reliably exposed to the tester. The folder field has the accessible label **Project folder** and ID `project-folder`. If testing the native picker, refresh the window list after opening it and inspect the returned dialog or owned window; never reuse element indexes from the main form.

## Validation — 2026-09-09

- Replaced an incomplete distribution: its GUI reported missing `ladybug._lbug_capi` and its agent executable was absent. The spec already contained the required hidden import; a completed rebuild includes it in both executables.
- Packaged GUI opened `build/gui-validation/Finance` through direct path entry, scanned successfully, and rendered 17 nodes and 23 edges. The packaged agent read the same live desktop graph with `storage: ladybug`.
- The frozen release gate scanned a temporary PBIP and reopened it in a separate process with the same 17 nodes and 23 edges; source hashes stayed unchanged.
- Desktop Python checks: 19 passed. Frontend checks: 9 passed; production build passed.
- Portable ZIP rebuilt. Installer and clean-machine acceptance remain pending; Inno Setup is unavailable here. Native folder-dialog automation was bypassed using the direct path field.

Native sources are pinned to LadybugDB `v0.20.0` and Git for Windows `v2.55.0.windows.5` (its bundled OpenSSL x64 runtime). SHA-256 checks happen before extraction. Third-party license texts ship in `_internal\licenses`.
