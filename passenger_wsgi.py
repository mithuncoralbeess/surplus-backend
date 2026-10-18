import os
import sys
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Reset apps.loading if left dirty from a previous failed load attempt
try:
    from django.apps import apps
    apps.loading = False
    apps.ready = False
except Exception:
    pass

try:
    from django.core.wsgi import get_wsgi_application
    _django_app = get_wsgi_application()

    def application(environ, start_response):
        return _django_app(environ, start_response)
except Exception:
    startup_err = traceback.format_exc()

    def application(environ, start_response):
        status = '500 Internal Server Error'
        output = ('Django Startup Error:\n\n' + startup_err).encode('utf-8')
        response_headers = [('Content-type', 'text/plain; charset=utf-8'), ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]
