# Architecture decisions

Record only decisions that affect more than one component or owner.

## ADR-001 - Initial shared job contract

- **Date:** 2026-09-23
- **Status:** proposed
- **Decision owner:** PERSON_A
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
