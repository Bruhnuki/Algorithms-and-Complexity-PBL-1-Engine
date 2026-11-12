"""Local AI server: an authenticated, queued, Tailscale-only front door for a local LLM (Ollama).

Independent of the game: it knows nothing about Scrum. The game sends messages and an optional JSON schema
and gets back constrained JSON. Swap the model with AI_MODEL; swap the engine by replacing backend.py.
"""
