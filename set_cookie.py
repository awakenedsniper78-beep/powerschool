"""
Borrow your browser's session so the scrape can get past the bot protection.

    python set_cookie.py

The portal sits behind Imperva, which challenges automated sign-ins. Your browser has
already passed that challenge, and the proof is a cookie called JSESSIONID. Pasting it
here lets the scrape reuse the session your browser already established, instead of
trying to log in on its own.

It expires -- hours to a few days -- and then the sync starts failing and the site shows
its stale warning. Run this again to hand it a fresh one.

Where to find it (Chrome or Edge on Windows):
  1. Sign in to the portal in your browser so you can see your grades.
  2. Press F12 to open DevTools.
  3. Go to the Application tab (>> if it's hidden).
  4. In the left sidebar: Storage -> Cookies -> the portal's address.
  5. Find the row named JSESSIONID and copy the long value next to it.

Safari on Mac: enable Develop in Settings -> Advanced, then Develop -> Show Web
Inspector -> Storage -> Cookies.
"""

import getpass
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env")

# JSESSIONID values are long hex-ish strings, sometimes with a .node suffix. Catching an
# obviously wrong paste here beats a confusing failure two steps later.
LOOKS_RIGHT = re.compile(r"^[A-Za-z0-9._~-]{16,}$")


def set_env_value(key, value):
    """Replace one key in .env, leaving every other line exactly as it was."""
    lines = []
    if os.path.exists(ENV):
        lines = open(ENV, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    with open(ENV, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass  # Windows doesn't do POSIX modes


def main():
    if not os.path.exists(ENV):
        sys.exit("No .env here yet. Run `python setup.py` first.")

    print(__doc__.split("Where to find it")[1].join(["Where to find it", ""]))

    # getpass so a session token doesn't sit in the terminal scrollback.
    value = getpass.getpass("Paste the JSESSIONID value (it won't be shown): ").strip()
    value = value.strip('"').strip("'")

    if not value:
        sys.exit("Nothing pasted.")
    if value.upper().startswith("JSESSIONID="):
        # Easy mistake: copying the whole "name=value" pair rather than the value.
        value = value.split("=", 1)[1].strip()
    if not LOOKS_RIGHT.match(value):
        sys.exit(f"That doesn't look like a JSESSIONID ({len(value)} characters).\n"
                 "Copy just the value column, not the name and not the whole row.")

    set_env_value("PS_COOKIE", value)
    print("Saved to .env.\n")

    print("Testing it...")
    done = subprocess.run([sys.executable, os.path.join(HERE, "ps_client.py")], cwd=HERE)
    if done.returncode:
        sys.exit("\nThat cookie didn't work. Make sure you're signed in to the portal in\n"
                 "the browser you copied it from, then grab a fresh one and try again.")

    print("\nWorking. Pulling your grades now...")
    if subprocess.run([sys.executable, os.path.join(HERE, "sync.py")], cwd=HERE).returncode:
        sys.exit("The sync failed -- see above.")
    print("\nDone. Your site is updating. When this cookie expires the sync will start\n"
          "failing and the site will say it's stale -- run this again for a fresh one.")


if __name__ == "__main__":
    main()
