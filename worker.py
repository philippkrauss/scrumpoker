"""Custom Gunicorn worker that avoids double monkey-patching.

The main app.py already calls gevent.monkey.patch_all(ssl=False) at import
time, so we just need to make sure the worker doesn't re-patch (especially
ssl).
"""

from geventwebsocket.gunicorn.workers import GeventWebSocketWorker


class JsonPatchedWorker(GeventWebSocketWorker):
    """Worker that skips monkey-patching since app.py already did it."""

    def patch(self):
        # Monkey-patching is already done in app.py (at import time),
        # so we intentionally skip the worker's own patch call.
        pass

