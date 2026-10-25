#!/usr/bin/env python3
"""Pick one non-conflicting section per course, in priority order, by the student's chosen axis.

Input (JSON, via --input, or the built-in example via --sample):
{
  "axis": "professor" | "schedule",
  "schedule_spec": {"earliest_start": "10:00", "latest_end": "15:00",
                     "days_off": ["Fri"], "compact": true} | null,
  "travel_buffer_minutes": 30,
  "courses": [
    {
      "name": "CSE 410",
      "priority": 1,
      "sections": [
        {"class_number": "12345", "instructor": "Jane Smith", "rating": 4.6, "campus": "Tempe",
         "days": ["Mon", "Wed", "Fri"], "start": "10:00", "end": "10:50"},

        // asynchronous section: no fixed meeting time, so it can never conflict with
        // anything. Omit "days"/"start"/"end" (or leave them empty/null) instead of guessing a time.
        {"class_number": "99999", "instructor": "Jane Smith", "rating": 4.6, "campus": "ASU Online"},

        // a lecture with a required, separately-numbered recitation: both class numbers
        // are needed, and both time blocks count for conflicts.
        {"class_number": "12346", "instructor": "Jane Smith", "rating": 4.6, "campus": "Tempe",
         "days": ["Mon", "Wed"], "start": "09:00", "end": "09:50",
         "recitation": {"class_number": "12347", "days": ["Fri"], "start": "09:00", "end": "09:50"}}
      ]
    }
  ]
}

"rating" may be null when no RateMyProfessors page was found for that instructor.
Days use three-letter codes: Mon, Tue, Wed, Thu, Fri, Sat, Sun.
"campus" is optional free text (e.g. "Tempe", "West Valley", "ASU Online"); when two sections sit
on different physical campuses back to back, "travel_buffer_minutes" (default 30) of gap is
required between them or they count as conflicting. Anything with "online" in its campus name
needs no travel buffer. "campus" can also be set on a "recitation" block when it differs from its
lecture's campus.

Output (JSON on stdout): the locked-in pick per course, plus any course that could not
get a conflict-free section, with its closest (still-conflicting) option for reference.
"""
import argparse
import json
import sys
from pathlib import Path

UNRATED_SCORE = 0  # worse than any real rating (-1 to -5), so unrated sections sort last
DEFAULT_TRAVEL_BUFFER_MINUTES = 30

SAMPLE_INPUT = {
    "axis": "professor",
    "schedule_spec": {"latest_end": "15:00"},
    "travel_buffer_minutes": 30,
    "courses": [
        {
            "name": "CSE 410",
            "priority": 1,
            "sections": [
                {"class_number": "10001", "instructor": "A. Rivera", "rating": 4.5, "campus": "Tempe",
                 "days": ["Mon", "Wed", "Fri"], "start": "10:00", "end": "10:50"},
                {"class_number": "10002", "instructor": "B. Chen", "rating": 3.2, "campus": "Tempe",
                 "days": ["Tue", "Thu"], "start": "13:30", "end": "14:45"},
            ],
        },
        {
            "name": "CSE 430",
            "priority": 2,
            "sections": [
                {"class_number": "10101", "instructor": "C. Patel", "rating": 4.5, "campus": "Tempe",
                 "days": ["Mon", "Wed", "Fri"], "start": "10:00", "end": "10:50"},
                {"class_number": "10102", "instructor": "D. Nguyen", "rating": 4.1, "campus": "Tempe",
                 "days": ["Tue", "Thu"], "start": "14:00", "end": "15:15"},
            ],
        },
        {
            "name": "HIST 103",
            "priority": 3,
            "sections": [
                {"class_number": "10201", "instructor": "E. Brooks", "rating": None, "campus": "Tempe",
                 "days": ["Mon", "Wed", "Fri"], "start": "11:00", "end": "11:50"},
            ],
        },
        {
            "name": "CSE 355",
            "priority": 4,
            "sections": [
                # two sections, same instructor, same rating -- a real tie. The first option is a
                # schedule-axis win (ends earlier, more travel room); the second collides with CSE 360.
                {"class_number": "25636", "instructor": "H. Lee", "rating": 4.0, "campus": "Tempe",
                 "days": ["Mon", "Wed"], "start": "13:30", "end": "14:45"},
                {"class_number": "14971", "instructor": "H. Lee", "rating": 4.0, "campus": "Tempe",
                 "days": ["Mon", "Wed"], "start": "15:00", "end": "16:15"},
            ],
        },
        {
            "name": "CSE 360",
            "priority": 5,
            "sections": [
                # only 15 minutes after CSE 355's later section, and a different campus --
                # a real transfer, not just a conflict, so travel_buffer_minutes applies here.
                {"class_number": "29843", "instructor": "D. Claveau", "rating": 4.0, "campus": "West Valley",
                 "days": ["Mon", "Wed"], "start": "16:30", "end": "17:45"},
            ],
        },
        {
            "name": "CSE 365",
            "priority": 6,
            "sections": [
                {"class_number": "23647", "instructor": "J. Baek", "rating": 3.5, "campus": "ASU Online"},
            ],
        },
    ],
}


