[CmdletBinding()]
param(
    [string]$PrimaryCodexHome = "",
    [string]$SecondaryCodexHome = "",
    [string]$StateRoot = "",
    [switch]$LoginSecondary,
    [switch]$SkipNpmLink,
    [switch]$SkipPathUpdate,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command '$Name' was not found on PATH."
    }
    return $command
}

function Resolve-HomePath {
    param([Parameter(Mandatory = $true)][string]$Value)
    $expanded = [Environment]::ExpandEnvironmentVariables($Value)
    if ($expanded -eq "~") { $expanded = $HOME }
    elseif ($expanded.StartsWith("~\") -or $expanded.StartsWith("~/")) {
        $expanded = Join-Path $HOME $expanded.Substring(2)
    }
    return [System.IO.Path]::GetFullPath($expanded)
}

function Escape-SingleQuotedPowerShell {
    param([Parameter(Mandatory = $true)][string]$Value)
    return $Value.Replace("'", "''")
}

if ($env:OS -ne "Windows_NT" -and -not $DryRun) {
    throw "This bootstrap is Windows-only."
}

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($StateRoot)) {
    $StateRoot = if ($env:LOCALAPPDATA) {
        Join-Path $env:LOCALAPPDATA "CodexQuotaWatcher"
    } else {
        Join-Path $HOME ".codex-quota-watcher"
    }
}
$StateRoot = Resolve-HomePath $StateRoot
$BinRoot = Join-Path $StateRoot "bin"
$ProfilesPath = Join-Path $StateRoot "profiles.json"

if ([string]::IsNullOrWhiteSpace($PrimaryCodexHome)) {
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        $PrimaryCodexHome = $env:CODEX_HOME
    } else {
        $PrimaryCodexHome = Join-Path $HOME ".codex"
    }
}
if ([string]::IsNullOrWhiteSpace($SecondaryCodexHome)) {
    $SecondaryCodexHome = Join-Path $StateRoot "profiles\B\codex-home"
}

$PrimaryCodexHome = Resolve-HomePath $PrimaryCodexHome
$SecondaryCodexHome = Resolve-HomePath $SecondaryCodexHome

if ($PrimaryCodexHome -eq $SecondaryCodexHome) {
    throw "Primary and secondary CODEX_HOME must be different."
}

$plan = [ordered]@{
    repoRoot = $RepoRoot
    stateRoot = $StateRoot
    primary = [ordered]@{ name = "A"; codexHome = $PrimaryCodexHome; preservesExistingHome = $true }
    secondary = [ordered]@{ name = "B"; codexHome = $SecondaryCodexHome; newIsolatedHome = $true }
    handoff = "local Git facts + lifecycle SESSION.md + compact semantic HANDOFF.md"
    credentialsCopied = $false
    nativeSessionsCopied = $false
    loginSecondary = [bool]$LoginSecondary
}

if ($DryRun) {
    $plan | ConvertTo-Json -Depth 5
    return
}

$null = Require-Command "node"
$null = Require-Command "npm"
$null = Require-Command "codex"
$null = Require-Command "git"

New-Item -ItemType Directory -Force -Path $StateRoot, $BinRoot, $SecondaryCodexHome | Out-Null

