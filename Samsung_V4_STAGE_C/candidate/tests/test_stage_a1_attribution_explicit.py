# tests/test_stage_a1_attribution_explicit.py
# STAGE A.1 CORRECTIVE TESTS — ЗАМЕЧАНИЯ №2 и №3 НЕЗАВИСИМОГО АУДИТА:
#
# №2 — «атрибуция ещё не встроена в производственный поток»: реализован и
#   протестирован САМОСТОЯТЕЛЬНЫЙ интерфейс атрибуции нового движка
#   (AttributionFactory: new_event / new_virtual_order / new_virtual_position /
#   append_csv_row / append_jsonl_row) с ЯВНОЙ передачей контекста; старые
#   production-механизмы Samsung V4 НЕ изменяются; исторические объекты
#   читаются без миграции и без выдуманной атрибуции.
#
# №3 — «убрать глобальный контекст атрибуции»: глобального изменяемого
#   состояния больше НЕ существует (set_current_context/get_current_context/
#   clear_current_context/_current_context удалены); единственный источник
#   атрибуции — ЯВНО переданный AttributionContext (или StrategyConfig).
#
# Обязательные проверки замечания №3 (по заданию Stage A.1):
#   1. две стратегии с разными strategy_id и config_hash;
#   2. одновременное создание объектов обеих стратегий;
#   3. объекты получают только собственную атрибуцию;
#   4. отсутствие перекрёстного загрязнения;
#   5. отсутствие контекста приводит к явной ошибке;
#   6. вложенные вызовы не меняют контекст вызывающего кода;
#   7. исключение при создании объекта не оставляет устаревший контекст;
#   8. повторный запуск тестов не зависит от порядка предыдущих тестов.
#
# Offline; без сети, брокера и заявок. Файлы создаются только в tmp_path.

import csv
import json
import os
import threading

import pytest

import attribution as at
from attribution import (
    ATTRIBUTION_FIELDS,
    AttributionContext,
    AttributionError,
    AttributionFactory,
    AttributionRequiredError,
    append_attributed_csv_row,
    append_attributed_jsonl_row,
    legacy_attribution_view,
    read_csv_attribution_report,
    read_jsonl_attribution_report,
    record_has_attribution,
    stamp,
)
from strategy_api import (
    ParamSpec,
    ParamType,
    Strategy,
    StrategyConfig,
    compute_config_hash,
)


# ---------------------------------------------------------------------------
# Две явные конфигурации двух разных стратегий (требование №1)
# ---------------------------------------------------------------------------

class _StrategyAlpha(Strategy):
    strategy_id = "alpha_engine"
    strategy_version = "1.0"

    def param_specs(self):
        return (ParamSpec("p_int", ParamType.INT, minimum=1),)

    def evaluate_entry(self, signal_input, config):
        raise NotImplementedError


class _StrategyBeta(Strategy):
    strategy_id = "beta_engine"
    strategy_version = "2.0"

    def param_specs(self):
        return (ParamSpec("p_int", ParamType.INT, minimum=1),)

    def evaluate_entry(self, signal_input, config):
        raise NotImplementedError


def _config_for(cls, p_int: int) -> StrategyConfig:
    return cls().get_config({"p_int": p_int})


@pytest.fixture
def context_alpha():
    return AttributionContext.from_config(_config_for(_StrategyAlpha, 1))


@pytest.fixture
def context_beta():
    return AttributionContext.from_config(_config_for(_StrategyBeta, 2))


@pytest.fixture
def legacy_trade_fields():
    # историческая схема торгового CSV из production logger.py (только чтение)
    import logger
    return list(logger.TRADE_FIELDS)


# ---------------------------------------------------------------------------
# Требование №3.5: отсутствие контекста — явная ошибка; глобального
# состояния не существует
# ---------------------------------------------------------------------------