def parse_time(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def is_async(section):
    """No fixed meeting time: nothing to conflict with and nothing to score against."""
    return not section.get("days") or not section.get("start") or not section.get("end")


def get_blocks(section):
    """A section's time blocks for conflict-checking: its own meeting time (if any) plus a
    linked recitation's, if it has one. An async section with no recitation has zero blocks,
    so it can never conflict with anything. A recitation without its own campus inherits its
    lecture's."""
    blocks = []
    if not is_async(section):
        blocks.append({"days": section["days"], "start": section["start"], "end": section["end"],
                        "campus": section.get("campus")})
    recitation = section.get("recitation")
    if recitation and not is_async(recitation):
        blocks.append({"days": recitation["days"], "start": recitation["start"], "end": recitation["end"],
                        "campus": recitation.get("campus", section.get("campus"))})
    return blocks


def needs_travel_buffer(campus_a, campus_b):
    def physical(c):
        return bool(c) and "online" not in c.lower()
    return physical(campus_a) and physical(campus_b) and campus_a.strip().lower() != campus_b.strip().lower()


def blocks_conflict(a, b, travel_buffer_minutes):
    if not (set(a["days"]) & set(b["days"])):
        return False
    a_start, a_end = parse_time(a["start"]), parse_time(a["end"])
    b_start, b_end = parse_time(b["start"]), parse_time(b["end"])
    if a_start < b_end and b_start < a_end:
        return True
    if needs_travel_buffer(a.get("campus"), b.get("campus")):
        gap = (b_start - a_end) if a_end <= b_start else (a_start - b_end)
        if gap < travel_buffer_minutes:
            return True
    return False


def sections_conflict(a, b, travel_buffer_minutes):
    return any(blocks_conflict(ba, bb, travel_buffer_minutes) for ba in get_blocks(a) for bb in get_blocks(b))


def schedule_violation_points(section, spec):
    if not spec or is_async(section):
        return 0
    points = 0
    start, end = parse_time(section["start"]), parse_time(section["end"])
    if spec.get("earliest_start"):
        e = parse_time(spec["earliest_start"])
        if start < e:
            points += e - start
    if spec.get("latest_end"):
        l = parse_time(spec["latest_end"])
        if end > l:
            points += end - l
    days_off = set(spec.get("days_off", []))
    overlap = days_off & set(section["days"])
    if overlap:
        points += 1000 * len(overlap)
    return points


def compactness_gap(section, locked):
    if is_async(section):
        return 0
    s_start, s_end = parse_time(section["start"]), parse_time(section["end"])
    best_gap = None
    for locked_section in locked:
        if is_async(locked_section):
            continue
        shared_days = set(locked_section["days"]) & set(section["days"])
        if not shared_days:
            continue
        l_start, l_end = parse_time(locked_section["start"]), parse_time(locked_section["end"])
        if s_start >= l_end:
            gap = s_start - l_end
        elif l_start >= s_end:
            gap = l_start - s_end
        else:
            gap = 0
        if best_gap is None or gap < best_gap:
            best_gap = gap
    return best_gap if best_gap is not None else 0


def score(section, axis, spec, locked):
    """A (primary, tiebreak) pair; lower is always better, in both slots. The axis the student
    didn't pick as primary still breaks ties on the one they did -- e.g. two equally-rated
    professors get decided by schedule fit instead of arbitrary list order."""
    rating = section.get("rating")
    rating_score = UNRATED_SCORE if rating is None else -rating
    schedule_score = schedule_violation_points(section, spec)
    if spec and spec.get("compact"):
        schedule_score += compactness_gap(section, locked)
    if axis == "professor":
        return (rating_score, schedule_score)
    return (schedule_score, rating_score)


def best_unconstrained(sections, axis, spec, locked):
    return min(sections, key=lambda s: score(s, axis, spec, locked))


def plan(data):
    axis = data["axis"]
    spec = data.get("schedule_spec")
    travel_buffer = data.get("travel_buffer_minutes", DEFAULT_TRAVEL_BUFFER_MINUTES)
    courses = sorted(data["courses"], key=lambda c: c["priority"])

    locked = []
    picks = []
    unresolved = []

    for course in courses:
        sections = course["sections"]
        candidates = [s for s in sections if not any(sections_conflict(s, L, travel_buffer) for L in locked)]

        if not candidates:
            closest = best_unconstrained(sections, axis, spec, locked)
            unresolved.append({
                "course": course["name"],
                "reason": "every available section conflicts with a higher-priority pick",
                "closest_option": closest,
            })
            continue

        picked = best_unconstrained(candidates, axis, spec, locked)
        unconstrained_best = best_unconstrained(sections, axis, spec, locked)
        compromised = picked is not unconstrained_best and score(picked, axis, spec, locked) != score(
            unconstrained_best, axis, spec, locked
        )

        locked.append(picked)
        pick = {
            "course": course["name"],
            "class_number": picked["class_number"],
            "instructor": picked["instructor"],
            "rating": picked.get("rating"),
            "campus": picked.get("campus"),
            "async": is_async(picked),
            "days": picked.get("days") or [],
            "start": picked.get("start"),
            "end": picked.get("end"),
            "compromised": compromised,
        }
        recitation = picked.get("recitation")
        if recitation:
            pick["recitation_class_number"] = recitation.get("class_number")
            pick["recitation_days"] = recitation.get("days")
            pick["recitation_start"] = recitation.get("start")
            pick["recitation_end"] = recitation.get("end")
        picks.append(pick)

    return {"axis": axis, "picks": picks, "unresolved": unresolved}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", help="path to the input JSON file")
    ap.add_argument("--sample", action="store_true", help="use the bundled sample input instead of --input")
    args = ap.parse_args()

    if args.sample:
        data = SAMPLE_INPUT
    elif args.input:
        try:
            data = json.loads(Path(args.input).read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"error: could not read input JSON ({e})", file=sys.stderr)
            sys.exit(2)
    else:
        print("error: pass --input <file> or --sample", file=sys.stderr)
        sys.exit(2)

    print(json.dumps(plan(data), indent=2))


if __name__ == "__main__":
    main()
