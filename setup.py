"""
Set this up on a new computer, start to finish.

    python setup.py

Installs the dependencies, asks for the four things it needs, checks the login actually
works, does a first sync, and schedules it to repeat every three hours. Re-running it is
safe: it keeps whatever is already configured and only asks about what's missing.

Nothing typed here leaves this computer. Credentials go into .env, which is gitignored;
what gets published is encrypted with the dashboard password you choose.
"""

import getpass
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env")

def _is_url(v):
    # Anything without a scheme and a host isn't fetchable, and requests fails deep
    # inside the scrape rather than here where it can be corrected.
    return bool(re.match(r"https?://[^/\s]+\.[^/\s]+", v))


FIELDS = [
    ("PS_BASE_URL", "Your district's PowerSchool address (press Enter to accept the default)",
     "https://birmingham.powerschool.com", False,
     _is_url, "That doesn't look like a web address -- it needs to start with https://"),
    ("PS_USERNAME", "Your PowerSchool username", None, False,
     lambda v: len(v) >= 2, "Too short to be a username."),
    ("PS_PASSWORD", "Your PowerSchool password", None, True,
     lambda v: len(v) >= 1, "Can't be blank."),
    ("DASH_USERNAME", "A username to invent for the website (not PowerSchool's)", None, False,
     lambda v: len(v) >= 2, "Too short to be a username."),
    ("DASH_PASSWORD", "A password to invent for the website, 8+ characters", None, True,
     lambda v: len(v) >= 8,
     "Needs 8+ characters -- the published file is public, so length is what protects it."),
]


def step(n, text):
    print(f"\n\033[1m[{n}/5] {text}\033[0m")


def read_env():
    if not os.path.exists(ENV):
        return {}
    out = {}
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def write_env(values):
    lines = ["# Written by setup.py. This file is gitignored -- keep it that way.", ""]
    for key, *_rest in FIELDS:
        lines.append(f"{key}={values.get(key, '')}")
    lines += ["", "# Optional fallback if the portal blocks automated logins.",
              f"PS_COOKIE={values.get('PS_COOKIE', '')}"]
    with open(ENV, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    # Credentials in a world-readable file are a needless risk on a shared machine.
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass  # Windows doesn't do POSIX modes; NTFS defaults are fine


def ask(existing):
    values = dict(existing)
    for key, prompt, default, secret, valid, complaint in FIELDS:
        # Validate what's already stored too. A bad value saved on an earlier run would
        # otherwise be kept forever, and re-running setup would never offer to fix it.
        current = values.get(key, "")
        if current and valid(current):
            print(f"  {key:<14} already set, keeping it")
            continue
        if current:
            print(f"  {key:<14} is set to {current[:30]!r}, which isn't valid. {complaint}")

        while True:
            hint = f" [{default}]" if default else ""
            answer = (getpass.getpass(f"  {prompt}: ") if secret
                      else input(f"  {prompt}{hint}: ").strip())
            answer = answer or (default or "")
            if not answer:
                print("    (required)")
                continue
            if not valid(answer):
                print(f"    {complaint}")
                continue
            values[key] = answer
            break
    return values


def run(label, args, **kw):
    print(f"  {label}...")
    done = subprocess.run(args, cwd=HERE, **kw)
    return done.returncode == 0


def main():
    print("Setting up Curve on this computer.")

    step(1, "Installing dependencies")
    if not run("pip install", [sys.executable, "-m", "pip", "install", "--quiet",
                               "-r", os.path.join(HERE, "requirements.txt")]):
        sys.exit("pip failed. Fix that, then run setup.py again.")
    print("  done")

    step(2, "Credentials")
    existing = read_env()
    if existing:
        print(f"  found an existing .env -- anything already filled in is kept")
    values = ask(existing)
    write_env(values)
    print(f"  saved to .env")

    step(3, "Checking the PowerSchool login")
    # Run as a subprocess so it picks up the .env we just wrote.
    if not run("signing in", [sys.executable, os.path.join(HERE, "ps_client.py")]):
        sys.exit("\nThe login didn't work -- the error above says why.\n"
                 "  'No scheme supplied'  -> PS_BASE_URL in .env is wrong\n"
                 "  'sent us back to the sign-in page' -> wrong username or password\n"
                 "  'Blocked by Imperva'  -> see the README for the PS_COOKIE fallback\n"
                 "Fix it in .env, or delete .env and run setup.py again to be re-asked.")

    step(4, "First sync")
    if not run("scraping and publishing", [sys.executable, os.path.join(HERE, "sync.py")]):
        sys.exit("\nThe sync failed -- see the error above. Once it's fixed, run:\n"
                 "  python sync.py\n  python install_schedule.py")

    step(5, "Scheduling it every three hours")
    if not run("installing the schedule",
               [sys.executable, os.path.join(HERE, "install_schedule.py")]):
        print("  couldn't schedule it automatically. Run this yourself:\n"
              "    python install_schedule.py")

    print("\n\033[1mAll set.\033[0m Your grades refresh every three hours while this "
          "computer is awake.")
    print(f"Sign in at your site with the username and password you chose in step 2.")


if __name__ == "__main__":
    main()