class TestNoGlobalContext:
    def test_global_context_api_removed(self):
        # глобальное изменяемое состояние удалено как обязательный источник
        for name in ("set_current_context", "get_current_context",
                     "clear_current_context", "_current_context"):
            assert not hasattr(at, name), \
                f"глобальное состояние атрибуции {name!r} не должно существовать"

    def test_missing_context_raises_explicit_error(self):
        # явно переданный None -> AttributionRequiredError
        with pytest.raises(AttributionRequiredError) as exc:
            stamp({"x": 1}, None)
        message = str(exc.value)
        assert "контекст" in message
        assert "фиктивные значения запрещены" in message
        # отсутствующий аргумент -> TypeError (fail-closed до входа)
        with pytest.raises(TypeError):
            stamp({"x": 1})

    def test_missing_context_factory_creation_raises(self):
        with pytest.raises(AttributionRequiredError):
            AttributionFactory(None)
        with pytest.raises(AttributionRequiredError):
            AttributionFactory("not-a-context")

    def test_no_fabricated_placeholders_ever(self, context_alpha):
        # в атрибуции НОВЫХ объектов нет UNKNOWN/пустых/случайных значений
        stamped = stamp({"x": 1}, context_alpha)
        for name in ATTRIBUTION_FIELDS:
            value = stamped[name]
            assert isinstance(value, str) and value
            assert value == getattr(context_alpha, name)
            assert value.upper() != "UNKNOWN"
        # и у СТАРЫХ записей отсутствующая атрибуция остаётся явным None,
        # а не заглушкой
        view = legacy_attribution_view({"trade_id": "T"})
        assert view["strategy_id"] is None
        assert view["config_hash"] is None
        assert view["has_attribution"] is False


# ---------------------------------------------------------------------------
# Единый явный механизм: AttributionContext или StrategyConfig (замечание №2)
# ---------------------------------------------------------------------------

class TestUnifiedExplicitMechanism:
    def test_from_config_builds_correct_context(self):
        config = _config_for(_StrategyAlpha, 1)
        context = AttributionContext.from_config(config)
        assert context.strategy_id == "alpha_engine"
        assert context.config_hash == config.config_hash
        assert context.as_dict() == config.attribution_dict()

    def test_from_config_rejects_none_and_garbage(self):
        with pytest.raises(AttributionError):
            AttributionContext.from_config(None)
        with pytest.raises(AttributionError):
            AttributionContext.from_config(object())
        from types import SimpleNamespace
        # объект без валидных полей атрибуции (утка без данных)
        with pytest.raises(AttributionError):
            AttributionContext.from_config(
                SimpleNamespace(strategy_id="", config_hash=""))
        with pytest.raises(AttributionError):
            AttributionContext.from_config(
                SimpleNamespace(strategy_id="s", config_hash=None))

    def test_stamp_accepts_strategy_config_directly(self):
        config = _config_for(_StrategyBeta, 2)
        stamped = stamp({"event": "SIGNAL"}, config)
        assert stamped["strategy_id"] == "beta_engine"
        assert stamped["config_hash"] == config.config_hash

    def test_factory_accepts_strategy_config_directly(self):
        config = _config_for(_StrategyAlpha, 1)
        factory = AttributionFactory(config)
        assert factory.context.strategy_id == "alpha_engine"
        assert factory.context.config_hash == config.config_hash

    def test_context_is_immutable(self, context_alpha):
        with pytest.raises(Exception):
            context_alpha.strategy_id = "hacked"
        # данные конфигурации и контекста совпадают и не расходятся
        config = _config_for(_StrategyAlpha, 1)
        assert AttributionContext.from_config(config).as_dict() == \
            config.attribution_dict()


# ---------------------------------------------------------------------------
# Требования №3.1–3.4: две стратегии, одновременное создание, только
# собственная атрибуция, отсутствие перекрёстного загрязнения
# ---------------------------------------------------------------------------

