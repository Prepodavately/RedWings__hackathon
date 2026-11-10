import React, { useState } from 'react';
import { ScoredCity, ScoringWeights } from '../utils/aviationModel';
import { Sliders, RotateCcw, Search } from 'lucide-react';

interface CityScoringSectionProps {
  scoredCities: ScoredCity[];
  weights: ScoringWeights;
  onChangeWeights: (newWeights: ScoringWeights) => void;
  selectedHubIata: string;
  onSelectHub: (iata: string) => void;
}

export const CityScoringSection: React.FC<CityScoringSectionProps> = ({
  scoredCities,
  weights,
  onChangeWeights,
  selectedHubIata,
  onSelectHub,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [regionFilter, setRegionFilter] = useState<string>('all');

  const sumWeights =
    weights.wPopulation +
    weights.wHubDistance +
    weights.wCompetitorGap +
    weights.wTourismDemand;

  const filteredCities = scoredCities.filter((city) => {
    const matchesSearch =
      city.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      city.iata.toLowerCase().includes(searchQuery.toLowerCase()) ||
      city.currentMainCompetitor.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesRegion = regionFilter === 'all' || city.region === regionFilter;
    return matchesSearch && matchesRegion;
  });

  const regions = Array.from(new Set(scoredCities.map((c) => c.region)));
  const top3 = scoredCities.slice(0, 3);

  return (
    <div className="space-y-6">
      {/* Блок настройки весов математической формулы скоринга */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              Автоматизированный скоринг 12 городов-кандидатов (Слой аналитики)
            </h2>
            <p className="text-sm text-slate-600 mt-0.5">
              Многокритериальная функция полезности с Min-Max нормализацией данных Росстата и Росавиации
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() =>
                onChangeWeights({
                  wPopulation: 30,
                  wHubDistance: 20,
                  wCompetitorGap: 30,
                  wTourismDemand: 20,
                })
              }
              className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors whitespace-nowrap shrink-0"
            >
              Сбалансированный (Дефолт)
            </button>
            <button
              type="button"
              onClick={() =>
                onChangeWeights({
                  wPopulation: 20,
                  wHubDistance: 25,
                  wCompetitorGap: 45,
                  wTourismDemand: 10,
                })
              }
              className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors whitespace-nowrap shrink-0"
            >
              Фокус: Свободная ниша без конкурентов
            </button>
            <button
              type="button"
              onClick={() =>
                onChangeWeights({
                  wPopulation: 45,
                  wHubDistance: 15,
                  wCompetitorGap: 15,
                  wTourismDemand: 25,
                })
              }
              className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors whitespace-nowrap shrink-0"
            >
              Фокус: Крупнейшие агломерации
            </button>
          </div>
        </div>

        {/* 4 ползунка весов */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-800 mb-2">
              <label htmlFor="weight-pop">1. Население агломерации</label>
              <span className="font-mono text-rose-600 tabular-nums">
                {sumWeights > 0 ? Math.round((weights.wPopulation / sumWeights) * 100) : 25}%
              </span>
            </div>
            <input
              id="weight-pop"
              type="range"
              min={5}
              max={70}
              step={5}
              value={weights.wPopulation}
              onChange={(e) =>
                onChangeWeights({ ...weights, wPopulation: Number(e.target.value) })
              }
              className="w-full accent-rose-600 cursor-pointer"
            />
            <div className="text-xs text-slate-500 mt-1">
              Данные Росстата (численность в радиусе 100 км от аэропорта)
            </div>
          </div>

          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-800 mb-2">
              <label htmlFor="weight-dist">2. Удаленность от МСК</label>
              <span className="font-mono text-rose-600 tabular-nums">
                {sumWeights > 0 ? Math.round((weights.wHubDistance / sumWeights) * 100) : 25}%
              </span>
            </div>
            <input
              id="weight-dist"
              type="range"
              min={5}
              max={70}
              step={5}
              value={weights.wHubDistance}
              onChange={(e) =>
                onChangeWeights({ ...weights, wHubDistance: Number(e.target.value) })
              }
              className="w-full accent-rose-600 cursor-pointer"
            />
            <div className="text-xs text-slate-500 mt-1">
              Оптимум плеча SJ-100 (750–1 550 км, где поезд идет &gt;14 ч)
            </div>
          </div>

          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-800 mb-2">
              <label htmlFor="weight-comp">3. Слабость баз конкурентов</label>
              <span className="font-mono text-rose-600 tabular-nums">
                {sumWeights > 0 ? Math.round((weights.wCompetitorGap / sumWeights) * 100) : 25}%
              </span>
            </div>
            <input
              id="weight-comp"
              type="range"
              min={5}
              max={70}
              step={5}
              value={weights.wCompetitorGap}
              onChange={(e) =>
                onChangeWeights({ ...weights, wCompetitorGap: Number(e.target.value) })
              }
              className="w-full accent-rose-600 cursor-pointer"
            />
            <div className="text-xs text-slate-500 mt-1">
              Отсутствие доминирующего базового перевозчика (&gt;50% слотов)
            </div>
          </div>

          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-800 mb-2">
              <label htmlFor="weight-demand">4. ПСП, Туризм и Субсидии</label>
              <span className="font-mono text-rose-600 tabular-nums">
                {sumWeights > 0 ? Math.round((weights.wTourismDemand / sumWeights) * 100) : 25}%
              </span>
            </div>
            <input
              id="weight-demand"
              type="range"
              min={5}
              max={70}
              step={5}
              value={weights.wTourismDemand}
              onChange={(e) =>
                onChangeWeights({ ...weights, wTourismDemand: Number(e.target.value) })
              }
              className="w-full accent-rose-600 cursor-pointer"
            />
            <div className="text-xs text-slate-500 mt-1">
              Средняя зарплата, деловая активность и лимиты ПП РФ №1242
            </div>
          </div>
        </div>

        {/* Витрина выбранного Топ-3 городов */}
        <div className="pt-2">
          <div className="text-xs font-semibold text-slate-500 mb-2.5">
            ИТОГОВЫЙ ТОП-3 ЛОКАЦИЙ ДЛЯ ЭКСПАНСИИ RED WINGS (КЛИКНИТЕ ДЛЯ ВЫБОРА БАЗОВОГО ХАБА):
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {top3.map((city) => {
              const isSelectedHub = city.iata === selectedHubIata;
              return (
                <button
                  key={city.iata}
                  type="button"
                  onClick={() => onSelectHub(city.iata)}
                  className={`text-left p-4 rounded-xl border transition-colors ${
                    isSelectedHub
                      ? 'bg-slate-900 text-white border-slate-900'
                      : 'bg-slate-50 text-slate-900 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-xs font-mono font-semibold ${
                        isSelectedHub ? 'text-rose-400' : 'text-rose-600'
                      }`}
                    >
                      РАНЖИРОВАНИЕ #{city.rank} · {city.iata}
                    </span>
                    <span className="text-lg font-mono font-bold tabular-nums">
                      {city.totalScore} / 100
                    </span>
                  </div>
                  <div className="text-base font-bold mt-1">{city.name}</div>
                  <div
                    className={`text-xs mt-1.5 ${
                      isSelectedHub ? 'text-slate-300' : 'text-slate-600'
                    }`}
                  >
                    Агломерация: {city.agglomerationPopMln} млн · Аэропорт: {city.airportPax2025Mln} млн пасс. · Доля лидера: {city.competitorSharePct}%
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Полная таблица ранжирования 12 городов */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">
              Матрица скоринга лонглиста городов-кандидатов ({filteredCities.length} из 12)
            </h3>
            <p className="text-xs text-slate-600 mt-0.5">
              Формула: Score = w₁·Norm(Pop) + w₂·Norm(Dist) + w₃·Norm(CompGap) + w₄·Norm(Demand)
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Поиск города или IATA..."
                aria-label="Поиск города или IATA"
                className="pl-8 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-300 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-rose-500"
              />
            </div>

            <select
              value={regionFilter}
              onChange={(e) => setRegionFilter(e.target.value)}
              aria-label="Фильтр по федеральному округу"
              className="text-xs bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-900 focus:outline-none focus:ring-2 focus:ring-rose-500"
            >
              <option value="all">Все федеральные округа</option>
              {regions.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs font-semibold text-slate-600">
                <th className="py-2.5 px-4">Ранг</th>
                <th className="py-2.5 px-4">Город (IATA)</th>
                <th className="py-2.5 px-4">Округ</th>
                <th className="py-2.5 px-4 text-right">Агломерация, млн</th>
                <th className="py-2.5 px-4 text-right">Пасс. 2025, млн</th>
                <th className="py-2.5 px-4 text-right">От МСК, км</th>
                <th className="py-2.5 px-4">Главный конкурент (доля)</th>
                <th className="py-2.5 px-4 text-right">Балл ниши</th>
                <th className="py-2.5 px-4 text-right">Итоговый балл</th>
                <th className="py-2.5 px-4">Статус</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-xs">
              {filteredCities.map((city) => (
                <tr
                  key={city.iata}
                  onClick={() => onSelectHub(city.iata)}
                  className={`cursor-pointer transition-colors ${
                    city.isTop3 ? 'bg-rose-50/40 hover:bg-rose-50/80' : 'hover:bg-slate-50'
                  }`}
                >
                  <td className="py-2.5 px-4 font-mono font-bold text-slate-900 tabular-nums">
                    #{city.rank}
                  </td>
                  <td className="py-2.5 px-4 font-semibold text-slate-900">
                    {city.name}{' '}
                    <span className="font-mono text-slate-500 font-normal">({city.iata})</span>
                  </td>
                  <td className="py-2.5 px-4 text-slate-600">{city.region}</td>
                  <td className="py-2.5 px-4 text-right font-mono tabular-nums text-slate-800">
                    {city.agglomerationPopMln.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono tabular-nums text-slate-800">
                    {city.airportPax2025Mln.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono tabular-nums text-slate-700">
                    {city.distanceToNearestHubKm}
                  </td>
                  <td className="py-2.5 px-4 text-slate-700">
                    {city.currentMainCompetitor} ({city.competitorSharePct}%)
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono tabular-nums text-slate-800">
                    {city.normCompScore}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono tabular-nums font-bold text-slate-900">
                    {city.totalScore.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 font-semibold text-slate-800">
                    {city.isTop3 ? 'ТОП-3 Рекомендован' : 'Резерв'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
