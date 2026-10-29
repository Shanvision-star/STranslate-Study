#Requires -Version 7.0
[CmdletBinding()]
param([string]$Dotnet = 'dotnet')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$cache = Join-Path $root 'output/dependencies'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
foreach ($asset in (Get-Content (Join-Path $PSScriptRoot 'dependencies.json') -Raw | ConvertFrom-Json)) {
    $path = Join-Path $cache $asset.name
    if (!(Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path).Hash -ne $asset.sha256) {
        Invoke-WebRequest -Uri $asset.url -OutFile $path -ConnectionTimeoutSeconds 30 -OperationTimeoutSeconds 300
    }
    if ((Get-FileHash -LiteralPath $path).Hash -ne $asset.sha256) { throw "Dependency hash mismatch: $($asset.name)" }
}

# 每次使用全新目录；不删除开发目录，也不复制现有用户配置。
$destination = Join-Path $root ('output/package-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $destination) { throw 'Output directory already exists' }
New-Item -ItemType Directory -Path $destination | Out-Null
$common = @('-c','Debug','-p:Optimize=true','-p:DebugType=None','-p:DebugSymbols=false',"-p:PathMap=$root=/_/STranslate-Study",'--configfile',(Join-Path $root 'NuGet.Study.config'))
& $Dotnet publish (Join-Path $root 'src/STranslate/STranslate.csproj') @common -r win-x64 --self-contained true -o $destination
if ($LASTEXITCODE -ne 0) { throw 'App publish failed' }
$pluginNames = @('STranslate.Plugin.Translate.MicrosoftBuiltIn','STranslate.Plugin.Translate.OpenAI','STranslate.Plugin.Ocr.Tesseract')
foreach ($name in $pluginNames) {
    & $Dotnet publish (Join-Path $root "src/Plugins/$name/$name.csproj") @common --self-contained false -o (Join-Path $destination "Plugins/$name")
    if ($LASTEXITCODE -ne 0) { throw "Plugin publish failed: $name" }
}
$tessdata = Join-Path $destination 'Plugins/STranslate.Plugin.Ocr.Tesseract/tessdata'
New-Item -ItemType Directory -Path $tessdata | Out-Null
foreach ($lang in @('eng','spa','chi_sim')) { Copy-Item -LiteralPath (Join-Path $cache "$lang.traineddata") -Destination $tessdata }
Expand-Archive -LiteralPath (Join-Path $cache 'python-3.14.10-embed-amd64.zip') -DestinationPath (Join-Path $destination 'python')
Add-Content -LiteralPath (Join-Path $destination 'python/python314._pth') -Value '../StudyTools' -Encoding utf8
$studyTools = Join-Path $destination 'StudyTools'
New-Item -ItemType Directory -Path $studyTools | Out-Null
foreach ($name in @('study_bridge.py','study_practice.py','study_privacy.py','study_tasks.py')) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $studyTools }
foreach ($name in @('Setup-Study.cmd','Run-Study.cmd','Enable-StudyTask.ps1','Disable-StudyTask.ps1')) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $destination }

function Write-Config([string]$Relative, $Value) {
    $path = Join-Path $destination $Relative
    New-Item -ItemType Directory -Force -Path (Split-Path $path -Parent) | Out-Null
    $Value | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $path -Encoding utf8NoBOM
}
Write-Config 'PortableConfig/Settings/Settings.json' @{
    Language='zh-cn'; AutoStartup=$false; AutoCheckUpdate=$false; EnableExternalCall=$false;
    StudyLibraryAutoSave=$true; StudyLibraryCloudSyncEnabled=$false;
    SourceLang='english'; TargetLang='chineseSimplified'; LanguageDetector='local'; ScreenshotOcrLanguage='english';
    IsMouseSelectionTranslationEnabled=$false; IsClipboardMonitorEnabled=$false
}
$ocrId = '33333333333343338333333333333333'
$msId = '11111111111141118111111111111111'
$apiId = '22222222222242228222222222222222'
Write-Config 'PortableConfig/Settings/ServiceSettings.json' @{
    ReplaceSvcID=''; ImageTranslateSvcID=''; ImageTranslateOcrSvcID=$ocrId;
    TranSvcDatas=@(@{SvcID=$msId;Name='Microsoft 在线翻译（自行启用）';IsEnabled=$false},@{SvcID=$apiId;Name='兼容接口（待配置）';IsEnabled=$false});
    OcrSvcDatas=@(@{SvcID=$ocrId;Name='Tesseract 本地 OCR';IsEnabled=$true}); TtsSvcDatas=@();VocabularySvcDatas=@()
}
$settingsRoot = 'PortableConfig/Settings/Plugins'
Write-Config "$settingsRoot/STranslate.Plugin.Translate.MicrosoftBuiltIn/$msId.json" @{}
Write-Config "$settingsRoot/STranslate.Plugin.Translate.OpenAI/$apiId.json" @{ApiMode='chatCompletions';ApiKey='';Url='';Model='';Models=@();Stream=$true}
Write-Config "$settingsRoot/STranslate.Plugin.Ocr.Tesseract/$ocrId.json" @{}

foreach ($file in @('LICENSE','README.md','THIRD_PARTY_NOTICES.md')) { Copy-Item -LiteralPath (Join-Path $root $file) -Destination $destination }
Copy-Item -LiteralPath (Join-Path $root 'licenses') -Destination $destination -Recurse
New-Item -ItemType Directory -Path (Join-Path $destination 'docs') | Out-Null
foreach ($file in @('study-assistants.md','study-intranet.md','study-release.md')) { Copy-Item -LiteralPath (Join-Path $root "docs/$file") -Destination (Join-Path $destination 'docs') }
& (Join-Path $destination 'python/python.exe') -B -X utf8 (Join-Path $PSScriptRoot 'collect_licenses.py') --root $root --output (Join-Path $destination 'licenses/nuget')
if ($LASTEXITCODE -ne 0) { throw 'Dependency notices failed' }
& (Join-Path $destination 'python/python.exe') -B -X utf8 (Join-Path $studyTools 'study_bridge.py') doctor --app-dir $destination
if ($LASTEXITCODE -ne 0) { throw 'Bundled Python import smoke failed' }
if (Get-ChildItem -LiteralPath $destination -Filter '*.pdb' -Recurse) { throw 'PDB files must not be distributed' }
if (Get-ChildItem -LiteralPath $studyTools -Filter '*.pyc' -Recurse) { throw 'Build-machine bytecode must not be distributed' }
if (Get-ChildItem -LiteralPath (Join-Path $destination 'PortableConfig') -Filter '*.db' -Recurse) { throw 'Package must not include a personal database' }
$zip = Join-Path $root 'output/STranslate-Study-win-x64.zip'
if (Test-Path -LiteralPath $zip) { throw 'Release ZIP exists; preserve it and choose a fresh output before rebuilding' }
Compress-Archive -Path (Join-Path $destination '*') -DestinationPath $zip -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zip).Hash.ToLowerInvariant()
"$hash  STranslate-Study-win-x64.zip" | Set-Content (Join-Path $root 'output/SHA256SUMS.txt') -Encoding ascii
Write-Output "PACKAGE_DIRECTORY=$destination"
Write-Output "PACKAGE_SHA256=$hash"
