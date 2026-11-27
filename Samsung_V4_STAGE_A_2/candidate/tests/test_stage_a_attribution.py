# tests/test_stage_a_attribution.py
# STAGE A: атрибуция новых объектов и обратная совместимость старых записей
# (ТЗ разделы 9, 9.1, 12).
#
# Обязательные проверки Этапа A:
#   * новые объекты получают корректную атрибуцию (strategy_id, config_hash);
#   * чтение старых записей БЕЗ атрибуции — безопасно и явно (None/False);
#   * отсутствие фиктивной атрибуции у старых объектов (никаких выдуманных
#     значений; старые файлы не переписываются);
#   * отсутствие атрибуции у нового объекта НЕ маскируется (fail-closed).
#
# ИЗМЕНЕНО В STAGE A.1 (замечания №2/№3 аудита; архитектурная адаптация,
# НЕ смена эталонов): глобальный контекст атрибуции УДАЛЕН из attribution.py
# как обязательный источник (set_current_context/get_current_context/
# clear_current_context больше не существуют). Контекст передаётся ЯВНО в
# каждый вызов; отсутствие контекста — явная ошибка (AttributionRequiredError
# при None, TypeError при отсутствующем аргументе). Формулировки проверок
# сохранены; дополнительные тесты явного DI и параллельной изоляции — в
# tests/test_stage_a1_attribution_explicit.py.
#
# Offline; без сети, брокера и заявок. Файлы создаются только в tmp_path.

import csv
import json
import os

import pytest

import attribution as at
from attribution import (
    ATTRIBUTION_FIELDS,
    AttributionContext,
    AttributionError,
    AttributionRequiredError,
    append_attributed_csv_row,
    legacy_attribution_view,
    read_csv_attribution_report,
    record_has_attribution,
    stamp,
)
import config as legacy_config
from engine_config import (
    EngineConfigError,
    EngineStatus,
    load_engine_config,
    require_trading_ready,
)


@pytest.fixture
def context():
    return AttributionContext(
        strategy_id="legacy_samsung_v4",
        config_hash="a" * 64,
    )


@pytest.fixture
def legacy_trade_fields():
    # историческая схема торгового CSV из production logger.py (только чтение)
    import logger
    return list(logger.TRADE_FIELDS)


# ---------------------------------------------------------------------------
# Штампование НОВЫХ объектов
# ---------------------------------------------------------------------------

class TestStampingNewObjects:
    def test_new_object_gets_attribution(self, context):
        event = {"timestamp_utc": "2026-01-01T00:00:00Z", "event": "TEST"}
        stamped = stamp(event, context)
        assert stamped["strategy_id"] == "legacy_samsung_v4"
        assert stamped["config_hash"] == "a" * 64
        assert record_has_attribution(stamped) is True

    def test_original_dict_not_mutated(self, context):
        event = {"x": 1}
        stamp(event, context)
        assert event == {"x": 1}

    def test_missing_context_fails_closed(self):
        # никакой фиктивной атрибуции: контекст ОБЯЗАТЕЛЕН (Stage A.1).
        # Явно переданный None -> AttributionRequiredError; отсутствующий
        # аргумент -> TypeError (fail-closed до входа в функцию).
        with pytest.raises(AttributionRequiredError):
            stamp({"x": 1}, None)
        with pytest.raises(TypeError):
            stamp({"x": 1})

    def test_missing_context_error_message_explains(self):
        with pytest.raises(AttributionRequiredError) as exc:
            stamp({}, None)
        message = str(exc.value)
        assert "фиктивные значения запрещены" in message
        assert "контекст" in message

    def test_explicit_context_is_the_only_source(self, context):
        # Stage A.1: атрибуция ТОЛЬКО из явно переданного контекста;
        # глобального состояния не существует
        assert not hasattr(at, "set_current_context")
        assert not hasattr(at, "get_current_context")
        assert not hasattr(at, "clear_current_context")
        assert not hasattr(at, "_current_context")
        stamped = stamp({"x": 1}, context)
        assert stamped["strategy_id"] == "legacy_samsung_v4"
        assert stamped["config_hash"] == "a" * 64

    def test_conflicting_existing_attribution_rejected(self, context):
        record = {"strategy_id": "other", "config_hash": "b" * 64}
        with pytest.raises(AttributionError):
            stamp(record, context)
        # явный overwrite разрешён и меняет только поля атрибуции
        stamped = stamp(record, context, overwrite=True)
        assert stamped["strategy_id"] == "legacy_samsung_v4"
        assert stamped["config_hash"] == "a" * 64

    def test_same_attribution_idempotent(self, context):
        record = {"strategy_id": "legacy_samsung_v4",
                  "config_hash": "a" * 64, "x": 1}
        stamped = stamp(record, context)
        assert stamped == record

    def test_invalid_context_rejected(self):
        with pytest.raises(AttributionError):
            AttributionContext(strategy_id="", config_hash="a" * 64)
        with pytest.raises(AttributionError):
            AttributionContext(strategy_id="s", config_hash="")

    def test_event_jsonl_payload_roundtrip(self, context):
        payload = stamp({"event": "SIGNAL", "figi": "F"}, context)
        text = json.dumps(payload, ensure_ascii=False)
        restored = json.loads(text)
        assert restored["strategy_id"] == "legacy_samsung_v4"
        assert restored["config_hash"] == "a" * 64


