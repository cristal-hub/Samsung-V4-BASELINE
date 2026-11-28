# ROLLBACK INSTRUCTIONS — STAGE D

Откат Stage D к состоянию Stage C.1 (commit
ee5080828dc71af5091d172568c7f6072c91196a).

Stage D добавляет РОВНО 2 файла и не изменяет ни одного существующего
файла — откат тривиален и безопасен.

## Полный откат

Удалить два новых файла; пакет становится бит-в-бит равным
Samsung_V4_STAGE_C_1:

```bash
rm Samsung_V4_STAGE_D/candidate/strategy_risk.py
rm Samsung_V4_STAGE_D/candidate/tests/test_stage_d_strategy_risk.py
rm -rf Samsung_V4_STAGE_D/candidate/**/__pycache__
```

Проверка после отката:

```bash
sha256sum Samsung_V4_STAGE_D/candidate/strategy_api.py  # и остальные ключевые
# Все хеши совпадают с FILE_MANIFEST_SHA256_STAGE_C1.txt
cd Samsung_V4_STAGE_D/candidate
python -m pytest -q        # 1391 passed
python -m pytest tests/ -q # 871 passed
```

## Частичный откат (оставить код, убрать тесты)

Недопустим для приёмки: тесты обязательны. Для локальной отладки можно
временно исключить файл: `mv candidate/tests/test_stage_d_strategy_risk.py /tmp/`,
после отладки вернуть НА МЕСТО байт-в-бит (sha256 из
CANDIDATE_SHA256_STAGE_D.txt).

## Откат результата расчёта

Stage D не имеет состояния и не изменяет хранилища/брокера: откатывать
нечего, кроме удаления файлов. Статус «Stage D принят/не принят»
отражается только в учётных записях проверяющего.

## Что НЕ трогать при откате

* файлы Stage A.2.1 / B.1 / C / C.1 — не изменялись, удалять нельзя;
* `docs/`, `archive/`, исторические отчёты предыдущих этапов —
  без изменений;
* golden fixtures (candidate/tests/fixtures/legacy_golden_signals.json) —
  не перегенерировать.
