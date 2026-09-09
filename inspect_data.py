"""
Show what's actually inside the published file.

    python inspect_data.py

The site can only draw what the scrape put in the file. This decrypts
docs/data.enc.json with your dashboard password and reports its shape -- how many
courses, which ones carry a grade, how many assignments each has -- so it's clear
whether something is missing from the data or just isn't being displayed.

It prints counts and flags, never a score or a grade. Safe to paste.
"""

import json
import os
import sys

from dotenv import load_dotenv

from publish import decrypt

HERE = os.path.dirname(os.path.abspath(__file__))
BLOB = os.path.join(HERE, "docs", "data.enc.json")
CACHE = os.path.join(HERE, "cache.json")

load_dotenv(os.path.join(HERE, ".env"))


def load_published():
    if not os.path.exists(BLOB):
        return None, "docs/data.enc.json doesn't exist yet."
    user = os.getenv("DASH_USERNAME", "").strip()
    pw = os.getenv("DASH_PASSWORD", "")
    if not user or not pw:
        return None, "DASH_USERNAME / DASH_PASSWORD aren't in .env, so it can't be opened."
    with open(BLOB, encoding="utf-8") as fh:
        data = decrypt(json.load(fh), user, pw)
    if data is None:
        return None, ("Those credentials don't open the file. The file was published "
                      "under a different username or password.")
    return data, None


def report(label, data):
    courses = data.get("courses") or []
    print(f"\n=== {label} ===")
    print(f"scraped_at : {data.get('scraped_at')}")
    print(f"is_sample  : {data.get('is_sample')}")
    print(f"gpa        : {'present' if data.get('gpa') else 'absent'}")
    print(f"courses    : {len(courses)}")

    if not courses:
        print("\nNo courses at all. The grades grid isn't being parsed.")
        return

    graded = sum(1 for c in courses if isinstance(c.get("grade_percent"), (int, float)))
    lettered = sum(1 for c in courses if c.get("grade_letter"))
    withwork = sum(1 for c in courses if c.get("assignments"))
    total = sum(len(c.get("assignments") or []) for c in courses)

    print(f"  with a percent  : {graded}/{len(courses)}")
    print(f"  with a letter   : {lettered}/{len(courses)}")
    print(f"  with assignments: {withwork}/{len(courses)}  ({total} rows in total)")

    print(f"\n{'course':<26} {'pct':>4} {'ltr':>4} {'link':>5} {'items':>6}  note")
    print("-" * 78)
    for c in courses:
        pct = "yes" if isinstance(c.get("grade_percent"), (int, float)) else "--"
        ltr = "yes" if c.get("grade_letter") else "--"
        link = "yes" if c.get("link") else "--"
        n = len(c.get("assignments") or [])
        note = (c.get("assignments_note") or "")[:30]
        print(f"{str(c.get('name'))[:26]:<26} {pct:>4} {ltr:>4} {link:>5} {n:>6}  {note}")

    # Name the conclusion rather than leaving it to be inferred from the table.
    print()
    if total == 0:
        print("VERDICT: the file contains no assignments at all, so this is the scrape,"
              "\n         not the app. Run: python diagnose.py")
    elif withwork < len(courses):
        print(f"VERDICT: {len(courses) - withwork} course(s) have no assignments while "
              f"others do.\n         The notes column says why for each.")
    else:
        print("VERDICT: every course has assignments in the file. If the app isn't "
              "showing\n         them, that's a display problem, not a scraping one.")


def main():
    data, err = load_published()
    if err:
        print(f"Published file: {err}")
    else:
        report("published (what the website serves)", data)

    # cache.json is what the last local scrape produced. When the two disagree, the
    # publish step is the thing that dropped the data.
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            report("cache.json (what the last local scrape got)", json.load(fh))
    else:
        print("\nNo cache.json here -- the last sync ran somewhere else "
              "(GitHub Actions, or another computer).")

    if err and not os.path.exists(CACHE):
        sys.exit(1)


if __name__ == "__main__":
    main()