# ---------------------------------------------------------------------------
# Чтение СТАРЫХ записей без атрибуции (обратная совместимость)
# ---------------------------------------------------------------------------

class TestLegacyRecordsReading:
    def test_old_record_view_is_explicitly_none(self):
        old = {"trade_id": "T1", "ticker": "SBER", "side": "BUY"}
        view = legacy_attribution_view(old)
        assert view["has_attribution"] is False
        assert view["strategy_id"] is None
        assert view["config_hash"] is None

    def test_no_fabricated_values_in_view(self):
        # никакого "UNKNOWN"/"LEGACY"/"" вместо отсутствующих данных
        view = legacy_attribution_view({"trade_id": "T2"})
        assert view["strategy_id"] is None
        assert view["config_hash"] is None

    def test_partial_attribution_is_not_trusted(self):
        record = {"strategy_id": "legacy_samsung_v4"}  # config_hash нет
        assert record_has_attribution(record) is False
        view = legacy_attribution_view(record)
        assert view["has_attribution"] is False
        assert view["config_hash"] is None

    def test_old_csv_read_safely_and_unchanged(self, tmp_path,
                                               legacy_trade_fields):
        # старый журнал в исторической схеме logger.TRADE_FIELDS
        old_csv = tmp_path / "research_trades.csv"
        with open(old_csv, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=legacy_trade_fields,
                                    delimiter=";")
            writer.writeheader()
            writer.writerow({
                "trade_id": "T1", "timestamp_utc": "2025-01-01T10:00:00Z",
                "ticker": "SBER", "figi": "BBG000000001", "lot_size": "1",
                "side": "BUY", "signal_reason": "MA(9/21) ↑",
            })
        before = old_csv.read_bytes()

        report = read_csv_attribution_report(str(old_csv))
        assert len(report) == 1
        assert report[0]["has_attribution"] is False
        assert report[0]["strategy_id"] is None
        assert report[0]["config_hash"] is None

        # исторический файл НЕ переписан, миграции НЕТ
        assert old_csv.read_bytes() == before

    def test_old_csv_many_rows_all_unattributed(self, tmp_path,
                                                legacy_trade_fields):
        old_csv = tmp_path / "research_trades.csv"
        with open(old_csv, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=legacy_trade_fields,
                                    delimiter=";")
            writer.writeheader()
            for i in range(5):
                writer.writerow({"trade_id": f"T{i}", "ticker": "SBER",
                                 "side": "BUY" if i % 2 == 0 else "SELL"})
        report = read_csv_attribution_report(str(old_csv))
        assert len(report) == 5
        assert all(not row["has_attribution"] for row in report)


# ---------------------------------------------------------------------------
# Новые CSV-журналы движка (только новые записи; старые файлы не трогаем)
# ---------------------------------------------------------------------------

