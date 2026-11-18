# Roosterly support ticket agent

Reads Roosterly's open tickets from the Nordavo helpdesk and sends one decision per ticket: reply, handoff or close.

## How to run

Python 3.11+. Copy `.env.example` to `.env` and fill in the empty values.

```
pip install -r requirements.txt
python -m pytest                 # 77 tests, no network
python -m eval.run_eval          # 10 labelled examples, sends nothing (--repeat 3 for the spread)
python -m agent.run --dry-run    # decide and log, send nothing
python -m agent.run              # handle every open ticket once
python -m agent.reset            # re-open practice tickets; asks you to type RESET
```

Logs: `logs/run-<date>_<time>.jsonl`, one line per ticket. Eval results: `eval/results/`.

## Decisions

1. **The model proposes, code decides.** One model call fills a fixed form (checked with pydantic). `policy.py` picks the action: a client-rule flag or tripwire word, orders in the ticket, no FAQ entry, partial cover, a language mismatch or confidence under 0.75 means handoff. Code never turns a handoff into a reply. Code also sets P1 for a security or legal risk.
2. **Dutch is handled directly; replies are checked without reading Dutch:** a word-count language check, a fact fence (links, numbers and menu steps must appear in the cited FAQ entries), a payment check, a back-translation that sees only the reply, and a support check (a second call that lists anything the FAQ does not say). Any failure means handoff. Cost: two extra calls per reply. The support check stopped invented troubleshooting steps in practice runs and once in the final run.
3. **The helpdesk's open list is the only record.** The agent checks a ticket is still open before every send, and again after a timeout.

**AI tools:** a Gemini prototype, built only to learn the API, was thrown away. This repo was built with Claude from a written plan (`CLAUDE.md` holds its rules). I ran every step against the real helpdesk, read the logs and decided each fix.

**Assumptions:** the brief leaves "unsure" open, so I defined it in code: the agent counts itself unsure, and hands the ticket to a human, when the model's confidence is under 0.75, no FAQ entry answers the ticket, the FAQ answers only part of it, the language is not Dutch, English or German or the word-count check disagrees with the model, the model gives no valid form or no reply, or a reply check fails (reply language, fact fence, payment details, support check). Upgrade questions are answered from F05; cancel, downgrade or pause go to a human. A Basis customer asking for a Plus feature is told it is in Plus and how to upgrade. Feature requests are answered from F10. Spam, empty tickets and thank-yous are closed. An outage for many users goes to a human.

## Reliability

- **503:** retry with a growing wait (0.5 s doubling to 8 s, 5 tries). **429:** wait `Retry-After`; calls spaced to 4 a second. **409:** never retried. All runs: 0 conflicts.
- **Crash:** the next run reads the open list and continues; a lock file stops two runs at once. Tested for real: a run stopped after 29 tickets on the model's rate limit, and the rerun handled only the last one. The final run finished in three parts for the same reason, each ticket handled once. Known limit: a crash between a send and its log line loses that line, not the decision.
- **Model:** invalid output gets one retry, then a handoff. A provider outage or a wait over 60 s stops the run; open tickets stay open.
- **Security:** keys only in `.env` (git-ignored). IBANs and 13-19 digit card numbers are masked before the model call and before logging. Ticket text is data inside `<ticket>` tags. The model has no tools. Logs hold no subject or body.

## Eval and fix

| | Baseline (prompt v1) | After fixes (v5, three runs) |
|---|---|---|
| Missed handoffs | 0 | 0, 0, 0 |
| Language / category | 10, 9 | 10, 9 (all runs) |
| Priority | 5/10 | 8, 8, 8 |
| Action | 9/10 | 8, 9, 9 |

**The fix:** every priority miss was too urgent (four by one level, E02 by two), because the prompt said "if two levels fit, choose the more urgent one". I replaced it with Nordavo's pattern (an answered how-to is P4, one user's problem with a workaround is P3): priority went from 5/10 to 8-9/10. Ten examples is small (one ticket = 10 points) and the model varies between runs. Still missed: E01, an old-iOS crash that F12 answers.

**Cost per 100 tickets** = (input tokens × $0.15 + output tokens × $0.60) / 1,000,000 / tickets × 100 (Groq, `openai/gpt-oss-120b`). Final run: (70,659 × 0.15 + 10,287 × 0.60) / 1,000,000 = $0.0168 for 30 tickets, **about $0.056 per 100**.

**Final run:** 30 tickets: 11 replies, 17 handoffs, 2 closes, 0 conflicts.

## What I would improve

**Next step:** when the reply-language check fails (it caught Dutch drafts for German customers), ask once for a rewrite instead of handing off. **One change to the client's help centre:** menu names exist only in Dutch with English meanings, so German customers never see German menu names; adding them would make German replies clearer.
