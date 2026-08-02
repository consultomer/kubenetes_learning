"""An interactive FastAPI application for learning Kubernetes concepts."""

from __future__ import annotations

import asyncio
import os
import time
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException


APP_DIRECTORY = Path(__file__).resolve().parent


class Settings:
    """Runtime values injected through the Kubernetes Downward API."""

    pod_name = os.getenv("POD_NAME", os.getenv("HOSTNAME", "local-development"))
    pod_namespace = os.getenv("POD_NAMESPACE", "default")
    pod_ip = os.getenv("POD_IP", "unknown")
    node_name = os.getenv("NODE_NAME", "local-machine")
    cluster_name = os.getenv("CLUSTER_NAME", "training-cluster")
    self_service_url = os.getenv("SELF_SERVICE_URL", "").rstrip("/")
    rate_limit_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "8"))
    rate_limit_window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "30"))


settings = Settings()


class SlidingWindowRateLimiter:
    """A deliberately in-memory rate limiter used to demonstrate its limits."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.lock = asyncio.Lock()

    async def check(self, client_key: str) -> tuple[bool, int, int]:
        """Return whether a request is allowed, remaining requests, and reset time."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self.lock:
            recent = [request_time for request_time in self.requests[client_key] if request_time > cutoff]
            self.requests[client_key] = recent
            reset_seconds = max(1, int(self.window_seconds - (now - recent[0]))) if recent else self.window_seconds

            if len(recent) >= self.limit:
                return False, 0, reset_seconds

            recent.append(now)
            self.requests[client_key] = recent
            return True, self.limit - len(recent), reset_seconds


rate_limiter = SlidingWindowRateLimiter(
    limit=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)


def running_in_kubernetes() -> tuple[client.CoreV1Api | None, str | None]:
    """Build an API client from the mounted ServiceAccount, when available."""
    try:
        config.load_incluster_config()
        return client.CoreV1Api(), None
    except ConfigException:
        return None, "No in-cluster ServiceAccount was found. Running in local demo mode."
    except Exception as error:  # Keep the dashboard useful if cluster access is unavailable.
        return None, f"Kubernetes API setup failed: {error}"


def condition_status(conditions: list[Any] | None, condition_type: str) -> bool:
    return any(
        condition.type == condition_type and condition.status == "True"
        for condition in (conditions or [])
    )


def current_identity() -> dict[str, str]:
    return {
        "pod_name": settings.pod_name,
        "namespace": settings.pod_namespace,
        "pod_ip": settings.pod_ip,
        "node_name": settings.node_name,
        "cluster_name": settings.cluster_name,
    }


def collect_cluster_overview(core_api: client.CoreV1Api | None, api_error: str | None) -> dict[str, Any]:
    """Read only non-sensitive cluster information for the learning dashboard."""
    overview: dict[str, Any] = {
        "identity": current_identity(),
        "service_url": settings.self_service_url or "Not configured (local mode)",
        "rate_limit": {
            "requests": settings.rate_limit_requests,
            "window_seconds": settings.rate_limit_window_seconds,
            "scope": "Per client, per application replica (intentionally local memory)",
        },
        "api_access": {"available": False, "message": api_error or "Kubernetes API unavailable"},
        "summary": {"nodes": 0, "pods_in_namespace": 0, "services_in_namespace": 0, "namespaces": 0},
        "nodes": [],
        "pods": [],
        "services": [],
        "namespaces": [],
    }

    if core_api is None:
        return overview

    try:
        nodes = core_api.list_node(_request_timeout=3).items
        pods = core_api.list_namespaced_pod(settings.pod_namespace, _request_timeout=3).items
        services = core_api.list_namespaced_service(settings.pod_namespace, _request_timeout=3).items
        namespaces = core_api.list_namespace(_request_timeout=3).items
    except Exception as error:
        overview["api_access"] = {"available": False, "message": f"Read-only API request failed: {error}"}
        return overview

    overview["api_access"] = {"available": True, "message": "Read-only ServiceAccount access is working."}
    overview["summary"] = {
        "nodes": len(nodes),
        "pods_in_namespace": len(pods),
        "services_in_namespace": len(services),
        "namespaces": len(namespaces),
    }
    overview["nodes"] = [
        {
            "name": node.metadata.name,
            "ready": condition_status(node.status.conditions, "Ready"),
            "architecture": node.status.node_info.architecture,
            "kubelet_version": node.status.node_info.kubelet_version,
            "os_image": node.status.node_info.os_image,
        }
        for node in nodes
    ]
    overview["pods"] = [
        {
            "name": pod.metadata.name,
            "phase": pod.status.phase,
            "node": pod.spec.node_name or "Pending scheduling",
            "pod_ip": pod.status.pod_ip or "Pending",
            "ready": condition_status(pod.status.conditions, "Ready"),
        }
        for pod in sorted(pods, key=lambda item: item.metadata.name)
    ]
    overview["services"] = [
        {
            "name": service.metadata.name,
            "type": service.spec.type,
            "cluster_ip": service.spec.cluster_ip,
            "ports": [
                f"{port.port} → {port.target_port or port.port}" + (f" (NodePort {port.node_port})" if port.node_port else "")
                for port in service.spec.ports
            ],
        }
        for service in sorted(services, key=lambda item: item.metadata.name)
    ]
    overview["namespaces"] = [namespace.metadata.name for namespace in sorted(namespaces, key=lambda item: item.metadata.name)]
    return overview


