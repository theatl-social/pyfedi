#!/usr/bin/env python3
"""Start the PieFed NNTP bridge server.

Run from the project root with the virtualenv active:

    python run_nntp.py [--host 0.0.0.0] [--port 1119]

The server listens on the given host/port and serves PieFed communities
as NNTP newsgroups.  It shares the same Flask app config and database as
the main PieFed web process, so it must be started in the same environment
(same .env / environment variables, same DATABASE_URL, etc.).

Point your NNTP client (e.g. Thunderbird, tin, slrn) at:
    nntp://localhost:1119

Note: port 1119 is used instead of the privileged default port 119.
"""

import argparse
import logging
import os

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
# Keep SQLAlchemy and other noisy loggers quiet
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
log = logging.getLogger('nntp')


def main():
    parser = argparse.ArgumentParser(description='PieFed NNTP bridge')
    parser.add_argument('--host', default=os.environ.get('NNTP_HOST', '127.0.0.1'),
                        help='Bind address (default: 127.0.0.1, env: NNTP_HOST)')
    parser.add_argument('--port', type=int, default=int(os.environ.get('NNTP_PORT', '1119')),
                        help='Bind port (default: 1119, env: NNTP_PORT)')
    args = parser.parse_args()

    from app import create_app
    from app.nntp.server import PieFedNNTPServer, PieFedNNTPConnectionHandler

    flask_app = create_app()

    log.info("Loading groups from database…")
    server = PieFedNNTPServer(
        flask_app,
        (args.host, args.port),
        PieFedNNTPConnectionHandler,
    )

    domain = flask_app.config.get('SERVER_NAME', 'localhost')
    log.info("PieFed NNTP bridge ready on %s:%d (domain: %s)", args.host, args.port, domain)
    log.info("Connect with:  nntp://%s:%d", args.host, args.port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        server.server_close()


if __name__ == '__main__':
    main()
