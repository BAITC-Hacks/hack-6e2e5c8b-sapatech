# Beeline Tariff Marketing Campaign Agent

Проект команды SapaTech для HackAlem AI 2026, трек 04 «Телекоммуникации».
Задача — выбрать до 10 маркетинговых кампаний по смене тарифа для синтетической
аудитории из 23 441 абонента. Решение должно повысить суммарный ARPU после
вычета стоимости контактов. Эти данные не описывают реальных клиентов или
показатели Beeline.

**Состояние этой ветки:** независимые проверки T-05 готовы. Интегрированный
`agent.py`, ядро `strategy/` и итоговый `submission.csv` находятся в работе у
других участников; результаты командного агента здесь пока не заявлены.

## Основной сценарий

Официальный runner передаёт объект `env` методу `Agent.act(env)`. Агент читает
профиль аудитории и тарифы, проводит небольшие пилоты через публичный
`env.run_pilot(...)`, использует наблюдения и возвращает список кампаний.
Организаторский evaluator затем рассчитывает прирост ARPU по уникальным
абонентам и вычитает стоимость всех контактов, включая пилотные.

Ограничения: 1–10 финальных кампаний, до 5 000 абонентов в каждой, всего до
15 000 контактов и 100 000 у.е.; до 20 пилотов по 10–200 человек. Каналы:
`push`, `sms`, `digital_ads`, `call`. Время исполнения агента планируется
меньше пяти минут при абсолютном пределе кейса в десять минут.

Компоненты по [контракту команды](docs/contracts.md):

- `agent.py` — официальный интерфейс и цикл пилотов; владелец Нурсултан;
- `strategy/` — генерация кандидатов, выбор пилотов и портфеля; владелец Бауыржан;
- `evals/` — независимая проверка сырого ответа и сравнение стратегий; владелец Ерлан;
- `docs/evaluation/` — подтверждённые агрегированные результаты проверок.

## Данные и зависимости

Нужен официальный архив `beeline_case_participants`, полученный на платформе
хакатона. Распакуйте его **вне репозитория**: там находятся
`customer_profile.csv`, `data/change_tariff.csv`, справочники тарифов,
`environment.py`, `mock_environment.py`, `scoring_core.py`, `local_eval.py`,
`make_submission.py` и `agent_template.py`. Архив, исходные CSV и ключи не
добавляются в Git. Для локального пути нужны Python, pandas и numpy; внешнее
API и GPU для базовой стратегии не требуются.

## Проверка опубликованных файлов T-05

Из корня репозитория, заменив `<package>` путём к распакованному архиву:

```text
python -m unittest evals.test_contract_checks -v
python evals/check_agent.py --agent <package>/agent_template.py --package <package> --seed 42
python evals/check_agent.py --agent <package>/agent_template.py --package <package> --feedback-check
python evals/compare_agents.py --baseline-agent <package>/agent_template.py --candidate-agent <package>/agent_template.py --package <package> --runs 10
python evals/check_submission.py --package <package> --agent <package>/agent_template.py
```

Эти команды проверены на локальном пакете с Python и pandas/numpy. Тест
`--feedback-check` у официального шаблона завершается кодом 1: он обнаруживает
нарушения контракта в искусственных крайних случаях. Агрегированные результаты
записаны в [baseline-отчёте](docs/evaluation/baseline.md).

## Подготовка итогового запуска в PowerShell

Ниже команда для Windows после появления `agent.py` и `strategy/` в командном
репозитории. Из корня клона команды укажите локальный путь к распакованному
официальному пакету:

```powershell
$Repo = (Get-Location).Path
$Case = 'C:\path\to\beeline_case_participants'
py -3 -m venv "$Repo\.venv"
$Python = "$Repo\.venv\Scripts\python.exe"
& $Python -m pip install pandas numpy
& $Python -m unittest evals.test_contract_checks -v
& $Python "$Repo\evals\check_agent.py" --agent "$Repo\agent.py" --package "$Case" --seed 42
& $Python "$Repo\evals\compare_agents.py" --baseline-agent "$Case\agent_template.py" --candidate-agent "$Repo\agent.py" --package "$Case" --runs 10
& $Python "$Repo\evals\check_submission.py" --package "$Case" --agent "$Repo\agent.py" --strategy "$Repo\strategy"
```

Для официальных команд сначала скопируйте только собственный код в отдельную
локальную копию распакованного пакета. Не перезаписывайте рабочие файлы других
участников и их финальный `submission.csv`:

```powershell
Copy-Item "$Repo\agent.py" "$Case\agent.py" -Force
New-Item -ItemType Directory -Path "$Case\strategy" -Force | Out-Null
Copy-Item "$Repo\strategy\*" "$Case\strategy" -Recurse -Force
Push-Location $Case
try {
    & $Python local_eval.py
    & $Python local_eval.py --runs 10
    & $Python make_submission.py
} finally {
    Pop-Location
}
```

PowerShell в текущем окружении отсутствует, поэтому эти Windows-команды пока
не отмечены как исполненные. Эквивалентные Python-вызовы проверены на macOS;
после интеграции нужно повторить чистый запуск на машине команды.

## Интерпретация результата

`local_eval.py` использует mock-эффекты, отличающиеся от скрытого судейства.
Его числа показывают корректность механики и устойчивость на данных-заглушке,
но не гарантируют скрытый балл. Валидатор T-05 проверяет исходный ответ
`Agent.act` до автоматического отбрасывания и обрезания evaluator; пилотная
обратная связь проверяется отдельно публичным stub. Известные ограничения и
измерения командного агента будут добавлены после его интеграции.
