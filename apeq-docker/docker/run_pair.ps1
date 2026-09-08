[CmdletBinding()]
param(
    [string]$Image = "apeq/mock",
    [string]$Protocol = "apeq",
    [string]$Backend = "ips_ole",
    [string]$Variant = "ole",
    [ValidateRange(1, 64)]
    [int]$Bits = 32,
    [int]$FieldBits = 128,
    [int]$Batch = 10,
    [int]$Rep = 0,
    [UInt64]$Seed = 1,
    [ValidateSet("lan", "wan")]
    [string]$Network = "lan",
    [double]$RttMs = 0,
    [double]$BandwidthMbps = 0,
    [int]$SecurityParam = 128,
    [int]$OleN = 1024,
    [int]$OleRho = 769,
    [int]$OleEll = 255,
    [int]$OleK = 128,
    [int]$OleT = 48,
    [int]$TimeoutSeconds = 30,
    [string]$Results = (Join-Path $PSScriptRoot "results.csv"),
    [switch]$KeepContainers
)

$ErrorActionPreference = "Stop"

function Invoke-Docker {
    param([string[]]$DockerArgs)
    $output = & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($DockerArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
    return $output
}

function Get-ContainerState {
    param([string]$Name)
    $raw = (& docker inspect --format '{{.State.Running}} {{.State.ExitCode}}' $Name).Trim()
    if ($LASTEXITCODE -ne 0) { throw "cannot inspect container $Name" }
    $parts = $raw -split ' '
    return [pscustomobject]@{
        Running = ($parts[0] -eq "true")
        ExitCode = [int]$parts[1]
    }
}

function Append-ResultFile {
    param([string]$Source, [string]$Destination)
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "expected party result was not written: $Source"
    }
    $lines = @(Get-Content -LiteralPath $Source)
    if ($lines.Count -lt 2) { throw "party result has no data row: $Source" }
    if (-not (Test-Path -LiteralPath $Destination)) {
        Set-Content -LiteralPath $Destination -Value $lines -Encoding utf8
    } else {
        Add-Content -LiteralPath $Destination -Value $lines[1..($lines.Count - 1)] -Encoding utf8
    }
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker engine is not running. Start Docker Desktop and wait until it reports Ready."
}

$resultPath = [System.IO.Path]::GetFullPath($Results)
$resultDir = Split-Path -Parent $resultPath
$runDir = Join-Path $resultDir "party-runs"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$runId = [guid]::NewGuid().ToString()
$shortId = $runId.Substring(0, 8)
$dockerNetwork = "apeq-$shortId"
$partyAName = "apeq-a-$shortId"
$partyBName = "apeq-b-$shortId"
$partyAFile = "$runId-A.csv"
$partyBFile = "$runId-B.csv"
$partyAHostPath = Join-Path $runDir $partyAFile
$partyBHostPath = Join-Path $runDir $partyBFile
$mountPath = $runDir.Replace('\', '/')
$timedOut = $false

$common = @(
    "--protocol", $Protocol,
    "--backend", $Backend,
    "--variant", $Variant,
    "--batch", $Batch,
    "--bits", $Bits,
    "--field-bits", $FieldBits,
    "--ole-n", $OleN,
    "--ole-rho", $OleRho,
    "--ole-ell", $OleEll,
    "--ole-k", $OleK,
    "--ole-t", $OleT,
    "--kappa", $SecurityParam,
    "--network", $Network,
    "--rtt", $RttMs,
    "--bandwidth", $BandwidthMbps,
    "--rep", $Rep,
    "--seed", $Seed,
    "--run-id", $runId,
    "--port", 12345,
    "--note", "docker_pair_smoke"
)

try {
    Invoke-Docker -DockerArgs @("network", "create", $dockerNetwork) | Out-Null

    $partyAArgs = @(
        "run", "-d", "--name", $partyAName,
        "--network", $dockerNetwork,
        "-v", "${mountPath}:/out",
        $Image
    ) + $common + @("--party", 1, "--host", "0.0.0.0", "--out", "/out/$partyAFile")

    Invoke-Docker -DockerArgs $partyAArgs | Out-Null

    # EMP 0.3 ultimately passes --host through inet_addr(), so a Docker DNS
    # name is not sufficient. Resolve the server's address on this isolated
    # bridge before starting the client.
    $partyAIp = (& docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $partyAName).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($partyAIp)) {
        throw "could not resolve party A address on network $dockerNetwork"
    }

    $partyBArgs = @(
        "run", "-d", "--name", $partyBName,
        "--network", $dockerNetwork,
        "-v", "${mountPath}:/out",
        $Image
    ) + $common + @("--party", 2, "--host", $partyAIp, "--out", "/out/$partyBFile")

    Invoke-Docker -DockerArgs $partyBArgs | Out-Null

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ($true) {
        $stateA = Get-ContainerState $partyAName
        $stateB = Get-ContainerState $partyBName
        if (-not $stateA.Running -and -not $stateB.Running) { break }
        if ([DateTime]::UtcNow -ge $deadline) {
            $timedOut = $true
            break
        }
        Start-Sleep -Milliseconds 200
    }

    if ($timedOut) {
        & docker rm -f $partyAName $partyBName *> $null
        throw "both-party run exceeded ${TimeoutSeconds}s; no result rows were merged"
    }

    $stateA = Get-ContainerState $partyAName
    $stateB = Get-ContainerState $partyBName
    if ($stateA.ExitCode -ne 0 -or $stateB.ExitCode -ne 0) {
        Write-Host "party A log:"
        & docker logs $partyAName
        Write-Host "party B log:"
        & docker logs $partyBName
        throw "party exit codes: A=$($stateA.ExitCode), B=$($stateB.ExitCode)"
    }

    Append-ResultFile -Source $partyAHostPath -Destination $resultPath
    Append-ResultFile -Source $partyBHostPath -Destination $resultPath
    Write-Host "merged A/B rows into $resultPath"
    Write-Host "run_id=$runId"
}
finally {
    if (-not $KeepContainers) {
        & docker rm -f $partyAName $partyBName *> $null
    }
    & docker network rm $dockerNetwork *> $null
}
