# Beeline Tariff Marketing Campaign Agent

**SapaTech · HackAlem AI 2026 · трек 04 «Телекоммуникации»**

Агент планирует кампании смены тарифа для 23 441 синтетического абонента:
изучает профиль и историю переходов, проводит пилоты, учитывает их результаты
и выбирает до 10 кампаний. Цель — максимизировать прирост ARPU за вычетом
стоимости контактов, соблюдая ограничения бюджета и охвата.

Решение запускается в терминале и реализует официальный интерфейс
`Agent.act(env) -> list[dict]`. Используется локальная статистическая стратегия;
ключи API, внешние модели, GPU и веб-сервер не требуются.

## Что нужно для запуска

- Git и доступ к этому репозиторию.
- **Python 3.11 или новее** с поддержкой `venv` и `pip`; проверен Python 3.13.7 на macOS.
- Интернет для клонирования и установки зависимостей. После установки агент работает локально.
- **Официальный `beeline_case_participants.zip` от организаторов.** В нём находятся
  данные, среда, evaluator и генератор CSV. Эти файлы не хранятся в Git.
  Судьям нужен исходный пакет кейса Beeline; если его нет, запросите его у организаторов.

Используйте новый клон: команда `make_submission.py` заново создаст в нём
`submission.csv`. Установщик перенесёт из ZIP только 13 необходимых файлов
без изменения их содержимого. В командах ниже замените путь к архиву на свой;
кавычки позволяют использовать путь с пробелами. Запускайте команды по порядку
из корня клона и переходите к следующей только после успешного завершения предыдущей.

## Запуск на macOS / Linux

Убедитесь, что `python3 --version` показывает Python 3.11+.
Если установлено несколько версий, используйте подходящую команду, например
`python3.13`, вместо `python3` при создании окружения. Активация venv не нужна.

```sh
git clone https://github.com/BAITC-Hacks/hack-6e2e5c8b-sapatech.git beeline_check
cd beeline_check
git switch main
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/prepare_case.py '/absolute/path/to/beeline_case_participants.zip'
.venv/bin/python -m unittest scripts.test_agent strategy.tests.test_core evals.test_contract_checks -v
.venv/bin/python local_eval.py
.venv/bin/python evals/check_agent.py --agent agent.py --package .
.venv/bin/python evals/check_agent.py --agent agent.py --package . --feedback-check
.venv/bin/python make_submission.py
git diff --exit-code --ignore-space-at-eol -- submission.csv
```

## Запуск на Windows / PowerShell

Убедитесь, что `py -3 --version` показывает Python 3.11+.
Команды используют Python Launcher (`py`); если его нет, используйте `python`
вместо `py -3`, предварительно проверив версию. Активация venv и изменение
ExecutionPolicy не нужны.

```powershell
git clone https://github.com/BAITC-Hacks/hack-6e2e5c8b-sapatech.git beeline_check
cd beeline_check
git switch main
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/prepare_case.py 'C:\path\to\beeline_case_participants.zip'
.\.venv\Scripts\python.exe -m unittest scripts.test_agent strategy.tests.test_core evals.test_contract_checks -v
.\.venv\Scripts\python.exe local_eval.py
.\.venv\Scripts\python.exe evals/check_agent.py --agent agent.py --package .
.\.venv\Scripts\python.exe evals/check_agent.py --agent agent.py --package . --feedback-check
.\.venv\Scripts\python.exe make_submission.py
git diff --exit-code --ignore-space-at-eol -- submission.csv
```

Полный чистый запуск подтверждён на macOS. Для Linux и Windows приведены
соответствующие команды; в последней независимой проверке эти ОС не запускались.

## Как понять, что проверка прошла

