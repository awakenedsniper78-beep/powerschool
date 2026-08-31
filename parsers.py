"""
Turns PowerSchool HTML into plain Python dictionaries.

The grades grid looks like this (simplified):

    | Exp | Last Week (5 cols) | This Week (5 cols) | Course | Q1 Q2 S1 Q3 Q4 S2 | Abs | Tardies |

The tricky part is that the header row has 12 cells but each course row has 20, because
"Last Week" and "This Week" each span five day-columns. Rather than hardcode column
numbers (which would break the moment the school changes terms), we anchor on the course
cell -- it's the only one with class `table-element-text-align-start` -- and count
outward from there.
"""

import re

from bs4 import BeautifulSoup

# A grade cell with no grade posted yet renders as the literal text "[ i ]" (an info
# icon linking to the assignments page). Treat that as "no grade".
NO_GRADE = {"[ i ]", "[i]", "", "_", "-", "--"}


def parse_grades_grid(html):
    """Parse /guardian/home.html into a list of course dicts."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.linkDescList.grid")
    if table is None:
        return {"courses": [], "terms": []}

    rows = table.find_all("tr")
    terms = _term_names(rows[0]) if rows else []

    courses = []
    for row in rows:
        cells = row.find_all(["th", "td"])
        course_cell = row.select_one("td.table-element-text-align-start")
        if course_cell is None:
            continue  # header / day-letter rows

        idx = cells.index(course_cell)
        grade_cells = cells[idx + 1 : idx + 1 + len(terms)]

        by_term = {}
        for term_name, cell in zip(terms, grade_cells):
            by_term[term_name] = _parse_grade_cell(cell)

        current = _pick_current_term(by_term, terms)
        name, teacher, room = _parse_course_cell(course_cell)

        courses.append({
            "name": name,
            "teacher": teacher,
            "room": room,
            "period": _clean(cells[idx - 11].get_text(" ", strip=True)) if idx >= 11 else "",
            "term": current,
            "grade_letter": by_term.get(current, {}).get("letter"),
            "grade_percent": by_term.get(current, {}).get("percent"),
            "link": by_term.get(current, {}).get("link"),
            "terms": by_term,
            "absences": _to_int(cells[-2].get_text(strip=True)),
            "tardies": _to_int(cells[-1].get_text(strip=True)),
            "assignments": [],
        })

    return {"courses": courses, "terms": terms}


def _term_names(header_row):
    """Pull term labels (Q1, Q2, S1...) out of the header row."""
    labels = [c.get_text(" ", strip=True) for c in header_row.find_all(["th", "td"])]
    return [l for l in labels if re.fullmatch(r"(Q|S|T|F)\d|Y\d?", l)]


def _parse_grade_cell(cell):
    """Extract letter grade, percent, and the assignments link from one grade cell."""
    link = cell.find("a")
    href = link.get("href") if link else None
    text = _clean(cell.get_text(" ", strip=True))

    if text in NO_GRADE:
        return {"letter": None, "percent": None, "link": href}

    # A graded cell reads like "B+ 88.4" or "A 95". Pull out whichever parts are there.
    percent = None
    match = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%?", text)
    if match:
        value = float(match.group(1))
        if 0 <= value <= 150:
            percent = value

    letter = None
    # Note: no \b here. A trailing "+" is not a word character, so \b would force the
    # regex to backtrack and match "B" instead of "B+". Assert "not a letter" instead.
    match = re.match(r"\s*([A-FI][+-]?)(?![A-Za-z])", text)
    if match:
        letter = match.group(1)

    return {"letter": letter, "percent": percent, "link": href}


def _pick_current_term(by_term, terms):
    """Prefer the earliest term that actually has a grade; otherwise the first term."""
    for term in terms:
        entry = by_term.get(term) or {}
        if entry.get("percent") is not None or entry.get("letter"):
            return term
    return terms[0] if terms else None


def _parse_course_cell(cell):
    """Course cell holds: name, a teacher link, and a room span."""
    name = _clean(cell.find(string=True).strip()) if cell.find(string=True) else ""

    teacher = ""
    detail = cell.find("a", title=re.compile(r"^Details about "))
    if detail:
        teacher = detail["title"].replace("Details about ", "").strip()
    else:
        mailto = cell.find("a", href=re.compile(r"^mailto:"))
        if mailto:
            teacher = _clean(mailto.get_text(" ", strip=True)).replace("Email ", "").strip()

    room = ""
    span = cell.select_one("span.display-flex")
    if span:
        match = re.search(r"Rm:?\s*(\S+)", _clean(span.get_text(" ", strip=True)))
        if match:
            room = match.group(1)

    return name, teacher, room


def parse_assignments(html):
    """
    Parse /guardian/scores.html into a list of assignment dicts.

    Written defensively: this portal has no assignments posted yet, so the exact table
    markup is unconfirmed. We locate the assignments table by looking for a header row
    containing "Due Date", then map columns by their header names rather than position.
    """
    soup = BeautifulSoup(html, "html.parser")

    table = None
    for candidate in soup.find_all("table"):
        headers = [_clean(c.get_text(" ", strip=True)).lower()
                   for c in candidate.find_all(["th", "td"], limit=12)]
        if any("due" in h for h in headers) and any("score" in h or "pts" in h for h in headers):
            table = candidate
            break
    if table is None:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    headers = [_clean(c.get_text(" ", strip=True)).lower() for c in rows[0].find_all(["th", "td"])]

    def col(*keywords):
        for i, h in enumerate(headers):
            if any(k in h for k in keywords):
                return i
        return None

    i_due, i_name = col("due"), col("assignment", "description")
    i_cat, i_score = col("category", "type"), col("score", "pts", "points")
    i_pct, i_grade = col("%", "percent"), col("grade", "letter")

    out = []
    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        get = lambda i: _clean(cells[i].get_text(" ", strip=True)) if i is not None and i < len(cells) else ""

        raw_score = get(i_score)
        score, possible = _split_score(raw_score)
        flags = " ".join(c.get("class", []) and " ".join(c.get("class")) or "" for c in cells).lower()
        row_text = _clean(row.get_text(" ", strip=True)).lower()

        out.append({
            "due_date": _to_iso_date(get(i_due)),
            "name": get(i_name),
            "category": get(i_cat),
            "score": score,
            "points_possible": possible,
            "percent": _to_float(get(i_pct)),
            "letter": get(i_grade) or None,
            "missing": "missing" in flags or "missing" in row_text,
            "late": "late" in flags or "late" in row_text,
        })
    return out


def parse_gpa(html):
    """Find a GPA figure on whatever page carries it. Returns {} if there isn't one."""
    text = _clean(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    out = {}
    for key, pattern in (
        ("weighted", r"weighted\s*GPA[^0-9]{0,12}(\d\.\d+)"),
        ("unweighted", r"unweighted\s*GPA[^0-9]{0,12}(\d\.\d+)"),
    ):
        match = re.search(pattern, text, re.I)
        if match:
            out[key] = float(match.group(1))

    if not out:
        match = re.search(r"\bGPA[^0-9]{0,12}(\d\.\d+)", text, re.I)
        if match:
            out["weighted"] = float(match.group(1))
    return out


# ---------- small helpers ----------

def _clean(text):
    """Collapse whitespace, including the non-breaking spaces PowerSchool loves."""
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ").replace("�", " ")).strip()


def _to_int(text):
    try:
        return int(float(_clean(text)))
    except (TypeError, ValueError):
        return 0


def _to_float(text):
    match = re.search(r"-?\d+(?:\.\d+)?", _clean(text) or "")
    return float(match.group()) if match else None


def _split_score(text):
    """'45/50' -> (45.0, 50.0);  '45' -> (45.0, None);  '--/50' -> (None, 50.0)."""
    text = _clean(text)
    if not text:
        return None, None
    if "/" in text:
        left, right = text.split("/", 1)
        return _to_float(left), _to_float(right)
    return _to_float(text), None


def _to_iso_date(text):
    """PowerSchool shows dates as M/D/YYYY or M/D/YY -> normalise to YYYY-MM-DD."""
    text = _clean(text)
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", text)
    if not match:
        return text or None
    month, day, year = (int(g) for g in match.groups())
    if year < 100:
        year += 2000
    return f"{year:04d}-{month:02d}-{day:02d}"
