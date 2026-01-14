from typing import List

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import redis.asyncio as redis
import os
import logging
import json
import httpx
from dotenv import load_dotenv

# Load .env file
load_dotenv()

r = redis.from_url(os.environ["CACHE_REDIS_URL"], decode_responses=True)
DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS configuration for cross-origin requests from piefed.social
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Dictionary of {user_id: set of asyncio.Queue instances}
connected_clients = {}

# HTTP client for connection pooling
http_client = None


@app.get("/notifications/stream")
async def notifications_stream(user_id: str):
    if not user_id:
        return {"error": "Missing user_id"}, 400

    logger.debug(f"New SSE connection for user {user_id}")
    q = asyncio.Queue()
    connected_clients.setdefault(user_id, set()).add(q)
    logger.debug(
        f"Total connections for user {user_id}: {len(connected_clients[user_id])}"
    )

    async def event_stream():
        try:
            logger.debug(f"Starting event stream for user {user_id}")
            yield ": connected\n\n"

            while True:
                try:
                    # Monitor the queue for 60 seconds
                    message = await asyncio.wait_for(q.get(), timeout=60.0)
                    logger.debug(f"Sending message to user {user_id}: {message}")
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:  # the queue has had nothing in it for 60 seconds so send a heartbeat to keep the connection alive
                    logger.debug(f"Sending heartbeat to user {user_id}")
                    yield ": heartbeat\n\n"
                except Exception as e:
                    logger.error(f"Error getting message for user {user_id}: {e}")
                    break
        except (asyncio.CancelledError, GeneratorExit) as e:
            logger.debug(
                f"SSE connection cancelled for user {user_id}: {type(e).__name__}: {e}"
            )
        except Exception as e:
            # Log unexpected errors but don't break the connection
            logger.error(
                f"SSE unexpected error for user {user_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )
        finally:
            logger.debug(f"Cleaning up SSE connection for user {user_id}")
            # Clean up the queue from connected clients
            if user_id in connected_clients:
                connected_clients[user_id].discard(q)
                # Remove user entry if no more connections
                if not connected_clients[user_id]:
                    del connected_clients[user_id]
                    logger.debug(f"Removed user {user_id} from connected_clients")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def send_http_posts(all_urls: List, all_headers: List, data_json: str):
    """Send HTTP POST requests to multiple URLs concurrently with connection limits"""
    if not http_client:
        logger.error("HTTP client not initialized")
        return

    async def post_to_url(url, headers):
        try:
            logger.debug(f"Sending POST to {url}")
            response = await http_client.post(
                url, headers=headers, data=data_json.encode("utf8"), timeout=10.0
            )
            if response.status_code >= 400:
                logger.warning(
                    f"HTTP POST to {url} failed with status {response.status_code} - {response.content!r}"
                )
            else:
                logger.debug(f"HTTP POST to {url} succeeded")
            return url, response.status_code
        except httpx.TimeoutError:
            logger.warning(f"HTTP POST to {url} timed out")
            return url, "timeout"
        except Exception as e:
            logger.error(f"HTTP POST to {url} failed: {e}")
            return url, f"error: {e}"

    # Process URLs in batches to respect connection limits
    results = []
    for i in range(0, len(all_urls), 100):
        url_batch = all_urls[i : i + 100]
        header_batch = all_headers[i : i + 100]
        batch_results = await asyncio.gather(
            *[post_to_url(url, header) for url, header in zip(url_batch, header_batch)],
            return_exceptions=True,
        )
        results.extend(batch_results)

    logger.info(f"Completed HTTP POST requests to {len(all_urls)} URLs")
    return results


async def redis_listener():
    while True:
        try:
            logger.info("Starting Redis listener")
            pubsub = r.pubsub()
            await pubsub.psubscribe("notifications:*", "http_posts:*", "messages:*")

            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"]
                    data = message["data"]

                    if channel.startswith("notifications:") or channel.startswith(
                        "messages:"
                    ):
                        # Handle SSE notification messages
                        _, user_id = channel.split(":", 1)
                        logger.debug(f"Received Redis notification for user {user_id}")
                        for q in connected_clients.get(user_id, []):
                            try:
                                await q.put(data)
                            except Exception as e:
                                logger.error(
                                    f"Failed to queue message for user {user_id}: {e}"
                                )

                    elif channel.startswith("http_posts:"):
                        # Handle HTTP POST messages
                        logger.debug(f"Received Redis HTTP POST message on {channel}")
                        try:
                            message_data = json.loads(data)
                            urls = message_data.get("urls", [])
                            headers = message_data.get("headers", [])
                            # Data is already a JSON string from the sender
                            post_data_json = message_data.get("data", "{}")

                            if not urls:
                                logger.warning("HTTP POST message missing URLs")
                                continue

                            # Send HTTP POST requests asynchronously
                            asyncio.create_task(
                                send_http_posts(urls, headers, post_data_json)
                            )

                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse HTTP POST message JSON: {e}")
                        except Exception as e:
                            logger.error(f"Failed to process HTTP POST message: {e}")

        except redis.ConnectionError as e:
            logger.error(f"Redis connection error: {e}")
            await asyncio.sleep(5)  # Wait before reconnecting
        except Exception as e:
            logger.error(f"Unexpected error in Redis listener: {e}", exc_info=True)
            await asyncio.sleep(5)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring/load balancers"""
    try:
        # Test Redis connection
        await r.ping()
        return {
            "status": "healthy",
            "redis": "connected",
            "active_connections": sum(
                len(conns) for conns in connected_clients.values()
            ),
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "redis": "disconnected", "error": str(e)}


@app.on_event("startup")
async def startup_event():
    global http_client
    # Initialize HTTP client with connection limits
    limits = httpx.Limits(max_keepalive_connections=200, max_connections=200)
    http_client = httpx.AsyncClient(limits=limits, http2=True)
    logger.info("HTTP client initialized with 200 connection limit")

    asyncio.create_task(redis_listener())


@app.on_event("shutdown")
async def shutdown_event():
    global http_client
    if http_client:
        await http_client.aclose()
        logger.info("HTTP client closed")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
