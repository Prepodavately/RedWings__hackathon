/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useMemo } from 'react';
import {
  CANDIDATE_CITIES,
  NETWORK_ROUTES,
  ScoringWeights,
  SimulationParams,
  ScenarioMode,
  scoreCandidateCities,
  calculateHypothesesComparison,
  TOTAL_RF_MARKET_PAX_2025,
  RED_WINGS_BASE_PAX_2025,
} from './utils/aviationModel';
import { CityScoringSection } from './components/CityScoringSection';
import { NetworkMapSection } from './components/NetworkMapSection';
import { GitHubArchitectureSection } from './components/GitHubArchitectureSection';
import {
  Download,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  ArrowUpRight,
} from 'lucide-react';

type ActiveSection = 'economics' | 'scoring' | 'map' | 'architecture';

export default function App() {
  const [activeSection, setActiveSection] = useState<ActiveSection>('economics');

  // Состояние весов скоринга 12 городов
  const [weights, setWeights] = useState<ScoringWeights>({
    wPopulation: 30,
    wHubDistance: 20,
    wCompetitorGap: 30,
    wTourismDemand: 20,
  });

  // Состояние входных параметров финансово-математической модели
  const [simParams, setSimParams] = useState<SimulationParams>({
    loadFactorPct: 84,
    avgFareRub: 8400,
    weeklyFreqPerRoute: 5,
    aircraftSeats: 100, // SJ-100 базовая вместимость
    activeRouteCount: 10, // от 8 до 12 маршрутов
    scenario: 'base',
    selectedHubIata: 'KUF',
  });

  const [exportSuccess, setExportSuccess] = useState(false);

  // 1. Автоматический пересчет скоринга 12 городов при изменении весов
  const scoredCities = useMemo(
    () => scoreCandidateCities(CANDIDATE_CITIES, weights),
    [weights]
  );

  // 2. Автоматический пересчет юнит-экономики двух гипотез при движении ползунков
  const comparison = useMemo(
    () => calculateHypothesesComparison(simParams),
    [simParams]
  );

  const top3Cities = useMemo(
    () => scoredCities.filter((c) => c.isTop3),
    [scoredCities]
  );

  const handleResetDefaults = () => {
    setSimParams({
      loadFactorPct: 84,
      avgFareRub: 8400,
      weeklyFreqPerRoute: 5,
      aircraftSeats: 100,
      activeRouteCount: 10,
      scenario: 'base',
      selectedHubIata: 'KUF',
    });
    setWeights({
      wPopulation: 30,
      wHubDistance: 20,
      wCompetitorGap: 30,
      wTourismDemand: 20,
    });
  };

  const handleExportCsv = () => {
    const headers = [
      'Гипотеза',
      'Сценарий',
      'Пассажиропоток_год',
      'Выручка_млн_руб',
      'Опер_расходы_млн_руб',
      'EBITDAR_млн_руб',
      'Маржа_EBITDAR_%',
      'Прирост_доли_рынка_%',
      'Потребность_SJ100_шт',
    ];
    const rows = [comparison.hub, comparison.p2p].map((m) => [
      `"${m.title}"`,
      simParams.scenario === 'base' ? 'Базовый' : 'Осторожный',
      m.annualPassengers,
      m.annualRevenueMlnRub,
      m.operatingCostMlnRub,
      m.ebitdarMlnRub,
      m.ebitdarMarginPct,
      m.marketShareDeltaPct,
      m.requiredAircraftSj100,
    ]);
    const csvContent =
      'data:text/csv;charset=utf-8,\uFEFF' +
      [headers.join(';'), ...rows.map((r) => r.join(';'))].join('\n');

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute(
      'download',
      `redwings_strategy_${simParams.scenario}_${simParams.selectedHubIata}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    setExportSuccess(true);
    setTimeout(() => setExportSuccess(false), 2000);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      {/* Top Bar Contract: 3 строгие зоны (Brand — 4 Nav Links — 1 Primary Action) */}
      <header className="sticky top-0 z-30 bg-white/95 backdrop-blur-xs border-b border-slate-200 px-6 py-3.5 flex items-center justify-between gap-8">
        {/* Zone 1: Brand title, single element */}
        <a
          href="#top"
          onClick={(e) => {
            e.preventDefault();
            setActiveSection('economics');
          }}
          className="text-base font-bold tracking-tight text-slate-900 whitespace-nowrap shrink-0"
        >
          Red Wings · Стратегия Сети 2028
        </a>

        {/* Zone 2: 4 single-line navigation links */}
        <nav
          className="flex items-center gap-6 text-sm font-medium text-slate-600 overflow-x-auto"
          aria-label="Основная навигация"
        >
          <button
            type="button"
            onClick={() => setActiveSection('economics')}
            className={`py-1 transition-colors whitespace-nowrap shrink-0 border-b-2 ${
              activeSection === 'economics'
                ? 'border-rose-600 text-slate-900 font-semibold'
                : 'border-transparent hover:text-slate-900'
            }`}
          >
            Юнит-экономика
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('scoring')}
            className={`py-1 transition-colors whitespace-nowrap shrink-0 border-b-2 ${
              activeSection === 'scoring'
                ? 'border-rose-600 text-slate-900 font-semibold'
                : 'border-transparent hover:text-slate-900'
            }`}
          >
            Скоринг городов
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('map')}
            className={`py-1 transition-colors whitespace-nowrap shrink-0 border-b-2 ${
              activeSection === 'map'
                ? 'border-rose-600 text-slate-900 font-semibold'
                : 'border-transparent hover:text-slate-900'
            }`}
          >
            Карта сети и Пруф
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('architecture')}
            className={`py-1 transition-colors whitespace-nowrap shrink-0 border-b-2 ${
              activeSection === 'architecture'
                ? 'border-rose-600 text-slate-900 font-semibold'
                : 'border-transparent hover:text-slate-900'
            }`}
          >
            Архитектура GitHub
          </button>
        </nav>

        {/* Zone 3: 1 Primary Action */}
        <div className="shrink-0">
          <button
            type="button"
            onClick={handleExportCsv}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg transition-colors whitespace-nowrap shrink-0 cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>{exportSuccess ? 'Отчет CSV выгружен' : 'Скачать расчет CSV'}</span>
          </button>
        </div>
      </header>

      {/* Основная рабочая область (1440px container presence) */}
      <main className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-6 space-y-6">
        {/* Верхняя аналитическая панель контекста и интерактивных ползунков допущений */}
        <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-4">
            <div className="max-w-3xl">
              <div className="text-xs text-slate-500 font-medium">
                Кейс Red Wings · Рынок РФ 2025: 108,9 млн пасс. · Флот экспансии: SJ-100 (поставки со 2П 2027 г.)
              </div>
              <h1 className="text-xl sm:text-2xl font-bold text-slate-900 mt-1 text-balance">
                Система выбора транспортной стратегии: Региональный хаб против Прямых межрегиональных рейсов
              </h1>
            </div>

            {/* Переключатель сценариев: Базовый vs Осторожный (пессимистичный) + Сброс */}
            <div className="flex flex-wrap items-center gap-3">
              <div
                className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg border border-slate-200"
                role="group"
                aria-label="Сценарий моделирования"
              >
                <button
                  type="button"
                  onClick={() =>
                    setSimParams((prev) => ({ ...prev, scenario: 'base' }))
                  }
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 ${
                    simParams.scenario === 'base'
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-700 hover:text-slate-900'
                  }`}
                >
                  Базовый сценарий
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setSimParams((prev) => ({ ...prev, scenario: 'conservative' }))
                  }
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 ${
                    simParams.scenario === 'conservative'
                      ? 'bg-rose-600 text-white'
                      : 'text-slate-700 hover:text-slate-900'
                  }`}
                >
                  Осторожный (пессимистичный)
                </button>
              </div>

              <button
                type="button"
                onClick={handleResetDefaults}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors whitespace-nowrap shrink-0"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Сбросить</span>
              </button>
            </div>
          </div>

          {/* Ползунки входных параметров финансово-математической модели */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {/* Ползунок 1: Процент коммерческой загрузки кресел */}
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-800 mb-1.5">
                <label htmlFor="slider-slf">Загрузка кресел (SLF)</label>
                <span className="font-mono text-rose-600 font-bold tabular-nums">
                  {simParams.loadFactorPct}%
                </span>
              </div>
              <input
                id="slider-slf"
                type="range"
                min={65}
                max={95}
                step={1}
                value={simParams.loadFactorPct}
                onChange={(e) =>
                  setSimParams((prev) => ({
                    ...prev,
                    loadFactorPct: Number(e.target.value),
                  }))
                }
                className="w-full accent-rose-600 cursor-pointer"
              />
              <div className="flex justify-between text-[11px] font-mono text-slate-500 mt-1">
                <span>65%</span>
                <span>Норма: 84%</span>
                <span>95%</span>
              </div>
            </div>

            {/* Ползунок 2: Средний тариф (руб.) */}
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-800 mb-1.5">
                <label htmlFor="slider-fare">Средний тариф (OW)</label>
                <span className="font-mono text-rose-600 font-bold tabular-nums">
                  {simParams.avgFareRub.toLocaleString('ru-RU')} ₽
                </span>
              </div>
              <input
                id="slider-fare"
                type="range"
                min={5500}
                max={13500}
                step={250}
                value={simParams.avgFareRub}
                onChange={(e) =>
                  setSimParams((prev) => ({
                    ...prev,
                    avgFareRub: Number(e.target.value),
                  }))
                }
                className="w-full accent-rose-600 cursor-pointer"
              />
              <div className="flex justify-between text-[11px] font-mono text-slate-500 mt-1">
                <span>5 500 ₽</span>
                <span>8 400 ₽</span>
                <span>13 500 ₽</span>
              </div>
            </div>

            {/* Ползунок 3: Частота рейсов в неделю */}
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-800 mb-1.5">
                <label htmlFor="slider-freq">Частота рейсов / нед.</label>
                <span className="font-mono text-rose-600 font-bold tabular-nums">
                  {simParams.weeklyFreqPerRoute} пар/нед
                </span>
              </div>
              <input
                id="slider-freq"
                type="range"
                min={2}
                max={10}
                step={1}
                value={simParams.weeklyFreqPerRoute}
                onChange={(e) =>
                  setSimParams((prev) => ({
                    ...prev,
                    weeklyFreqPerRoute: Number(e.target.value),
                  }))
                }
                className="w-full accent-rose-600 cursor-pointer"
              />
              <div className="flex justify-between text-[11px] font-mono text-slate-500 mt-1">
                <span>2 р/нед</span>
                <span>Порог хаба: 6+</span>
                <span>10 р/нед</span>
              </div>
            </div>

            {/* Ползунок 4: Число маршрутов в сети (8–12) */}
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-800 mb-1.5">
                <label htmlFor="slider-routes">Маршрутов в сети</label>
                <span className="font-mono text-rose-600 font-bold tabular-nums">
                  {simParams.activeRouteCount} линий
                </span>
              </div>
              <input
                id="slider-routes"
                type="range"
                min={8}
                max={12}
                step={1}
                value={simParams.activeRouteCount}
                onChange={(e) =>
                  setSimParams((prev) => ({
                    ...prev,
                    activeRouteCount: Number(e.target.value),
                  }))
                }
                className="w-full accent-rose-600 cursor-pointer"
              />
              <div className="flex justify-between text-[11px] font-mono text-slate-500 mt-1">
                <span>8 мин.</span>
                <span>10 опт.</span>
                <span>12 макс.</span>
              </div>
            </div>

            {/* Выбор кандидата хаба из Топ-3 скоринга */}
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 flex flex-col justify-between">
              <label
                htmlFor="select-hub-candidate"
                className="text-xs font-semibold text-slate-800"
              >
                Кандидат под Хаб (Топ-3)
              </label>
              <select
                id="select-hub-candidate"
                value={simParams.selectedHubIata}
                onChange={(e) =>
                  setSimParams((prev) => ({
                    ...prev,
                    selectedHubIata: e.target.value,
                  }))
                }
                className="mt-1.5 w-full text-xs font-semibold bg-white border border-slate-300 rounded-lg px-2.5 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-rose-500"
              >
                {top3Cities.map((c) => (
                  <option key={c.iata} value={c.iata}>
                    #{c.rank} {c.name.split(' (')[0]} ({c.iata}) — {c.totalScore} б.
                  </option>
                ))}
              </select>
              <div className="text-[11px] text-slate-500 mt-1">
                Топ-3 пересчитывается в разделе «Скоринг»
              </div>
            </div>
          </div>
        </section>

        {/* ВКЛАДКА 1: ЮНИТ-ЭКОНОМИКА И СРАВНЕНИЕ ГИПОТЕЗ */}
        {activeSection === 'economics' && (
          <div className="space-y-6">
            {/* Вердикт математической модели */}
            <div className="bg-slate-900 text-white rounded-xl p-5 border border-slate-800 flex flex-col lg:flex-row lg:items-center justify-between gap-5">
              <div className="space-y-1.5 max-w-4xl">
                <div className="flex items-center gap-2 text-xs font-mono text-rose-400">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>
                    МАТЕМАТИЧЕСКИ ОБОСНОВАННЫЙ ВЫБОР · СЦЕНАРИЙ:{' '}
                    {simParams.scenario === 'base'
                      ? 'БАЗОВЫЙ'
                      : 'ОСТОРОЖНЫЙ (СДВИГ ПОСТАВОК SJ-100 НА 2П 2027)'}
                  </span>
                </div>
                <h2 className="text-lg sm:text-xl font-bold text-white">
                  Рекомендована {comparison.winnerTitle}
                </h2>
                <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
                  {comparison.rationale}
                </p>
              </div>

              <div className="flex flex-wrap sm:flex-nowrap items-center gap-4 shrink-0 border-t lg:border-t-0 pt-3 lg:pt-0 border-slate-800">
                <div className="bg-slate-800/90 border border-slate-700 rounded-lg px-4 py-3 text-right">
                  <div className="text-xs text-slate-400">Прирост доли рынка РФ</div>
                  <div className="text-xl font-bold font-mono text-emerald-400 tabular-nums mt-0.5">
                    +
                    {comparison.winner === 'p2p'
                      ? comparison.p2p.marketShareDeltaPct
                      : comparison.hub.marketShareDeltaPct}
                    %
                  </div>
                  <div className="text-[11px] font-mono text-slate-400">
                    Доля RW:{' '}
                    {comparison.winner === 'p2p'
                      ? comparison.p2p.newTotalMarketSharePct
                      : comparison.hub.newTotalMarketSharePct}
                    %
                  </div>
                </div>

                <div className="bg-slate-800/90 border border-slate-700 rounded-lg px-4 py-3 text-right">
                  <div className="text-xs text-slate-400">Преимущество по выручке</div>
                  <div className="text-xl font-bold font-mono text-white tabular-nums mt-0.5">
                    +{comparison.revenueDeltaMlnRub.toLocaleString('ru-RU')} млн ₽
                  </div>
                  <div className="text-[11px] font-mono text-slate-400">
                    Дельта пасс.: {comparison.paxDelta.toLocaleString('ru-RU')} чел.
                  </div>
                </div>
              </div>
            </div>

            {/* Сравнение двух гипотез бок о бок */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {[comparison.p2p, comparison.hub].map((item) => {
                const isWinner = comparison.winner === item.type;
                return (
                  <div
                    key={item.type}
                    className={`bg-white rounded-xl border p-5 space-y-5 ${
                      isWinner
                        ? 'border-slate-900 ring-1 ring-slate-900'
                        : 'border-slate-200'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
                      <div>
                        <div className="text-xs font-mono font-semibold text-rose-600">
                          {isWinner
                            ? 'ЛИДЕР МОДЕЛИРОВАНИЯ · РЕКОМЕНДОВАНО К ЗАПУСКУ'
                            : 'АЛЬТЕРНАТИВНАЯ ГИПОТЕЗА'}
                        </div>
                        <h3 className="text-lg font-bold text-slate-900 mt-0.5">
                          {item.title}
                        </h3>
                        <p className="text-xs text-slate-600 mt-0.5">{item.subtitle}</p>
                      </div>
                      <div className="text-right font-mono shrink-0">
                        <div className="text-xs text-slate-500">Потребность во флоте</div>
                        <div className="text-base font-bold text-slate-900 tabular-nums">
                          {item.requiredAircraftSj100} борта SJ-100
                        </div>
                      </div>
                    </div>

                    {/* 3 Главные метрики кейса: Пассажиропоток, Выручка, Доля рынка */}
                    <div className="grid grid-cols-3 gap-3">
                      <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
                        <div className="text-xs text-slate-500">1. Пассажиропоток</div>
                        <div className="text-lg font-bold font-mono text-slate-900 tabular-nums mt-1">
                          {(item.annualPassengers / 1000).toFixed(1)} тыс.
                        </div>
                        <div className="text-[11px] font-mono text-slate-500 mt-0.5 tabular-nums">
                          {item.annualPassengers.toLocaleString('ru-RU')} чел./год
                        </div>
                      </div>

                      <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
                        <div className="text-xs text-slate-500">2. Годовая выручка</div>
                        <div className="text-lg font-bold font-mono text-slate-900 tabular-nums mt-1">
                          {(item.annualRevenueMlnRub / 1000).toFixed(2)} млрд ₽
                        </div>
                        <div className="text-[11px] font-mono text-slate-500 mt-0.5 tabular-nums">
                          {item.annualRevenueMlnRub.toLocaleString('ru-RU')} млн ₽
                        </div>
                      </div>

                      <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
                        <div className="text-xs text-slate-500">3. Прирост доли РФ</div>
                        <div className="text-lg font-bold font-mono text-rose-600 tabular-nums mt-1">
                          +{item.marketShareDeltaPct}%
                        </div>
                        <div className="text-[11px] font-mono text-slate-500 mt-0.5 tabular-nums">
                          Итого RW: {item.newTotalMarketSharePct}%
                        </div>
                      </div>
                    </div>

                    {/* Детализация юнит-экономики */}
                    <div className="divide-y divide-slate-200 text-xs border-t border-slate-200 pt-2">
                      <div className="py-2 flex items-center justify-between">
                        <span className="text-slate-600">
                          Количество рейсов и кресельная емкость в год
                        </span>
                        <span className="font-mono font-semibold text-slate-900 tabular-nums">
                          {item.annualFlights.toLocaleString('ru-RU')} рейсов ·{' '}
                          {item.annualSeats.toLocaleString('ru-RU')} кресел
                        </span>
                      </div>
                      <div className="py-2 flex items-center justify-between">
                        <span className="text-slate-600">
                          Эффективная загрузка (с учетом синергии/сценария)
                        </span>
                        <span className="font-mono font-semibold text-slate-900 tabular-nums">
                          {item.effectiveLoadFactorPct}% (безубыточность: {item.breakEvenLoadFactorPct}%)
                        </span>
                      </div>
                      <div className="py-2 flex items-center justify-between">
                        <span className="text-slate-600">
                          Эффективный средний тариф (с учетом трансфера/прямой премии)
                        </span>
                        <span className="font-mono font-semibold text-slate-900 tabular-nums">
                          {item.avgEffectiveFareRub.toLocaleString('ru-RU')} ₽
                        </span>
                      </div>
                      <div className="py-2 flex items-center justify-between">
                        <span className="text-slate-600">
                          Операционные расходы (OPEX + содержание базы)
                        </span>
                        <span className="font-mono font-semibold text-slate-900 tabular-nums">
                          {item.operatingCostMlnRub.toLocaleString('ru-RU')} млн ₽
                        </span>
                      </div>
                      <div className="py-2 flex items-center justify-between">
                        <span className="text-slate-800 font-semibold">
                          Операционная прибыль (EBITDAR) и маржинальность
                        </span>
                        <span
                          className={`font-mono font-bold tabular-nums ${
                            item.ebitdarMlnRub >= 0 ? 'text-emerald-700' : 'text-rose-600'
                          }`}
                        >
                          {item.ebitdarMlnRub >= 0 ? '+' : ''}
                          {item.ebitdarMlnRub.toLocaleString('ru-RU')} млн ₽ ({item.ebitdarMarginPct}%)
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Быстрый переход к карте маршрутов, скорингу и архитектуре GitHub */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Топ-3 города по текущим весам скоринга:{' '}
                  {top3Cities
                    .map((c) => `#${c.rank} ${c.name.split(' (')[0]} (${c.iata}: ${c.totalScore} б.)`)
                    .join(' · ')}
                </h3>
                <p className="text-xs text-slate-600 mt-0.5">
                  Перейдите на вкладку «Карта сети и Пруф» для просмотра 8–12 маршрутов и дорожной карты поставок SJ-100 до 2028 г.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => setActiveSection('scoring')}
                  className="px-3.5 py-2 text-xs font-semibold text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors whitespace-nowrap shrink-0"
                >
                  Настроить веса скоринга (12 городов)
                </button>
                <button
                  type="button"
                  onClick={() => setActiveSection('map')}
                  className="px-3.5 py-2 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors whitespace-nowrap shrink-0"
                >
                  Открыть карту маршрутов ({simParams.activeRouteCount} линий)
                </button>
                <button
                  type="button"
                  onClick={() => setActiveSection('architecture')}
                  className="px-3.5 py-2 text-xs font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-lg transition-colors whitespace-nowrap shrink-0"
                >
                  Структура GitHub и API контракты
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ВКЛАДКА 2: АВТОМАТИЗИРОВАННЫЙ СКОРИНГ ГОРОДОВ */}
        {activeSection === 'scoring' && (
          <CityScoringSection
            scoredCities={scoredCities}
            weights={weights}
            onChangeWeights={setWeights}
            selectedHubIata={simParams.selectedHubIata}
            onSelectHub={(iata) =>
              setSimParams((prev) => ({ ...prev, selectedHubIata: iata }))
            }
          />
        )}

        {/* ВКЛАДКА 3: КАРТА МАРШРУТНОЙ СЕТИ И ДОКАЗАТЕЛЬНАЯ БАЗА */}
        {activeSection === 'map' && (
          <NetworkMapSection
            scoredCities={scoredCities}
            routes={NETWORK_ROUTES}
            selectedHubIata={simParams.selectedHubIata}
            onSelectHub={(iata) =>
              setSimParams((prev) => ({ ...prev, selectedHubIata: iata }))
            }
            activeRouteCount={simParams.activeRouteCount}
            loadFactorPct={simParams.loadFactorPct}
            avgFareRub={simParams.avgFareRub}
            weeklyFreqPerRoute={simParams.weeklyFreqPerRoute}
          />
        )}

        {/* ВКЛАДКА 4: АРХИТЕКТУРА GITHUB РЕПОЗИТОРИЯ И КОНТРАКТЫ */}
        {activeSection === 'architecture' && <GitHubArchitectureSection />}
      </main>

      {/* Чистый минималистичный футер */}
      <footer className="border-t border-slate-200 bg-white px-6 py-4 mt-8">
        <div className="max-w-[1400px] mx-auto flex flex-wrap items-center justify-between gap-4 text-xs text-slate-500">
          <span>
            Red Wings Strategic Route Planning System · Команда ПМИ (Прикладная математика и информатика)
          </span>
          <span>
            Источники данных: Росавиация (2025: 108,9 млн пасс.), Росстат, ПП РФ №1242
          </span>
        </div>
      </footer>
    </div>
  );
}
