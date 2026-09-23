# Beeline Tariff Marketing Campaign Agent

Проект команды SapaTech для HackAlem AI 2026, трек 04 «Телекоммуникации».
Задача — выбрать до 10 маркетинговых кампаний по смене тарифа для синтетической
аудитории из 23 441 абонента. Решение должно повысить суммарный ARPU после
вычета стоимости контактов. Эти данные не описывают реальных клиентов или
показатели Beeline.

**Состояние проекта:** в ветке Нурсултана `feat/T-03-nursultan-agent`
объединены `agent.py`, `strategy/` и проверки T-05 (merge `dca1954` с
сохранением авторства). В этой рабочей ветке Ерлана находятся только его
проверки и документация; команды полного проекта запускаются из
интегрированной ветки. Общий `submission.csv` и сдача на платформе остаются
ответственностью Нурсултана; публикация Git-коммита сама по себе не сдача.

## Основной сценарий

Официальный runner передаёт объект `env` методу `Agent.act(env)`. Агент читает
профиль аудитории и тарифы, проводит небольшие пилоты через публичный
`env.run_pilot(...)`, использует наблюдения и возвращает список кампаний.
Организаторский evaluator затем рассчитывает прирост ARPU по уникальным
абонентам и вычитает стоимость всех контактов, включая пилотные.

Ограничения: 1–10 финальных кампаний, до 5 000 абонентов в каждой, всего до
15 000 контактов и 100 000 у.е.; до 20 пилотов с запросом 10–200 человек.
Фактический охват пилота может быть 1–9 после ограничения аудиторией или
ресурсами. Каналы: `push`, `sms`, `digital_ads`, `call`.
Время исполнения агента планируется
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

## Проверка интегрированного проекта

Требуются Python, pandas и numpy, а также **отдельная локальная копия**
официального пакета с `agent.py` и `strategy/` из интегрированной ветки.
Оригинал пакета и общий `submission.csv` не перезаписывайте. Из корня
интегрированного клона, заменив `<staged>` и `<package>` локальными путями:

```text
python -m unittest evals.test_contract_checks -v
python evals/check_agent.py --agent <staged>/agent.py --package <staged> --seed 42
python evals/check_agent.py --agent <staged>/agent.py --package <staged> --feedback-check
python evals/check_submission.py --package <package> --agent <staged>/agent.py --strategy <staged>/strategy
```

Эти команды фактически исполнены на macOS с интегрированным исполняемым
кодом `7c27cfe`: 9/9 тестов, raw-check без ошибок, pilot feedback меняет
кампании, два CSV идентичны. Полное сравнение на одинаковых seed 0–9
публиковалось ранее: 9/10 положительных mock-результатов, средний net ARPU
533 014.48. Это не прогноз hidden judge; после документальных коммитов
полный multi-seed без изменения агента/ядра не повторяли. Доказательства:
[интеграционный отчёт](docs/evaluation/integrated-f95a8e3.md),
[повторная проверка](docs/evaluation/recheck-9f782f1.md),
[ER-001](docs/evaluation/ER-001-r2.md).

## Официальный template как baseline

Из корня репозитория, заменив `<package>` путём к распакованному архиву:

```text
python -m unittest evals.test_contract_checks -v
python evals/check_agent.py --agent <package>/agent_template.py --package <package> --seed 42
python evals/check_agent.py --agent <package>/agent_template.py --package <package> --feedback-check
python evals/compare_agents.py --baseline-agent <package>/agent_template.py --candidate-agent <package>/agent_template.py --package <package> --runs 10
python evals/check_submission.py --package <package> --agent <package>/agent_template.py
```

Два CSV совпадают внутри macOS. В ER-001 проверено: SHA-256 Windows-файла,
сообщённый интегратором, точно равен SHA-256 того же macOS CSV после замены
LF на CRLF. Содержание и порядок строк при этой операции не меняются;
межплатформенную разницу байтов объясняют окончания строк. Подробные хеши и
версии среды — в [отчёте ER-001](docs/evaluation/ER-001-r2.md).

Эти команды проверены на локальном пакете с Python и pandas/numpy. Тест
`--feedback-check` у официального шаблона завершается кодом 1: он обнаруживает
нарушения контракта в искусственных крайних случаях. Сравнение шаблона с ним
же тоже возвращает код 1: на seed 3 исходный ответ содержит ноль финальных
кампаний, хотя evaluator продолжает считать проведённые пилоты.
Агрегированные результаты записаны в
[baseline-отчёте](docs/evaluation/baseline.md).
Готов [пятиминутный демо-сценарий](docs/evaluation/demo.md). Для показа нужно
взять проверенные метрики из отчётов выше; фактический публичный показ ещё не
подтверждён.

## Проверенный запуск в PowerShell (Windows)

Нурсултан выполнил на Windows Python 3.12.14, pandas 3.0.1, numpy 2.3.5:
9/9 тестов, raw-check seed 42, feedback-check, две генерации CSV,
`local_eval.py` и `make_submission.py` — все с exit 0. Подтверждённые
команды и хеши записаны в [RECEIPTS на коммите `2dd4277`](https://github.com/BAITC-Hacks/hack-6e2e5c8b-sapatech/blob/2dd4277/coordination/RECEIPTS.md).
Из корня интегрированного клона задайте путь к **уже установленному**
`python.exe` и распакованному официальному пакету; `$C` — отдельная копия.
Имена переменных и временный путь адаптированы для повторения, а сами
Python-вызовы сверены с RECEIPTS:

```powershell
$R = (Get-Location).Path
$P = 'C:\path\to\existing\python.exe'
$SourceCase = 'C:\path\to\beeline_case_participants'
$C = Join-Path $env:TEMP ("beeline-t05-" + [guid]::NewGuid().ToString('N'))
Copy-Item -LiteralPath $SourceCase -Destination $C -Recurse
& $P -m unittest evals.test_contract_checks -v
& $P evals/check_agent.py --agent "$R/agent.py" --package $C --seed 42
& $P evals/check_agent.py --agent "$R/agent.py" --package $C --feedback-check
& $P evals/check_submission.py --package $C --agent "$R/agent.py" --strategy "$R/strategy"
```

Нурсултан использовал конкретный `python.exe` из своей локальной среды; его
машинный путь в RECEIPTS не обязателен для других компьютеров. Для запуска
официальных команд скопируйте собственный код только в `$C`:

```powershell
Copy-Item "$R\agent.py" "$C\agent.py" -Force
New-Item -ItemType Directory -Path "$C\strategy" -Force | Out-Null
Copy-Item "$R\strategy\*" "$C\strategy" -Recurse -Force
Push-Location $C
try {
    & $P local_eval.py
    & $P make_submission.py
} finally {
    Pop-Location
}
```

На машине Ерлана PowerShell недоступен, поэтому Windows-результаты выше —
свидетельства Нурсултана, а не мои прогоны. Создание venv, `py -3`,
`pip install` и `local_eval.py --runs 10` в описанном Windows-сеансе **не
исполнялись**; установка Python и зависимостей остаётся общей инструкцией,
не подтверждённой этим тестом.

## Интерпретация результата

`local_eval.py` использует mock-эффекты, отличающиеся от скрытого судейства.
Его числа показывают корректность механики и устойчивость на данных-заглушке,
но не гарантируют скрытый балл. Валидатор T-05 проверяет исходный ответ
`Agent.act` до автоматического отбрасывания и обрезания evaluator; пилотная
обратная связь проверяется отдельно публичным stub. Известные ограничения и
измерения проверенной интеграции записаны в отчёте выше.