| Шаг | Ожидаемый результат |
|---|---|
| Установка ZIP | `Installed 13 unchanged files` |
| Unit-тесты | `Ran 35 tests`, затем `OK` |
| `local_eval.py` | `Статус: PASS`, чистый результат около **+327 917** на seed 42 |
| `check_agent.py` | `"errors": []`, 10 финальных кампаний и 20 пилотов |
| `--feedback-check` | `"feedback_changes_campaigns": true`; `errors` пуст в обоих сценариях |
| `make_submission.py` | `submission.csv` с 10 строками кампаний и заголовком |
| Последний `git diff` | Нет вывода и код завершения 0: CSV совпал с версией в Git с учётом различий LF/CRLF |

На seed 42 суммарно используются **15 000 контактов** и **99 998 из 100 000**
единиц бюджета. Выполнение `Agent.act` в проверке на macOS заняло около 2 секунд.
Строка evaluator «Кампаний: 30» включает 20 пилотов и 10 финальных кампаний.
Предупреждения о cap 5 000, частичном охвате и повторных контактах допустимы;
проверка исходного ответа через `check_agent.py` должна завершиться без ошибок.

## Проверка на нескольких сценариях

После установки выполните:

```sh
.venv/bin/python local_eval.py --runs 10
```

В PowerShell используйте `.\.venv\Scripts\python.exe local_eval.py --runs 10`.
В независимой проверке все 10 прогонов завершились: 9 прибыльных, 1 убыточный;
медиана **+575 915**, минимум **−282 662**, максимум **+943 808**.
По [расширенному аудиту 100 seed](docs/planning/next_round_2026_09_23/project_actual_audit_2026_09_23_ru.md)
75 прогонов прибыльны, 25 убыточны; средний net **+315 844.67**.

Данные синтетические и не описывают реальных клиентов или показатели Beeline.
Mock-среда проверяет механику, но её эффекты отличаются от скрытого судейства:
эти числа не предсказывают итоговый балл и не гарантируют прибыль.

## Как работает решение

1. `agent.py` читает публичные данные и историю, управляет пилотами, временем
   и ресурсами, проверяет формат финального ответа.
2. `strategy/` строит кандидатов по текущему тарифу и ARPU-сегменту, уточняет
   исторические оценки по результатам пилотов и выбирает портфель кампаний.
3. `evals/` проверяет исходный ответ до исправлений официального evaluator,
   соблюдение лимитов, влияние обратной связи и воспроизводимость.
4. Официальный `make_submission.py` запускает агента на seed 42 и создаёт CSV.

Ограничения: 1–10 финальных кампаний, до 5 000 абонентов на кампанию,
15 000 контактов и 100 000 бюджета **вместе с пилотами**; до 20 пилотов
с запросом 10–200 абонентов. Каналы: `push`, `sms`, `digital_ads`, `call`.
Один абонент даёт только лучший эффект, но повторные контакты расходуют ресурсы.

История переходов не доказывает причинный эффект кампании. Перенос оценок
бесплатных push-пилотов на платные каналы — приближение без прямой проверки
пилотами на этих каналах. Подробнее: [описание стратегии](strategy/README.md)
и [разбор рисков](strategy/reports/B1-002-r1.md).

## Если запуск не удался

| Сообщение / ситуация | Что проверить |
|---|---|
| `Repository not found` при клонировании | Доступ вашей учётной записи GitHub к командному репозиторию |
| Ошибка установки numpy/pandas | Версию Python (3.11+), наличие pip и доступ к PyPI; используйте зафиксированный `requirements.txt` |
| Не найден `local_eval.py`, `mock_environment` или CSV | Успешно ли выполнен `scripts/prepare_case.py`; текущий каталог должен быть корнем клона |
| `FileNotFoundError` при установке ZIP | Заменён ли пример пути на существующий архив |
| `KeyError` при установке ZIP | Используется ли исходный ZIP кейса: установщик ожидает официальную структуру файлов |
| `Refusing to overwrite different file` | Используйте новый клон: установщик сохраняет уже существующие отличающиеся файлы |
