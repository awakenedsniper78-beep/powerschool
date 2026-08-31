"""
Build a single self-contained grades.html -- no hosting required.

GitHub Pages charges for private repositories. This sidesteps hosting entirely: it
inlines the stylesheet, the script, and your encrypted grades into ONE html file. That
file still asks for your username and password, and still decrypts locally, exactly like
the hosted version. The difference is it has no dependencies, so it works from anywhere:

  * Save it to iCloud Drive, then open it from the Files app on your iPhone.
  * Or drag it onto a free static host (Netlify Drop, Cloudflare Pages) to get a URL.

Run it the same way as publish.py:

    python build_offline.py
"""

import json
import os
import sys

from publish import derive_key, encrypt, load_payload, prompt_credentials

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")
OUT_FILE = os.path.join(HERE, "grades.html")


def read(name):
    with open(os.path.join(DOCS, name), encoding="utf-8") as fh:
        return fh.read()


def build(blob):
    html = read("index.html")
    css = read("style.css")
    js = read("app.js")

    # The hosted page fetches data.enc.json over the network. There is no network here,
    # so hand the script the same object directly and let it skip the fetch.
    inline_data = f"window.__GRADES_BLOB__ = {json.dumps(blob)};"

    html = html.replace(
        '<link rel="stylesheet" href="style.css" />',
        f"<style>\n{css}\n</style>",
    )
    html = html.replace(
        '<script src="app.js"></script>',
        f"<script>\n{inline_data}\n{js}\n</script>",
    )
    # These only resolve against a web server; as a lone file they'd just 404.
    for tag in (
        '<link rel="apple-touch-icon" href="icon.png" />',
        '<link rel="icon" href="icon.png" />',
        '<link rel="manifest" href="manifest.webmanifest" />',
    ):
        html = html.replace(tag, "")

    return html


def main():
    payload = load_payload()
    username, password = prompt_credentials()

    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.write(build(encrypt(payload, username, password)))

    size_kb = os.path.getsize(OUT_FILE) / 1024
    print(f"\nWrote {os.path.relpath(OUT_FILE, HERE)} ({size_kb:.0f} KB, self-contained)")
    print("\nTo read it on your iPhone, either:")
    print("  * Save it into iCloud Drive, then open it from the Files app, or")
    print("  * Drag it onto https://app.netlify.com/drop for a private URL.")


if __name__ == "__main__":
    main()
