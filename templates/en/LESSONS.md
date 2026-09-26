# LESSONS.md · Incident log

Record incidents and near misses one at a time, event first and lesson second. Newest on top.
When the same pattern shows up twice, promote it to a rule in `RULES.md` and note "promoted" here.
The agent reads only the lessons tied to the file it is about to change. It never reads the whole log.

## Format

```
## YYYY-MM-DD · One-line title (what went wrong)
- Event: what happened. Use numbers if there are any.
- Cause: why. If it's a guess, say so.
- Lesson: what to do differently. If a checker can catch it, name the checker.
```

## Examples

## 2026-09-07 · All 8 stale rules were copies
- Event: an audit of the instruction documents found 8 wrong rules. Every one of them was a copy left in another document after the original was updated.
- Cause: rule bodies and counts had been copied into routing documents for convenience. Only the originals got updated.
- Lesson: content lives in one place. Routing documents hold names, summaries and locations. Promoted to a rule.

## 2026-08-16 · The same sample got built four times
- Event: several AI sessions, unaware of each other, built the same video sample. Four identical results.
- Cause: there was no place to see who was working on what.
- Lesson: claim any job over 30 minutes on `TASKBOARD.md` first. If it is already there, don't start. Promoted to a rule.
