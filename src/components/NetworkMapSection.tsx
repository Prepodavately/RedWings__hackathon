import React, { useState } from 'react';
import {
  CandidateCity,
  ScoredCity,
  RouteSpecification,
  HypothesisType,
} from '../utils/aviationModel';
import { Plane, CheckCircle2, ArrowRight, Calendar, ShieldCheck } from 'lucide-react';

interface NetworkMapSectionProps {
  scoredCities: ScoredCity[];
  routes: RouteSpecification[];
  selectedHubIata: string;
  onSelectHub: (iata: string) => void;
  activeRouteCount: number;
  loadFactorPct: number;
  avgFareRub: number;
  weeklyFreqPerRoute: number;
}

export const NetworkMapSection: React.FC<NetworkMapSectionProps> = ({
  scoredCities,
  routes,
  selectedHubIata,
  onSelectHub,
  activeRouteCount,
  loadFactorPct,
  avgFareRub,
  weeklyFreqPerRoute,
}) => {
  const [mapMode, setMapMode] = useState<HypothesisType>('p2p');
  const [selectedRouteId, setSelectedRouteId] = useState<string>(routes[0]?.id || 'r1');
  const [subsidyFilter, setSubsidyFilter] = useState<'all' | 'subsidized'>('all');

  const cityByIata = React.useMemo(() => {
    const map = new Map<string, ScoredCity>();
    scoredCities.forEach((c) => map.set(c.iata, c));
    return map;
  }, [scoredCities]);

  const top3Cities = scoredCities.filter((c) => c.isTop3);
  const hubCity = cityByIata.get(selectedHubIata) || top3Cities[0] || scoredCities[0];

  // Формируем отображаемый набор из activeRouteCount маршрутов (от 8 до 12)
  const displayedRoutes = React.useMemo(() => {
    const baseSlice = routes.slice(0, activeRouteCount);
    const adapted = baseSlice.map((route, idx) => {
      const dynamicPax = Math.round(
        weeklyFreqPerRoute * 2 * 52 * 100 * (loadFactorPct / 100) * (mapMode === 'hub' ? 0.98 : 1.02)
      );
      if (mapMode === 'hub' && hubCity) {
        // В режиме Регионального хаба все лучи ведут из выбранного хаба Топ-3
        const targetIata =
          route.destIata === hubCity.iata ? route.originIata : route.destIata;
        const targetCityObj = cityByIata.get(targetIata);
        return {
          ...route,
          code: `WZ-50${idx + 1}`,
          originIata: hubCity.iata,
          originCity: hubCity.name.split(' (')[0],
          destIata: targetCityObj ? targetCityObj.iata : route.destIata,
          destCity: targetCityObj ? targetCityObj.name.split(' (')[0] : route.destCity,
          estimatedAnnualPax: dynamicPax,
          proposedFareRub: Math.round(avgFareRub * 0.94),
        };
      }
      return {
        ...route,
        estimatedAnnualPax: dynamicPax,
        proposedFareRub: Math.round(avgFareRub * 1.04),
      };
    });

    if (subsidyFilter === 'subsidized') {
      return adapted.filter((r) => r.subsidyEligible);
    }
    return adapted;
  }, [
    routes,
    activeRouteCount,
    mapMode,
    hubCity,
    cityByIata,
    weeklyFreqPerRoute,
    loadFactorPct,
    avgFareRub,
    subsidyFilter,
  ]);

  const activeRoute =
    displayedRoutes.find((r) => r.id === selectedRouteId) || displayedRoutes[0];

  return (
    <div className="space-y-6">
      {/* Панель управления картой сети */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">
            Интерактивная карта маршрутной сети и пруф спроса ({displayedRoutes.length} маршрутов)
          </h2>
          <p className="text-sm text-slate-600 mt-0.5">
            Сравнение географии полетов SJ-100 в обход перегруженного Московского авиаузла (данные Росавиации и Росстата)
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Переключатель топологии сети */}
          <div
            className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg border border-slate-200"
            role="group"
            aria-label="Режим маршрутной сети"
          >
            <button
              type="button"
              onClick={() => setMapMode('p2p')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 ${
                mapMode === 'p2p'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'text-slate-700 hover:text-slate-900'
              }`}
            >
              Гипотеза Б: Прямые рейсы (P2P)
            </button>
            <button
              type="button"
              onClick={() => setMapMode('hub')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap shrink-0 ${
                mapMode === 'hub'
                  ? 'bg-slate-900 text-white shadow-xs'
                  : 'text-slate-700 hover:text-slate-900'
              }`}
            >
              Гипотеза А: Хаб ({selectedHubIata})
            </button>
          </div>

          {/* Выбор базового хаба из Топ-3 */}
          <div className="flex items-center gap-2">
            <label htmlFor="hub-map-select" className="text-xs font-medium text-slate-600 whitespace-nowrap">
              База хаба (Топ-3):
            </label>
            <select
              id="hub-map-select"
              value={selectedHubIata}
              onChange={(e) => onSelectHub(e.target.value)}
              className="text-xs font-semibold bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-900 focus:outline-none focus:ring-2 focus:ring-rose-500"
            >
              {top3Cities.map((c) => (
                <option key={c.iata} value={c.iata}>
                  #{c.rank} {c.iata} — {c.name.split(' (')[0]} ({c.totalScore} б.)
                </option>
              ))}
            </select>
          </div>

          {/* Фильтр субсидируемых маршрутов ПП РФ №1242 */}
          <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg border border-slate-200">
            <button
              type="button"
              onClick={() => setSubsidyFilter('all')}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
                subsidyFilter === 'all'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Все рейсы
            </button>
            <button
              type="button"
              onClick={() => setSubsidyFilter('subsidized')}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
                subsidyFilter === 'subsidized'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Субсидия ПП №1242
            </button>
          </div>
        </div>
      </div>

      {/* Сетка: Карта слева (7 колонок) + Карточка пруфа выбранного маршрута справа (5 колонок) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        {/* SVG Карта маршрутной сети Red Wings */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col justify-between text-white">
          <div className="flex items-center justify-between gap-4 mb-3">
            <div>
              <span className="text-xs font-mono text-slate-400">
                ГЕОГРАФИЯ ПОЛЕТОВ SJ-100 · ДАЛЬНОСТЬ ДО 2 500 КМ
              </span>
              <h3 className="text-base font-semibold text-white mt-0.5">
                {mapMode === 'p2p'
                  ? 'Топология Point-to-Point: Прямые связки между городами Топ-3 ПФО и Урала'
                  : `Веерная топология: Концентрация стыковочных волн через хаб ${hubCity?.name}`}
              </h3>
            </div>
            <div className="text-right font-mono text-xs text-slate-300 shrink-0">
              <span>Рейсов в сети: {displayedRoutes.length}</span>
            </div>
          </div>

          {/* Интерактивный SVG граф */}
          <div className="relative w-full overflow-hidden rounded-lg bg-slate-950/90 border border-slate-800">
            <svg
              viewBox="155 195 475 245"
              className="w-full h-[340px] select-none"
              role="img"
              aria-label="Интерактивная карта маршрутной сети Red Wings по регионам России"
            >
              {/* Координатная сетка меридианов и параллелей */}
              <g stroke="#1e293b" strokeWidth="1" strokeDasharray="3 3">
                <line x1="160" y1="240" x2="640" y2="240" />
                <line x1="160" y1="300" x2="640" y2="300" />
                <line x1="160" y1="360" x2="640" y2="360" />
                <line x1="160" y1="420" x2="640" y2="420" />
                <line x1="240" y1="195" x2="240" y2="465" />
                <line x1="340" y1="195" x2="340" y2="465" />
                <line x1="440" y1="195" x2="440" y2="465" />
                <line x1="540" y1="195" x2="540" y2="465" />
              </g>

              {/* Контур европейской части, Поволжья, Урала и Западной Сибири */}
              <path
                d="M165,245 L220,210 L330,205 L460,215 L620,235 L630,360 L520,400 L360,410 L230,455 L175,410 Z"
                fill="#0f172a"
                stroke="#334155"
                strokeWidth="1.5"
              />

              {/* Москва (ориентир перегруженного узла, который мы обходим) */}
              <g transform="translate(195, 270)">
                <circle r="4" fill="#475569" />
                <text x="-8" y="-8" fill="#64748b" fontSize="9" fontFamily="JetBrains Mono">
                  MOW (МСК)
                </text>
              </g>

              {/* Линии маршрутов */}
              {displayedRoutes.map((route) => {
                const orig = cityByIata.get(route.originIata);
                const dest = cityByIata.get(route.destIata);
                if (!orig || !dest) return null;

                const isSelected = activeRoute?.id === route.id;
                const midX = (orig.mapX + dest.mapX) / 2;
                const midY = (orig.mapY + dest.mapY) / 2 - 18;

                return (
                  <g
                    key={route.id}
                    onClick={() => setSelectedRouteId(route.id)}
                    className="cursor-pointer"
                  >
                    <path
                      d={`M ${orig.mapX} ${orig.mapY} Q ${midX} ${midY} ${dest.mapX} ${dest.mapY}`}
                      fill="none"
                      stroke={
                        isSelected
                          ? '#f43f5e'
                          : mapMode === 'p2p'
                          ? '#38bdf8'
                          : '#fb7185'
                      }
                      strokeWidth={isSelected ? '3' : '1.75'}
                      strokeOpacity={isSelected ? '1' : '0.65'}
                    />
                  </g>
                );
              })}

              {/* Узлы 12 городов-кандидатов */}
              {scoredCities.map((city) => {
                const isHub = city.iata === selectedHubIata && mapMode === 'hub';
                const isTop3 = city.isTop3;

                return (
                  <g
                    key={city.iata}
                    transform={`translate(${city.mapX}, ${city.mapY})`}
                    onClick={() => {
                      if (city.isTop3) onSelectHub(city.iata);
                    }}
                    className="cursor-pointer"
                  >
                    {isHub && (
                      <circle
                        r="12"
                        fill="none"
                        stroke="#f43f5e"
                        strokeWidth="1.5"
                        strokeDasharray="2 2"
                      />
                    )}
                    <circle
                      r={isHub ? '7' : isTop3 ? '6' : '4.5'}
                      fill={isHub ? '#f43f5e' : isTop3 ? '#38bdf8' : '#94a3b8'}
                      stroke="#0f172a"
                      strokeWidth="1.5"
                    />
                    <text
                      x="8"
                      y="3"
                      fill={isTop3 ? '#f8fafc' : '#cbd5e1'}
                      fontSize={isTop3 ? '10.5' : '9'}
                      fontWeight={isTop3 ? '700' : '500'}
                      fontFamily="JetBrains Mono"
                    >
                      {city.iata}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Легенда карты */}
          <div className="flex flex-wrap items-center justify-between gap-4 pt-3 text-xs text-slate-300">
            <div className="flex items-center gap-4">
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-sky-400 inline-block" />
                Города Топ-3 скоринга
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" />
                Выбранный маршрут / Базовый хаб
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-slate-400 inline-block" />
                Кандидаты лонглиста (#4–#12)
              </span>
            </div>
            <span className="font-mono text-slate-400">
              Кликните на линию или строку таблицы для проверки пруфа
            </span>
          </div>
        </div>

        {/* Пруф-панель выбранного маршрута А -> Б */}
        <div className="lg:col-span-5 bg-white border border-slate-200 rounded-xl p-5 flex flex-col justify-between">
          {activeRoute ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <div>
                  <div className="text-xs font-mono text-slate-500">
                    ДОКАЗАТЕЛЬНАЯ БАЗА МАРШРУТА · {activeRoute.code}
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 mt-0.5 flex items-center gap-2">
                    <span>
                      {activeRoute.originCity} ({activeRoute.originIata})
                    </span>
                    <ArrowRight className="w-4 h-4 text-rose-600 shrink-0" />
                    <span>
                      {activeRoute.destCity} ({activeRoute.destIata})
                    </span>
                  </h3>
                </div>
                <div className="text-right font-mono">
                  <div className="text-xs text-slate-500">Старт запуска</div>
                  <div className="text-sm font-bold text-slate-900">{activeRoute.launchQuarter}</div>
                </div>
              </div>

              {/* Ключевые параметры маршрута */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <div className="text-xs text-slate-500">Дальность и время в пути</div>
                  <div className="text-base font-bold font-mono text-slate-900 mt-0.5 tabular-nums">
                    {activeRoute.distanceKm} км · {activeRoute.flightTimeMin} мин
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <div className="text-xs text-slate-500">Ожидаемый поток (год)</div>
                  <div className="text-base font-bold font-mono text-rose-600 mt-0.5 tabular-nums">
                    {activeRoute.estimatedAnnualPax.toLocaleString('ru-RU')} пасс.
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <div className="text-xs text-slate-500">Тариф Red Wings vs Рынок</div>
                  <div className="text-base font-bold font-mono text-slate-900 mt-0.5 tabular-nums">
                    {activeRoute.proposedFareRub.toLocaleString('ru-RU')} ₽{' '}
                    <span className="text-xs font-normal text-slate-500 line-through">
                      {activeRoute.competitorFareRub.toLocaleString('ru-RU')} ₽
                    </span>
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <div className="text-xs text-slate-500">Частота конкурентов (прямые)</div>
                  <div className="text-base font-bold font-mono text-slate-900 mt-0.5 tabular-nums">
                    {activeRoute.directCompetitorFlightsWeekly} рейсов/нед.
                  </div>
                </div>
              </div>

              {/* Доказательство источника пассажиров */}
              <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
                  <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Обоснование источника пассажиров (Data Proof)</span>
                </div>
                <p className="text-xs text-slate-700 leading-relaxed">
                  {activeRoute.proofSource}
                </p>
                <div className="text-xs text-slate-500 pt-1 border-t border-slate-200 flex items-center justify-between">
                  <span>Текущие перевозчики: {activeRoute.competitorCarriers}</span>
                  <span className="font-mono font-medium text-slate-800">
                    {activeRoute.subsidyEligible ? 'Субсидия ПП №1242: Да' : 'Коммерческий рейс'}
                  </span>
                </div>
              </div>
            </div>
          ) : null}

          {/* Быстрый выбор маршрута кнопками */}
          <div className="pt-4 border-t border-slate-200 mt-4">
            <div className="text-xs font-medium text-slate-500 mb-2">
              Выберите маршрут сети для детальной верификации:
            </div>
            <div className="flex flex-wrap gap-1.5">
              {displayedRoutes.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => setSelectedRouteId(r.id)}
                  className={`px-2.5 py-1 text-xs font-mono rounded-md border transition-colors whitespace-nowrap shrink-0 ${
                    activeRoute?.id === r.id
                      ? 'bg-slate-900 text-white border-slate-900 font-semibold'
                      : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  {r.originIata}→{r.destIata}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Таблица всех маршрутов + Дорожная карта запуска до 2028 года */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">
              Ведомость маршрутной сети и дорожная карта запуска до 2028 года
            </h3>
            <p className="text-xs text-slate-600 mt-0.5">
              Поэтапный ввод маршрутов синхронизирован с графиком поставок импортозамещенных SJ-100 (сдвиг на 2П 2027 г.)
            </p>
          </div>
          <div className="text-xs font-mono text-slate-600">
            Частота модели: {weeklyFreqPerRoute} парных рейсов/нед. · SLF: {loadFactorPct}%
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs font-semibold text-slate-600">
                <th className="py-2.5 px-4">Рейс</th>
                <th className="py-2.5 px-4">Направление (А → Б)</th>
                <th className="py-2.5 px-4 text-right">Плечо, км</th>
                <th className="py-2.5 px-4 text-right">Прямые конк.</th>
                <th className="py-2.5 px-4 text-right">Тариф RW, ₽</th>
                <th className="py-2.5 px-4 text-right">Пассажиропоток/год</th>
                <th className="py-2.5 px-4">Госсубсидия</th>
                <th className="py-2.5 px-4">Этап запуска</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-xs">
              {displayedRoutes.map((route) => {
                const isSelected = activeRoute?.id === route.id;
                return (
                  <tr
                    key={route.id}
                    onClick={() => setSelectedRouteId(route.id)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-rose-50/70' : 'hover:bg-slate-50'
                    }`}
                  >
                    <td className="py-2.5 px-4 font-mono font-semibold text-slate-900">
                      {route.code}
                    </td>
                    <td className="py-2.5 px-4 font-medium text-slate-900">
                      {route.originCity} ({route.originIata}) → {route.destCity} ({route.destIata})
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono tabular-nums text-slate-700">
                      {route.distanceKm}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono tabular-nums text-slate-700">
                      {route.directCompetitorFlightsWeekly} р/нед
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono tabular-nums font-semibold text-slate-900">
                      {route.proposedFareRub.toLocaleString('ru-RU')} ₽
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono tabular-nums font-semibold text-rose-600">
                      {route.estimatedAnnualPax.toLocaleString('ru-RU')}
                    </td>
                    <td className="py-2.5 px-4 text-slate-700">
                      {route.subsidyEligible ? 'ПП РФ №1242 (Да)' : 'Коммерческий'}
                    </td>
                    <td className="py-2.5 px-4 font-mono text-slate-800">
                      {route.launchQuarter}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
