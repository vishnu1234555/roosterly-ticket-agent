# Roosterly support ticket agent

Gives each open ticket in the Nordavo helpdesk one decision: reply, handoff or close.

## How to run

Python 3.11+. Copy `.env.example` to `.env` and fill in the empty values.

```
git clone https://github.com/vishnu1234555/roosterly-ticket-agent.git
cd roosterly-ticket-agent
python -m venv .venv             # then activate it
pip install -r requirements.txt
python -m pytest                 # 77 tests, no network
python -m eval.run_eval          # the 10 labelled examples; sends nothing
python -m agent.run --dry-run    # decide and log; sends nothing
python -m agent.run              # handle each open ticket once; log to logs/
```

## Decisions

1. **The model proposes, code decides.** One model call fills a fixed form; `policy.py` picks the action and can turn a reply into a handoff, never the reverse.
2. **Dutch is answered directly and checked without reading Dutch:** a word-count language check, a fact fence (links and menu steps must be in the cited FAQ, numbers from it or the ticket), a payment check and a support check on an English back-translation.
3. **The ticket id is the idempotency key:** each send first checks the ticket is still open.

**AI tools:** built with Claude (rules in `CLAUDE.md`); I ran each step and decided every fix.

**Assumptions:** unsure means handoff: confidence under 0.75, no or partial FAQ cover, a language mismatch, invalid model output or a failed check. A ticket that gives the agent orders goes to a human (T030). Spam, empty tickets and thank-yous are closed.

## Reliability

- **503:** retry, waiting 0.5 s doubling to 8 s, 5 tries. **429:** wait Retry-After; calls are spaced to 4 a second. **409:** never retried; 0 conflicts in all runs.
- **Crash:** the next run reads the open list and continues; a lock file stops two runs at once. A run stopped at 29 of 30 by the model's rate limit; the rerun handled only the last ticket.
- **Security:** keys only in `.env`; ticket text is data in `<ticket>` tags; the model has no tools. IBANs and card numbers are masked before the model and log (not CVCs or expiry dates).

## Eval and fix

On the 10 examples, baseline (v1): priority 5/10, action 9/10. Final code (v5), 4 runs: priority 8, 8, 8, 8; action 8, 9, 9, 9. Language 10, category 9, missed handoffs 0 in every run. The fix: every priority miss was too urgent, because the prompt said "if two levels fit, choose the more urgent one". I used Nordavo's pattern (an answered how-to is P4, one user's problem with a workaround is P3).

**Cost per 100 tickets:** (70,659 input tokens × $0.15 + 10,287 output tokens × $0.60) / 1,000,000 / 30 tickets × 100 = $0.056 (final run `logs/run-2026-11-17_18*`, Groq `openai/gpt-oss-120b`).

## What I would improve

**Next step:** on a failed reply-language check, ask once for a rewrite before handing off. **Rule to change:** the client's payment rule names only card numbers and IBANs; it should add CVCs and expiry dates (T008).