if (-not $SkipNpmLink) {
    Push-Location $RepoRoot
    try {
        & npm link
        if ($LASTEXITCODE -ne 0) { throw "npm link failed with exit code $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}

$HandoffCli = Join-Path $RepoRoot "src\handoff-cli.mjs"
foreach ($profileHome in @($PrimaryCodexHome, $SecondaryCodexHome)) {
    & node $HandoffCli install-agent --codex-home $profileHome
    if ($LASTEXITCODE -ne 0) { throw "Failed to install handoff agent into '$profileHome'." }
}

$profiles = [ordered]@{
    schema = 1
    updatedAt = [DateTimeOffset]::UtcNow.ToString("o")
    profiles = @(
        [ordered]@{ id = "A"; displayName = "Primary"; codexHome = $PrimaryCodexHome },
        [ordered]@{ id = "B"; displayName = "Secondary"; codexHome = $SecondaryCodexHome }
    )
    security = [ordered]@{
        containsCredentials = $false
        copiesAuthFiles = $false
        copiesNativeSessions = $false
    }
}
$profiles | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $ProfilesPath

$launcherTemplate = @'
[CmdletBinding()]
param(
    [string]$Workspace = ".",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CodexArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$targetHome = '__CODEX_HOME__'
$profileId = '__PROFILE_ID__'
$repoRoot = '__REPO_ROOT__'
$handoffCli = Join-Path $repoRoot 'src\handoff-cli.mjs'
$resolvedWorkspace = Resolve-Path $Workspace
$workspacePath = [System.IO.Path]::GetFullPath($resolvedWorkspace.Path)

$insideGit = $false
try {
    & git -C $workspacePath rev-parse --is-inside-work-tree *> $null
    $insideGit = ($LASTEXITCODE -eq 0)
} catch {
    $insideGit = $false
}

$sessionStarted = $false
if ($insideGit) {
    & node $handoffCli session-start --profile $profileId $workspacePath
    if ($LASTEXITCODE -ne 0) { throw "Handoff session start failed; refusing to launch profile $profileId." }
    $sessionStarted = $true
}

$previousHome = $env:CODEX_HOME
$codexExitCode = 1
$handoffEndError = $null
try {
    $env:CODEX_HOME = $targetHome
    Push-Location $workspacePath
    try {
        & codex @CodexArgs
        $codexExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    if ($sessionStarted) {
        try {
            & node $handoffCli session-end --profile $profileId --exit-code $codexExitCode $workspacePath
            if ($LASTEXITCODE -ne 0) {
                $handoffEndError = "Handoff final checkpoint failed for profile $profileId."
            }
        } catch {
            $handoffEndError = "Handoff final checkpoint failed for profile ${profileId}: $($_.Exception.Message)"
        }
    }

    if ($null -eq $previousHome) { Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue }
    else { $env:CODEX_HOME = $previousHome }
}

if ($handoffEndError) { throw $handoffEndError }
if ($codexExitCode -ne 0) { throw "Codex exited with code $codexExitCode" }
'@

$repoEscaped = Escape-SingleQuotedPowerShell $RepoRoot
$launchers = @(
    @{ Name = "codex-a.ps1"; Home = $PrimaryCodexHome; Profile = "A" },
    @{ Name = "codex-b.ps1"; Home = $SecondaryCodexHome; Profile = "B" }
)
foreach ($launcher in $launchers) {
    $homeEscaped = Escape-SingleQuotedPowerShell $launcher.Home
    $content = $launcherTemplate.Replace("__CODEX_HOME__", $homeEscaped).Replace("__PROFILE_ID__", $launcher.Profile).Replace("__REPO_ROOT__", $repoEscaped)
    Set-Content -Encoding UTF8 -Path (Join-Path $BinRoot $launcher.Name) -Value $content
}

$cmdTemplate = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0__PS1__`" %*`r`n"
Set-Content -Encoding ASCII -Path (Join-Path $BinRoot "codex-a.cmd") -Value ($cmdTemplate.Replace("__PS1__", "codex-a.ps1"))
Set-Content -Encoding ASCII -Path (Join-Path $BinRoot "codex-b.cmd") -Value ($cmdTemplate.Replace("__PS1__", "codex-b.ps1"))

if (-not $SkipPathUpdate) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($userPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($parts -notcontains $BinRoot) {
        $newUserPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $BinRoot } else { "$userPath;$BinRoot" }
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    }
    if (($env:Path -split ";") -notcontains $BinRoot) {
        $env:Path = "$env:Path;$BinRoot"
    }
}

if ($LoginSecondary) {
    Write-Host "Opening the official Codex login flow for profile B..."
    $previousHome = $env:CODEX_HOME
    try {
        $env:CODEX_HOME = $SecondaryCodexHome
        & codex --login
        if ($LASTEXITCODE -ne 0) { throw "Secondary profile login failed or was cancelled." }
    } finally {
        if ($null -eq $previousHome) { Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue }
        else { $env:CODEX_HOME = $previousHome }
    }
}

Write-Host ""
Write-Host "Dual Codex profile bootstrap complete."
Write-Host "A CODEX_HOME: $PrimaryCodexHome"
Write-Host "B CODEX_HOME: $SecondaryCodexHome"
Write-Host "Safe profile metadata: $ProfilesPath"
Write-Host "Launch A: codex-a"
Write-Host "Launch B: codex-b"
Write-Host ""
Write-Host "Each launcher records session start and writes a final Git checkpoint after Codex exits."
Write-Host "No auth file, OAuth token, cookie, or native session store was copied."
