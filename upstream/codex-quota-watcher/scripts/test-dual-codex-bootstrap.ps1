Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("codex-dual-profile-test-" + [Guid]::NewGuid().ToString("N"))
$MockBin = Join-Path $TempRoot "mock-bin"
$StateRoot = Join-Path $TempRoot "state"
$PrimaryHome = Join-Path $TempRoot "primary-home"
$SecondaryHome = Join-Path $TempRoot "secondary-home"
$Workspace = Join-Path $TempRoot "workspace"
$MockLog = Join-Path $TempRoot "codex.log"

New-Item -ItemType Directory -Force -Path $MockBin, $PrimaryHome, $Workspace | Out-Null

$mockCodex = @"
@echo off
>>"$MockLog" echo %CODEX_HOME%^|%*
>>"post-exit.txt" echo changed-during-codex
exit /b 0
"@
Set-Content -Encoding ASCII -Path (Join-Path $MockBin "codex.cmd") -Value $mockCodex
$env:Path = "$MockBin;$env:Path"

Push-Location $Workspace
try {
    git init -q
    git config user.name "Dual Profile Test"
    git config user.email "dual-profile@example.invalid"
    Set-Content -Encoding UTF8 -Path "sample.txt" -Value "initial"
    git add sample.txt
    git commit -qm "initial"
} finally {
    Pop-Location
}

$setup = Join-Path $RepoRoot "scripts\setup-dual-codex.ps1"
& $setup -PrimaryCodexHome $PrimaryHome -SecondaryCodexHome $SecondaryHome -StateRoot $StateRoot -SkipNpmLink -SkipPathUpdate

$profilesPath = Join-Path $StateRoot "profiles.json"
Assert-True (Test-Path $profilesPath) "profiles.json was not created"
$profiles = Get-Content -Raw $profilesPath | ConvertFrom-Json
Assert-True ($profiles.profiles.Count -eq 2) "expected two profiles"
Assert-True ($profiles.security.containsCredentials -eq $false) "profile metadata must not contain credentials"
Assert-True ($profiles.security.copiesAuthFiles -eq $false) "bootstrap must not copy auth files"
Assert-True ($profiles.security.copiesNativeSessions -eq $false) "bootstrap must not copy native sessions"

foreach ($profileHome in @($PrimaryHome, $SecondaryHome)) {
    $agents = Join-Path $profileHome "AGENTS.md"
    Assert-True (Test-Path $agents) "AGENTS.md was not installed into $profileHome"
    $text = Get-Content -Raw $agents
    Assert-True ($text.Contains("codex-quota-watcher:handoff:start")) "handoff rule missing from $profileHome"
    Assert-True ($text.Contains("SESSION.md")) "session-aware handoff rule missing from $profileHome"
}

$bin = Join-Path $StateRoot "bin"
$aCmd = Join-Path $bin "codex-a.cmd"
$bCmd = Join-Path $bin "codex-b.cmd"
Assert-True (Test-Path $aCmd) "codex-a.cmd missing"
Assert-True (Test-Path $bCmd) "codex-b.cmd missing"
Assert-True ((Get-Content -Raw $bCmd).Contains("`r`n")) "codex-b.cmd must contain real CRLF line breaks"
Assert-True (-not (Get-Content -Raw $bCmd).Contains('`r`n')) "codex-b.cmd contains literal backtick newline text"

$bLauncher = Join-Path $bin "codex-b.ps1"
& $bLauncher -Workspace $Workspace --version

$handoffDir = Join-Path $Workspace ".codex-handoff"
$factsPath = Join-Path $handoffDir "FACTS.md"
$sessionPath = Join-Path $handoffDir "session.json"
Assert-True (Test-Path $factsPath) "FACTS.md was not created for profile B"
Assert-True (Test-Path (Join-Path $handoffDir "HANDOFF.md")) "HANDOFF.md was not created for profile B"
Assert-True (Test-Path (Join-Path $handoffDir "SESSION.md")) "SESSION.md was not created for profile B"
Assert-True (Test-Path $sessionPath) "session.json was not created for profile B"

$facts = Get-Content -Raw $factsPath
Assert-True ($facts.Contains("post-exit.txt")) "final checkpoint did not capture a file created while Codex was running"

$sessionB = Get-Content -Raw $sessionPath | ConvertFrom-Json
Assert-True ($sessionB.current.profile -eq "B") "profile B session was not recorded"
Assert-True ($sessionB.current.exitCode -eq 0) "profile B exit code was not recorded"
Assert-True (-not [string]::IsNullOrWhiteSpace($sessionB.current.endedAt)) "profile B session end was not recorded"
Assert-True (-not [string]::IsNullOrWhiteSpace($sessionB.current.endFingerprint)) "profile B end fingerprint was not recorded"

$aLauncher = Join-Path $bin "codex-a.ps1"
& $aLauncher -Workspace $Workspace --help
$sessionA = Get-Content -Raw $sessionPath | ConvertFrom-Json
Assert-True ($sessionA.current.profile -eq "A") "profile A session was not recorded"
Assert-True ($sessionA.previous.profile -eq "B") "profile transition B -> A was not preserved"
Assert-True ($sessionA.previous.exitCode -eq 0) "previous profile exit status was not preserved"

$log = Get-Content -Raw $MockLog
Assert-True ($log.Contains($SecondaryHome)) "profile B launcher did not set the secondary CODEX_HOME"
Assert-True ($log.Contains($PrimaryHome)) "profile A launcher did not set the primary CODEX_HOME"
Assert-True ($log.Contains("--version")) "profile B launcher did not forward Codex arguments"
Assert-True ($log.Contains("--help")) "profile A launcher did not forward Codex arguments"

Write-Host "Windows dual-profile bootstrap integration test passed."
