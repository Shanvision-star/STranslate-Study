[CmdletBinding(SupportsShouldProcess)]
param([string]$AppDir = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $AppDir).Path
if ($PSCmdlet.ShouldProcess($root, 'Remove this application scheduled task')) {
    & (Join-Path $root 'python/python.exe') -X utf8 (Join-Path $root 'StudyTools/study_bridge.py') uninstall-task --app-dir $root --confirm
    if ($LASTEXITCODE -ne 0) { throw 'Task removal did not complete' }
}
