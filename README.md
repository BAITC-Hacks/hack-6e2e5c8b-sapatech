# HackAlem AI Tariff Marketing Campaign Agent

Team workspace for HackAlem AI 2026, track 04 Telecommunications, Beeline Tariff Marketing Campaigns Case.

The current source of truth is [`HACKATHON.md`](HACKATHON.md). It records the official agent contract, campaign limits, supplied data, evaluation commands, security rules, planned strategy, team ownership, and open organizer clarifications.

План до сдачи, модели и ресурсы: [PLAN.md](PLAN.md).
Персональные инструкции: [Нурсултан](coordination/people/NURSULTAN.md),
[Бауыржан](coordination/people/BAUYRZHAN.md), [Ерлан](coordination/people/ERLAN.md).
Бауыржан начинает ядро по T-04 от первого пакета `580f1eb`, не ожидая остальных.
Это планирование: проверки и результаты реализации пока не заявлены.

Implementation has not started. The first milestone is a reproducible root-level `agent.py` that uses `env.run_pilot(...)`, respects every budget and contact constraint, passes `python local_eval.py`, remains stable across multiple seeds, and generates `submission.csv` through `python make_submission.py`.

## Structure

```text
AGENTS.md                 shared instructions for every Codex session
HACKATHON.md              selected case, constraints, plan, and live status
docs/                     shared contracts and architecture
coordination/             task cards and architecture decisions
controller/               optional application orchestration
executor/                 optional self-hosted runtime and tools
web/                      optional user interface
demo_data/                safe reproducible demo inputs only
evals/                    quality checks and expected outputs
deploy/                   local or cloud deployment definitions
jobs/                     generated runtime state, ignored by Git
```

Do not commit API keys, `.env` files, the participant ZIP, or organizer-provided datasets unless organizers explicitly authorize storing the data in the private team repository.
