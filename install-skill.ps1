$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $repoRoot "skills\vision-power"

if ($env:CODEX_HOME) {
    $codexHome = $env:CODEX_HOME
} else {
    $codexHome = Join-Path $HOME ".codex"
}

$targetRoot = Join-Path $codexHome "skills"
$target = Join-Path $targetRoot "vision-power"

New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
Copy-Item -LiteralPath $source -Destination $targetRoot -Recurse -Force

Write-Host "Installed skill to $target"
Write-Host "Restart Codex if the skill list is already loaded."
