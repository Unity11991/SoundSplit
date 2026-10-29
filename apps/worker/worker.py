import sys
import os
import json
import time
import signal
import asyncio
import logging
from pathlib import Path

# Add project root and apps/api to sys.path so worker can import shared modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

import redis.asyncio as aioredis
from app.core.config import settings
from app.core.database import init_db
from apps.worker.engine.pipeline import separation_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AI-WORKER] %(name)s - %(message)s"
)
logger = logging.getLogger("stemlab.worker")

class StandaloneWorker:
    def __init__(self):
        self._running = True
        self._redis_client = None

    def stop(self, *args):
        logger.info("Worker received shutdown signal. Finishing active task and stopping...")
        self._running = False

    async def run(self):
        logger.info("==================================================")
        logger.info(f"Starting StemLab AI Asynchronous Worker")
        logger.info(f"Listening on Redis Queue: {settings.REDIS_QUEUE_NAME}")
        logger.info(f"Separation Model: {settings.DEFAULT_MODEL}")
        logger.info("==================================================")

        init_db()

        # Warm up Demucs model adapter
        logger.info("Warming up Demucs model...")
        separation_pipeline.adapter.load()
        logger.info("Demucs model ready for inference!")

        while self._running:
            try:
                if not self._redis_client:
                    self._redis_client = aioredis.from_url(
                        settings.REDIS_URL,
                        decode_responses=True,
                        socket_connect_timeout=5.0
                    )
                    await self._redis_client.ping()
                    logger.info("Connected to Redis successfully.")

                # Wait for job from Redis queue (blocking pop with 2s timeout)
                result = await self._redis_client.blpop([settings.REDIS_QUEUE_NAME], timeout=2)
                if not result:
                    continue

                _, job_json = result
                job_data = json.loads(job_json)
                logger.info(f"Popped job from queue: {job_data.get('job_id')}")

                # Execute separation pipeline
                await separation_pipeline.execute_job(job_data)

            except (aioredis.ConnectionError, aioredis.TimeoutError):
                logger.warning("Redis disconnected. Retrying in 5 seconds...")
                self._redis_client = None
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Worker iteration exception: {e}", exc_info=True)
                await asyncio.sleep(2)

        if self._redis_client:
            await self._redis_client.close()
        logger.info("Worker gracefully stopped.")

def main():
    worker = StandaloneWorker()
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)
    asyncio.run(worker.run())

if __name__ == "__main__":
    main()
