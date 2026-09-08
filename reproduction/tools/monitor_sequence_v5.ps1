[CmdletBinding()]
param(
    [switch]$Watch,
    [ValidateRange(5, 3600)][int]$IntervalSeconds = 30,
    [ValidateRange(0, 100)][int]$Tail = 5
)
$ErrorActionPreference = 'Stop'
$jobDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) 'experiments\sequence-v5'
function Convert-StatusUtc($Value) {
    # PowerShell 7 may deserialize ISO timestamps into DateTime automatically;
    # re-parsing their display string loses the UTC kind and adds eight hours.
    if ($Value -is [DateTime]) { return $Value.ToUniversalTime() }
    return [DateTimeOffset]::Parse([string]$Value).UtcDateTime
}
do {
    $statePath = Join-Path $jobDirectory 'status.json'
    $launchPath = Join-Path $jobDirectory 'launcher.json'
    $state = $null
    $alive = $false
    if (Test-Path -LiteralPath $launchPath) {
        $launch = Get-Content -LiteralPath $launchPath -Raw | ConvertFrom-Json
        $process = Get-Process -Id $launch.host_pid -ErrorAction SilentlyContinue
        $alive = $null -ne $process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $launch.host_start_ticks
    }
    if (Test-Path -LiteralPath $statePath) {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $terminal = $state.state -in @('COMPLETED', 'FAILED')
        $display = if (-not $alive -and -not $terminal) { 'INTERRUPTED (launcher exited)' } else { $state.state }
        $percent = [Math]::Round(100.0 * $state.completed / $state.total, 1)
        $elapsed = [DateTime]::UtcNow - (Convert-StatusUtc $state.started_utc)
        Write-Host ("[{0}] {1} | {2} | E3 sequences {3}/{4} ({5}%) | preflight {6}/4 | elapsed {7}" -f `
            (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $display, $state.stage, $state.completed, `
            $state.total, $percent, $state.preflight_completed, $elapsed.ToString('hh\:mm\:ss'))
        Write-Host ("Current: {0} | last progress UTC: {1}" -f $state.current, (Convert-StatusUtc $state.updated_utc).ToString('yyyy-MM-dd HH:mm:ss'))
        if ($Tail -gt 0 -and $state.current_log) {
            $logPath = Join-Path $jobDirectory $state.current_log
            if (Test-Path -LiteralPath $logPath) { Get-Content -LiteralPath $logPath -Tail $Tail }
        }
        if ($state.state -eq 'COMPLETED') {
            Write-Host 'E3 sequences collection and per-pair correctness checks are complete. Run the independent analysis next.' -ForegroundColor Green
        } elseif ($state.state -eq 'FAILED' -or -not $alive) {
            Write-Host 'Stopped before successful completion. Inspect status.json and error.txt (if present); preserve this attempt before rerunning.' -ForegroundColor Yellow
            $stderrPath = Join-Path $jobDirectory 'job.stderr.log'
            if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Tail 8 }
        }
        if ($terminal -or -not $alive) { break }
    } else {
        Write-Host ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $(if ($alive) { 'STARTING: waiting for first status file' } else { 'NOT RUNNING: no live launcher or status' }))
        if (-not $alive) { break }
    }
    if ($Watch) { Start-Sleep -Seconds $IntervalSeconds }
} while ($Watch)
# Read-only monitoring: no docker commands, no retries, no task automation.
