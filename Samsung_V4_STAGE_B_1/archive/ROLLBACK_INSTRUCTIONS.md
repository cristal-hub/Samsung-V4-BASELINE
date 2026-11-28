# ROLLBACK_INSTRUCTIONS.md
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE A.1: ИНСТРУКЦИЯ ПО ОТКАТУ

Откат Stage A.1 — это возврат от корректированной версии Stage A.1 к
исходному пакету Stage A (или далее — к baseline 884cefd). Все операции
offline, без брокера, без заявок.

## 1. ЧТО МЕНЯЛОСЬ В STAGE A.1 (объём отката)

Изменены (4 файла):
1. `candidate/strategy_api.py`
2. `candidate/attribution.py`
3. `candidate/engine_config.py`
4. `candidate/tests/test_stage_a_attribution.py`

Добавлены (2 файла):
5. `candidate/tests/test_stage_a1_config_immutability.py`
6. `candidate/tests/test_stage_a1_attribution_explicit.py`

Все остальные файлы пакета (176) байт-неизменны; production-код baseline
не менялся.

## 2. ПОЛНЫЙ ОТКАТ STAGE A.1 → STAGE A (рекомендуемый способ)

Исходный пакет Stage A сохранён отдельно (`Samsung_V4_STAGE_A.zip`,
SHA256 — см. п. 5). Полный откат:

1. Распаковать исходный пакет Stage A:
   ```
   unzip Samsung_V4_STAGE_A.zip -d SAMSUNG_V4_STAGE_A_restored
   ```
2. Использовать его `candidate/` вместо корректированного:
   ```
   # удалить/переименовать корректированную копию
   mv candidate candidate_stage_a1_backup
   cp -r SAMSUNG_V4_STAGE_A_restored/candidate candidate
   ```
3. Проверить целостность:
   ```
   cd candidate
   python -m pytest            # ожидание: 899 passed, 0 failed
   python -m pytest tests      # ожидание: 379 passed, 0 failed
   ```

При таком откате не требуется никаких миграций данных: Stage A.1 не
создавал производственных записей и не менял схемы журналов
(research_trades.csv / research_events.jsonl не модифицировались).

## 3. ТОЧЕЧНЫЙ ОТКАТ (только затронутые файлы)

1. Восстановить 4 изменённых файла из исходного пакета Stage A:
   ```
   cp SAMSUNG_V4_STAGE_A_restored/candidate/strategy_api.py   candidate/strategy_api.py
   cp SAMSUNG_V4_STAGE_A_restored/candidate/attribution.py    candidate/attribution.py
   cp SAMSUNG_V4_STAGE_A_restored/candidate/engine_config.py  candidate/engine_config.py
   cp SAMSUNG_V4_STAGE_A_restored/candidate/tests/test_stage_a_attribution.py \
      candidate/tests/test_stage_a_attribution.py
   ```
2. Удалить 2 новых corrective-теста (опционально — можно оставить: они
   ссылаются на удалённые API и в этом случае падают, поэтому при точечном
   откате их удаляют):
   ```
   rm candidate/tests/test_stage_a1_config_immutability.py
   rm candidate/tests/test_stage_a1_attribution_explicit.py
   ```
3. Прогнать регрессию (ожидание 899 passed).

Примечание: точечный откат возвращает глобальный контекст атрибуции
(замечание №3 аудита снова открыто) — использовать только как временную
меру или для диагностики.

## 4. ОТКАТ STAGE A → BASELINE 884cefd (если требуется)

Вне объёма Stage A.1 (см. ROLLBACK_INSTRUCTIONS.md пакета Stage A): все
production-файлы Stage A.1 байт-идентичны baseline, поэтому после п. 2
состояние совпадает с Stage A; дальнейший откат к baseline выполняется
инструментами Stage A.

## 5. КОНТРОЛЬ ЦЕЛОСТНОСТИ ПОСЛЕ ОТКАТА

* SHA256-манифест исходного пакета Stage A — `Samsung_V4_STAGE_A.zip` /
  `FILE_MANIFEST_SHA256.txt` внутри него;
* SHA256-манифест Stage A.1 — `FILE_MANIFEST_SHA256.txt` этого пакета;
* быстрое health-проверка после отката:
  ```
  cd candidate
  python -m pytest -q     # Stage A: 899 passed; Stage A.1: 980 passed
  ```

## 6. ЧЕГО НЕ ТРЕБУЕТСЯ ПРИ ОТКАТЕ

* миграций CSV/JSONL — не выполнялось;
* очистки state.json/журналов — они не затрагивались;
* изменений engine.json / runtime-переменных — не выполнялось;
* сетевых/брокерских действий — пакет полностью offline.
