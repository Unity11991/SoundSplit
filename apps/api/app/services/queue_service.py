import json
import asyncio
from typing import Dict, Any, AsyncGenerator, Optional
import redis.asyncio as aioredis

from app.core.config import settings

class QueueService:
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self._local_subscribers: Dict[str, list[asyncio.Queue]] = {}
        self._redis_available = False

    async def connect(self):
        try:
            self.redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2.0
            )
            await self.redis_client.ping()
            self._redis_available = True
        except Exception:
            self._redis_available = False
            self.redis_client = None

    async def is_redis_connected(self) -> bool:
        if self._redis_available and self.redis_client:
            try:
                await self.redis_client.ping()
                return True
            except Exception:
                self._redis_available = False
        return False

    async def enqueue_job(self, job_data: Dict[str, Any]) -> bool:
        """Enqueue a separation job to Redis queue or dispatch to local worker."""
        job_json = json.dumps(job_data)
        if await self.is_redis_connected():
            try:
                await self.redis_client.rpush(settings.REDIS_QUEUE_NAME, job_json)
                return True
            except Exception:
                self._redis_available = False
        
        # In-process asynchronous task dispatch fallback
        from app.services.local_worker import local_worker
        asyncio.create_task(local_worker.process_job_async(job_data))
        return True

    async def publish_event(self, job_id: str, event_data: Dict[str, Any]):
        """Publish real-time progress update for SSE subscribers."""
        event_json = json.dumps(event_data)
        
        # Publish to Redis channel if available
        if await self.is_redis_connected():
            try:
                channel = f"job_events:{job_id}"
                await self.redis_client.publish(channel, event_json)
            except Exception:
                pass

        # Publish to local in-memory listeners
        if job_id in self._local_subscribers:
            for queue in self._local_subscribers[job_id]:
                await queue.put(event_data)

    async def subscribe_events(self, job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to real-time events for a specific separation job."""
        local_q = asyncio.Queue()
        if job_id not in self._local_subscribers:
            self._local_subscribers[job_id] = []
        self._local_subscribers[job_id].append(local_q)

        pubsub = None
        if await self.is_redis_connected():
            try:
                pubsub = self.redis_client.pubsub()
                await pubsub.subscribe(f"job_events:{job_id}")
            except Exception:
                pubsub = None

        try:
            while True:
                # Check local queue first
                try:
                    event = await asyncio.wait_for(local_q.get(), timeout=1.0)
                    yield event
                    if event.get("status") in ["completed", "failed", "cancelled"]:
                        break
                    continue
                except asyncio.TimeoutError:
                    pass

                # Check Redis PubSub if active
                if pubsub:
                    try:
                        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                        if msg and msg.get("data"):
                            event = json.loads(msg["data"])
                            yield event
                            if event.get("status") in ["completed", "failed", "cancelled"]:
                                break
                    except Exception:
                        pass
                
                # Heartbeat keep-alive yield
                await asyncio.sleep(0.5)

        finally:
            if job_id in self._local_subscribers and local_q in self._local_subscribers[job_id]:
                self._local_subscribers[job_id].remove(local_q)
                if not self._local_subscribers[job_id]:
                    del self._local_subscribers[job_id]
            if pubsub:
                try:
                    await pubsub.unsubscribe(f"job_events:{job_id}")
                    await pubsub.close()
                except Exception:
                    pass

queue_service = QueueService()
