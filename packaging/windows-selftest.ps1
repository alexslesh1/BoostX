<#
Checks the routing engine on a real Windows machine, without any server.

Run in PowerShell as administrator from a folder that holds
nexora-engine.exe, WinDivert64.dll, WinDivert64.sys and nexora-testrelay.exe:

    powershell -ExecutionPolicy Bypass -File windows-selftest.ps1 -Dir <that folder>

nexora-testrelay plays the relay and the whole internet: through it,
1.2.3.4 echoes UDP and refuses TCP. Without the tunnel, 1.2.3.4 does not
answer at all. So an echo proves the full path: WinDivert capture, finding
the program that owns the socket, the rule, the encrypted tunnel, and the
reply injected back into Windows.
#>
param([string]$Dir = (Get-Location).Path)

$ErrorActionPreference = "Stop"
$failures = 0
function Pass($what) { Write-Host "PASS  $what" -ForegroundColor Green }
function Fail($what) { Write-Host "FAIL  $what" -ForegroundColor Red; $script:failures++ }

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this from an administrator PowerShell: the engine loads a driver."
}

$work = Join-Path ([IO.Path]::GetTempPath()) ("nexora-selftest-" + [guid]::NewGuid())
New-Item -ItemType Directory $work | Out-Null
$session = Join-Path $work "session.json"
$keyFile = Join-Path $work "engine.key"
$engineLog = Join-Path $work "engine.log"
$port = 47650
$base = "http://127.0.0.1:$port/v1"
$myExe = [IO.Path]::GetFileName((Get-Process -Id $PID).Path)   # pwsh.exe or powershell.exe

$relay = Start-Process (Join-Path $Dir "nexora-testrelay.exe") -ArgumentList "-listen", "127.0.0.1:4799", "-out", "`"$session`"" -PassThru -WindowStyle Hidden
$engine = Start-Process (Join-Path $Dir "nexora-engine.exe") -ArgumentList "serve", "-listen", "127.0.0.1:$port", "-key-file", "`"$keyFile`"", "-log", "`"$engineLog`"" -PassThru -WindowStyle Hidden

function Api($method, $path, $body) {
    $key = (Get-Content $keyFile -Raw).Trim()
    $params = @{ Method = $method; Uri = "$base$path"; Headers = @{ "X-Nexora-Key" = $key }; TimeoutSec = 30 }
    if ($null -ne $body) { $params.Body = ($body | ConvertTo-Json -Depth 6); $params.ContentType = "application/json" }
    Invoke-RestMethod @params
}

function UdpEcho($text) {
    $udp = New-Object System.Net.Sockets.UdpClient
    $udp.Client.ReceiveTimeout = 4000
    try {
        $bytes = [Text.Encoding]::ASCII.GetBytes($text)
        [void]$udp.Send($bytes, $bytes.Length, "1.2.3.4", 5555)
        $from = New-Object System.Net.IPEndPoint ([Net.IPAddress]::Any, 0)
        $reply = [Text.Encoding]::ASCII.GetString($udp.Receive([ref]$from))
        return "$reply from $from"
    } catch { return $null } finally { $udp.Close() }
}

function TcpResult() {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $tcp.ConnectAsync("1.2.3.4", 5555)
        if (-not $task.Wait(4000)) { return "timeout" }
        return "connected"
    } catch {
        $inner = $_.Exception.InnerException
        while ($inner -and -not ($inner -is [System.Net.Sockets.SocketException])) { $inner = $inner.InnerException }
        if ($inner -and $inner.SocketErrorCode -eq "ConnectionRefused") { return "refused" }
        return "error: $($_.Exception.Message)"
    } finally { $tcp.Close() }
}

# Small requests plus one 10 MB download from a program that is not routed
# (curl.exe), so the engine's effect on everyone else's traffic shows up
# as failures or as time, compared with the same run without the engine.
function Measure-Web($label) {
    $urls = @("https://api.github.com/zen", "https://www.microsoft.com/", "https://www.cloudflare.com/cdn-cgi/trace") * 2
    $failed = 0; $slowest = 0.0
    foreach ($u in $urls) {
        $out = & curl.exe -s -o NUL -m 20 -w "%{http_code} %{time_total}" $u
        $code, $time = "$out".Split(" ")
        if ($code -notmatch "^[23]") { $failed++; Write-Host "      ${label}: $u -> $out" }
        $slowest = [Math]::Max($slowest, [double]$time)
    }
    $start = Get-Date
    & curl.exe -s -o NUL -m 60 "https://speed.cloudflare.com/__down?bytes=10000000"
    if ($LASTEXITCODE -ne 0) { $failed++; Write-Host "      ${label}: 10 MB download failed ($LASTEXITCODE)" }
    $bulk = ((Get-Date) - $start).TotalSeconds
    [pscustomobject]@{ Count = $urls.Count + 1; Failed = $failed; Slowest = $slowest; Bulk = $bulk }
}

$baseline = Measure-Web "without the engine"

