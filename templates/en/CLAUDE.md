# CLAUDE.md

The top-level instructions an AI agent reads every time it works in this folder.
This file is a table of contents. Rule bodies live in their own source documents. Here you only write a name, a one-line summary and a location.

## Document map

- Coding rules: `RULES.md`. Read before writing or changing code.
- Incident log: `LESSONS.md`. When something goes wrong, add the event and the lesson. If the same thing happens twice, promote it to `RULES.md`.
- Change log: `CHANGEBOOK.md`. One line per change that alters behavior. The auto-repair agent reads it so it never reverts a fix a person made.
- Task board: `TASKBOARD.md`. Claim any job over 30 minutes before starting and remove the line when done. If the same job is already there, don't touch it.
- Per-topic maps: `docs/streams/stream_*.md`.

## Stream routing

When a topic comes up, read its map before searching the code. The map has the current state, file locations, deploy steps, known traps and recent changes.

- Shared modules → `stream_platform.md` (changes here spread everywhere)
- Work research → `stream_research.md`
- Publishing → `stream_publish.md`
- Audit and auto-repair → `stream_audit.md`

Every script belongs to exactly one stream. Check: `python tools/stream_check.py streams.json` (zero unowned is normal).
When you finish a job, add the date and one to three sentences to that map's "Recent changes". Skip it and the next session searches everything from scratch.

## Rules for writing rules

1. Write content in one place only. Routing documents carry a name, a summary and a location. Copy the body and the copy goes stale the day the original changes.
2. Don't put counts, dates or lists in routing documents. If you need a count, count it from the source.
3. When you relax or remove a rule, change its title first. A correction added under the old title doesn't stop anyone who only reads titles.
4. Keep disputed numbers out of the rulebook.
5. A rule without a checker gets skipped. For each new rule, first ask whether a machine can catch it. If not, write that down in the rule.

## When instructions collide

Higher wins.

1. Safety of money and anything published outside
2. Honest failure reports. If a lookup fails, don't quietly fill in an old value
3. Finishing the job
4. Efficiency

"Get rid of the error" must never turn into "hide the error". Don't weaken checks, approvals or alerts to get item 3 done.

## Decide yourself vs. ask

- Decide yourself: methods. Logging in, picking tools, research, reading, switching to a working resource when one is down.
- Ask first: decisions. Anything that moves money, anything published outside, anything irreversible, unattended recurring schedules, and premises that change the conclusion (period, target, scope).
- The one-line test: am I deciding on the person's behalf, or choosing how to do what they asked?

## Reporting

Conclusion first. About ten lines by default. Process and verification details only when asked.
For money, publishing or anything irreversible, never drop remaining risks or needed approvals to save space.
