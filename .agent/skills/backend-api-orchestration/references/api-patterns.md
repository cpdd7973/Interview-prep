---
name: api-patterns
description: Rate limiting, request validation middleware, error handling, health checks, and OpenAPI spec patterns for Python FastAPI and Node.js Fastify backends serving LLM-powered applications.
---

# API Patterns Reference

Production-hardening patterns for the interview agent backend.

---

## Rate Limiting

Per-session and per-IP rate limiting using Redis sliding window.

```python
# FastAPI — Redis sliding window rate limiter
import time
from fastapi import Request, HTTPException

async def rate_limit(
    request: Request,
    key_prefix: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    """Sliding window rate limiter using Redis sorted sets."""
    identifier = (
        request.headers.get("X-Session-Id")
        or request.client.host
        or "anonymous"
    )
    key = f"rate:{key_prefix}:{identifier}"
    now = time.time()
    window_start = now - window_seconds

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)       # Remove old entries
    pipe.zadd(key, {str(now): now})                   # Add current request
    pipe.zcard(key)                                   # Count in window
    pipe.expire(key, window_seconds + 1)
    results = await pipe.execute()

    count = results[2]
    if count > max_requests:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "RATE_LIMITED",
                "retry_after": window_seconds,
                "limit": max_requests,
                "window": window_seconds,
            },
            headers={"Retry-After": str(window_seconds)},
        )


# Apply to message submission endpoint
@app.post("/sessions/{session_id}/messages")
async def submit_message(request: Request, ...):
    await rate_limit(request, "messages", max_requests=20, window_seconds=60)
    ...
```

```typescript
// Fastify — rate limiting with @fastify/rate-limit
import rateLimit from '@fastify/rate-limit'

await app.register(rateLimit, {
  global: false,  // Apply selectively per route
  redis: redisConnection,
  keyGenerator: (request) => {
    // Rate limit by session ID if present, fall back to IP
    return request.headers['x-session-id'] as string
      || request.ip
  },
  errorResponseBuilder: (request, context) => ({
    error: 'RATE_LIMITED',
    retryAfter: context.after,
    limit: context.max,
  }),
})

// Apply to message endpoint only
app.post('/sessions/:sessionId/messages', {
  config: {
    rateLimit: { max: 20, timeWindow: '1 minute' }
  },
  ...
})
```

---

## Request Validation Middleware

```python
# FastAPI — global validation error handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append({
            "field":   ".".join(str(loc) for loc in error["loc"][1:]),
            "message": error["msg"],
            "type":    error["type"],
        })

    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "errors": errors,
        }
    )


# Global exception handler — catch unhandled errors before they leak stack traces
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")

    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            # Never expose exc details in production
        }
    )
```

```typescript
// Fastify — global error handler
app.setErrorHandler((error, request, reply) => {
  // Validation errors
  if (error.validation) {
    return reply.code(422).send({
      error: 'VALIDATION_ERROR',
      errors: error.validation.map(v => ({
        field: v.instancePath.replace('/', ''),
        message: v.message,
      })),
    })
  }

  // Known HTTP errors
  if (error.statusCode) {
    return reply.code(error.statusCode).send({
      error: error.code ?? 'HTTP_ERROR',
      message: error.message,
    })
  }

  // Unknown errors — log and return generic 500
  request.log.error(error)
  return reply.code(500).send({
    error: 'INTERNAL_ERROR',
    message: 'An unexpected error occurred',
  })
})
```

---

## Health Check Endpoints