class TestTwoStrategiesIsolation:
    def test_two_strategies_have_different_ids_and_hashes(self):
        config_a = _config_for(_StrategyAlpha, 1)
        config_b = _config_for(_StrategyBeta, 2)
        assert config_a.strategy_id != config_b.strategy_id
        assert config_a.config_hash != config_b.config_hash
        assert AttributionContext.from_config(config_a) != \
            AttributionContext.from_config(config_b)

    def test_interleaved_creation_keeps_own_attribution(self,
                                                        context_alpha,
                                                        context_beta):
        # одновременное (чередующееся) создание объектов обеих стратегий
        factory_a = AttributionFactory(context_alpha)
        factory_b = AttributionFactory(context_beta)
        e1 = factory_a.new_event({"seq": 1})
        e2 = factory_b.new_event({"seq": 2})
        e3 = factory_a.new_event({"seq": 3})
        e4 = factory_b.new_event({"seq": 4})
        assert (e1["strategy_id"], e3["strategy_id"]) == \
            ("alpha_engine", "alpha_engine")
        assert (e2["strategy_id"], e4["strategy_id"]) == \
            ("beta_engine", "beta_engine")
        assert e1["config_hash"] == e3["config_hash"] == \
            context_alpha.config_hash
        assert e2["config_hash"] == e4["config_hash"] == \
            context_beta.config_hash
        assert e1["config_hash"] != e2["config_hash"]

    def test_same_record_stamped_by_both_strategies_no_cross_leak(self,
                                                                 context_alpha,
                                                                 context_beta):
        record = {"event": "SHARED"}
        from_a = stamp(record, context_alpha)
        from_b = stamp(record, context_beta)
        assert from_a["strategy_id"] == "alpha_engine"
        assert from_b["strategy_id"] == "beta_engine"
        # исходная запись не мутировалась и не получила атрибуцию
        assert record == {"event": "SHARED"}
        assert not record_has_attribution(record)

    def test_concurrent_threads_no_cross_contamination(self,
                                                       context_alpha,
                                                       context_beta):
        # параллельная работа: каждая стратегия создаёт объекты в своём
        # потоке; перекрёстного загрязнения нет
        factory_a = AttributionFactory(context_alpha)
        factory_b = AttributionFactory(context_beta)
        results = {"alpha": [], "beta": []}
        errors = []

        def produce(factory, key, count):
            try:
                for i in range(count):
                    obj = factory.new_event({"thread": key, "i": i})
                    results[key].append(obj)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=produce,
                             args=(factory_a, "alpha", 50)),
            threading.Thread(target=produce,
                             args=(factory_b, "beta", 50)),
            threading.Thread(target=produce,
                             args=(factory_a, "alpha", 50)),
            threading.Thread(target=produce,
                             args=(factory_b, "beta", 50)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        assert len(results["alpha"]) == 100
        assert len(results["beta"]) == 100
        for obj in results["alpha"]:
            assert obj["strategy_id"] == "alpha_engine"
            assert obj["config_hash"] == context_alpha.config_hash
        for obj in results["beta"]:
            assert obj["strategy_id"] == "beta_engine"
            assert obj["config_hash"] == context_beta.config_hash

    def test_context_of_calling_code_not_changed_by_nested_calls(self,
                                                                context_alpha,
                                                                context_beta):
        # требование №3.6: вложенные вызовы не меняют контекст вызывающего
        # кода — с явным DI контекст ХРАНИТСЯ В ЛОКАЛЬНОЙ ПЕРЕМЕННОЙ
        # вызывающего кода и не может быть подменён извне
        factory_a = AttributionFactory(context_alpha)

        def nested_work_deep_with_other_strategy(context_beta):
            factory_b = AttributionFactory(context_beta)
            return factory_b.new_event({"who": "beta"})

        outer_before = factory_a.context
        nested_result = nested_work_deep_with_other_strategy(context_beta)
        assert nested_result["strategy_id"] == "beta_engine"
        # контекст вызывающего кода не изменился
        assert factory_a.context is outer_before
        assert factory_a.context.strategy_id == "alpha_engine"
        # следующий объект вызывающего кода по-прежнему alpha
        assert factory_a.new_event({"who": "alpha"})["strategy_id"] == \
            "alpha_engine"

    def test_exception_does_not_leave_stale_context(self,
                                                    context_alpha,
                                                    context_beta):
        # требование №3.7: исключение при создании объекта не оставляет
        # «устаревший» контекст — контекст фабрики неизменяем по построению
        factory_a = AttributionFactory(context_alpha)
        conflicting = {"strategy_id": "beta_engine",
                       "config_hash": "c" * 64}
        with pytest.raises(AttributionError):
            factory_a.stamp(conflicting)
        # фабрика продолжила работу со СВОИМ контекстом
        assert factory_a.context == context_alpha
        following = factory_a.stamp({"x": 1})
        assert following["strategy_id"] == "alpha_engine"
        assert following["config_hash"] == context_alpha.config_hash

    def test_repeated_runs_order_independent(self, context_alpha,
                                             context_beta):
        # требование №3.8: повторный запуск не зависит от порядка
        # предыдущих тестов — один и тот же сценарий в двух порядках даёт
        # байт-идентичные результаты
        def scenario(order):
            factory_a = AttributionFactory(context_alpha)
            factory_b = AttributionFactory(context_beta)
            events = []
            for kind in order:
                if kind == "alpha":
                    events.append(factory_a.new_event({"step": kind}))
                else:
                    events.append(factory_b.new_event({"step": kind}))
            return [dict(e) for e in events]

        forward = scenario(["alpha", "beta", "alpha", "beta"])
        backward = scenario(["beta", "alpha", "beta", "alpha"])
        # у каждой стратегии свои неизменные значения атрибуции
        forward_alpha = [e for e in forward if e["step"] == "alpha"]
        backward_alpha = [e for e in backward if e["step"] == "alpha"]
        assert forward_alpha == backward_alpha
        forward_beta = [e for e in forward if e["step"] == "beta"]
        backward_beta = [e for e in backward if e["step"] == "beta"]
        assert forward_beta == backward_beta
        assert {e["strategy_id"] for e in forward_alpha} == {"alpha_engine"}
        assert {e["strategy_id"] for e in forward_beta} == {"beta_engine"}


# ---------------------------------------------------------------------------
# Замечание №2: интерфейсы атрибуции всех типов НОВЫХ объектов движка
# ---------------------------------------------------------------------------

class TestNewEngineObjectAttribution:
    def test_new_event_carries_attribution(self, context_alpha):
        factory = AttributionFactory(context_alpha)
        event = factory.new_event(
            {"event_id": "E1", "timestamp_utc": "2026-01-01T00:00:00Z",
             "figi": "BBG000000001", "kind": "SIGNAL"})
        assert record_has_attribution(event)
        assert event["strategy_id"] == "alpha_engine"
        assert event["config_hash"] == context_alpha.config_hash
        # JSONL-совместимость payload
        restored = json.loads(json.dumps(event, ensure_ascii=False))
        assert restored["strategy_id"] == "alpha_engine"

    def test_new_virtual_order_carries_attribution(self, context_alpha):
        factory = AttributionFactory(context_alpha)
        order = factory.new_virtual_order(
            {"order_id": "V1", "figi": "BBG000000001", "side": "BUY",
             "lots": 1, "status": "VIRTUAL_RESEARCH"})
        assert order["strategy_id"] == "alpha_engine"
        assert order["config_hash"] == context_alpha.config_hash

    def test_new_virtual_position_carries_attribution(self, context_alpha):
        factory = AttributionFactory(context_alpha)
        position = factory.new_virtual_position(
            {"position_id": "P1", "figi": "BBG000000001",
             "state": "OPEN_RESEARCH"})
        assert position["strategy_id"] == "alpha_engine"
        assert position["config_hash"] == context_alpha.config_hash

    def test_factory_rejects_non_mapping_records(self, context_alpha):
        factory = AttributionFactory(context_alpha)
        with pytest.raises(AttributionError):
            factory.new_event(["not", "a", "mapping"])
        with pytest.raises(AttributionError):
            factory.new_virtual_order("order")
        with pytest.raises(AttributionError):
            factory.new_virtual_position(42)

    def test_conflicting_fields_object_not_created(self, context_alpha):
        factory = AttributionFactory(context_alpha)
        bad = {"strategy_id": "beta_engine", "x": 1}
        with pytest.raises(AttributionError):
            factory.new_event(bad)
        with pytest.raises(AttributionError):
            factory.new_virtual_order(bad)
        with pytest.raises(AttributionError):
            factory.new_virtual_position(bad)

    def test_conflicting_csv_row_not_created_file_untouched(
            self, tmp_path, context_alpha):
        factory = AttributionFactory(context_alpha)
        path = str(tmp_path / "engine_research.csv")
        factory.append_csv_row(
            path, {"event_id": "E1"}, ["event_id", "timestamp_utc"])
        before = open(path, "rb").read()
        with pytest.raises(AttributionError):
            factory.append_csv_row(
                path, {"event_id": "E2", "strategy_id": "beta_engine"},
                ["event_id", "timestamp_utc"])
        # конфликтная строка НЕ записана, файл не изменён
        assert open(path, "rb").read() == before


# ---------------------------------------------------------------------------
# Замечание №2: новые журналы CSV/JSONL движка
# ---------------------------------------------------------------------------

class TestNewEngineJournals:
    CSV_BASE = ["event_id", "timestamp_utc", "figi", "kind"]

    def test_csv_row_appended_with_attribution(self, tmp_path,
                                               context_alpha):
        factory = AttributionFactory(context_alpha)
        path = str(tmp_path / "engine_research.csv")
        written = factory.append_csv_row(
            path,
            {"event_id": "E1", "timestamp_utc": "2026-01-01T00:00:00Z",
             "figi": "F", "kind": "SIGNAL"},
            self.CSV_BASE)
        assert written["strategy_id"] == "alpha_engine"
        rows = read_csv_attribution_report(path)
        assert len(rows) == 1
        assert rows[0]["has_attribution"] is True
        assert rows[0]["strategy_id"] == "alpha_engine"

    def test_jsonl_row_appended_with_attribution(self, tmp_path,
                                                 context_alpha):
        factory = AttributionFactory(context_alpha)
        path = str(tmp_path / "engine_events.jsonl")
        written = factory.append_jsonl_row(
            path, {"event_id": "E1", "kind": "SIGNAL"})
        assert written["strategy_id"] == "alpha_engine"
        with open(path, "r", encoding="utf-8") as handle:
            lines = [line for line in handle if line.strip()]
        assert len(lines) == 1
        restored = json.loads(lines[0])
        assert restored["strategy_id"] == "alpha_engine"
        assert restored["config_hash"] == context_alpha.config_hash

    def test_jsonl_multiple_rows_keep_own_attribution(self, tmp_path,
                                                      context_alpha,
                                                      context_beta):
        path = str(tmp_path / "engine_events.jsonl")
        append_attributed_jsonl_row(
            path, {"event_id": "A1"}, context=context_alpha)
        append_attributed_jsonl_row(
            path, {"event_id": "B1"}, context=context_beta)
        append_attributed_jsonl_row(
            path, {"event_id": "A2"}, context=context_alpha)
        report = read_jsonl_attribution_report(path)
        assert [v["strategy_id"] for v in report] == \
            ["alpha_engine", "beta_engine", "alpha_engine"]
        assert report[0]["config_hash"] == context_alpha.config_hash
        assert report[1]["config_hash"] == context_beta.config_hash

    def test_jsonl_without_context_fails_closed(self, tmp_path):
        path = str(tmp_path / "engine_events.jsonl")
        with pytest.raises(AttributionRequiredError):
            append_attributed_jsonl_row(
                path, {"event_id": "X"}, context=None)
        with pytest.raises(TypeError):
            append_attributed_jsonl_row(path, {"event_id": "X"})
        assert not os.path.isfile(path)

    def test_module_level_csv_writer_still_explicit(self, tmp_path,
                                                    context_alpha):
        path = str(tmp_path / "engine_research.csv")
        written = append_attributed_csv_row(
            path, {"event_id": "E1"}, self.CSV_BASE, context=context_alpha)
        assert written["strategy_id"] == "alpha_engine"


# ---------------------------------------------------------------------------
# Замечание №2: старые объекты остаются совместимыми; миграции НЕТ;
# чтение старой записи не добавляет ей атрибуцию
# ---------------------------------------------------------------------------

class TestLegacyObjectsUnchanged:
    def test_old_jsonl_read_safely_and_file_unchanged(self, tmp_path):
        old_jsonl = tmp_path / "research_events.jsonl"
        lines = [
            {"event_id": "E1", "timestamp_utc": "2025-01-01T10:00:00Z",
             "event": "SIGNAL", "figi": "BBG000000001"},
            {"event_id": "E2", "timestamp_utc": "2025-01-01T10:05:00Z",
             "event": "HOLD", "figi": "BBG000000002"},
        ]
        with open(old_jsonl, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        before = old_jsonl.read_bytes()

        report = read_jsonl_attribution_report(str(old_jsonl))
        assert len(report) == 2
        for view in report:
            assert view["has_attribution"] is False
            assert view["strategy_id"] is None
            assert view["config_hash"] is None
        # исторический файл НЕ переписан, атрибуция НЕ добавлена, миграции НЕТ
        assert old_jsonl.read_bytes() == before

    def test_old_csv_read_safely_and_file_unchanged(self, tmp_path,
                                                    legacy_trade_fields):
        old_csv = tmp_path / "research_trades.csv"
        with open(old_csv, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=legacy_trade_fields,
                                    delimiter=";")
            writer.writeheader()
            writer.writerow({"trade_id": "T1", "ticker": "SBER",
                             "side": "BUY"})
        before = old_csv.read_bytes()
        report = read_csv_attribution_report(str(old_csv))
        assert report[0]["has_attribution"] is False
        assert report[0]["strategy_id"] is None
        assert old_csv.read_bytes() == before

    def test_mixed_journal_reads_correctly(self, tmp_path, context_alpha):
        # журнал, в котором есть и старые записи (без атрибуции), и новые
        # (с явной атрибутностью): чтение не «дописывает» старым
        path = str(tmp_path / "mixed_events.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"event_id": "OLD1"}) + "\n")
        append_attributed_jsonl_row(
            path, {"event_id": "NEW1"}, context=context_alpha)
        report = read_jsonl_attribution_report(path)
        assert report[0]["has_attribution"] is False
        assert report[0]["strategy_id"] is None
        assert report[1]["has_attribution"] is True
        assert report[1]["strategy_id"] == "alpha_engine"
        # первая строка файла по-прежнему без атрибуции (не переписана)
        with open(path, "r", encoding="utf-8") as handle:
            first = json.loads(handle.readline())
        assert first == {"event_id": "OLD1"}


# ---------------------------------------------------------------------------
# Старая production-схема logger.py не изменена (граница Stage A)
# ---------------------------------------------------------------------------

class TestStageABoundaryUnchanged:
    def test_trade_fields_have_no_attribution_columns_yet(self):
        import logger
        assert "strategy_id" not in logger.TRADE_FIELDS
        assert "config_hash" not in logger.TRADE_FIELDS
        assert at.TRADE_ATTRIBUTION_FIELDS == ("strategy_id", "config_hash")

    def test_events_file_name_unchanged(self):
        # имена исторических журналов в ИСХОДНОМ КОДЕ logger.py не изменены
        # (runtime-значение может быть monkeypatched в conftest для изоляции)
        import pathlib
        candidate_root = pathlib.Path(__file__).resolve().parent.parent
        source = (candidate_root / "logger.py").read_text(encoding="utf-8")
        assert 'EVENTS_FILE = "research_events.jsonl"' in source
        assert 'TRADES_FILE = "research_trades.csv"' in source

    def test_attribution_module_does_not_touch_production_flow(self):
        # атрибуция нового движка — самостоятельный интерфейс: она не
        # вызывается из production-потока baseline (main/execution/logger
        # не импортируют attribution)
        import io
        import pathlib
        candidate_root = pathlib.Path(__file__).resolve().parent.parent
        for name in ("main.py", "execution.py", "logger.py",
                     "order_ledger.py", "strategy.py", "config.py"):
            text = (candidate_root / name).read_text(encoding="utf-8")
            assert "attribution" not in text.replace(
                "attribution.py", ""), \
                f"{name} не должен зависеть от атрибуции нового движка"
