# Stop the AI server and the game server started by start_all.ps1 (the model engine, Ollama, is left running: it unloads the model by itself after 5 minutes).
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "ai_server|run_dev\.py" -and $_.Name -match "python" } | ForEach-Object {
    "stopping $($_.ProcessId): $($_.CommandLine)"
    Stop-Process -Id $_.ProcessId -Force
}
