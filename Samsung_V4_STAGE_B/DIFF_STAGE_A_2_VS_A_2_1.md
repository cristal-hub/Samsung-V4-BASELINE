# DIFF_STAGE_A_2_VS_A_2_1.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.2.1 FINAL CORRECTIVE

Полный diff: `DIFF_STAGE_A_2_VS_A_2_1.patch` (1643 строки; применение
проверено: `git apply` к чистому пакету Stage A.2 воспроизводит Stage A.2.1
побайтово по всем 4 файлам).

## Состав изменений

### 1. candidate/strategy_api.py (+97 / −2)
* шапка: раздел STAGE A.2.1 (описание дефекта №3 и правила Enum.value);
* добавлен блок «Enum-значения параметров»: `_ENUM_SAFE_SCALAR_TYPES`
  (None/bool/int/float/str), `_ENUM_UNWRAP_LIMIT = 8` (защита от
  искусственной циклической цепочки Enum->Enum);
* добавлена `_validate_enum_value(value)` — рекурсивная проверка значения
  Enum (fail-closed): допустимы только безопасные неизменяемые скаляры;
  изменяемые и прочие нескалярные значения отклоняются
  `StrategyConfigError`; NaN/Infinity в значении отклоняются; возвращает
  раскрытое конечное значение;
* `_normalize_for_json`: перед существующими ветками добавлена валидация
  Enum (объект НЕ меняется — str-миксин сериализуется как str, обычный
  Enum — как .value; хеши корректных конфигураций не меняются) — проверка
  срабатывает в том числе при ПРЯМОМ внешнем вызове
  `compute_config_hash`/`canonical_config_payload`;
* `deep_freeze`: добавлена ветка Enum с валидацией (defense-in-depth:
  «замороженная» структура не может содержать Enum с изменяемым значением);
* `StrategyConfig.recompute_config_hash`: docstring дополнен — метод
  (переопределяемый подклассом) больше НЕ используется как источник
  проверки в `AttributionContext.from_config`; там применяется исходный
  алгоритм `compute_config_hash` напрямую.
* Торговая логика/параметры/сигналы/риск/исполнение: НЕ затронуты.

### 2. candidate/attribution.py (+216 / −31)
* шапка: раздел STAGE A.2.1 с описанием трёх дефектов и ДОКУМЕНТИРОВАННЫМ
  решением дефекта №2 (наследование не поддерживается);
* добавлены `_ContextCreationTicket` (приватный класс-свидетель; билетом
  служит сам класс — deepcopy/pickle сохраняют тождество типов) и
  `_VERIFIED_MARKER` (маркер проверенного создания);
* `AttributionContext`:
  - `@dataclass(frozen=True, init=False)` + явный охраняемый `__init__`:
    без приватного билета создание отклоняется `AttributionError`
    (любые позиционные/именованные формы, в том числе с валидно
    выглядящими строками);
  - валидация полей (непустые строки) и формата хеша
    (`validate_config_hash_format`, 64 hex) сохранена/добавлена;
  - маркер проверенного создания выставляется ТОЛЬКО охраняемым
    конструктором (не поле dataclass: не участвует в eq/repr/as_dict);
  - `__reduce__` явный: deepcopy/pickle восстанавливаются через охраняемый
    конструктор и не теряют проверенность;
  - `from_config`: точный тип `type(config) is StrategyConfig` (вместо
    isinstance — подкласс не может провести ослабленную проверку);
    перепроверка ИСХОДНЫМ алгоритмом `compute_config_hash` по фактическим
    strategy_id/strategy_version/params/config_hash (вместо
    переопределяемого `recompute_config_hash`); перепроверка формата хеша;
    создание контекста только с внутренним билетом;
* `_resolve_context`: контекст принимается ТОЛЬКО при точном типе и
  наличии маркера проверенного создания; StrategyConfig (точный тип) —
  через `from_config`; всё остальное — `AttributionRequiredError`/
  `AttributionError` (fail-closed, без фиктивных значений).
* `AttributionFactory`/`stamp`/`append_attributed_csv_row`/
  `append_attributed_jsonl_row`: сигнатуры НЕ изменены — гарантии
  обеспечены единым `_resolve_context`/`from_config`.

### 3. candidate/tests/test_stage_a_attribution.py (+48 / −12)
Адаптация фикстуры Stage A по правилу исправления fixtures (см. отчёт,
раздел 2.4): контекст получается ТОЛЬКО из проверенной StrategyConfig
(`compute_config_hash` + `AttributionContext.from_config`); утверждения
обновлены с произвольного `'a'*64` на вычисленный `_EXPECTED_HASH`;
комментарий `test_invalid_context_rejected` отражает новый смысл
(любое прямое создание запрещено). Ни один тест не пропущен/удалён/ослаблен.

### 4. candidate/tests/test_stage_a2_1_context_integrity.py (+1020, новый)
76 тестов: 16 обязательных пунктов задания + сериализация, JSON round-trip,
обратная совместимость + дополнительные проверки defense-in-depth
(`canonical_config_payload`, `deep_freeze`, «наивная» сборка мимо
конструктора, байтовая идентичность golden-фикстуры, эталонные хеши
Stage A.2 из pristine-кода).

## Не изменено
Все остальные файлы пакета побайтово идентичны Stage A.2 (194 файла,
включая production-файлы baseline: main.py, execution.py, logger.py,
order_ledger.py, config.py, strategy.py, risk_manager.py, engine_config.py,
engine.json и др.).
