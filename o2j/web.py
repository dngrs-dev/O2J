"""Serve the local browser workbench and one PDF analysis endpoint."""

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlsplit

from .pdf import DocumentError
from .pipeline import Pipeline

STATIC = Path(__file__).with_name('static')
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
}
MAX_UPLOAD = 50 * 1024 * 1024


def serve(pipeline: Pipeline, host: str, port: int) -> None:
    slots = BoundedSemaphore(4)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status: HTTPStatus, content: bytes, media_type: str, **headers) -> None:
            self.send_response(status)
            self.send_header('Content-Type', media_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
            for name, value in headers.items():
                self.send_header(name.replace('_', '-'), str(value))
            self.end_headers()
            self.wfile.write(content)

        def json_response(self, status: HTTPStatus, value: dict) -> None:
            self.reply(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode(),
                       'application/json; charset=utf-8')

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == '/api/status':
                self.json_response(HTTPStatus.OK, {
                    'model': pipeline.model.model if pipeline.model else None,
                    'classes': [spec.label for spec in pipeline.classes.values()],
                    'max_upload': MAX_UPLOAD,
                })
            elif path in ASSETS:
                filename, media_type = ASSETS[path]
                self.reply(HTTPStatus.OK, (STATIC / filename).read_bytes(), media_type)
            else:
                self.json_response(HTTPStatus.NOT_FOUND, {'error': 'Nie znaleziono zasobu.'})

        def do_POST(self) -> None:
            route = urlsplit(self.path)
            if route.path not in {'/api/analyze', '/api/preview'}:
                self.json_response(HTTPStatus.NOT_FOUND, {'error': 'Nie znaleziono zasobu.'})
                return
            origin = self.headers.get('Origin')
            allowed_origins = {f'http://{name}:{port}' for name in ('127.0.0.1', 'localhost')}
            if origin and origin not in allowed_origins:
                self.json_response(HTTPStatus.FORBIDDEN, {'error': 'Nieprawidłowe pochodzenie żądania.'})
                return
            if self.headers.get_content_type() != 'application/pdf':
                self.json_response(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {'error': 'Wybierz dokument PDF.'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                size = 0
            if not 0 < size <= MAX_UPLOAD:
                self.json_response(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                                   {'error': 'Plik PDF musi mieć od 1 bajtu do 50 MB.'})
                return
            if not slots.acquire(blocking=False):
                self.json_response(HTTPStatus.SERVICE_UNAVAILABLE,
                                   {'error': 'Trwa analiza innych dokumentów. Spróbuj ponownie za chwilę.'})
                return
            try:
                self.connection.settimeout(20)
                raw = self.rfile.read(size)
                if len(raw) != size or b'%PDF-' not in raw[:1024]:
                    self.json_response(HTTPStatus.BAD_REQUEST, {'error': 'Plik nie jest poprawnym dokumentem PDF.'})
                    return
                if route.path == '/api/preview':
                    try:
                        page = int(parse_qs(route.query).get('page', ['1'])[0])
                    except ValueError:
                        self.json_response(HTTPStatus.BAD_REQUEST, {'error': 'Podaj numer strony PDF.'})
                        return
                    image, total = pipeline.reader.preview(raw, page)
                    self.reply(HTTPStatus.OK, image, 'image/png', X_PDF_Pages=total)
                else:
                    result = pipeline.process(raw, trace=True)
                    self.json_response(HTTPStatus.OK, result.as_dict())
            except DocumentError as exc:
                self.json_response(HTTPStatus.UNPROCESSABLE_CONTENT, {'error': str(exc)})
            except (TimeoutError, ConnectionError):
                return
            finally:
                slots.release()

    with ThreadingHTTPServer((host, port), Handler) as server:
        print(f'Odwołania2JSON • http://127.0.0.1:{port}', flush=True)
        server.serve_forever()
