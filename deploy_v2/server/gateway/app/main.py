from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.config import load_config


ROOT_CONFIG = load_config()
CONFIG = ROOT_CONFIG["gateway"]
SERVICES = ROOT_CONFIG["services"]
ROUTES = CONFIG["routes"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=CONFIG["request_timeout"])
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(title="AIGC API Gateway", version="2.0.0", lifespan=lifespan)


@app.exception_handler(httpx.HTTPError)
async def handle_service_error(_request: Request, exc: httpx.HTTPError):
    return JSONResponse(
        status_code=502,
        content={"detail": f"内部模型服务连接失败: {exc}"},
    )


@app.get("/health")
async def health(request: Request):
    status = {}
    for name, service in SERVICES.items():
        try:
            response = await request.app.state.http.get(
                f"{service['base_url']}/health"
            )
            status[name] = response.is_success
        except httpx.HTTPError:
            status[name] = False
    return {
        "status": "ok" if all(status.values()) else "degraded",
        "services": status,
    }


@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    api_path = f"/v1/{path}"
    service_name = next(
        (
            ROUTES[prefix]
            for prefix in sorted(ROUTES, key=len, reverse=True)
            if api_path == prefix or api_path.startswith(f"{prefix}/")
        ),
        None,
    )
    if service_name is None:
        raise HTTPException(status_code=404, detail="未配置该 API 路由")

    response = await request.app.state.http.request(
        method=request.method,
        url=f"{SERVICES[service_name]['base_url']}{api_path}",
        params=request.query_params,
        content=await request.body(),
        headers={"content-type": request.headers.get("content-type", "application/json")},
    )
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type"),
    )
