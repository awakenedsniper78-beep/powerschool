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

    # A course with no grade posted may genuinely have no assignments, so look at the
    # ones that DO have a grade -- those are where rows must exist.
    graded = [c for c in courses if isinstance(c.get("grade_percent"), (int, float))
              and c.get("link")]
    targets = graded[:2] or [c for c in courses if c.get("link")][:2]
    if not targets:
        sys.exit("\nNo course has a usable link. That's the bug: the scrape never even "
                 "requests an assignments page.")
    print(f"\nInspecting {len(targets)} course(s) that have grades posted."
          if graded else "\nNo course has a grade posted; inspecting the first two anyway.")

    for n, target in enumerate(targets):
        print(f"\n{'='*70}\n{target['name']}\n{'='*70}")
        url = _resolve(target["link"])
        html = client.get(url)
        print(f"  url    {url}")
        print(f"  saved  {save(f'scores{n}.html', html)}")
        print(f"  bytes  {len(html)}")

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        print(f"  tables {len(tables)}")
        for i, t in enumerate(tables):
            headers = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:20]
                       for c in t.find_all(["th", "td"], limit=10)]
            print(f"    table {i}: {len(t.find_all('tr'))} rows | cells: {headers}")

        parsed = parse_assignments(html)
        print(f"  parse_assignments() -> {len(parsed)} rows")
        if parsed:
            print("  first row shape (values hidden):")
            for k, v in parsed[0].items():
                print(f"    {k:<16} {'empty' if v in (None, '', []) else 'present'}")
            continue

        text = soup.get_text(" ", strip=True)
        print(f"  no table matched. Page text begins:\n    {text[:260]}")
        if not tables:
            print("\n  NO tables at all. If the page is mostly script tags, the portal"
                  "\n  draws assignments in JavaScript and this needs a different"
                  "\n  endpoint entirely.")
        scripts = soup.find_all("script")
        print(f"  script tags: {len(scripts)}")
        # A JSON payload embedded in the page is the usual alternative to a table, and
        # would be a far better thing to read than HTML.
        for sc in scripts:
            body = sc.string or ""
            if any(k in body for k in ('"assignment', "assignments", "_assignmentsData")):
                print(f"    ! a script mentions assignments ({len(body)} chars) -- the"
                      " data is probably embedded as JSON")
                break

    print("\nDone. saved_html/ holds the raw pages -- they contain your grades, so it is"
          "\ngitignored. Share the structure above, not the files, unless you're happy to.")


if __name__ == "__main__":
    main()