def response_identity() -> dict[str, Any]:
    return {
        "message": "This response identifies the replica selected by the Kubernetes Service.",
        "served_by": current_identity(),
        "timestamp_unix": int(time.time()),
    }


@asynccontextmanager
async def lifespan(application: FastAPI):
    core_api, api_error = running_in_kubernetes()
    application.state.core_api = core_api
    application.state.api_error = api_error
    yield


app = FastAPI(
    title="Kubernetes Learning Lab",
    description="A hands-on dashboard for exploring Pods, Nodes, Services, load balancing, and rate limiting.",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=APP_DIRECTORY / "static"), name="static")


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(APP_DIRECTORY / "static" / "index.html")


@app.get("/healthz", tags=["Operations"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/overview", tags=["Cluster"])
async def overview(request: Request) -> dict[str, Any]:
    return await run_in_threadpool(collect_cluster_overview, request.app.state.core_api, request.app.state.api_error)


@app.get("/api/whoami", tags=["Experiments"])
async def whoami() -> dict[str, Any]:
    return response_identity()


@app.get("/api/lab/load-balance", tags=["Experiments"])
async def load_balance(requests: int = Query(default=12, ge=1, le=300)) -> dict[str, Any]:
    """Call this app through its ClusterIP Service using new connections."""
    if not settings.self_service_url:
        raise HTTPException(
            status_code=400,
            detail="Load-balancing lab is available only in Kubernetes. Set SELF_SERVICE_URL to the Service DNS name.",
        )

    responses: list[dict[str, Any]] = []
    timeout = httpx.Timeout(3.0)
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=0)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, headers={"Connection": "close"}) as http_client:
        for request_number in range(1, requests + 1):
            try:
                response = await http_client.get(f"{settings.self_service_url}/api/whoami")
                response.raise_for_status()
                payload = response.json()
                responses.append({"request": request_number, "pod": payload["served_by"]["pod_name"], "node": payload["served_by"]["node_name"]})
            except (httpx.HTTPError, KeyError, ValueError) as error:
                responses.append({"request": request_number, "error": str(error)})

    replica_counts = Counter(result["pod"] for result in responses if "pod" in result)
    return {
        "service_url": settings.self_service_url,
        "requests_sent": requests,
        "replica_counts": dict(replica_counts),
        "responses": responses,
        "lesson": "A Kubernetes Service chooses endpoints per connection. Counts vary; the goal is to observe more than one replica over repeated new connections.",
    }


@app.get("/api/lab/rate-limit", tags=["Experiments"])
async def rate_limit(request: Request, response: Response) -> dict[str, Any]:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    client_address = forwarded_for or (request.client.host if request.client else "unknown")
    allowed, remaining, reset_seconds = await rate_limiter.check(client_address)
    headers = {
        "X-RateLimit-Limit": str(settings.rate_limit_requests),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset-Seconds": str(reset_seconds),
        "X-RateLimit-Replica": settings.pod_name,
    }
    for name, value in headers.items():
        response.headers[name] = value

    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for this replica. Wait for the reset window.", headers=headers)

    return {
        "allowed": True,
        "served_by": current_identity(),
        "remaining": remaining,
        "reset_seconds": reset_seconds,
        "lesson": "This limiter is intentionally stored in each Pod's memory. Requests sent to another replica have a different counter. Production rate limits use shared storage or an API gateway.",
    }
