import sys
import os
from pathlib import Path

# Ensure project root and apps directory are in sys.path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "apps" / "api"))
sys.path.insert(0, str(ROOT_DIR / "apps" / "worker"))

import gradio as gr
from app.main import app as fastapi_app

# Clean Gradio status & control dashboard for the Hugging Face Space
with gr.Blocks(title="SoundSplit AI Engine", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🎵 SoundSplit AI — Audio & Vocal Isolation Engine
    
    This Hugging Face Space powers the backend AI inference for your **SoundSplit Studio**.
    
    ### API Status & Endpoints:
    - **Health Check**: [`/api/v1/health`](/api/v1/health)
    - **Interactive API Docs**: [`/docs`](/docs)
    - **OpenAPI Schema**: [`/api/openapi.json`](/api/openapi.json)
    
    ---
    *Connect your Vercel frontend by setting `NEXT_PUBLIC_API_URL` to this Space's direct URL.*
    """)

# Mount Gradio onto the FastAPI app so all /api/v1/... REST endpoints remain accessible
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
