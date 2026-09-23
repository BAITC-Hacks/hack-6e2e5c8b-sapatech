# Ерлан

- Message-ID: ER-001
- Revision: 3
- Role: ERLAN
- Task: T-05
- State: ready
- Working-branch: test/T-05-erlan-evaluation
- Target-commit: dca1954a6955b730a11bfecb91fa68b62bd855ed
- Reply-path: docs/evaluation/ER-001-r3.md
- Timebox: 15 минут; только документация, без повторных прогонов

Сначала CONTROL и MAILBOX. ER-001/r2 принят: verifier 6d0207b и отчёт
7c3cf37 объединены merge dca1954 с сохранением авторства. Нового кода не требуется.
Нурсултан проверил на Windows снимок cb7e414 + evals из 7c3cf37:
9/9 checker tests, raw seed42 errors=[], feedback меняет кампании и обе
errors=[], две независимые генерации CSV совпадают. Официальные local_eval.py
и make_submission.py тоже exit 0. Точные команды, среда и hashes в RECEIPTS.
Агент и ядро не менялись; полный multi-seed не повторять.

Осталось завершить документацию:

1. README должен описывать запуск общей интегрированной ветки, включая
   agent.py и strategy/, а не только состояние собственной T-05 без этого кода.
   Указать фактически выполненные Нурсултаном PowerShell-команды со ссылкой
   на RECEIPTS; для Python разрешить явный путь к существующему python.exe.
2. На Windows Нурсултана команда py отсутствует; использован Python 3.12.14
   по явному пути (RECEIPTS), pandas 3.0.1/numpy 2.3.5. Создание venv и pip
   не исполнялись: не отмечать исходный блок py -3 -m venv как проверенный.
   Разделить проверенные вызовы и общие инструкции установки. Машинный путь
   координатора — доказательство среды, не обязательный путь для всех пользователей.
3. Обновить свою T-05: последний критерий README закрывать только по реально
   опубликованным Windows-свидетельствам. Уточнить в README статус демо-сценария
   и ссылку на готовые метрики; не выдавать пример команд за новые измерения.
4. Опубликовать ER-001-r3 с Source/Target hash, Automation-ID/state и статусом
   needs_review. Это документальная передача: старые тесты и seed повторять
   не нужно. Сохранить оговорки mock, CRLF/LF и непроверенной установки.

Owned paths: README.md, docs/evaluation/**, coordination/tasks/T-05.md.
В этой revision не менять evals/, agent.py, strategy/ или official package.
После needs_review ожидать новую revision или CONTROL stop; сдача запрещена.
