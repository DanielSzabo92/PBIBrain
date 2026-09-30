$ErrorActionPreference = 'Continue'

$install = 'C:\Users\Daniel\AppData\Local\Programs\PBIBrain\PBIBrain.exe'
$work = 'C:\Users\Daniel\Desktop\PBIBrain\docs\evidence\desktop-audit-2026-09-29'
$outDir = Join-Path $work 'verification'

function Get-ProcessTree([int]$rootPid) {
    $rows = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    [void]$ids.Add($rootPid)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($row in $rows) {
            if ($row.ParentProcessId -and $ids.Contains([int]$row.ParentProcessId) -and $ids.Add([int]$row.ProcessId)) {
                $changed = $true
            }
        }
    }
    @($ids | Sort-Object)
}

function Get-Listeners([int]$rootPid) {
    $ids = @(Get-ProcessTree $rootPid)
    @(
        Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $ids -contains [int]$_.OwningProcess } |
            Select-Object LocalAddress, LocalPort, OwningProcess, State
    )
}

function Probe-Listener([object]$listener) {
    $port = [int]$listener.LocalPort
    $result = [ordered]@{ port = $port; root = $null; session = $null; bootstrap = $null }
    foreach ($name in @('root', 'session', 'bootstrap')) {
        $path = switch ($name) {
            'root' { '/' }
            'session' { '/desktop/session' }
            'bootstrap' { '/desktop/bootstrap.js' }
        }
        try {
            $response = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}{1}" -f $port, $path) -UseBasicParsing -TimeoutSec 5
            $result[$name] = [ordered]@{ status = [int]$response.StatusCode; length = $response.Content.Length; prefix = $response.Content.Substring(0, [Math]::Min(160, $response.Content.Length)) }
        } catch {
            $result[$name] = [ordered]@{ error = $_.Exception.Message }
        }
    }
    [pscustomobject]$result
}

function Run-Check([string]$label, [bool]$sanitized) {
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $install
    $psi.WorkingDirectory = $work
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    if ($sanitized) {
        foreach ($key in @($psi.Environment.Keys)) {
            if ($key -match '^(PYTHON|LBUG|VIRTUAL_ENV|NODE_PATH)') {
                [void]$psi.Environment.Remove($key)
            }
        }
        $psi.Environment['PATH'] = 'C:\Windows\System32;C:\Windows'
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $psi
    $startedAt = Get-Date
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $points = @()
    foreach ($targetMs in @(1000, 5000, 10000)) {
        $remaining = $targetMs - [int]$sw.ElapsedMilliseconds
        if ($remaining -gt 0) { Start-Sleep -Milliseconds $remaining }
        $listeners = @(Get-Listeners $process.Id)
        $points += [pscustomobject]@{
            target_ms = $targetMs
            elapsed_ms = [int]$sw.ElapsedMilliseconds
            pid = $process.Id
            exited = $process.HasExited
            tree = @(Get-ProcessTree $process.Id)
            listeners = $listeners
        }
    }
    $probes = @()
    $lastListeners = @($points[-1].listeners)
    foreach ($listener in $lastListeners) { $probes += Probe-Listener $listener }
    $closeResult = $null
    $closeWaitMs = $null
    if (-not $process.HasExited) {
        $closeResult = $process.CloseMainWindow()
        $closeWait = [Diagnostics.Stopwatch]::StartNew()
        [void]$process.WaitForExit(15000)
        $closeWait.Stop()
        $closeWaitMs = [int]$closeWait.ElapsedMilliseconds
    }
    $stdout = ''
    $stderr = ''
    if ($process.HasExited) {
        try { $stdout = $stdoutTask.Result } catch { $stdout = "<read failed: $($_.Exception.Message)>" }
        try { $stderr = $stderrTask.Result } catch { $stderr = "<read failed: $($_.Exception.Message)>" }
    }
    $record = [ordered]@{
        label = $label
        sanitized = $sanitized
        started_at = $startedAt.ToString('o')
        working_directory = $work
        executable = $install
        pid = $process.Id
        exit_code = if ($process.HasExited) { $process.ExitCode } else { $null }
        checkpoints = $points
        probes_after_10s = $probes
        close_main_window_result = $closeResult
        close_wait_ms = $closeWaitMs
        exited_after_close = $process.HasExited
        stdout = $stdout
        stderr = $stderr
    }
    $jsonPath = Join-Path $outDir ("startup-{0}.json" -f $label)
    $logPath = Join-Path $outDir ("startup-{0}.log.txt" -f $label)
    $record | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $jsonPath -Encoding UTF8
    [IO.File]::WriteAllText($logPath, ("STDOUT`r`n{0}`r`nSTDERR`r`n{1}`r`n" -f $stdout, $stderr), (New-Object System.Text.UTF8Encoding($false)))
    [pscustomobject]$record
}

$results = @()
$results += Run-Check 'sanitized' $true
$results += Run-Check 'ordinary' $false
$results | ConvertTo-Json -Depth 12