class TestAttributedCsvWriter:
    BASE_FIELDS = ["event_id", "timestamp_utc", "figi", "kind"]

    def test_new_row_carries_attribution(self, tmp_path, context):
        path = str(tmp_path / "engine_events.csv")
        written = append_attributed_csv_row(
            path, {"event_id": "E1", "timestamp_utc": "2026-01-01T00:00:00Z",
                   "figi": "F", "kind": "SIGNAL"},
            self.BASE_FIELDS, context=context)
        assert written["strategy_id"] == "legacy_samsung_v4"
        with open(path, "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter=";"))
        assert len(rows) == 1
        assert rows[0]["strategy_id"] == "legacy_samsung_v4"
        assert rows[0]["config_hash"] == "a" * 64
        # поля атрибуции добавлены В КОНЕЦ шапки
        with open(path, "r", encoding="utf-8") as handle:
            first = handle.readline().strip()
        assert first.split(";")[-2:] == list(ATTRIBUTION_FIELDS)

    def test_no_context_no_row(self, tmp_path):
        # Stage A.1: контекст обязателен; None -> AttributionRequiredError,
        # файл не создаётся
        path = str(tmp_path / "engine_events.csv")
        with pytest.raises(AttributionRequiredError):
            append_attributed_csv_row(
                path, {"event_id": "E1"}, self.BASE_FIELDS, context=None)
        assert not os.path.isfile(path)

    def test_legacy_reader_still_reads_base_columns(self, tmp_path, context):
        # совместимость: читатель со СТАРОЙ шапкой читает базовые столбцы;
        # дополнительные столбцы атрибуции в КОНЦЕ строки не сдвигают
        # базовые столбцы (позиционное чтение csv.reader)
        path = str(tmp_path / "engine_events.csv")
        append_attributed_csv_row(
            path, {"event_id": "E1", "timestamp_utc": "t", "figi": "F",
                   "kind": "SIGNAL"},
            self.BASE_FIELDS, context=context)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter=";")
            header = next(reader)
            row = next(reader)
        assert header[:len(self.BASE_FIELDS)] == self.BASE_FIELDS
        base_values = row[:len(self.BASE_FIELDS)]
        assert base_values[0] == "E1"
        assert base_values[2] == "F"
        assert base_values[3] == "SIGNAL"
        # новые столбцы идут строго после базовых
        assert header[len(self.BASE_FIELDS):] == list(ATTRIBUTION_FIELDS)
        assert row[-2] == "legacy_samsung_v4"
        assert row[-1] == "a" * 64

    def test_multiple_rows_append_only(self, tmp_path, context):
        path = str(tmp_path / "engine_events.csv")
        for i in range(3):
            append_attributed_csv_row(
                path, {"event_id": f"E{i}", "timestamp_utc": "t",
                       "figi": "F", "kind": "K"},
                self.BASE_FIELDS, context=context)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter=";"))
        assert [r["event_id"] for r in rows] == ["E0", "E1", "E2"]
        assert all(r["config_hash"] == "a" * 64 for r in rows)


# ---------------------------------------------------------------------------
# Связка с конфигурацией движка: атрибуция невозможна без CONFIGURED
# ---------------------------------------------------------------------------

class TestEngineConfigLink:
    def test_unconfigured_produces_no_attribution(self, tmp_path):
        p = tmp_path / "engine.json"
        p.write_text(json.dumps({"ACTIVE_STRATEGY": None}),
                     encoding="utf-8")
        cfg = load_engine_config(engine_json_path=str(p), environ={})
        assert cfg.status is EngineStatus.UNCONFIGURED
        assert cfg.attribution is None
        with pytest.raises(EngineConfigError):
            require_trading_ready(cfg)
        # и штампование без явного контекста запрещено (None передан явно)
        with pytest.raises(AttributionRequiredError):
            stamp({}, None)

    def test_config_error_produces_no_attribution(self, tmp_path):
        p = tmp_path / "engine.json"
        p.write_text(json.dumps({"ACTIVE_STRATEGY": "no_such"}),
                     encoding="utf-8")
        cfg = load_engine_config(engine_json_path=str(p), environ={})
        assert cfg.status is EngineStatus.CONFIG_ERROR
        assert cfg.attribution is None

    def test_trade_attribution_fields_reserved_for_stage_b(self):
        # предложение для Этапа B задокументировано, но production
        # logger.py на Этапе A НЕ изменён: TRADE_FIELDS не содержит полей
        import logger
        assert "strategy_id" not in logger.TRADE_FIELDS
        assert "config_hash" not in logger.TRADE_FIELDS
        assert at.TRADE_ATTRIBUTION_FIELDS == ("strategy_id", "config_hash")

    def test_baseline_config_module_untouched(self):
        # изоляция: тесты атрибуции не меняли baseline config
        assert legacy_config.PROFILE == "FORCE_TRADE"
