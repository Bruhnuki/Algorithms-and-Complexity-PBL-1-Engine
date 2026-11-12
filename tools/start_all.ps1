# Host everything on THIS PC: the AI (model engine + AI server) and the game server, both listening on this PC's Tailscale address only.
# Other people on your tailnet then open  http://<this-pc-tailscale-ip>:8000/play/  to play, and  http://<ip>:8765/console  to check the AI.
#
#   .\tools\start_all.ps1                 # Tailscale address (needs Tailscale signed in on this PC)
#   .\tools\start_all.ps1 -Local          # test on this PC only (127.0.0.1)
#   .\tools\start_all.ps1 -Model qwen3.5:4b -Debug
# Stop with .\tools\stop_all.ps1. Logs and secrets live in %LOCALAPPDATA%\fixit.
param([switch]$Local, [string]$Model = "qwen3.5:9b", [string]$ChatModel = "qwen3.5:4b", [int]$AiPort = 8765, [int]$GamePort = 8000, [switch]$Debug, [switch]$Open)

$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $env:LOCALAPPDATA "fixit"; New-Item -ItemType Directory -Force $dir | Out-Null
function Get-Secret([string]$file) {   # made once, kept outside the project
    $p = Join-Path $dir $file
    if (-not (Test-Path $p)) { python -c "import secrets;print(secrets.token_urlsafe(32), end='')" | Set-Content -Path $p -NoNewline }
    return (Get-Content $p -Raw)
}
$old = Join-Path $env:LOCALAPPDATA "fixit_ai_token.txt"
if ((Test-Path $old) -and -not (Test-Path (Join-Path $dir "ai_token.txt"))) { Copy-Item $old (Join-Path $dir "ai_token.txt") }   # keep the token made earlier
$token = Get-Secret "ai_token.txt"; $session = Get-Secret "session_secret.txt"; $instructor = (Get-Secret "instructor_code.txt").Substring(0, 12)

# Where to listen
if ($Local) { $ip = "127.0.0.1"; $env:FIXIT_AI_ALLOW_LOCAL = "1" }
else {
    $ip = $null
    foreach ($exe in @("tailscale", "C:\Program Files\Tailscale\tailscale.exe")) { try { $o = & $exe ip -4 2>$null; if ($o -match "^100\.") { $ip = ($o | Select-Object -First 1).Trim(); break } } catch {} }
    if (-not $ip) { throw "No Tailscale address on this PC. Sign in to Tailscale first (or use -Local to test on this PC only)." }
}

# 1. The model engine, tuned (see docs/ai/README.md); it only listens on this PC
Get-Process -Name "ollama", "ollama app" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$env:OLLAMA_FLASH_ATTENTION = "1"; $env:OLLAMA_KV_CACHE_TYPE = "q8_0"; $env:OLLAMA_NUM_PARALLEL = "1"; $env:OLLAMA_MAX_LOADED_MODELS = $(if ($ChatModel) { "2" } else { "1" })   # both models stay in VRAM (about 9 GB together); $env:OLLAMA_KEEP_ALIVE = "24h"; $env:OLLAMA_HOST = "127.0.0.1:11434"
Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
for ($i = 0; $i -lt 30; $i++) { try { Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 1 } }

# Load both models into VRAM now and keep them there: idle, they use no GPU compute, and the first chat or project has no loading delay.
foreach ($m in (@($Model, $ChatModel) | Where-Object { $_ } | Select-Object -Unique)) {
    try { Invoke-RestMethod http://127.0.0.1:11434/api/generate -Method Post -ContentType "application/json" -TimeoutSec 120 -Body (@{ model = $m; prompt = "ok"; stream = $false; keep_alive = "24h"; think = $false; options = @{ num_ctx = 3072; num_predict = 1 } } | ConvertTo-Json -Depth 4) | Out-Null } catch { Write-Host "Could not preload $m : $_" }
}

# 2. The AI server (token + Tailscale-only)
$env:AI_TOKEN = $token; $env:AI_MODEL = $Model; $env:AI_ALLOWED_MODELS = (@($Model, $ChatModel) | Where-Object { $_ } | Select-Object -Unique) -join ","; $env:AI_BIND = $ip; $env:AI_PORT = "$AiPort"; $env:AI_KEEP_ALIVE = "24h"
Start-Process -FilePath "python" -ArgumentList "-m", "ai_server" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dir "ai_server.log") -RedirectStandardError (Join-Path $dir "ai_server.err.log")

# 3. The game server, connected to that AI over the same address
$ai = "http://${ip}:$AiPort"
$env:FIXIT_HOST = $ip; $env:PORT = "$GamePort"; $env:FIXIT_AI_URL = $ai; $env:FIXIT_CHAT_MODEL = $ChatModel; $env:FIXIT_AI_TOKEN = $token; $env:MODEL_URL = $ai; $env:MODEL_TOKEN = $token
$env:SESSION_SECRET = $session; $env:INSTRUCTOR_CODE = $instructor
if ($Debug) { $env:FIXIT_DEBUG = "1" } else { Remove-Item Env:FIXIT_DEBUG -ErrorAction SilentlyContinue }
Start-Process -FilePath "python" -ArgumentList "run_dev.py" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dir "game.log") -RedirectStandardError (Join-Path $dir "game.err.log")

$up = @{ ai = $false; game = $false }
for ($i = 0; $i -lt 40 -and -not ($up.ai -and $up.game); $i++) {
    Start-Sleep -Seconds 1
    try { $up.ai = (Invoke-RestMethod "$ai/healthz" -TimeoutSec 2).status -eq "ok" } catch {}
    try { $up.game = (Invoke-RestMethod "http://${ip}:$GamePort/healthz" -TimeoutSec 2).ok } catch {}
}
Write-Host ""
Write-Host "Game      : http://${ip}:$GamePort/play/   $(if ($up.game) { '(running)' } else { '(NOT answering, see ' + $dir + '\game.err.log)' })"
Write-Host "AI console: $ai/console          $(if ($up.ai) { '(running)' } else { '(NOT answering, see ' + $dir + '\ai_server.err.log)' })"
Write-Host "AI token  : $dir\ai_token.txt   (paste it into the AI console)"
Write-Host "Instructor sign-up code: $instructor"
if ($Open -and $up.game) { Start-Process "http://${ip}:$GamePort/play/" }
