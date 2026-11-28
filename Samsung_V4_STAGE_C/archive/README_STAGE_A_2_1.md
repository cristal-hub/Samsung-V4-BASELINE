# README_STAGE_A_2_1.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.2.1 FINAL CORRECTIVE

Пакет: `Samsung_V4_STAGE_A_2_1` (полный исправленный пакет на базе
Stage A.2). Baseline: commit `884cefd6f12a99f6adc14b5ed4c9eeda21d32e04`.

## Что это

Финальное корректирующее исправление поверх Stage A.2: закрыты три
оставшихся обхода целостности атрибуции, найденные независимой проверкой:

1. **Дефект №1** — прямое создание `AttributionContext(strategy_id,
   config_hash)` с произвольными строками. Теперь контекст создаётся
   ТОЛЬКО из проверенной `StrategyConfig` (`AttributionContext.from_config`);
   охраняемый конструктор с внутренним приватным билетом; все потребители
   (factory/stamp/CSV/JSONL) принимают только подтверждённый контекст
   (маркер проверенного создания); отсутствие подтверждённой конфигурации —
   fail-closed.
2. **Дефект №2** — наследование `StrategyConfig`. `from_config` принимает
   ТОЛЬКО точный тип `StrategyConfig` (`type(config) is StrategyConfig`,
   наследование не поддерживается — решение документировано) и перепроверяет
   хеш ИСХОДНЫМ алгоритмом `compute_config_hash` по фактическим полям —
   переопределяемые методы подкласса не используются как источник проверки.
3. **Дефект №3** — изменяемый `Enum.value`. Рекурсивная проверка: допустимы
   только безопасные неизменяемые скаляры (None/bool/int/float/str);
   dict/list/set/bytearray и прочие нескалярные отклоняются
   `StrategyConfigError` при создании конфигурации, при прямом
   `compute_config_hash` и в `deep_freeze`.

## Ключевые гарантии (завершение Stage A.2.1)

* через обычный публичный API невозможно получить неподтверждённый
  `AttributionContext`;
* наследование не обходит проверку `config_hash`;
* изменяемые `Enum.value` не могут нарушить целостность конфигурации;
* контекст и фабрика неизменяемы; deepcopy/pickle не теряют проверенность;
* все 1037 существующих тестов Stage A.2 (включая 980 Stage A.1) проходят
  без изменений и ослаблений + 76 новых тестов: суммарно **1113 passed,
  0 failed, 0 skipped**;
* хеши корректных существующих конфигураций сохранены (эталонные значения,
  вычисленные кодом Stage A.2 до изменений, подтверждены тестом);
* golden fixtures не перегенерировались; профили SANDBOX_TEST /
  TECH_CHECK / CONSERVATIVE не менялись; FORCE_TRADE не добавлялся и не
  использовался; Stage B не начат.

## Документы пакета (Stage A.2.1)

* `CORRECTIVE_REPORT_STAGE_A_2_1.md` — полный отчёт по трём исправлениям
  (решения, обязательные тесты, регрессия, неизменность, ограничения,
  критерий завершения);
* `TEST_RESULTS_STAGE_A_2_1.txt` — полные логи pytest ДО и ПОСЛЕ;
* `DIFF_STAGE_A_2_VS_A_2_1.patch` / `DIFF_STAGE_A_2_VS_A_2_1.md` — полный
  diff A.2 → A.2.1 (применение проверено побайтово);
* `FILE_MANIFEST_SHA256_STAGE_A_2_1.txt` — SHA256-манифест пакета и
  подтверждение неизменности baseline/production-файлов;
* `ROLLBACK_INSTRUCTIONS_STAGE_A_2_1.md` — откат к Stage A.2;
* `CHANGELOG.md` — дополнен разделом Stage A.2.1.

## Быстрая проверка

```bash
cd candidate
python -m pytest            # 1113 passed
python -m pytest tests      # 593 passed
python -m pytest tests/test_stage_a2_1_context_integrity.py   # 76 passed
```

## Граница защиты (честно)

Защита закрывает обычный публичный API. Полная Python-интроспекция
(`object.__new__` + `object.__setattr__` всех атрибутов, включая
приватный маркер; monkeypatch модульных функций) сознательно не является
целью абсолютной защиты (по заданию Stage A.2.1); «наивная» сборка мимо
конструктора отсекается на границе `_resolve_context`. Полный перечень
оставшихся ограничений — CORRECTIVE_REPORT_STAGE_A_2_1.md, раздел 7.

## Статус

REGRESSION_ONLY. Торговля запрещена (fail-closed). Offline. Stage B не
начат.
