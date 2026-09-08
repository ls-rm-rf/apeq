[CmdletBinding()]
param([string]$Distribution = '')
$ErrorActionPreference = 'Stop'
$paperDirectory = Split-Path -Parent $PSScriptRoot
$jobDirectory = Join-Path $paperDirectory 'experiments\application-v5'
if (-not (Test-Path -LiteralPath (Join-Path $jobDirectory 'freeze.json'))) {
    throw 'Prepare and freeze the design before launching.'
}
if (Test-Path -LiteralPath (Join-Path $jobDirectory 'status.json')) {
    throw 'This job has already been attempted. Inspect its status; do not overwrite or start duplicates.'
}
$launchRecord = Join-Path $jobDirectory 'launcher.json'
if (Test-Path -LiteralPath $launchRecord) {
    throw 'A launch record already exists. Inspect the monitor before attempting another launch.'
}
$distroArgs = if ($Distribution) { @('-d', $Distribution) } else { @() }
$portablePaper = $paperDirectory.Replace('\', '/')
$wslResult = & wsl.exe @distroArgs --exec wslpath -a $portablePaper
if ($LASTEXITCODE -ne 0 -or -not $wslResult) {
    throw 'Unable to resolve the WSL paper directory.'
}
$wslPaper = $wslResult.Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslPaper.StartsWith('/mnt/')) {
    throw 'Unable to resolve the WSL paper directory.'
}
# Quote the script path to support spaces in the release directory.
$prefix = if ($Distribution) { '-d "' + $Distribution + '" ' } else { '' }
$arguments = $prefix + '-- python3 -u "' + $wslPaper + '/tools/run_application_v5.py" run'
$process = Start-Process -FilePath 'wsl.exe' -ArgumentList $arguments -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $jobDirectory 'job.stdout.log') `
    -RedirectStandardError (Join-Path $jobDirectory 'job.stderr.log')
$record = [ordered]@{
    host_pid = $process.Id
    host_start_ticks = $process.StartTime.ToUniversalTime().Ticks.ToString()
    launched_utc = [DateTime]::UtcNow.ToString('o')
    distro = $(if ($Distribution) { $Distribution } else { 'WSL default' })
    command = $arguments
}
$record | ConvertTo-Json | Set-Content -LiteralPath $launchRecord -Encoding utf8
Write-Host "Started background job. Windows launcher PID: $($process.Id)"
Write-Host "Monitor: & '$PSScriptRoot\monitor_application_v5.ps1' -Watch"
