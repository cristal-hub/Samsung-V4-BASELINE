# ROLLBACK INSTRUCTIONS — STAGE C.1

Дата: 2026-11-28

## Что откатывать

Stage C.1 = ровно 2 изменённых файла поверх кандидата Stage C:

1. `candidate/strategy_contracts.py`;
2. `candidate/tests/test_stage_c_exit_service.py`.

Никакие другие файлы не менялись (пруф: `STAGE_C1_IMMUTABILITY_PROOF.txt`).

## Откат к Stage C (полный)

1. Взять доставленный пакет Stage C (`Samsung_V4_STAGE_C.zip`,
   исходный commit `9a69a300e6759f9264d5feb1a6b54ea80f615e4a`).
2. Восстановить из него два файла поверх C.1-версий:
   ```bash
   unzip Samsung_V4_STAGE_C.zip 'candidate/strategy_contracts.py' \
        'candidate/tests/test_stage_c_exit_service.py' -d /tmp/rollback
   cp /tmp/rollback/Samsung_V4_STAGE_C/candidate/strategy_contracts.py candidate/
   cp /tmp/rollback/Samsung_V4_STAGE_C/candidate/tests/test_stage_c_exit_service.py candidate/tests/
   ```
3. Удалить документы/appendix Stage C.1 по желанию (они не влияют на
   исполнение и тесты): `STAGE_C1_*`, `FILE_MANIFEST_SHA256_STAGE_C1.txt`,
   `IMPLEMENTATION_REPORT_STAGE_C1.md`, `README_STAGE_C1.md`,
   `TEST_RESULTS_STAGE_C1.txt`, `CHANGED_FILES_STAGE_C1.md`,
   `appendix_stage_c1/`, `DIFF_STAGE_C_VS_C1.patch`.
4. Контроль после отката: `python -m pytest -v` → 1384 passed;
   `python -m pytest tests -v` → 864 passed.

## Откат отдельных частей

* Только тесты: восстановить из Stage C
  `candidate/tests/test_stage_c_exit_service.py` — минус 7 тестов C.1,
  правка порядка остаётся.
* Только правка порядка: вернуть в `strategy_contracts.py` прежний
  порядок (get_state до check_price) из Stage C — тогда дефект
  воспроизводится; делать это ВМЕСТЕ с откатом тестов C.1, иначе
  сценарии 1-3 упадут (они проверяют отсутствие следов в хранилище).

## Совместимость

* Контракт Stage B.1 не менялся — откат C.1 не затрагивает Stage B.1.
* Stage A.2.1 не менялся — откат не требуется.
* Golden fixtures не перегенерировались — восстанавливать нечего.
