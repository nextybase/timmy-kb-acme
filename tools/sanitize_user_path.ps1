param(
    [switch]$WhatIf,
    [switch]$Deduplicate
)

function Broadcast-EnvChange {
    $sig = '[DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, int Msg, IntPtr wParam, string lParam, int fuFlags, int uTimeout, out IntPtr lpdwResult);'
    $User32 = Add-Type -MemberDefinition $sig -Name 'Win32SendMessageTimeout' -Namespace Win32Functions -PassThru
    $HWND_BROADCAST = [intptr]0xffff
    $WM_SETTINGCHANGE = 0x1A
    $result = [intptr]::Zero
    $User32::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE, [IntPtr]::Zero, 'Environment', 2, 5000, [ref]$result) | Out-Null
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $env:USERPROFILE ("Desktop\\path-backup-$timestamp")
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

$userPath = [Environment]::GetEnvironmentVariable('Path',[EnvironmentVariableTarget]::User)
Set-Content -Path (Join-Path $backupDir 'user_path_before.txt') -Value $userPath

$cleanSegments = $userPath -split ';' |
    ForEach-Object { $_.Trim() -replace '"','' } |
    Where-Object { $_ -and ($_ -notmatch 'Unknown command:') -and ($_ -notmatch 'npm help') }

if ($Deduplicate) {
    # Deduplicate case-insensitively, treating trailing slashes/backslashes as equivalent
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $deduped = New-Object System.Collections.Generic.List[string]
    foreach ($seg in $cleanSegments) {
        $key = $seg -replace "[\\/]+$",""  # drop trailing separators for comparison
        if (-not [string]::IsNullOrWhiteSpace($key)) {
            if ($seen.Add($key)) { $deduped.Add($seg) }
        }
    }
    $cleanSegments = $deduped
}

$newUserPath = ($cleanSegments -join ';').Trim(';')
Set-Content -Path (Join-Path $backupDir 'user_path_after_preview.txt') -Value $newUserPath

if ($WhatIf) {
    Write-Host "Preview only. No changes applied."
    Write-Host "Backup + preview saved to: $backupDir"
    return
}

[Environment]::SetEnvironmentVariable('Path', $newUserPath, [EnvironmentVariableTarget]::User)
Set-Content -Path (Join-Path $backupDir 'user_path_after_applied.txt') -Value $newUserPath
Broadcast-EnvChange
Write-Host "Updated User PATH. Backup saved to: $backupDir"
