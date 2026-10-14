$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
    & $taskPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
if (-not (Test-Path -LiteralPath '.env')) { throw 'Create .env from .env.example and fill in your Plivo credentials first.' }
$taskTools = Join-Path $PSScriptRoot 'tools'
New-Item -ItemType Directory -Path $taskTools -Force | Out-Null
$taskTunnelExe = Join-Path $taskTools 'cloudflared.exe'
if (-not (Test-Path -LiteralPath $taskTunnelExe)) {
    Write-Host 'Downloading the Cloudflare HTTPS tunnel client...'
    Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $taskTunnelExe
}
$taskLog = Join-Path $taskTools 'tunnel.log'
$taskOut = Join-Path $taskTools 'tunnel-output.log'
$taskTunnel = Start-Process -FilePath $taskTunnelExe -ArgumentList @('tunnel', '--protocol', 'http2', '--url', 'http://127.0.0.1:5000', '--no-autoupdate') -WindowStyle Hidden -RedirectStandardError $taskLog -RedirectStandardOutput $taskOut -PassThru
try {
    Write-Host 'Starting public HTTPS tunnel...'
    $taskUrl = $null
    for ($taskAttempt = 0; $taskAttempt -lt 90; $taskAttempt++) {
        Start-Sleep -Seconds 1
        if ($taskTunnel.HasExited) { throw 'Tunnel exited. Inspect tools\tunnel.log or use the manual ngrok instructions in README.md.' }
        if (Test-Path -LiteralPath $taskLog) {
            $taskMatch = [regex]::Match((Get-Content -LiteralPath $taskLog -Raw), 'https://[a-z0-9-]+\.trycloudflare\.com')
            if ($taskMatch.Success) { $taskUrl = $taskMatch.Value; break }
        }
    }
    if (-not $taskUrl) { throw 'No public tunnel URL received. See tools\tunnel.log.' }
    $taskEnvPath = Join-Path $PSScriptRoot '.env'
    $taskEnvText = Get-Content -LiteralPath $taskEnvPath -Raw
    if ($taskEnvText -match '(?m)^PUBLIC_BASE_URL=') {
        $taskEnvText = [regex]::Replace($taskEnvText, '(?m)^PUBLIC_BASE_URL=.*$', "PUBLIC_BASE_URL=$taskUrl")
    } else { $taskEnvText += "`nPUBLIC_BASE_URL=$taskUrl`n" }
    [System.IO.File]::WriteAllText($taskEnvPath, $taskEnvText)
    Write-Host "Public callbacks: $taskUrl"
    Write-Host 'Open http://127.0.0.1:5000 in your browser. OTP: 2711'
    Write-Host 'Keep this window open during the call. Press Ctrl+C to stop.'
    & $taskPython app.py
} finally {
    if (-not $taskTunnel.HasExited) { Stop-Process -Id $taskTunnel.Id -ErrorAction SilentlyContinue }
}
