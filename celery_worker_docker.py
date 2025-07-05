#!/usr/bin/env python
import os
from app import celery, create_app

app = create_app()
app.app_context().push()

# Import tasks to register them with Celery
from app.shared.tasks import maintenance
