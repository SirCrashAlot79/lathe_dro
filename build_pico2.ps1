$ErrorActionPreference = "Stop"

$gitCommand = Get-Command git.exe -ErrorAction Stop
$gitRoot = Split-Path (Split-Path $gitCommand.Source -Parent) -Parent
$runtimeBin = Join-Path $gitRoot "mingw64\bin"
$picotool = Join-Path $PSScriptRoot "build-pico2\_deps\picotool\picotool.exe"

if (-not (Test-Path (Join-Path $runtimeBin "libstdc++-6.dll"))) {
    throw "Git for Windows MinGW runtime not found at $runtimeBin"
}
if (-not (Test-Path $picotool)) {
    throw "picotool not found at $picotool; configure the Pico build first."
}

$env:PATH = "$runtimeBin;$env:PATH"
& $picotool version
if ($LASTEXITCODE -ne 0) {
    throw "picotool could not start with the Git for Windows runtime."
}

Push-Location $PSScriptRoot
try {
    & cmake --build build-pico2
    if ($LASTEXITCODE -ne 0) {
        throw "Pico firmware build failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
