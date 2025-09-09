#!/usr/bin/env python
import os

from app import celery, create_app

app = create_app()
app.app_context().push()

# Import all task modules to register them with Celery
from app.shared.tasks import (
    adds,
    blocks,
    deletes,
    flags,
    follows,
    groups,
    likes,
    locks,
    maintenance,
    notes,
    pages,
    removes,
    users,
)
