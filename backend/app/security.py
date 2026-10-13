"""Safe API diagnostics: never include raw payloads or exception text."""
import logging
import time
from uuid import uuid4
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger('pesopilot.security')


class BodyLimit:
    """Bound total request bytes before multipart parsing or JSON decoding."""
    def __init__(self, app, limit=2_000_000):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > self.limit:
                return await JSONResponse({'detail': 'Request exceeds 2 MB'}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        body, replayed = b''.join(chunks), False
        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)


def install_security(app):
    app.add_middleware(BodyLimit)
    @app.middleware('http')
    async def privacy_headers(request, call_next):
        request.state.request_id = str(uuid4())
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # Do not log str(exc), request URLs, query strings, cookies or bodies.
            logger.error('request_failed request_id=%s', request.state.request_id)
            response = JSONResponse({'detail': 'Internal server error', 'request_id': request.state.request_id}, status_code=500)
        response.headers.update({
            'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
            'X-Request-ID': request.state.request_id,
        })
        logger.info('request_completed request_id=%s status=%d elapsed_ms=%d', request.state.request_id, response.status_code, (time.monotonic() - started) * 1000)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic input/ctx/message may embed private values. Expose field names only.
        errors = [{'loc': list(e['loc']), 'type': e['type']} for e in exc.errors()]
        return JSONResponse({'detail': 'Invalid request fields', 'errors': errors, 'request_id': request.state.request_id}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logger.error('database_unavailable request_id=%s', request.state.request_id)
        return JSONResponse({'detail': 'Database operation unavailable; retry safely', 'request_id': request.state.request_id}, status_code=503)
