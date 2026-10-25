---
name: class-priority-planner
description: Picks the best non-conflicting class section for each course, weighing RateMyProfessors ratings against schedule fit in the student's own priority order. Use this whenever the student mentions registering for classes, building next semester's schedule, picking between professors or sections, says they can't decide between class times, or asks which professor to take for a course, even if they don't say "schedule" or name Cubbie directly.
---

# Class Priority Planner

A student ranks their upcoming classes by importance and says whether professor quality or
schedule fit matters more overall. This Skill finds, for each class in priority order, the best
section on that axis that doesn't conflict with a higher-priority class already locked in. The
highest-priority class always gets its best possible section; lower-priority classes compromise
around it, never the other way around.

## When to use

- "Help me pick my classes for next semester, I care more about good professors than times"
- "I'm registering for CSE 410, CSE 430, and HIST 103. 410 and 430 matter way more than history"
- "Which section of MAT 243 should I take"
- "I can't decide between these professors for my classes next semester"

Do not use it for Canvas due dates, study plans, or anything after the student has already
registered — this is only for choosing sections before registering.

## Steps

1. **Get the course list, in priority order.** Ask which classes the student is registering for
   next semester and which matters most, down to least. If they only name a subject and number
   loosely ("data structures"), ask for the exact course code (e.g. "CSE 310") since that's what
   the class search tool needs.
2. **Get the axis.** Ask, once, for the whole semester: professor ratings or schedule fit matters
   more when the two pull in different directions. Don't ask this per class — it applies to all
   of them.
3. **If the axis is schedule, ask what that means to them**, in their own words — don't assume a
   category. Follow up only if their answer is too vague to act on (e.g. "a good schedule" alone
   needs a follow-up; "nothing before 10am and Fridays off" doesn't). Turn the answer into:
   - `earliest_start` / `latest_end` ("HH:MM", 24-hour) if they named a time they want to start or
     be done by
   - `days_off` (three-letter day codes: Mon, Tue, Wed, Thu, Fri, Sat, Sun) if they named days
     they want free
   - `compact: true` if they said something like "back to back", "no dead time between classes",
     or "don't want to be on campus longer than I have to"
   Any of these can be combined or omitted; only set what the student actually said.
4. **Ask which term**, if not already said (e.g. "Spring 2026").
5. **Gather sections for each course** using the **browser**: open ASU's public class search
   (https://catalog.apps.asu.edu/catalog/classes/classlist), search the course's subject and
   catalog number for that term, and read every open section's listing. The page layout can
   shift, so look for the columns by meaning rather than an exact position: a class number
   (5-digit ASU registration number), instructor name, days, and start/end time. Skip sections
   with no listed instructor (nothing to rate, and usually a placeholder) unless a course has no
   other option. No sign-in is needed; this tool is public.
6. **Look up each distinct instructor's rating** using the **web**: search `<instructor name>
   ratemyprofessors Arizona State University` and read their RateMyProfessors page for the
   overall rating. Look up each instructor once even if they teach multiple sections or multiple
   courses in this list. If no RateMyProfessors page is found for an instructor, use `null` for
   their rating rather than guessing — the script treats unrated sections as the least preferred
   on the professor axis, and you should flag it to the student.
7. **Run the planner.** Write what you gathered into a JSON file (course names, priority as 1 =
   highest, the axis, the schedule spec if any, and each course's sections with `class_number`,
   `instructor`, `rating`, `days`, `start`, `end`), then run:

   ```bash
   python3 plan_schedule.py --input <path to the JSON file you wrote>
   ```

   Try `python3 plan_schedule.py --sample` first to see the exact input/output shape from a
   built-in example before building a real input file.
8. **Relay the result**, in the Replies format below. For any course in the output's
   `"unresolved"` list, tell the student plainly that nothing conflict-free was found and show the
   closest option anyway so they can decide by hand (maybe they drop a lower-priority class or
   re-rank).

## Replies

Keep it short and plain text, one idea per message, no Markdown symbols. One line per class:
course, class number, instructor, rating (or "no rating yet"), days and time. Lead with the
top-priority class. When a pick was a compromise (the script's `"compromised": true`), say why in
a half-sentence — "CSE 430's top pick clashed with CSE 410, so this is the next best." If more
than five classes are in the plan, offer to send a one-page document instead of a wall of texts,
and only speak the first three plus the total count until the student asks for the rest. Always
end with the class numbers together in one line, since that's what the student will actually type
into registration, and ask if they want anything re-ranked.

## When something fails

- Class search has no sections for a course, or the course code doesn't exist for that term: say
  so and ask the student to double check the course code or term.
- An instructor's RateMyProfessors page can't be found: use `null` for that section's rating, tell
  the student there's no rating for that professor, and keep going — don't block the whole plan on
  one missing rating.
- A course shows up in `"unresolved"`: it means every section of that course overlaps with a
  higher-priority class already picked. Say which class it's conflicting with and let the student
  decide (swap priority order, drop a class, or accept the conflict and sort it out themselves).
- `plan_schedule.py` exits with an error: the input JSON was missing or malformed. Don't guess
  values — re-check what was gathered and rebuild the file.
