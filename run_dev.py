"""Dev server without a model: python run_dev.py  (set MODEL_URL to use llama-server)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
import uvicorn  # noqa: E402

os.environ.setdefault("INSTRUCTOR_CODE", "dev-instructor")
if __name__ == "__main__":
    uvicorn.run("fixit.api.app:app_from_env", factory=True, host="127.0.0.1", port=8000)
