# Architecture decisions

Record only decisions that affect more than one component or owner.

## ADR-001 - Initial shared job contract

- **Date:** 2026-09-23
- **Status:** superseded by ADR-003
- **Decision owner:** Нурсултан
- **Context:** UI and Controller need a stable interface for parallel development.
- **Decision:** Use the request, status, and result schemas in `docs/contracts.md` until the official case interface is integrated.
- **Consequences:** Producers, mocks, and consumers must update together when the schema changes.

## ADR-002 - Select the Beeline tariff campaign case

- **Date:** 2026-09-23
- **Status:** accepted
- **Decision owner:** team
- **Context:** HackAlem published the official tracks and the team selected track 04 Telecommunications, Beeline Tariff Marketing Campaigns Case.
- **Decision:** Treat the official root-level `Agent.act(env) -> list[dict]` interface and the supplied evaluator as the submission contract. Build a deterministic local strategy first. Managed Agents, a controller, an executor, and a web UI remain optional until the evaluator path is working.
- **Consequences:** `agent.py`, pilot use, hard budget/contact checks, multi-seed evaluation, and reproducible `submission.csv` take priority over the neutral skeleton's optional components. Any external model call requires a local fallback.

## ADR-003 — Разделение ядра, интеграции и проверки

- **Date:** 2026-09-23
- **Status:** accepted for implementation; implementation pending
- **Decision owner:** Нурсултан
- **Context:** Нурсултан поручил распределить работу на троих и сначала выдать Бауыржану ядро.
- **Decision:** Бауыржан владеет `strategy/` (кандидаты, выбор пилотов, обновление оценок, портфель). Нурсултан владеет `agent.py`, загрузкой данных, вызовами публичного `env.run_pilot`, интеграцией и сдачей. Ерлан владеет `evals/`, отчётами проверки и итоговым README. Внутренние синхронные функции описаны в `docs/contracts.md`; они не получают объект env. Официальный `Agent.act(env) -> list[dict]` сохраняется.
- **Consequences:** три отдельные ветки и непересекающиеся пути. На первом этапе только pandas/numpy и локальная детерминированная стратегия. UI, GPU и обязательные LLM-вызовы не нужны. Проверяется исходный список кампаний до обрезания evaluator. Изменения контракта согласует Нурсултан до изменения зависимого кода.
- **Delivery:** инструкции Бауыржану коммитятся первым пакетом T-02; инструкции остальным — следующим. T-01 и авторство её коммитов сохраняются.
- **Verification:** при повторной сверке публичного конструктора уточнено: источник profile — `env.customer_profile`; внутренние сигнатуры v1 не меняются.
