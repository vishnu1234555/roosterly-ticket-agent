# Roosterly support ticket agent

An agent that reads Roosterly's open support tickets from the Nordavo helpdesk and sends one decision per ticket: reply, handoff or close.

## How to run

Python 3.11 or newer.

```
python -m venv .venv
.venv\Scripts\activate             (Mac or Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env             (Mac or Linux: cp .env.example .env), then fill in the empty values
python -m pytest                   # tests, no network
python -m eval.run_eval            # eval on the 10 labelled examples; sends nothing
python -m agent.run --dry-run      # decide and log every open ticket; sends nothing
python -m agent.run                # handle every open ticket once
python -m agent.reset              # re-open the practice tickets; asks you to type RESET
```

Each run writes `logs/run-<date>_<time>.jsonl`, one line per ticket. Each eval writes a file in `eval/results/`.

## Decisions

1. **The model proposes, code decides.** One model call per ticket returns a fixed form, validated with pydantic. `policy.py` turns it into the action with plain rules: a client-rule flag or tripwire word, orders inside the ticket, no FAQ entry, partial cover, a language mismatch, or confidence under 0.75 means handoff. Code can turn a reply into a handoff, never the reverse. Unsure means handoff.
2. **Dutch is handled directly, and every reply is checked without reading Dutch:** a word-count language check, a fact fence (every link, email, number and menu step must appear in the cited FAQ entries), a payment-pattern check, and a separate back-translation call that sees only the reply and is saved in the log. A failed check turns the reply into a handoff. Cost: one extra model call per reply.
3. **The helpdesk's open list is the only record of what is handled.** Before every send the agent checks the ticket is still open, and after a timeout it checks again before any retry.

TODO: how I used AI tools (with a pointer to CLAUDE.md), and the assumptions I made where the brief was open.

## Reliability

- **503:** retried with a growing wait (0.5 s, doubling, up to 8 s; 5 tries). **429:** waits `Retry-After`; calls are spaced to 4 a second. **409:** logged and never retried; the check before each send is there to prevent it.
- **Crash:** the next run reads the open list again and continues. A lock file stops two runs at once. TODO: crash test result. Known limit: if the process dies between a send and its log line, that line is missing; the decision is in the helpdesk and the next run skips the ticket.
- **Model:** invalid output gets one retry with the error, then a handoff with a plain note. If the provider is down or a daily limit is hit, the run stops and the remaining tickets stay open.
- **Security:** keys only in `.env`, which git ignores. IBANs (any country) and 13-19 digit card numbers are masked before the model call and before anything is logged. Ticket text goes inside `<ticket>` tags as data; a ticket that gives orders goes to a human. The model has no tools. Logs hold no subject or body.

## Eval and fix

TODO: scores before (missed handoffs, needless handoffs, then language, category, priority and action out of 10), the one fix, scores after. Ten examples is a small set: one ticket is 10 points.

Cost per 100 tickets = (input tokens × $0.15 + output tokens × $0.60) / 1,000,000 / tickets × 100, at Groq's prices for `openai/gpt-oss-120b`. TODO: the real numbers from a full run.

## What I would improve

TODO: the next step, and one thing to change in the brief or the client's rules.
