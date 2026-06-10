"""
PoUW CAPTCHA Server - Main Application

FastAPI application entry point with middleware, routes, and lifecycle management.
"""

import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.exceptions import RequestValidationError

from app.config import get_settings
from app.api import captcha, verification, federated, metrics, sites
from app.api.captcha import inference_log  # Import shared inference log
from app.models import init_db, close_db
from app.utils.redis_client import init_redis, close_redis

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
DEMO_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "demo" / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown."""
    # Startup
    logger.info("Starting PoUW CAPTCHA Server...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Initialize Redis
    await init_redis()
    logger.info("Redis initialized")

    yield

    # Shutdown
    logger.info("Shutting down PoUW CAPTCHA Server...")

    await close_db()
    await close_redis()

    logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="PoUW CAPTCHA API",
    description="Proof-of-Useful-Work CAPTCHA System API",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
        },
    )


# Validation error handler - DETAILED LOGGING
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors with detailed logging."""
    logger.error("=" * 80)
    logger.error(f"VALIDATION ERROR on {request.method} {request.url.path}")
    logger.error("=" * 80)
    
    # Log the raw body if possible
    try:
        body = await request.body()
        body_str = body.decode('utf-8')
        logger.error(f"Raw request body:\n{body_str}")
        
        # Try to parse and pretty-print
        try:
            body_json = json.loads(body_str)
            logger.error(f"Parsed JSON structure:")
            for key, value in body_json.items():
                if isinstance(value, dict):
                    logger.error(f"  {key}: {{dict with keys: {list(value.keys())}}}")
                elif isinstance(value, list):
                    logger.error(f"  {key}: [list with {len(value)} items]")
                else:
                    logger.error(f"  {key}: {type(value).__name__} = {str(value)[:100]}")
        except json.JSONDecodeError:
            pass
    except Exception as e:
        logger.error(f"Could not read body: {e}")
    
    # Log each validation error in detail
    logger.error(f"\nValidation Errors ({len(exc.errors())} total):")
    for i, error in enumerate(exc.errors(), 1):
        loc = " -> ".join(str(x) for x in error.get("loc", []))
        logger.error(f"  Error {i}:")
        logger.error(f"    Location: {loc}")
        logger.error(f"    Type: {error.get('type')}")
        logger.error(f"    Message: {error.get('msg')}")
        logger.error(f"    Input: {str(error.get('input'))[:200]}")
    
    logger.error("=" * 80)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": exc.errors(),
        },
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for load balancers."""
    return {"status": "healthy", "version": "0.1.0"}


# Ready check endpoint
@app.get("/ready", tags=["Health"])
async def ready_check():
    """Readiness check: verifies DB, Redis and model store connectivity."""
    from sqlalchemy import text
    from app.models.base import engine
    from app.utils.redis_client import get_redis
    from app.ml.model_store import get_model_store

    checks = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    try:
        models = get_model_store().list_models()
        checks["models"] = f"ok ({len(models)} loaded)"
    except Exception as exc:
        checks["models"] = f"error: {exc}"

    all_ok = all(v.startswith("ok") for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )


# Include API routers
app.include_router(captcha.router, prefix="/api/v1", tags=["CAPTCHA"])
app.include_router(verification.router, prefix="/api/v1", tags=["Verification"])
app.include_router(federated.router, prefix="/api/v1", tags=["Federated Learning"])
app.include_router(metrics.router, prefix="/api/v1", tags=["Metrics"])
app.include_router(sites.router, prefix="/api/v1", tags=["Sites"])


# Root endpoint
@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint."""
    return {
        "name": "PoUW CAPTCHA API",
        "version": "0.1.0",
        "docs": "/docs" if settings.debug else None,
    }


@app.get("/demo", include_in_schema=False)
async def demo_frontend():
    """Serve the interactive demo frontend."""
    return FileResponse(DEMO_FRONTEND_DIR / "index.html")


# API endpoint for inference data
@app.get("/api/v1/inferences")
async def get_inferences(limit: int = 100):
    """Get inference log data as JSON."""
    return {
        "inferences": inference_log[-limit:][::-1],  # Most recent first
        "total": len(inference_log),
    }