```python
# FastAPI health check with dependency checks
from enum import Enum

class HealthStatus(str, Enum):
    HEALTHY   = "healthy"
    DEGRADED  = "degraded"
    UNHEALTHY = "unhealthy"

@app.get("/health", tags=["ops"])
async def health_check():
    checks = await asyncio.gather(
        check_redis(),
        check_database(),
        check_llm_connectivity(),
        return_exceptions=True,
    )

    results = {
        "redis":    _format_check(checks[0]),
        "database": _format_check(checks[1]),
        "llm":      _format_check(checks[2]),
    }

    all_healthy  = all(r["status"] == "ok" for r in results.values())
    any_critical = any(r["critical"] and r["status"] != "ok"
                       for r in results.values())

    overall = (
        HealthStatus.HEALTHY   if all_healthy else
        HealthStatus.UNHEALTHY if any_critical else
        HealthStatus.DEGRADED
    )

    status_code = 200 if overall != HealthStatus.UNHEALTHY else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "checks": results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

async def check_redis() -> dict:
    try:
        await redis.ping()
        return {"status": "ok", "critical": True}
    except Exception as e:
        return {"status": "error", "error": str(e), "critical": True}

async def check_llm_connectivity() -> dict:
    """Non-critical — degraded but operational if LLM is slow."""
    try:
        start = time.monotonic()
        # Lightweight check — don't generate tokens
        await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"status": "ok", "latency_ms": latency_ms, "critical": False}
    except Exception as e:
        return {"status": "error", "error": str(e), "critical": False}
```

---

## OpenAPI Spec Patterns

Good OpenAPI documentation saves your frontend team hours of guesswork.

```python
# FastAPI — enrich OpenAPI with examples and response schemas
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title="Interview Agent API",
        version="1.0.0",
        description="""
## Authentication
All session endpoints require a `Bearer {token}` header.
Tokens are issued on session creation and expire when the session ends.

## Streaming
Use `/sessions/{id}/stream` for real-time SSE or connect via WebSocket at `/ws/{id}`.
        """,
        routes=app.routes,
    )

    # Add security scheme
    schema["components"]["securitySchemes"] = {
        "SessionToken": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }

    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi


# Enrich individual endpoints with examples
@app.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=201,
    summary="Create a new interview session",
    responses={
        201: {
            "description": "Session created",
            "content": {
                "application/json": {
                    "example": {
                        "session_id": "550e8400-e29b-41d4-a716-446655440000",
                        "token": "eyJhbGciOiJIUzI1NiJ9...",
                        "expires_at": "2025-02-27T16:00:00Z",
                        "websocket_url": "wss://api.example.com/ws/550e8400...",
                    }
                }
            }
        },
        401: {"description": "Invalid API key"},
        422: {"description": "Validation error"},
    }
)
async def create_session(...): ...
```

---

## CORS Configuration

```python
# FastAPI
from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    "https://app.example.com",
    "https://staging.example.com",
    # "http://localhost:3000",  # Add for local dev via env var
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Session-Id"],
    expose_headers=["X-Request-Id"],
    max_age=3600,  # Cache preflight for 1 hour
)
```

```typescript
// Fastify
import cors from '@fastify/cors'

await app.register(cors, {
  origin: (origin, callback) => {
    const allowed = process.env.ALLOWED_ORIGINS?.split(',') ?? []
    if (!origin || allowed.includes(origin)) {
      callback(null, true)
    } else {
      callback(new Error('Not allowed by CORS'), false)
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Authorization', 'Content-Type', 'X-Session-Id'],
})
```

---

## Request ID Middleware

Every request needs a traceable ID. Essential for debugging distributed systems.

```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())

        # Make available to handlers
        request.state.request_id = request_id

        # Add to structured logs
        with logger.contextualize(request_id=request_id):
            response = await call_next(request)

        response.headers["X-Request-Id"] = request_id
        return response

app.add_middleware(RequestIdMiddleware)
```

```typescript
// Fastify request ID is built-in — just configure it
const app = Fastify({
  logger: {
    level: 'info',
    serializers: {
      req: (req) => ({
        method: req.method,
        url: req.url,
        requestId: req.id,
        sessionId: req.headers['x-session-id'],
      }),
    },
  },
  genReqId: () => crypto.randomUUID(),
})

// Add request ID to all responses
app.addHook('onSend', async (request, reply) => {
  reply.header('X-Request-Id', request.id)
})
```

---

## Security Headers

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.update({
            "X-Content-Type-Options":    "nosniff",
            "X-Frame-Options":           "DENY",
            "X-XSS-Protection":          "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy":           "strict-origin-when-cross-origin",
            "Permissions-Policy":        "camera=(), microphone=(), geolocation=()",
        })
        # Remove server fingerprinting
        response.headers.pop("Server", None)
        return response

app.add_middleware(SecurityHeadersMiddleware)
```
