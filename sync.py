"""
One command to put your current grades on the website.

    python sync.py

Scrapes the portal, encrypts the result, commits it, pushes it. A minute later the
GitHub Pages site is showing the same thing your local dashboard shows.

Set DASH_USERNAME and DASH_PASSWORD in `.env` and it won't ask you anything at all.
Those are the credentials you type on your phone -- not your PowerSchool ones.
"""

import json
import os
import subprocess
import sys

from dotenv import load_dotenv

from publish import OUT_FILE, encrypt, prompt_credentials

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "cache.json")

load_dotenv(os.path.join(HERE, ".env"))


def git(*args, check=True):
    return subprocess.run(
        ["git", *args], cwd=HERE, check=check, capture_output=True, text=True
    )


def credentials():
    """From .env if it's set up, otherwise ask -- same rules either way."""
    username = os.getenv("DASH_USERNAME", "").strip()
    password = os.getenv("DASH_PASSWORD", "")

    if username and password:
        if len(password) < 8:
            sys.exit("DASH_PASSWORD is under 8 characters. Make it longer.")
        return username, password

    # On GitHub Actions there is no keyboard: prompting would hang the job until it
    # times out. Fail loudly instead, naming what's missing.
    if not sys.stdin.isatty():
        sys.exit("DASH_USERNAME and DASH_PASSWORD aren't set. In GitHub Actions, add them "
                 "under Settings > Secrets and variables > Actions.")

    print("Tip: set DASH_USERNAME and DASH_PASSWORD in .env to skip this next time.")
    return prompt_credentials()


def main():
    # Credentials first: they're needed to read the published file, and a missing secret
    # should stop the run before it touches the school's servers.
    username, password = credentials()

    # 1. Scrape. Imported here so a login failure surfaces before anything else happens.
    print("Reading the portal...")
    from scrape import scrape_all

    data = scrape_all()

    courses = data.get("courses", [])
    graded = [c for c in courses if c.get("grade_percent") is not None]
    print(f"  {len(courses)} courses, {len(graded)} with grades posted")

    # 2. Encrypt.
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(encrypt(data, username, password), fh, indent=2)
    print("Encrypted.")

    # 3. Publish. Nothing to do if the grades haven't moved since last time.
    # Every run republishes, even when no grade moved, so the timestamp the site shows
    # is when it last checked rather than when a grade last changed. A stale "synced"
    # reading looks broken; two commits a day does not.
    rel = os.path.relpath(OUT_FILE, HERE)
    git("add", rel)
    if not git("diff", "--cached", "--quiet", check=False).returncode:
        print("\nNothing staged -- nothing to publish.")
        return

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    # A fresh Actions runner has no git identity configured, and commit refuses without one.
    if not git("config", "user.email", check=False).stdout.strip():
        git("config", "user.email", "actions@github.com")
        git("config", "user.name", "Grades bot")
    git("commit", "-m", f"Update grades ({data.get('scraped_at', '')})")
    print(f"Pushing to {branch}...")
    push = git("push", "origin", branch, check=False)
    if push.returncode:
        sys.exit(f"Push failed:\n{push.stderr.strip()}")

    # Only now that the data is actually published does the cache become the record of
    # what the site is showing. Writing it earlier would make a run that failed to
    # publish look, to the next run, like it had succeeded.
    with open(CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)

    print("\nDone. Your site updates in about a minute:")
    print(f"  https://{origin_user()}.github.io/{repo_name()}/")
    if branch != "main":
        print(f"\nHeads up: you're on '{branch}', but Pages builds from 'main'.")
        print("Merge it to main for the site to pick this up.")


def _origin():
    return git("remote", "get-url", "origin", check=False).stdout.strip()


def origin_user():
    parts = _origin().rstrip("/").removesuffix(".git").split("/")
    return parts[-2] if len(parts) >= 2 else "<you>"


def repo_name():
    return _origin().rstrip("/").removesuffix(".git").split("/")[-1] or "<repo>"


if __name__ == "__main__":
    main()
