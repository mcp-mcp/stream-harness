# STREAM MAP · <stream name>

> Owned code is defined by `<key>` in `streams.json`. If the rules live in a separate document, only name it here.
> Keep only durable structure, procedures and traps in this map. Don't write volatile values (prices, balances, visitor counts). Write how to look them up.

## What it covers

Two or three lines. What this stream handles and what it doesn't (things that look similar but belong to another stream).

## File map

- Main script: `<path>` (when it runs, what it does)
- Data: `<path>`
- Settings: `<path>` (never secrets here, only where the vault is)

## Procedures

Deploy, run and roll back, in order. Mark the steps a person has to do.

## Traps

Only what actually went wrong in this stream. Nothing "just in case".

## In progress

Point to open items by their task number only.

## Recent changes

- YYYY-MM-DD What changed and why, in one to three sentences. Long incident write-ups go to the incident log, not here.
