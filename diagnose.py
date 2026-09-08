"""
Work out why assignments aren't showing.

    python diagnose.py

Grades appear but assignment lists come back empty, which means the scrape is losing
them at one of two points: the per-course link on the grades grid, or the parsing of the
assignments page itself. This checks both and prints a structural report -- column
headers, row counts, which links exist -- without printing any actual scores.

It also saves the raw HTML into saved_html/ (gitignored, never committed) so the real
markup can be compared against what the parser expects.
"""

import os
import re
import sys

from bs4 import BeautifulSoup

from parsers import parse_assignments, parse_grades_grid
from ps_client import PowerSchoolClient
from scrape import _resolve

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "saved_html")


def save(name, html):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return os.path.relpath(path, HERE)


def describe_link(href):
    """A link that goes nowhere is the most likely silent failure: the scrape follows
    it, lands back on some other page, finds no table, and reports zero assignments."""
    if not href:
        return "MISSING"
    clean = href.strip()
    if clean in ("#", "") or clean.lower().startswith("javascript:"):
        return f"DEAD ({clean[:40]!r})"
    return f"ok -> {clean[:60]}"


def main():
    print("Signing in...")
    client = PowerSchoolClient().login()

    home = client.get("/guardian/home.html")
    print(f"  saved {save('home.html', home)}")

    grid = parse_grades_grid(home)
    courses = grid["courses"]
    print(f"\nGrades grid: {len(courses)} courses, terms {grid.get('terms')}")

    if not courses:
        sys.exit("No courses parsed at all -- the grid parser is the problem, not assignments.")

    print("\nPer-course assignment links:")
    for c in courses:
        print(f"  {c['name'][:28]:<28} grade={str(c.get('grade_percent')):>6}  "
              f"link={describe_link(c.get('link'))}")

    # Also look at every term's cell, not just the current one -- if only one term
    # carries the link, that alone explains empty assignment lists.
    print("\nLinks found across all term cells (first course):")
    for term, cell in (courses[0].get("terms") or {}).items():
        print(f"  {term}: {describe_link((cell or {}).get('link'))}")

    target = next((c for c in courses if c.get("link")), None)
    if target is None:
        sys.exit("\nNo course has a usable link. That's the bug: the scrape never even "
                 "requests an assignments page.")

    print(f"\nFetching assignments page for {target['name']}...")
    url = _resolve(target["link"])
    html = client.get(url)
    print(f"  url    {url}")
    print(f"  saved  {save('scores.html', html)}")
    print(f"  bytes  {len(html)}")

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    print(f"\nTables on that page: {len(tables)}")
    for i, t in enumerate(tables):
        headers = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:18]
                   for c in t.find_all(["th", "td"], limit=10)]
        print(f"  table {i}: {len(t.find_all('tr'))} rows | first cells: {headers}")

    parsed = parse_assignments(html)
    print(f"\nparse_assignments() returned {len(parsed)} rows")
    if parsed:
        keys = parsed[0]
        print("  first row shape (values hidden):")
        for k, v in keys.items():
            state = "empty" if v in (None, "", []) else "present"
            print(f"    {k:<16} {state}")
    else:
        # No table matched. The most common modern cause is a page whose contents are
        # drawn by JavaScript, which requests never executes.
        text = soup.get_text(" ", strip=True)[:300]
        print("  nothing matched. Page begins:")
        print(f"    {text[:280]}")
        if len(tables) == 0:
            print("\n  There are NO tables at all. If the page is short and mentions a"
                  "\n  script or app root, the portal renders assignments in JavaScript"
                  "\n  and this approach needs a different endpoint.")

    print("\nDone. saved_html/ holds the raw pages -- they contain your grades, so it is"
          "\ngitignored. Share the structure above, not the files, unless you're happy to.")


if __name__ == "__main__":
    main()
