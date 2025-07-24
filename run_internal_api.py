#!/usr/bin/env python3
"""
Entrypoint to run the internal API as a standalone Flask service.
"""
import os
from flask import Flask
from app import db
from app.internal_api import internal_bp


app = Flask(__name__)
app.config.from_object('config.Config')

# Initialize db with app
with app.app_context():
    db.init_app(app)

app.register_blueprint(internal_bp)

if __name__ == "__main__":
    port = int(os.environ.get("INTERNAL_API_PORT", 5932))
    app.run(host="0.0.0.0", port=port)
