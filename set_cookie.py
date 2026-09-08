"""
Hand the scrape your browser's signed-in session.

    python set_cookie.py

The portal is behind Imperva, which challenges automated sign-ins. Your browser has
already passed that challenge. Copying one cookie isn't enough -- Imperva keeps its own
cookies as proof, and the session is tied to the browser's User-Agent -- so this takes
the whole request your browser makes and reuses it verbatim.

How to copy it:
  1. Open your SCHOOL PORTAL and sign in so you can see your grades. The address bar
     must show powerschool.com.
  2. Press F12, then click the "Network" tab.
  3. Reload the page (F5). A list of requests appears.
  4. Click the FIRST row in that list (it will be home.html or similar).
  5. Right-click it -> Copy -> "Copy as cURL". In Firefox pick "Copy as cURL (POSIX)"
     if it offers a choice.
  6. Run this script and paste at the prompt, then press Enter twice.

Sessions last hours, not days. When it expires the sync fails, the site shows its stale
warning, and you run this again.
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env")

# Matches -H 'cookie: ...' / -H "Cookie: ..." / --header 'Cookie: ...', which is how
# every browser's "Copy as cURL" writes headers, whichever quoting style it uses.
HEADER = re.compile(
    r"""(?:-H|--header)\s+(['"])\s*(?P<name>[A-Za-z-]+)\s*:\s*(?P<value>.*?)\1""",
    re.S,
)
# Windows "Copy as cURL" wraps lines with ^ and doubles quotes; Firefox POSIX uses \.
CONTINUATIONS = re.compile(r"[\^\\]\r?\n\s*")


def read_paste():
    print("\nPaste the copied cURL command, then press Enter on a blank line.")
    print("(It is long and will wrap over several lines -- that's fine.)\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip() and lines:
            break
        lines.append(line)
    return "\n".join(lines)


def parse(blob):
    """Pull the Cookie header and User-Agent out of a pasted cURL command."""
    text = CONTINUATIONS.sub(" ", blob).replace('^"', '"')
    found = {m.group("name").lower(): m.group("value").strip()
             for m in HEADER.finditer(text)}
    return found.get("cookie", ""), found.get("user-agent", "")


def set_env_values(pairs):
    """Replace these keys in .env, leaving every other line exactly as it was."""
    lines = open(ENV, encoding="utf-8").read().splitlines() if os.path.exists(ENV) else []
    for key, value in pairs.items():
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

    print(__doc__.split("How to copy it:")[1].split("Sessions last")[0]
          .join(["How to copy it:", ""]))

    blob = read_paste()
    if not blob.strip():
        sys.exit("Nothing pasted.")

    cookie, agent = parse(blob)

    if not cookie:
        sys.exit("Couldn't find a Cookie header in that.\n"
                 "Make sure you used Copy as cURL on a request to the portal while "
                 "signed in -- not Copy as fetch, and not the URL on its own.")
    if "JSESSIONID" not in cookie.upper():
        print("  ! No JSESSIONID in there. That usually means the request you copied "
              "wasn't\n    a signed-in page. Trying anyway.")

    names = [c.split("=", 1)[0].strip() for c in cookie.split(";") if "=" in c]
    print(f"\nFound {len(names)} cookies: {', '.join(sorted(set(names))[:8])}"
          f"{'...' if len(names) > 8 else ''}")
    if not any(n.startswith(("visid_incap", "incap_ses")) for n in names):
        print("  ! No Imperva cookies among them. If this fails, reload the portal page"
              "\n    and copy the very first request rather than a later one.")
    print(f"User-Agent: {'captured' if agent else 'not found, will use the default'}")

    set_env_values({"PS_COOKIE_HEADER": cookie, "PS_USER_AGENT": agent, "PS_COOKIE": ""})
    print("Saved to .env.\n")

    print("Testing it...")
    if subprocess.run([sys.executable, os.path.join(HERE, "ps_client.py")], cwd=HERE).returncode:
        sys.exit("\nStill refused. Worth checking: are you signed in in that browser "
                 "right now,\nand did you copy a request to powerschool.com rather than "
                 "some other site?")

    print("\nWorking. Pulling your grades...")
    if subprocess.run([sys.executable, os.path.join(HERE, "sync.py")], cwd=HERE).returncode:
        sys.exit("The sync failed -- see above.")
    print("\nDone. Your site is updating.")


if __name__ == "__main__":
    main()
