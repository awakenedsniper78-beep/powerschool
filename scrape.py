"""
Runs the whole job: log in -> read the grades grid -> follow each course to its
assignments page -> save everything to cache.json.

Run directly:   python scrape.py
"""

import datetime
import json
import os
import time

from bs4 import BeautifulSoup

from parsers import parse_assignments, parse_gpa, parse_grades_grid
from ps_client import PowerSchoolClient

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(HERE, "cache.json")

# Be polite to the school's servers: a short pause between page fetches.
DELAY_SECONDS = 0.5


def scrape_all(save_html=False):
    client = PowerSchoolClient().login()

    home_html = client.get("/guardian/home.html")
    grid = parse_grades_grid(home_html)
    courses = grid["courses"]

    if save_html:
        os.makedirs(os.path.join(HERE, "saved_html"), exist_ok=True)
        with open(os.path.join(HERE, "saved_html", "home.html"), "w", encoding="utf-8") as fh:
            fh.write(home_html)

    # Follow each course's link to pull its assignments.
    for course in courses:
        if not course.get("link"):
            continue
        try:
            time.sleep(DELAY_SECONDS)
            course["assignments"] = parse_assignments(client.get(_resolve(course["link"])))
        except Exception as err:
            # One bad course page shouldn't kill the whole scrape.
            print(f"  ! couldn't read assignments for {course['name']}: {err}")
            course["assignments"] = []

    data = {
        "student": {"name": _student_name(home_html), "school": ""},
        "scraped_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "is_sample": False,
        "gpa": _try_gpa(client),
        "attendance": {
            "absences": sum(c.get("absences", 0) for c in courses),
            "tardies": sum(c.get("tardies", 0) for c in courses),
        },
        "terms": grid.get("terms", []),
        "courses": courses,
    }
    return data


def _resolve(link):
    """
    Links in the grid are relative to /guardian/ (e.g. "scores.html?frn=...").
    Resolving them against the site root gives /scores.html, which 404s.
    """
    if link.startswith(("http://", "https://", "/")):
        return link
    return f"/guardian/{link}"


def _student_name(html):
    """The signed-in student's name sits in the header nav."""
    soup = BeautifulSoup(html, "html.parser")
    for sel in ("#userName span", "#userName", ".userName"):
        el = soup.select_one(sel)
        if el:
            name = el.get_text(" ", strip=True)
            if name:
                return name
    return ""


def _try_gpa(client):
    """GPA lives on different pages depending on the district; try the usual ones."""
    for path in ("/guardian/termgrades.html", "/guardian/gradehistory.html"):
        try:
            gpa = parse_gpa(client.get(path))
            if gpa:
                return gpa
        except Exception:
            continue
    return {}


if __name__ == "__main__":
    print("Logging in...")
    data = scrape_all(save_html=True)

    with open(CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)

    courses = data["courses"]
    graded = [c for c in courses if c.get("grade_percent") is not None]
    assignments = sum(len(c.get("assignments", [])) for c in courses)

    print(f"\nStudent:     {data['student']['name'] or '(name not found)'}")
    print(f"Courses:     {len(courses)}")
    print(f"With grades: {len(graded)}")
    print(f"Assignments: {assignments}")
    print(f"GPA:         {data['gpa'] or '(none published)'}")
    print(f"\nSaved to cache.json")

    if not graded:
        print(
            "\nNote: no grades are posted yet -- every grade cell on the portal is still\n"
            "empty. The dashboard will show your courses now and fill in grades\n"
            "automatically once your teachers start entering them."
        )
