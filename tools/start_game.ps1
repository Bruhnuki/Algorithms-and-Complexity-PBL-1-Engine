# Start the game with the AI connected over Tailscale. The AI runs on another PC (tools\start_ai.ps1 there, which listens on that PC's Tailscale address only).
#   .\tools\start_game.ps1 -AiUrl http://<ai-pc-name>:8765 -Token <the token>      # MagicDNS name or the 100.x address
# Without -AiUrl the game simply runs without the AI (authored content only).
param([string]$AiUrl = "", [string]$Token = "", [switch]$Debug)
if ($AiUrl) {
    if (-not $Token) { $Token = (Get-Content (Join-Path $env:LOCALAPPDATA "fixit_ai_token.txt") -Raw -ErrorAction Stop) }
    $env:FIXIT_AI_URL = $AiUrl
    $env:FIXIT_AI_TOKEN = $Token
    $env:MODEL_URL = $AiUrl      # live teammate chat through the same server (falls back to authored lines if it is slow or down)
    $env:MODEL_TOKEN = $Token
}
if ($Debug) { $env:FIXIT_DEBUG = "1" }   # developer shortcuts; never in a class
python run_dev.py
