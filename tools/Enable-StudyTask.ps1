[CmdletBinding(SupportsShouldProcess)]
param([string]$AppDir = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $AppDir).Path
if ($PSCmdlet.ShouldProcess($root, 'Register a current-user daily vocabulary check')) {
    & (Join-Path $root 'python/python.exe') -X utf8 (Join-Path $root 'StudyTools/study_bridge.py') install-task --app-dir $root --confirm
    if ($LASTEXITCODE -ne 0) { throw 'Task registration did not complete' }
}
