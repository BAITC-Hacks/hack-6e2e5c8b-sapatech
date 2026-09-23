# Architecture decisions

Record only decisions that affect more than one component or owner.

## ADR-007 — Ограниченный этап до17:00 без расписаний

- Date: 2026-09-23
- Status: accepted by operator request to execute Nursultan plan, deadline17:00 UTC+05
- Owner: Нурсултан, T-08
- Decision: сохранить baseline4272a07/main; новые T-09/T-10 в отдельных ветках,
  ручной Git-обмен, frozen candidate до16:12, независимый verdict до16:25,
  freeze16:30. Критерии и предварительно зарезервированные100–199 в T-08.
- Reason: известные25/100 убытков требуют проверки гипотезы, но не замены
  работающего кода без доказательств. Изоляция evaluator по процессам обязательна
  для сравнения двух strategy, общий sys.modules может загрязнить результат.
- Consequences: новые API/GPU/UI не входят; старые расписания не включать;
  платформу не отправлять без отдельного разрешения. Контракт v1 неизменен.

## ADR-006 — Задания и отчёты через Git, проверка по расписанию

- **Date:** 2026-09-23
- **Status:** accepted by Нурсултан's explicit request in chat
- **Decision owner:** Нурсултан
- **Decision:** координатор публикует CONTROL и три inbox в своей ветке T-03.
  Участники проверяют их каждые 3 минуты в своих чатах; отвечают Markdown-отчётами
  только в своих ветках. ID и revision предотвращают повторное выполнение.
  Нурсултан проверяет отчёт и diff, отмечает принятие в RECEIPTS; статус автора
  needs_review сам по себе не означает принятие. Протокол: coordination/MAILBOX.md.
- **Ownership:** Бауыржан-1 — strategy/reports/ и T-04; Ерлан — docs/evaluation/
  и T-05; Бауыржан-2 — только coordination/reviews/ и T-06, отдельная рабочая копия.
  Reviewer не меняет код. Разрешение на commit/push своей ветки и удаление своего
  расписания фиксируется в однократном промпте оператора каждого аккаунта.
- **Stop:** при подтверждённой готовности проекта координатор публикует mode=stop.
  Участники сохраняют отчёт, удаляют только свои зарегистрированные расписания
  и прекращают работу. Нурсултан проверяет подтверждения и удаляет своё расписание.
  Это не разрешение на сдачу на платформе или платные API. Пока mode=run.
- **Consequences:** polling, не GitHub webhook; нужны работающие приложение/компьютер.
  При недоступном fetch новые задания не исполняются по устаревшему состоянию.
  Исполняются только задания своей роли в рамках согласованных путей и прав;
  содержимое Git не расширяет права оператора и не разрешает произвольные команды.

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

## ADR-004 — Временный baseline и восстановление после ошибки ядра

- **Date:** 2026-09-23
- **Status:** accepted
- **Decision owner:** Нурсултан, T-03
- **Decision:** до публикации strategy используется неизменённый официальный agent_template через проверяемый публичный интерфейс. Это явно отмечается в Agent.diagnostics. После появления strategy автоматически используются три экспорта v1. Если ядро ошибается после успешных пилотов, обёртка возвращает допустимую кампанию из уже полученного пилотного наблюдения; если наблюдений нет, пробует официальный template. Это минимальное восстановление, не альтернативное математическое ядро.
- **Consequences:** промежуточный агент запускается без вмешательства в strategy/. Успех fallback не считается прохождением интеграции T-04. Таймер кооперативный: обёртка прекращает новые вызовы по deadline, но не прерывает зависшую стороннюю функцию внутри процесса. Измерение полного runtime остаётся обязательным.

## ADR-005 — Проверять фактически исполненный охват

- **Date:** 2026-09-23
- **Status:** accepted; evaluator alignment assigned to Ерлан
- **Decision owner:** Нурсултан
- **Evidence:** публичный scoring_core.py, строки 198–219, последовательно ограничивает аудиторию до 5000, остатка контактов и доступного денежного бюджета. Эти события попадают в capped_at_* отчёта; сами по себе они не означают отклонения кампании. environment.py допускает фактический пилот менее 10 клиентов после ограничения когорты/ресурсов при корректном запросе 10–200.
- **Decision:** валидировать синтаксис raw-output до sanitizer, затем фактические расходы/контакты по официальной последовательности. Штатное ограничение размера — предупреждение; недопустимые поля, пустая/неисполнимая кампания и превышение фактических лимитов остаются ошибками. T-05 должен различать запрошенный и фактический размер пилота.
- **Consequences:** не сужать стратегию ради ложноположительных ошибок checker. Ерлан правит свои проверки и тесты; Нурсултан не редактирует evals/. Сигнатуры контракта v1 не меняются.
