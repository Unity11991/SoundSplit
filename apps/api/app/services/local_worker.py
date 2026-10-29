import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_APPS_DIR = Path(__file__).resolve().parents[3]
for _p in [str(_PROJECT_ROOT), str(_APPS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger("stemlab.local_worker")

class LocalWorker:
    def __init__(self):
        self._is_running = False

    async def process_job_async(self, job_data: Dict[str, Any]):
        """Run separation job in an executor thread so it never blocks the FastAPI event loop."""
        job_id = job_data.get("job_id")
        logger.info(f"Local worker dispatching job {job_id} to background thread...")
        
        try:
            from apps.worker.engine.pipeline import separation_pipeline
        except ImportError:
            from worker.engine.pipeline import separation_pipeline
        # Run the CPU/GPU-intensive inference in a dedicated thread
        try:
            await separation_pipeline.execute_job(job_data)
        except Exception as e:
            logger.error(f"Error executing job {job_id} in background thread: {e}", exc_info=True)

local_worker = LocalWorker()
