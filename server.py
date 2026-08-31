"""
Tiny local web server. Two jobs:
  1. serve the dashboard files in static/
  2. hand the scraped grade data to the page as JSON

Why a server at all? The dashboard is JavaScript running in your browser, and browsers
block a page on localhost from posting your credentials to powerschool.com (CORS). So
Python does the login and scraping, and the browser just asks Python for the result.

Binds to 127.0.0.1 only -- that means this is reachable from THIS computer and nothing
else. Not from your phone, not from the internet.
"""

import json
import os

from flask import Flask, jsonify, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "cache.json")
SAMPLE_FILE = os.path.join(HERE, "sample_data.json")

# static_url_path="" serves static/style.css at /style.css rather than /static/style.css,
# which is what index.html asks for.
app = Flask(__name__, static_folder="static", static_url_path="")


def load_data(force_refresh=False):
    """Return grade data: freshly scraped if asked, else cached, else sample."""
    if force_refresh:
        # scrape.py is written once we have your real HTML to parse.
        from scrape import scrape_all

        data = scrape_all()
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return data

    for path in (CACHE_FILE, SAMPLE_FILE):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    return {"courses": [], "error": "No data yet."}


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/grades")
def api_grades():
    from flask import request

    force = request.args.get("refresh") == "1"
    try:
        return jsonify(load_data(force_refresh=force))
    except Exception as err:  # surface scrape/login errors in the UI, not just the console
        return jsonify({"error": str(err)}), 500


if __name__ == "__main__":
    print("Dashboard running at http://127.0.0.1:5000  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=5000, debug=False)
