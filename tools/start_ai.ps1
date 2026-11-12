# Start the tuned model engine (Ollama) and the AI server on this PC.
#   .\tools\start_ai.ps1                 # model qwen3.5:9b, listens on the Tailscale address
#   .\tools\start_ai.ps1 -Model qwen3.5:4b -Bind 127.0.0.1    # one-PC test
# Needs AI_TOKEN in the environment (python -m ai_server token).
param([string]$Model = "qwen3.5:9b", [string]$Bind = "tailscale", [int]$Port = 8765)

$tokenFile = Join-Path $env:LOCALAPPDATA "fixit_ai_token.txt"   # made once, kept outside the project
if (-not $env:AI_TOKEN) {
    if (-not (Test-Path $tokenFile)) { python -m ai_server token | Set-Content -Path $tokenFile -NoNewline }
    $env:AI_TOKEN = Get-Content $tokenFile -Raw
}

# Lean engine settings: less VRAM and less work per token.
$env:OLLAMA_FLASH_ATTENTION = "1"        # cheaper attention, less memory for long prompts
$env:OLLAMA_KV_CACHE_TYPE   = "q8_0"     # half-size KV cache, no visible quality loss at these sizes
$env:OLLAMA_NUM_PARALLEL    = "1"        # one request at a time: no VRAM reserved for parallel slots
$env:OLLAMA_MAX_LOADED_MODELS = "1"      # only one primary model in VRAM
$env:OLLAMA_KEEP_ALIVE      = "5m"       # leaves VRAM 5 minutes after the last request
$env:OLLAMA_HOST            = "127.0.0.1:11434"   # the engine itself is never reachable from the network

Get-Process -Name "ollama", "ollama app" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
for ($i = 0; $i -lt 30; $i++) { try { Invoke-RestMethod http://127.0.0.1:11434/api/version -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 1 } }

$env:AI_MODEL = $Model; $env:AI_ALLOWED_MODELS = "qwen3.5:9b,qwen3.5:4b"; $env:AI_BIND = $Bind; $env:AI_PORT = "$Port"; $env:AI_KEEP_ALIVE = "5m"
python -m ai_server
