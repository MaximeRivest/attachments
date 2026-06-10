"""Gunicorn entry point with build-in warmup.

With ``gunicorn --preload wsgi:app`` this module is imported ONCE in the
gunicorn master process. The warmup (processor imports + one tiny OCR
inference) therefore runs before any worker forks, and every worker shares
the warm engines via copy-on-write fork memory.
"""

import warmup

warmup.main()

from attachments.server import create_app  # noqa: E402

app = create_app()
