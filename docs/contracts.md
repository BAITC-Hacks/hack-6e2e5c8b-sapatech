# Контракт Beeline v1

Владелец: Нурсултан. Решение: ADR-003. Это согласованный интерфейс для реализации,
а не утверждение о готовом коде. Приоритет имеют публичные файлы официального пакета.

## Официальная граница

Корневой `agent.py` экспортирует `class Agent` с `act(self, env) -> list[dict]`.
Нурсултан загружает локальную историю, вызывает функции strategy, проводит пилоты
через публичный env и возвращает 1–10 кампаний. Только он изменяет `agent.py`.
`make_submission.py` генерирует CSV отдельно; `act` не пишет submission.

Доступны публичные `env.customer_profile`, `env.tariffs`, `env.channels`, счётчики бюджета,
контактов и пилотов, `pilot_history` и `run_pilot`. Закрытые эффекты не извлекаются.

## Интерфейс ядра Бауыржана

`strategy/__init__.py` экспортирует три функции:

```python
def build_candidates(profile, tariffs, history) -> list[dict]: ...
def choose_pilot(profile, tariffs, channels, candidates, observations, resources) -> dict | None: ...
def select_campaigns(profile, tariffs, channels, candidates, observations, resources) -> list[dict]: ...
```

- `profile = env.customer_profile`, `tariffs = env.tariffs`, `history`:
  pandas.DataFrame официального формата. Имя profile — локальный аргумент ядра,
  атрибута env.profile в официальном пакете нет.
- `history`: `data/change_tariff.csv`; при отсутствии — пустой DataFrame.
- `channels`: публичный `env.channels`, без переименования ключей/полей пакета.
- Функции синхронные, детерминированные при одинаковых входах, без изменения входов.
- Нет env, чтения файлов, сети, API, скрытого глобального состояния и записи CSV.
- Разрешены стандартная библиотека, pandas, numpy; новые зависимости согласует Нурсултан.
- Пустая история допустима; отсутствие обязательных колонок profile — явная диагностическая ошибка.

Каждый кандидат содержит:

```text
candidate_id: str                 стабильный ID из target_tariff и канонических filters
target_tariff: str                существующий код тарифа
filters: dict                    только четыре официальных filter_* ключа
audience_n: int                   размер подходящей аудитории до cap 5000
audience_arpu_sum: float          сумма predicted_arpu подходящей аудитории
history_count: int               количество пригодных исторических наблюдений
prior_change_ratio: float        робастная оценка относительного изменения ARPU
priority: float                  конечное число для порядка исследования
```

`prior_change_ratio` — исторический ориентир изменения ARPU при переходе,
не вероятность согласия и не причинный эффект кампании. При отсутствии истории
используется документированный консервативный prior и `history_count=0`.
Все числа конечные; деление на нулевой/отрицательный исходный ARPU исключается.
При равных приоритетах порядок определяется `candidate_id`.

```python
resources = {
    "remaining_budget": 100000.0,  # актуальное значение env после пилотов
    "remaining_contacts": 15000,
    "pilots_left": 20,
    "seconds_left": 240.0,        # остаток общего таймера act
    "max_campaigns": 10,
    "max_customers_per_campaign": 5000,
}
observations = [{
    "candidate_id": "stable-id",
    "request": {"target_tariff": "tariff_10", "channel": "push", "n_customers": 100},
    "result": {},                # полный публичный ответ run_pilot
}]
```

Числа в примере ресурсов иллюстративные: ядро использует переданные остатки.
Успешный публичный ответ содержит `pilot`, `target_tariff`, `channel`,
`n_customers` (фактическое число), `cost`, `observed_lift_ratio`,
`observed_lift_total`, `remaining_budget`, `remaining_contacts`.

`choose_pilot` возвращает `None` для остановки или:

```python
{"candidate_id": "stable-id", "request": {
    "target_tariff": "tariff_10", "channel": "push", "n_customers": 100,
    "filter_current_tariff": "tariff_4", "filter_arpu_segment": "HIGH"
}}
```

`request` содержит только аргументы `env.run_pilot`: target_tariff, channel,
n_customers и четыре filter_* ниже. Запрашивается 10–200 клиентов, с учётом
остатков. При доступной аудитории и ресурсах начальное исследование включает
минимум один пилот. Не нужно обязательно тратить все 20 пилотов.
Нурсултан проверяет запрос, исполняет его, записывает request/result, обновляет
ресурсы и снова вызывает функцию. Ошибки ограничиваются по числу попыток;
неуспешный запрос не выдаётся за наблюдение.

## Кампании и ограничения

`select_campaigns` возвращает только официальный список словарей:

```python
{"campaign_name": "c01", "target_tariff": "tariff_10", "channel": "push",
 "filter_current_tariff": "tariff_4", "filter_arpu_segment": "HIGH"}
```

Фильтры: `filter_arpu_segment` LOW/MID/HIGH, `filter_data_segment`
NON_USER/LITE/HEAVY, `filter_call_segment` LOW/MEDIUM/HIGH,
`filter_current_tariff` — существующие коды через `;`. Отсутствие ключа или None
означает отсутствие фильтра. Каналы берутся из env, в пакете: push, sms,
digital_ads, call. В финальном словаре нет candidate_id, n_customers или explicit_ids.

Планировщик учитывает официальный порядок: фильтрация, сортировка ID_NUMBER,
первые 5000, остатки контактов и денег, последовательное применение кампаний.
Один абонент даёт только лучший эффект, но все повторные контакты оплачиваются.
Пилоты уже расходовали ресурсы. Точные ID участников пилотов публичный ответ
не сообщает: пересечение с ними оценивается консервативно, не объявляется известным.

`observed_lift_ratio` уже включает влияние выбранного канала — нельзя ещё раз
умножать его на multiplier этого же канала. Перенос оценки между каналами —
отдельная приближённая гипотеза с оговоркой о насыщении конверсии, а не факт.

Сначала корректный непустой результат, затем улучшение net ARPU. Если все оценки
отрицательны, выбирается валидная кампания с минимальным оценённым риском;
положительная прибыль не гарантируется и пустой ответ не маскирует проблему.

## Проверка и изменения

Ерлан проверяет исходный результат до sanitizer, лимиты с пилотами, повторяемость,
влияние разных наблюдений на решения и несколько seed. Не изменяет official scorer.
Нурсултан проверяет общий таймер <5 минут (жёсткий предел ТЗ 10 минут).
Изменение сигнатуры/полей: сначала решение в coordination/decisions.md, затем
контракт и согласованное обновление производителя, потребителя и проверок.
