<#
.SYNOPSIS
    Put a "F.R.I.D.A.Y." shortcut on the Desktop.

.DESCRIPTION
    By default the shortcut launches the desktop UI (friday_ui.py) with the
    venv's pythonw.exe, so there's no console window. Use -Console for the
    plain terminal loop (friday.py), or -Uninstall to remove the shortcut.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1
    powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1 -Console
    powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1 -Uninstall
#>
param(
    [switch]$Console,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop 'F.R.I.D.A.Y..lnk'

if ($Uninstall) {
    if (Test-Path $linkPath) { Remove-Item $linkPath; "Removed $linkPath" }
    else { "No shortcut at $linkPath" }
    return
}

# Pick an interpreter: prefer the project venv, fall back to PATH.
if ($Console) {
    $venvExe = Join-Path $repo '.venv\Scripts\python.exe'
    $fallback = 'python.exe'
    $script = 'friday.py'
} else {
    $venvExe = Join-Path $repo '.venv\Scripts\pythonw.exe'
    $fallback = 'pythonw.exe'
    $script = 'friday_ui.py'
}
if (Test-Path $venvExe) {
    $target = $venvExe
} else {
    $cmd = Get-Command $fallback -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "Can't find $fallback. Create the venv first (see CLAUDE.md)." }
    $target = $cmd.Source
    Write-Warning "No .venv found - using $target. Run 'pip install -r requirements.txt' there."
}

$icon = Join-Path $repo 'assets\friday.ico'

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($linkPath)
$lnk.TargetPath = $target
$lnk.Arguments = "`"$script`""
$lnk.WorkingDirectory = $repo
$lnk.Description = 'F.R.I.D.A.Y. - local voice assistant'
if (Test-Path $icon) { $lnk.IconLocation = "$icon,0" }
$lnk.WindowStyle = 1
$lnk.Save()

"Shortcut created: $linkPath"
"  -> $target `"$script`"   (cwd: $repo)"
if ($Console) { "  mode: console loop" } else { "  mode: desktop UI" }
