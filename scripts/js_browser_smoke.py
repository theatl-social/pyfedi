"""Load real pages in headless Chrome and check the site's JavaScript ran.

Why this exists: the v1.8.11 merge (PR #107) auto-merged app/static/js/scripts.js
into a file with a syntax error. Git reported no conflict, every Python test and
template check passed, the image built, and in production the 3-line mobile
menu and the mobile Subscribed/Local/Popular/All filter dropdown stopped
working, because the browser refused to run any of scripts.js.

This script serves the app on SQLite, opens pages at phone width in headless
Chrome, and fails if:
  * the console shows an uncaught error, or a setup that runSetups() caught
    and logged as "<name>() failed:", or
  * setupMobileNav() didn't run. base.html renders the toggler with
    aria-expanded="true"; setupMobileNav() sets it to "false" on narrow
    screens, so the attribute shows whether scripts.js got as far as its setups.

Usage:  uv run python scripts/js_browser_smoke.py [--chrome PATH]
Needs Google Chrome/Chromium (preinstalled on GitHub's ubuntu runners).
"""

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
PAGES = ["/auth/login", "/auth/register"]
PORT = 5057

CHROME_CANDIDATES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_chrome(explicit):
    if explicit:
        return explicit
    for c in CHROME_CANDIDATES:
        path = shutil.which(c) or (c if os.path.exists(c) else None)
        if path:
            return path
    sys.exit("js_browser_smoke: no Chrome/Chromium found; pass --chrome")


def start_server(db_path):
    os.environ.update(
        SERVER_NAME=f"127.0.0.1:{PORT}",
        DATABASE_URL=f"sqlite:///{db_path}",
        CACHE_TYPE="NullCache",
        SECRET_KEY=os.environ.get("SECRET_KEY")
        or "js-smoke-secret-key-padding-32-plus-chars",
    )
    sys.path[:0] = [str(REPO), str(REPO / "tests")]
    import app as _app  # noqa: F401  (breaks the config<->app import cycle)
    from conftest import create_all_for_tests
    from pyfedi import app
    from app import db
    from app.models import Site
    from werkzeug.serving import make_server

    with app.app_context():
        create_all_for_tests(db)
        if not db.session.get(Site, 1):
            db.session.add(Site(id=1, name="Smoke", registration_mode="Open"))
            db.session.commit()

    print("READY", flush=True)
    make_server("127.0.0.1", PORT, app, threaded=True).serve_forever()


def spawn_server(db_path):
    """Run the app in a child process. In-process, Chrome's page load hung."""
    proc = subprocess.Popen(
        [sys.executable, __file__, "--serve", db_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = []
    deadline = time.time() + 120
    for line in proc.stdout:
        output.append(line)
        if line.strip() == "READY":
            threading.Thread(
                target=proc.stdout.read, daemon=True
            ).start()  # keep the pipe drained
            return proc
        if time.time() > deadline:
            break
    proc.kill()
    sys.exit("js_browser_smoke: server did not start:\n" + "".join(output[-40:]))


def load(chrome, url, profile):
    """Return (dom, chrome_log) for one page load.

    Chrome prints the DOM once the page has loaded, then shuts down. On macOS
    the shutdown sometimes stalls (a "teardown watchdog" exit, or a hang), so
    after the timeout Chrome is killed and whatever it already printed is used.
    One retry, with a fresh profile, if no DOM came back at all.
    """
    for attempt in range(2):
        with tempfile.TemporaryFile("w+") as log:
            proc = subprocess.Popen(
                [
                    chrome,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    f"--user-data-dir={profile}-{attempt}",
                    "--window-size=390,844",
                    "--enable-logging=stderr",
                    "--v=0",
                    "--dump-dom",
                    url,
                ],
                stdout=subprocess.PIPE,
                stderr=log,
                text=True,
            )
            try:
                dom, _ = proc.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                dom, _ = proc.communicate()
            log.seek(0)
            chrome_log = log.read()
        if "</html>" in dom:
            return dom, chrome_log
    return dom, chrome_log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome")
    ap.add_argument("--serve", metavar="DB_PATH", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.serve:
        return start_server(args.serve)
    chrome = find_chrome(args.chrome)

    work = tempfile.mkdtemp(prefix="js-smoke-")
    server = spawn_server(os.path.join(work, "smoke.db"))
    failures = []
    try:
        for page in PAGES:
            url = f"http://127.0.0.1:{PORT}{page}"
            profile = os.path.join(work, "profile-" + page.strip("/").replace("/", "-"))
            dom, log = load(chrome, url, profile)
            errors = [
                ln
                for ln in log.splitlines()
                if "CONSOLE" in ln and ("Uncaught" in ln or "() failed:" in ln)
            ]
            toggler = re.search(r'<button[^>]*id="navbar-toggler"[^>]*>', dom)
            if not toggler:
                failures.append(
                    f"{page}: navbar-toggler missing from rendered DOM (page didn't render?)"
                )
            elif 'aria-expanded="false"' not in toggler.group(0):
                failures.append(
                    f"{page}: setupMobileNav() did not run - scripts.js failed before its setups"
                )
            for e in errors:
                failures.append(f"{page}: {e.strip()}")
            print(
                f"{page}: {'FAIL' if any(f.startswith(page + ':') for f in failures) else 'ok'}"
            )
    finally:
        server.kill()
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("\nBrowser JavaScript smoke test FAILED:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("Browser JavaScript smoke test passed.")


if __name__ == "__main__":
    main()