try {
    $deadline = (Get-Date).AddSeconds(20)
    while (-not ((Test-Path $session) -and (Test-Path $keyFile))) {
        if ((Get-Date) -gt $deadline) { throw "relay or engine did not start" }
        Start-Sleep -Milliseconds 200
    }
    while ($true) {
        try { Api GET "/status" $null | Out-Null; break } catch {
            if ((Get-Date) -gt $deadline) { throw "engine API did not answer" }
            Start-Sleep -Milliseconds 200
        }
    }
    Pass "engine and test relay started"

    # Before routing: nothing answers from 1.2.3.4.
    if (UdpEcho "before") { Fail "1.2.3.4 answered before routing was on" } else { Pass "1.2.3.4 is silent without the tunnel" }

    $s = Get-Content $session -Raw | ConvertFrom-Json
    $rules = @(@{ name = "selftest"; exes = @($myExe); dirs = @() })
    try {
        Api POST "/start" @{ relay = $s.relay; relay_public_key = $s.relay_public_key; token = $s.token; rules = $rules } | Out-Null
        Pass "capture opened (WinDivert driver loaded)"
    } catch {
        Fail "engine could not start capturing: $($_.ErrorDetails.Message)"
        throw
    }

    $deadline = (Get-Date).AddSeconds(10)
    do { $st = Api GET "/status" $null; Start-Sleep -Milliseconds 200 } until ($st.tunnel.connected -or (Get-Date) -gt $deadline)
    if ($st.tunnel.connected) { Pass "tunnel connected (virtual IP $($st.tunnel.virtual_ip))" } else { Fail "tunnel did not connect: $($st.tunnel.error)" }

    $echo = UdpEcho "hello"
    if ($echo -like "echo:hello from 1.2.3.4:5555") { Pass "UDP of $myExe went through the tunnel and back ($echo)" } else { Fail "UDP of $myExe got no echo ($echo)" }

    $tcp = TcpResult
    if ($tcp -eq "refused") { Pass "TCP connect of $myExe went through the tunnel (refused by the test relay)" } else { Fail "TCP connect of ${myExe}: $tcp" }

    $during = Measure-Web "while capturing"
    if ($during.Failed -eq 0) {
        Pass ("other programs reach the internet normally while capturing: {0} requests ok, slowest {1:N2} s, 10 MB in {2:N1} s (without the engine: slowest {3:N2} s, 10 MB in {4:N1} s)" -f $during.Count, $during.Slowest, $during.Bulk, $baseline.Slowest, $baseline.Bulk)
    } else {
        Fail ("other programs' requests failed while capturing: {0} of {1} (without the engine: {2} of {3})" -f $during.Failed, $during.Count, $baseline.Failed, $baseline.Count)
    }
    if ($during.Bulk -gt 3 * [Math]::Max($baseline.Bulk, 1)) {
        Write-Host ("WARN  10 MB download is much slower while capturing: {0:N1} s vs {1:N1} s" -f $during.Bulk, $baseline.Bulk) -ForegroundColor Yellow
    }

    & curl.exe -s -o NUL --connect-timeout 4 http://1.2.3.4:5555/ ; $curlExit = $LASTEXITCODE
    if ($curlExit -eq 28) { Pass "curl.exe (not selected) was not routed: its connection timed out" } else { Fail "curl.exe (not selected) got exit $curlExit instead of a timeout" }

    $st = Api GET "/status" $null
    $mine = @($st.flows | Where-Object { $_.app -eq "selftest" })
    if ($mine.Count -ge 2) { Pass "status lists $($mine.Count) routed connections of $($mine[0].exe)" } else { Fail "status lists $($mine.Count) routed connections" }

    $rules += @{ name = "curl"; exes = @("curl.exe"); dirs = @() }
    Api POST "/rules" @{ rules = $rules } | Out-Null
    & curl.exe -s -o NUL --connect-timeout 4 http://1.2.3.4:5555/ ; $curlExit = $LASTEXITCODE
    if ($curlExit -eq 7) { Pass "after adding curl.exe live, its connection went through the tunnel (refused)" } else { Fail "after adding curl.exe, exit $curlExit instead of 7" }
    $echo = UdpEcho "still"
    if ($echo -like "echo:still*") { Pass "$myExe kept working through the rule change" } else { Fail "$myExe stopped working after the rule change" }

    Api POST "/stop" $null | Out-Null
    if (UdpEcho "after") { Fail "1.2.3.4 still answers after stop" } else { Pass "after stop, traffic is direct again" }

    Api POST "/shutdown" $null | Out-Null
    if ($engine.WaitForExit(10000)) { Pass "engine exited on request" } else { Fail "engine did not exit on request" }

    # The engine must never outlive the app that started it.
    $parent = Start-Process "ping.exe" -ArgumentList "-n", "120", "127.0.0.1" -PassThru -WindowStyle Hidden
    $orphan = Start-Process (Join-Path $Dir "nexora-engine.exe") -ArgumentList "serve", "-listen", "127.0.0.1:47651", "-key-file", "`"$keyFile`"", "-parent-pid", "$($parent.Id)" -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    Stop-Process -Id $parent.Id -Force
    if ($orphan.WaitForExit(10000)) { Pass "engine exits when its parent app dies" } else { Fail "engine kept running after its parent died"; Stop-Process -Id $orphan.Id -Force }
}
finally {
    foreach ($p in @($engine, $relay)) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
    Write-Host "`n--- engine log ---"
    if (Test-Path $engineLog) { Get-Content $engineLog }
}

if ($failures -gt 0) { Write-Host "`n$failures check(s) failed" -ForegroundColor Red; exit 1 }
Write-Host "`nAll checks passed" -ForegroundColor Green
# curl's expected non-zero exits above must not become this script's result.
exit 0
