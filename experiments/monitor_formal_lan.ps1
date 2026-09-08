param(
    [ValidateRange(5, 3600)]
    [int]$RefreshSeconds = 30
)

$TaskRoot = Split-Path -Parent $PSScriptRoot
$RawCsv = Join-Path $TaskRoot 'formal-lan-76a3.csv'
$NormalizedCsv = Join-Path $TaskRoot 'formal-lan-normalized-76a3.csv'
$LogFile = Join-Path $TaskRoot 'formal-lan-76a3.log'
$ErrorLogFile = Join-Path $TaskRoot 'formal-lan-76a3.err.log'
$ExitFile = Join-Path $TaskRoot 'formal-lan-76a3.exit'
$PidFile = Join-Path $TaskRoot '.formal-lan-76a3.pid'
$ExpectedExecutions = 3360
$ExpectedRows = 6720

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

    $elapsedText = '等待日志'
    $etaText = '计算中'
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

    $processText = 'PID 文件尚未出现'
    if (Test-Path -LiteralPath $PidFile) {
        $windowsPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
        if ($windowsPid -match '^\d+$') {
            $processResult = Get-Process -Id ([int]$windowsPid) -ErrorAction SilentlyContinue
            if ($processResult) {
                $processText = 'Windows PID {0}，CPU {1:N1}s，状态运行中' -f $processResult.Id, $processResult.CPU
            } else {
                $processText = "Windows PID $windowsPid 已结束或正在收尾"
            }
        }
    }

    Clear-Host
    Write-Host 'APEQ 正式 LAN 矩阵监视器'
    Write-Host ('时间：{0}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
    Write-Host ('进度：{0}/{1} executions，{2}/{3} rows，{4:N2}%' -f $executions, $ExpectedExecutions, $rows, $ExpectedRows, $percent)
    Write-Host ('已运行：{0}    预计剩余：{1}' -f $elapsedText, $etaText)
    Write-Host ('后台：{0}' -f $processText)
    Write-Host ''
    Write-Host '最新日志：'
    if (Test-Path -LiteralPath $LogFile) {
        Get-Content -LiteralPath $LogFile -Tail 10
    } else {
        Write-Host '日志文件尚未创建。'
    }
    if ((Test-Path -LiteralPath $ErrorLogFile) -and
        (Get-Item -LiteralPath $ErrorLogFile).Length -gt 0) {
        Write-Host ''
        Write-Host '最新 stderr：'
        Get-Content -LiteralPath $ErrorLogFile -Tail 5
    }

    if (Test-Path -LiteralPath $ExitFile) {
        Write-Host ''
        Write-Host '后台任务已结束：'
        Get-Content -LiteralPath $ExitFile
        if (Test-Path -LiteralPath $NormalizedCsv) {
            $normalizedRows = Get-DataRowCount $NormalizedCsv
            Write-Host ("归一化 CSV：$normalizedRows 行")
        }
        break
    }

    Start-Sleep -Seconds $RefreshSeconds
}
