# Независимые проверки Beeline

Владелец: Ерлан, T-05. Скрипты используют только публичный интерфейс
`Agent.act(env)` и официальный пакет участника, расположенный вне Git.

- `contract_checks.py` проверяет исходный список кампаний до sanitizer:
  поля, фильтры, аудитории, пилоты, лимиты, платные повторные контакты.
- `public_stub.py` возвращает управляемый публичный результат пилота для
  проверки, меняется ли решение агента при иной обратной связи.
- `check_agent.py` запускает агента на mock-среде или stub и выводит
  агрегированный JSON. `--feedback-check` использует ответы +0.5 и -0.5.
- `compare_agents.py` прогоняет два агента на одинаковых seed официальным
  `local_eval.evaluate_agent`, до sanitizer сохраняет ошибки исходного ответа
  по каждому seed и сводит net ARPU, расходы, время агента и полное время.
  Автоматический cap 5 000 и частичная обрезка ресурсами — предупреждения:
  в официальном формате кампании нельзя указать число контактов. Нулевой
  фактический охват — ошибка.
  Код 1 означает незавершённый прогон, предупреждение evaluator или ошибку
  raw-контракта, даже если score вычислен.
- `check_submission.py` дважды запускает официальный `make_submission.py` в
  отдельной временной копии без `OPENAI_API_KEY` и сравнивает SHA-256 CSV.
- `test_contract_checks.py` проверяет сам валидатор на нормальном и ошибочном
  ответе, пропусках, нулевом ARPU, отрицательном пилоте и истощении ресурсов.

Запуск из корня репозитория:

```text
python -m unittest evals.test_contract_checks -v
python evals/check_agent.py --agent <package>/agent_template.py --package <package> --seed 42
python evals/compare_agents.py --baseline-agent <package>/agent_template.py --candidate-agent <package>/agent.py --package <package> --runs 10
python evals/check_submission.py --package <package> --agent <package>/agent.py
```

Замените `<package>` локальным путём к распакованному официальному пакету.
Командный `agent.py` и `strategy/` интегрируются владельцем T-03. При проверке
`check_submission.py` можно передать `--strategy <repo>/strategy`.
Проверки не меняют официальные `local_eval.py` и `scoring_core.py`.

Замер baseline: [docs/evaluation/baseline.md](../docs/evaluation/baseline.md).
