$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$distPath = Join-Path $projectRoot 'build\sidecar'
$binaryPath = Join-Path $projectRoot 'src-tauri\binaries\bilinovel-server.exe'

Push-Location $projectRoot
try {
    python -m PyInstaller --noconfirm --clean --onefile --name bilinovel-server `
        --distpath $distPath --workpath (Join-Path $projectRoot 'build\pyinstaller') `
        --paths $projectRoot server\app.py
    New-Item -ItemType Directory -Force (Split-Path -Parent $binaryPath) | Out-Null
    Copy-Item (Join-Path $distPath 'bilinovel-server.exe') $binaryPath -Force
}
finally {
    Pop-Location
}
