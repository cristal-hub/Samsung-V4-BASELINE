# historical_engine/engine.py
# SAMSUNG V4 — NEW STRATEGY ENGINE. STAGE E.
#
# BacktestEngine: фасад детерминированного исторического симулятора.
# Компонует HistoricalDataFeed / EventEngine / StrategyRunner /
# HistoricalExecutionSimulator / RiskIntegration (Stage D) /
# PortfolioLedger / BacktestReport.
#
# IS / VALIDATION / OOS (ТЗ Stage E §8): движок поддерживает РАЗДЕЛЬНЫЕ
# прогоны по SegmentSpec. КАЖДЫЙ сегмент — независимый прогон с нулевой
# позиции и начальным кэшем EngineConfig (позиции не переносятся через
# границу сегмента). Оптимизация параметров ОТСУТСТВУЕТ: движок не
# возвращает и не принимает «улучшенные» параметры; результаты OOS не
# могут автоматически менять параметры (архитектурно: отчёты — данные
# только для чтения; входные параметры прогона задаются ДО запуска).

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from strategy_api import Strategy, StrategyConfig

from .data_feed import HistoricalDataFeed
from .event_engine import EventEngine
from .execution import HistoricalExecutionSimulator
from .ledger import PortfolioLedger
from .models import (
    EngineConfig,
    EngineConfigError,
    SegmentSpec,
)
from .report import BacktestReportBuilder
from .risk_integration import RiskIntegration
from .strategy_runner import StrategyRunner


class BacktestEngine:
    """Детерминированный исторический симулятор (research only)."""

    def __init__(self, *,
                 strategy: Strategy,
                 strategy_config: StrategyConfig,
                 engine_config: EngineConfig,
                 feed: HistoricalDataFeed) -> None:
        if not isinstance(strategy, Strategy):
            raise EngineConfigError(
                "BacktestEngine требует стратегию контракта Stage A")
        if type(strategy_config) is not StrategyConfig:
            raise EngineConfigError(
                "BacktestEngine требует точный тип StrategyConfig")
        if type(engine_config) is not EngineConfig:
            raise EngineConfigError(
                "BacktestEngine требует точный тип EngineConfig")
        if type(feed) is not HistoricalDataFeed:
            raise EngineConfigError(
                "BacktestEngine требует точный тип HistoricalDataFeed")
        if strategy_config.strategy_id != strategy.strategy_id:
            raise EngineConfigError(
                "конфигурация принадлежит другой стратегии: "
                f"{strategy_config.strategy_id!r} != "
                f"{strategy.strategy_id!r}")
        self._strategy = strategy
        self._strategy_config = strategy_config
        self._cfg = engine_config
        self._feed = feed

    # --- компонование независимого прогона --------------------------------------

    def _build_components(self) -> Tuple[
            PortfolioLedger, HistoricalExecutionSimulator,
            StrategyRunner, EventEngine]:
        """Свежие компоненты для НЕЗАВИСИМОГО прогона (изоляция сегментов:
        ни состояние портфеля, ни состояние стратегии не переносятся)."""
        ledger = PortfolioLedger(initial_cash=self._cfg.initial_cash,
                                 figi=self._cfg.figi)
        risk = RiskIntegration(engine_config=self._cfg,
                               strategy_config=self._strategy_config)

        def levels_provider():
            position = ledger.position
            if position is None:
                return None
            return {"stop_price": position.stop_price,
                    "take_price": position.take_price}

        runner = StrategyRunner(
            strategy=self._strategy,
            strategy_config=self._strategy_config,
            feed=self._feed,
            engine_config=self._cfg,
            levels_provider=levels_provider,
        )
        simulator = HistoricalExecutionSimulator(
            engine_config=self._cfg, ledger=ledger, risk_integration=risk)
        event_engine = EventEngine(
            strategy=self._strategy,
            strategy_config=self._strategy_config,
            feed=self._feed,
            engine_config=self._cfg,
            ledger=ledger,
            simulator=simulator,
            runner=runner,
        )
        return ledger, simulator, runner, event_engine

    # --- прогоны -------------------------------------------------------------------

    def run_segment(self, segment: SegmentSpec) -> Dict[str, Any]:
        """Независимый прогон одного сегмента [start_index, end_index)."""
        if type(segment) is not SegmentSpec:
            raise EngineConfigError(
                "run_segment требует точный тип SegmentSpec")
        if segment.end_index > self._feed.length:
            raise EngineConfigError(
                f"граница сегмента {segment.end_index} вне данных "
                f"(длина {self._feed.length})")
        ledger, _simulator, _runner, event_engine = self._build_components()
        run_summary = event_engine.run(
            start_index=segment.start_index, end_index=segment.end_index)
        builder = BacktestReportBuilder(
            segment_label=segment.label,
            start_index=segment.start_index,
            end_index=segment.end_index,
            feed=self._feed,
            engine_config=self._cfg,
            strategy_config=self._strategy_config,
            ledger=ledger,
            events=event_engine.events,
            run_summary=run_summary,
        )
        return builder.build()

    def run_full(self) -> Dict[str, Any]:
        """Прогон всей серии как одного сегмента с меткой FULL."""
        return self.run_segment(
            SegmentSpec(label="FULL", start_index=0,
                        end_index=self._feed.length))

    def run_segments(self, segments: List[SegmentSpec]) -> Dict[str, Any]:
        """Независимые прогоны списка сегментов (IS/VALIDATION/OOS).

        Требования: сегменты внутри границ данных; перекрытия допускаются
        (каждый сегмент — независимый прогон), но для классической схемы
        IS/VALIDATION/OOS они не нужны. Возвращается бандл с отчётами и
        общим идентификатором; НИКАКИХ параметров из отчётов не
        извлекается и не подстраивается (ТЗ §8: запрет использования
        OOS-результатов для изменения параметров).
        """
        reports: List[Dict[str, Any]] = []
        for segment in segments:
            if type(segment) is not SegmentSpec:
                raise EngineConfigError(
                    "run_segments принимает только точный тип SegmentSpec")
            if segment.end_index > self._feed.length:
                raise EngineConfigError(
                    f"граница сегмента {segment.end_index} вне данных "
                    f"(длина {self._feed.length})")
            reports.append(self.run_segment(segment))
        bundle_id_source = {
            "engine_config_sha256": self._cfg.config_sha256(),
            "strategy_config_hash": self._strategy_config.config_hash,
            "data_sha256": self._feed.data_sha256,
            "segments": [
                {"label": s.label, "start_index": s.start_index,
                 "end_index": s.end_index} for s in segments],
        }
        from .models import canonical_json, sha256_hex
        return {
            "bundle_schema": "samsung_v4_stage_e_bundle_v1",
            "bundle_id": sha256_hex(canonical_json(bundle_id_source)),
            "reports": reports,
            "note": "Параметры стратегий НЕ оптимизируются движком; "
                    "отчёты IS/VALIDATION/OOS — данные только для чтения.",
        }

    # --- вспомогательное ---------------------------------------------------------------

    @property
    def strategy_config(self) -> StrategyConfig:
        return self._strategy_config

    @property
    def engine_config(self) -> EngineConfig:
        return self._cfg