# ML Inference Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """ML Inference Dashboard - Shows all image classifications done."""
    from datetime import datetime
    
    # Calculate stats
    total = len(inference_log)
    valid_count = sum(1 for i in inference_log if i.get("is_valid", False))
    accuracy = (valid_count / total * 100) if total > 0 else 0
    avg_inference_ms = sum(i.get("inference_ms", 0) for i in inference_log) / total if total > 0 else 0
    avg_confidence = sum(i.get("confidence", 0) for i in inference_log) / total if total > 0 else 0
    # Build inference rows HTML
    inference_rows = ""
    for i, inf in enumerate(reversed(inference_log[-50:])):  # Show last 50
        valid_badge = '<span class="badge valid">Valid</span>' if inf.get("is_valid") else '<span class="badge invalid">Invalid</span>'
        
        # Top-K predictions
        top_k_html = ""
        for pred in inf.get("top_k", [])[:3]:
            top_k_html += f'<div class="topk-item"><span>{pred["label"]}</span><span>{pred["confidence"]:.1%}</span></div>'
        
        # Image display
        img_url = inf.get("image_url") or "https://via.placeholder.com/60x60?text=?"
        
        inference_rows += f'''
        <tr>
            <td>#{total - i}</td>
            <td><img src="{img_url}" alt="sample" class="sample-img" onerror="this.src='https://via.placeholder.com/60x60?text=?'"></td>
            <td><strong>{inf.get("predicted_label", "?")}</strong></td>
            <td>
                <div class="confidence-bar">
                    <div class="confidence-fill" style="width: {inf.get("confidence", 0) * 100}%"></div>
                    <span>{inf.get("confidence", 0):.1%}</span>
                </div>
            </td>
            <td>{valid_badge}</td>
            <td>{inf.get("inference_ms", 0)}ms</td>
            <td class="topk-cell">{top_k_html}</td>
            <td class="timestamp">{inf.get("timestamp", "")[:19]}</td>
        </tr>
        '''
    
    if not inference_rows:
        inference_rows = '<tr><td colspan="8" class="empty">No inferences yet. Use the frontend to submit CAPTCHA challenges!</td></tr>'
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>ML Inference Dashboard - PoUW CAPTCHA</title>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="5">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Sora:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #f3ebdf;
                --panel: rgba(255, 250, 244, 0.9);
                --panel-strong: #f1e5d6;
                --line: rgba(113, 82, 59, 0.14);
                --ink: #3e3023;
                --ink-soft: #6d5947;
                --ink-faint: #9b846d;
                --accent: #94684a;
                --accent-dark: #704c33;
                --accent-soft: #e4cfb8;
                --success: #50795a;
                --danger: #a55e57;
                --shadow: 0 24px 70px rgba(96, 68, 42, 0.12);
            }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: 'Sora', sans-serif;
                color: var(--ink);
                min-height: 100vh;
                padding: 22px;
                background:
                    radial-gradient(circle at 14% 16%, rgba(219, 188, 152, 0.32), transparent 24%),
                    radial-gradient(circle at 86% 18%, rgba(177, 136, 96, 0.18), transparent 22%),
                    linear-gradient(180deg, #f8f2e8 0%, #f1e7d9 100%);
            }}
            body::before {{
                content: '';
                position: fixed;
                inset: 0;
                background-image:
                    linear-gradient(rgba(113, 82, 59, 0.05) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(113, 82, 59, 0.05) 1px, transparent 1px);
                background-size: 72px 72px;
                pointer-events: none;
                mask-image: radial-gradient(circle at center, black 56%, transparent 92%);
            }}
            .container {{
                position: relative;
                z-index: 1;
                max-width: 1400px;
                margin: 0 auto;
            }}
            h1 {{
                font-family: 'Instrument Serif', serif;
                font-size: clamp(2.4rem, 3.6vw, 3.4rem);
                margin-bottom: 8px;
                color: var(--accent-dark);
                letter-spacing: -0.05em;
                line-height: 0.95;
            }}
            .subtitle {{ color: var(--ink-soft); margin-bottom: 24px; }}
            .header-row {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                gap: 16px;
                margin-bottom: 24px;
            }}
            .api-note {{
                background:
                    linear-gradient(180deg, rgba(255, 255, 255, 0.55), transparent 22%),
                    var(--panel);
                padding: 12px 16px;
                border-radius: 14px;
                font-size: 12px;
                color: var(--ink-soft);
                border: 1px solid var(--line);
                box-shadow: var(--shadow);
            }}
            .api-note code {{
                background: var(--panel-strong);
                padding: 2px 6px;
                border-radius: 6px;
                color: var(--accent-dark);
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }}
            .stat-card {{
                background:
                    linear-gradient(180deg, rgba(255, 255, 255, 0.55), transparent 22%),
                    var(--panel);
                border-radius: 18px;
                padding: 20px;
                border: 1px solid var(--line);
                box-shadow: var(--shadow);
            }}
            .stat-label {{
                color: var(--ink-faint);
                font-size: 13px;
                margin-bottom: 4px;
            }}
            .stat-value {{
                font-size: 32px;
                font-weight: 700;
                color: var(--ink);
            }}
            .stat-value.green {{ color: var(--success); }}
            .stat-value.blue {{ color: var(--accent-dark); }}
            .stat-value.purple {{ color: #7b6c93; }}
            .stat-value.orange {{ color: #a97a47; }}
            .table-container {{
                background:
                    linear-gradient(180deg, rgba(255, 255, 255, 0.55), transparent 22%),
                    var(--panel);
                border-radius: 18px;
                border: 1px solid var(--line);
                overflow: hidden;
                box-shadow: var(--shadow);
            }}
            .table-header {{
                padding: 16px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 16px;
                border-bottom: 1px solid var(--line);
            }}
            .table-header h2 {{ font-size: 18px; }}
            .refresh-note {{
                color: var(--ink-faint);
                font-size: 12px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th, td {{
                padding: 12px 16px;
                text-align: left;
                border-bottom: 1px solid rgba(113, 82, 59, 0.08);
                vertical-align: middle;
            }}
            th {{
                background: rgba(241, 229, 214, 0.82);
                color: var(--ink-faint);
                font-weight: 500;
                font-size: 12px;
                text-transform: uppercase;
            }}
            tbody tr:hover {{
                background: rgba(255, 253, 249, 0.72);
            }}
            .sample-img {{
                width: 50px;
                height: 50px;
                border-radius: 10px;
                object-fit: cover;
            }}
            .confidence-bar {{
                width: 100px;
                height: 20px;
                position: relative;
                overflow: hidden;
                border-radius: 6px;
                background: rgba(113, 82, 59, 0.1);
            }}
            .confidence-fill {{
                height: 100%;
                border-radius: 6px;
                background: linear-gradient(90deg, var(--accent), #c89c72);
            }}
            .confidence-bar span {{
                position: absolute;
                left: 50%;
                top: 50%;
                transform: translate(-50%, -50%);
                font-size: 11px;
                font-weight: 700;
                color: var(--ink);
            }}
            .badge {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
            }}
            .badge.valid {{ background: rgba(80, 121, 90, 0.14); color: var(--success); }}
            .badge.invalid {{ background: rgba(165, 94, 87, 0.14); color: var(--danger); }}
            .topk-cell {{ min-width: 150px; }}
            .topk-item {{
                display: flex;
                justify-content: space-between;
                font-size: 11px;
                color: var(--ink-soft);
                padding: 2px 0;
            }}
            .timestamp {{
                font-size: 11px;
                color: var(--ink-faint);
                font-family: monospace;
            }}
            .empty {{
                text-align: center;
                padding: 40px;
                color: var(--ink-faint);
            }}
            @media (max-width: 820px) {{
                .header-row {{
                    flex-direction: column;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-row">
                <div>
                    <h1>ML Inference Dashboard</h1>
                    <p class="subtitle">Real-time visibility into CAPTCHA image classifications</p>
                </div>
                <div class="api-note">
                    API: <code>GET /api/v1/inferences</code> | Auto-refresh: 5s
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total Inferences</div>
                    <div class="stat-value blue">{total}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Verified Rate</div>
                    <div class="stat-value green">{accuracy:.1f}%</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Average Latency</div>
                    <div class="stat-value purple">{avg_inference_ms:.0f}ms</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Average Confidence</div>
                    <div class="stat-value orange">{avg_confidence:.1%}</div>
                </div>
            </div>
            
            <div class="table-container">
                <div class="table-header">
                    <h2>Recent Image Classifications</h2>
                    <span class="refresh-note">Showing last 50 | Auto-refreshes every 5 seconds</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Image</th>
                            <th>Predicted Label</th>
                            <th>Confidence</th>
                            <th>Valid</th>
                            <th>Time</th>
                            <th>Top-K Predictions</th>
                            <th>Timestamp</th>
                        </tr>
                    </thead>
                    <tbody>
                        {inference_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    '''
    return html


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
