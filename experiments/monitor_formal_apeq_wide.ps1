param(
    [ValidateRange(5, 3600)]
    [int]$RefreshSeconds = 30
)

$TaskRoot = Split-Path -Parent $PSScriptRoot
$RawCsv = Join-Path $TaskRoot 'formal-apeq-wide-8251.csv'
$NormalizedCsv = Join-Path $TaskRoot 'formal-apeq-wide-normalized-8251.csv'
$LogFile = Join-Path $TaskRoot 'formal-apeq-wide-8251.log'
$ErrorLogFile = Join-Path $TaskRoot 'formal-apeq-wide-8251.err.log'
$ExitFile = Join-Path $TaskRoot 'formal-apeq-wide-8251.exit'
$PidFile = Join-Path $TaskRoot '.formal-apeq-wide-8251.pid'
$ExpectedExecutions = 560
$ExpectedRows = 1120

function Get-DataRowCount([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return 0
    }
    $lineCount = (Get-Content -LiteralPath $Path | Measure-Object -Line).Lines
    return [Math]::Max(0, $lineCount - 1)
}

while ($true) {
    $rows = Get-DataRowCount $RawCsv
    $executions = [Math]::Floor($rows / 2)
    $percent = [Math]::Min(100, 100.0 * $executions / $ExpectedExecutions)

    $elapsedText = 'waiting for log'
    $etaText = 'calculating'
    if (Test-Path -LiteralPath $LogFile) {
        $elapsed = (Get-Date) - (Get-Item -LiteralPath $LogFile).CreationTime
        $elapsedText = '{0:hh\:mm\:ss}' -f $elapsed
        if ($executions -gt 0) {
            $etaSeconds = $elapsed.TotalSeconds *
                ($ExpectedExecutions - $executions) / $executions
            $eta = [TimeSpan]::FromSeconds([Math]::Max(0, $etaSeconds))
            $etaText = '{0:hh\:mm\:ss}' -f $eta
        }
    }

    $processText = 'PID file not found yet'
    if (Test-Path -LiteralPath $PidFile) {
        $windowsPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
        if ($windowsPid -match '^\d+$') {
            $processResult = Get-Process -Id ([int]$windowsPid) -ErrorAction SilentlyContinue
            if ($processResult) {
                $processText = 'Windows PID {0}, CPU {1:N1}s, running' -f $processResult.Id, $processResult.CPU
            } else {
                $processText = "Windows PID $windowsPid exited or finalizing"
            }
        }
    }

    Clear-Host
    Write-Host 'APEQ-only 120/126-bit formal LAN+WAN monitor'
    Write-Host ('Time: {0}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
    Write-Host ('Progress: {0}/{1} executions, {2}/{3} rows, {4:N2}%' -f $executions, $ExpectedExecutions, $rows, $ExpectedRows, $percent)
    Write-Host ('Elapsed: {0}    ETA: {1}' -f $elapsedText, $etaText)
    Write-Host ('Background: {0}' -f $processText)
    Write-Host ''
    Write-Host 'Latest log:'
    if (Test-Path -LiteralPath $LogFile) {
        Get-Content -LiteralPath $LogFile -Tail 10
    } else {
        Write-Host 'Log file not created yet.'
    }
    if ((Test-Path -LiteralPath $ErrorLogFile) -and
        (Get-Item -LiteralPath $ErrorLogFile).Length -gt 0) {
        Write-Host ''
        Write-Host 'Latest stderr:'
        Get-Content -LiteralPath $ErrorLogFile -Tail 5
    }

    if (Test-Path -LiteralPath $ExitFile) {
        Write-Host ''
        Write-Host 'Background run finished:'
        Get-Content -LiteralPath $ExitFile
        if (Test-Path -LiteralPath $NormalizedCsv) {
            $normalizedRows = Get-DataRowCount $NormalizedCsv
            Write-Host ("Normalized CSV: $normalizedRows rows")
        }
        break
    }

    Start-Sleep -Seconds $RefreshSeconds
}
