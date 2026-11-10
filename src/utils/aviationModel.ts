export interface CandidateCity {
  id: string;
  iata: string;
  name: string;
  region: string;
  agglomerationPopMln: number; // Росстат, млн чел.
  airportPax2025Mln: number; // Росавиация 2025, млн пасс.
  distanceToNearestHubKm: number; // Удаленность от МСК/СПб/SVX, км
  competitorGapScore: number; // 0-100: насколько слабо представлен базовый конкурент
  tourismBusinessScore: number; // 0-100: деловой и туристический потенциал + ПСП
  subsidyPotentialScore: number; // 0-100: потенциал софинансирования по ПП РФ №1242
  currentMainCompetitor: string;
  competitorSharePct: number;
  mapX: number; // SVG coordinate X (0..1000)
  mapY: number; // SVG coordinate Y (0..520)
}

export interface ScoringWeights {
  wPopulation: number; // Вес населения агломерации
  wHubDistance: number; // Вес удаленность от существующих хабов
  wCompetitorGap: number; // Вес свободной ниши (слабость конкурентов)
  wTourismDemand: number; // Вес платежеспособного спроса и туризма
}

export interface ScoredCity extends CandidateCity {
  normPopScore: number;
  normDistScore: number;
  normCompScore: number;
  normDemandScore: number;
  totalScore: number;
  rank: number;
  isTop3: boolean;
}

export type ScenarioMode = 'base' | 'conservative';
export type HypothesisType = 'hub' | 'p2p';

export interface SimulationParams {
  loadFactorPct: number; // % коммерческой загрузки кресел (SLF), напр. 84
  avgFareRub: number; // Средний тариф в одну сторону, руб., напр. 8400
  weeklyFreqPerRoute: number; // Частота парных рейсов в неделю на 1 маршрут, напр. 5
  aircraftSeats: number; // Вместимость борта (SJ-100 = 100 кресел)
  activeRouteCount: number; // Количество маршрутов в сети (8..12)
  scenario: ScenarioMode; // Базовый или Осторожный (пессимистичный)
  selectedHubIata: string; // Выбранный хаб из Топ-3 для Гипотезы А
}

export interface HypothesisMetrics {
  type: HypothesisType;
  title: string;
  subtitle: string;
  annualFlights: number;
  annualSeats: number;
  effectiveLoadFactorPct: number;
  annualPassengers: number;
  avgEffectiveFareRub: number;
  annualRevenueMlnRub: number;
  operatingCostMlnRub: number;
  ebitdarMlnRub: number;
  ebitdarMarginPct: number;
  marketShareDeltaPct: number; // Прирост доли рынка РФ (% от 108.9 млн)
  newTotalMarketSharePct: number; // Новая доля Red Wings
  requiredAircraftSj100: number;
  breakEvenLoadFactorPct: number;
  riskIndex: number; // 0-100 (ниже = безопаснее)
}

export interface ComparisonResult {
  hub: HypothesisMetrics;
  p2p: HypothesisMetrics;
  winner: HypothesisType;
  winnerTitle: string;
  paxDelta: number;
  revenueDeltaMlnRub: number;
  marketShareDiffPct: number;
  rationale: string;
}

export interface RouteSpecification {
  id: string;
  code: string;
  originIata: string;
  originCity: string;
  destIata: string;
  destCity: string;
  hypothesis: HypothesisType;
  distanceKm: number;
  flightTimeMin: number;
  recommendedWeeklyFreq: number;
  competitorFareRub: number;
  proposedFareRub: number;
  competitorCarriers: string;
  directCompetitorFlightsWeekly: number;
  proofSource: string;
  estimatedAnnualPax: number;
  subsidyEligible: boolean;
  launchQuarter: string;
}

export const TOTAL_RF_MARKET_PAX_2025 = 108_900_000;
export const RED_WINGS_BASE_PAX_2025 = 4_465_000; // ~4.10% доли рынка

export const CANDIDATE_CITIES: CandidateCity[] = [
  {
    id: 'kuf',
    iata: 'KUF',
    name: 'Самара (Курумоч)',
    region: 'Приволжский ФО',
    agglomerationPopMln: 2.74,
    airportPax2025Mln: 3.58,
    distanceToNearestHubKm: 855,
    competitorGapScore: 86,
    tourismBusinessScore: 84,
    subsidyPotentialScore: 82,
    currentMainCompetitor: 'Аэрофлот / Smartavia',
    competitorSharePct: 31,
    mapX: 305,
    mapY: 325,
  },
  {
    id: 'goj',
    iata: 'GOJ',
    name: 'Нижний Новгород (Стригино)',
    region: 'Приволжский ФО',
    agglomerationPopMln: 2.08,
    airportPax2025Mln: 1.48,
    distanceToNearestHubKm: 410,
    competitorGapScore: 89,
    tourismBusinessScore: 88,
    subsidyPotentialScore: 79,
    currentMainCompetitor: 'Аэрофлот (Россия)',
    competitorSharePct: 34,
    mapX: 255,
    mapY: 275,
  },
  {
    id: 'ufa',
    iata: 'UFA',
    name: 'Уфа',
    region: 'Приволжский ФО',
    agglomerationPopMln: 1.68,
    airportPax2025Mln: 4.72,
    distanceToNearestHubKm: 1165,
    competitorGapScore: 78,
    tourismBusinessScore: 83,
    subsidyPotentialScore: 85,
    currentMainCompetitor: 'Utair / Азимут',
    competitorSharePct: 28,
    mapX: 365,
    mapY: 320,
  },
  {
    id: 'kzn',
    iata: 'KZN',
    name: 'Казань',
    region: 'Приволжский ФО',
    agglomerationPopMln: 1.79,
    airportPax2025Mln: 5.36,
    distanceToNearestHubKm: 720,
    competitorGapScore: 68,
    tourismBusinessScore: 94,
    subsidyPotentialScore: 76,
    currentMainCompetitor: 'Северный Ветер / ЮВТ Аэро',
    competitorSharePct: 44,
    mapX: 295,
    mapY: 285,
  },
  {
    id: 'mrv',
    iata: 'MRV',
    name: 'Минеральные Воды',
    region: 'Северо-Кавказский ФО',
    agglomerationPopMln: 1.12,
    airportPax2025Mln: 4.86,
    distanceToNearestHubKm: 1350,
    competitorGapScore: 64,
    tourismBusinessScore: 95,
    subsidyPotentialScore: 70,
    currentMainCompetitor: 'Азимут / Аэрофлот',
    competitorSharePct: 48,
    mapX: 215,
    mapY: 408,
  },
  {
    id: 'pee',
    iata: 'PEE',
    name: 'Пермь (Большое Савино)',
    region: 'Приволжский ФО',
    agglomerationPopMln: 1.26,
    airportPax2025Mln: 1.98,
    distanceToNearestHubKm: 1155,
    competitorGapScore: 84,
    tourismBusinessScore: 77,
    subsidyPotentialScore: 88,
    currentMainCompetitor: 'Победа / Сибирь (S7)',
    competitorSharePct: 36,
    mapX: 390,
    mapY: 265,
  },
  {
    id: 'svx',
    iata: 'SVX',
    name: 'Екатеринбург (Кольцово)',
    region: 'Уральский ФО',
    agglomerationPopMln: 2.24,
    airportPax2025Mln: 7.95,
    distanceToNearestHubKm: 1420,
    competitorGapScore: 54,
    tourismBusinessScore: 91,
    subsidyPotentialScore: 74,
    currentMainCompetitor: 'Уральские Авиалинии',
    competitorSharePct: 52,
    mapX: 435,
    mapY: 285,
  },
  {
    id: 'cek',
    iata: 'CEK',
    name: 'Челябинск (Баландино)',
    region: 'Уральский ФО',
    agglomerationPopMln: 1.56,
    airportPax2025Mln: 2.16,
    distanceToNearestHubKm: 1495,
    competitorGapScore: 82,
    tourismBusinessScore: 76,
    subsidyPotentialScore: 81,
    currentMainCompetitor: 'Аэрофлот / Smartavia',
    competitorSharePct: 39,
    mapX: 440,
    mapY: 325,
  },
  {
    id: 'tjm',
    iata: 'TJM',
    name: 'Тюмень (Рощино)',
    region: 'Уральский ФО',
    agglomerationPopMln: 1.05,
    airportPax2025Mln: 2.68,
    distanceToNearestHubKm: 1715,
    competitorGapScore: 58,
    tourismBusinessScore: 86,
    subsidyPotentialScore: 84,
    currentMainCompetitor: 'Utair (базовый хаб)',
    competitorSharePct: 56,
    mapX: 495,
    mapY: 280,
  },
  {
    id: 'vog',
    iata: 'VOG',
    name: 'Волгоград (Гумрак)',
    region: 'Южный ФО',
    agglomerationPopMln: 1.38,
    airportPax2025Mln: 1.62,
    distanceToNearestHubKm: 915,
    competitorGapScore: 83,
    tourismBusinessScore: 78,
    subsidyPotentialScore: 80,
    currentMainCompetitor: 'Победа / Аэрофлот',
    competitorSharePct: 41,
    mapX: 245,
    mapY: 375,
  },
  {
    id: 'gsv',
    iata: 'GSV',
    name: 'Саратов (Гагарин)',
    region: 'Приволжский ФО',
    agglomerationPopMln: 1.22,
    airportPax2025Mln: 1.15,
    distanceToNearestHubKm: 730,
    competitorGapScore: 88,
    tourismBusinessScore: 73,
    subsidyPotentialScore: 83,
    currentMainCompetitor: 'Победа / Икар',
    competitorSharePct: 37,
    mapX: 265,
    mapY: 345,
  },
  {
    id: 'oms',
    iata: 'OMS',
    name: 'Омск (Центральный)',
    region: 'Сибирский ФО',
    agglomerationPopMln: 1.34,
    airportPax2025Mln: 1.74,
    distanceToNearestHubKm: 2235,
    competitorGapScore: 79,
    tourismBusinessScore: 72,
    subsidyPotentialScore: 86,
    currentMainCompetitor: 'Сибирь (S7) / Северный Ветер',
    competitorSharePct: 43,
    mapX: 575,
    mapY: 315,
  },
];

/**
 * Min-Max нормализация значения в шкалу [0..100]
 */
function normalizeValue(val: number, min: number, max: number): number {
  if (max <= min) return 50;
  const clamped = Math.max(min, Math.min(max, val));
  return ((clamped - min) / (max - min)) * 100;
}

/**
 * Автоматизированный скоринг 12 городов-кандидатов с настраиваемыми весами
 */
export function scoreCandidateCities(
  cities: CandidateCity[],
  weights: ScoringWeights
): ScoredCity[] {
  const sumW =
    weights.wPopulation +
    weights.wHubDistance +
    weights.wCompetitorGap +
    weights.wTourismDemand;

  const wPop = sumW > 0 ? weights.wPopulation / sumW : 0.25;
  const wDist = sumW > 0 ? weights.wHubDistance / sumW : 0.25;
  const wComp = sumW > 0 ? weights.wCompetitorGap / sumW : 0.25;
  const wDem = sumW > 0 ? weights.wTourismDemand / sumW : 0.25;

  const pops = cities.map((c) => c.agglomerationPopMln);
  const minPop = Math.min(...pops);
  const maxPop = Math.max(...pops);

  // Для регионального самолета SJ-100 (дальность 2000-3000 км) оптимум плеча от МСК — 700..1500 км
  const scored = cities.map((city) => {
    const normPopScore = Number(normalizeValue(city.agglomerationPopMln, minPop, maxPop).toFixed(1));
    // Оптимум удаленности от перегруженного московского авиаузла: 750–1550 км дает высший балл
    const distDiff = Math.abs(city.distanceToNearestHubKm - 1150);
    const normDistScore = Number(Math.max(35, 100 - (distDiff / 1200) * 65).toFixed(1));
    const normCompScore = city.competitorGapScore;
    const normDemandScore = Number(
      (city.tourismBusinessScore * 0.65 + city.subsidyPotentialScore * 0.35).toFixed(1)
    );

    const rawTotal =
      normPopScore * wPop +
      normDistScore * wDist +
      normCompScore * wComp +
      normDemandScore * wDem;

    return {
      ...city,
      normPopScore,
      normDistScore,
      normCompScore,
      normDemandScore,
      totalScore: Number(rawTotal.toFixed(2)),
      rank: 0,
      isTop3: false,
    };
  });

  scored.sort((a, b) => b.totalScore - a.totalScore);

  return scored.map((city, idx) => ({
    ...city,
    rank: idx + 1,
    isTop3: idx < 3,
  }));
}

/**
 * Финансово-математическая модель расчета двух бизнес-гипотез:
 * Гипотеза А (Новый региональный хаб) vs Гипотеза Б (Прямые межрегиональные рейсы Point-to-Point)
 */
export function calculateHypothesesComparison(
  params: SimulationParams
): ComparisonResult {
  const weeksPerYear = 52;
  const safeRoutes = Math.max(8, Math.min(12, params.activeRouteCount));
  const safeFreq = Math.max(1, Math.min(21, params.weeklyFreqPerRoute));
  const safeSeats = Math.max(75, Math.min(220, params.aircraftSeats));
  const safeLoadPct = Math.max(50, Math.min(98, params.loadFactorPct));
  const safeFare = Math.max(3500, Math.min(25000, params.avgFareRub));

  // Сценарные коэффициенты (Базовый vs Осторожный/Пессимистичный со сдвигом SJ-100 на 2П 2027)
  const scenarioDemandFactor = params.scenario === 'base' ? 1.0 : 0.87;
  const scenarioCostInflation = params.scenario === 'base' ? 1.0 : 1.08;
  const subsidyPerFlightRub = params.scenario === 'base' ? 145_000 : 95_000;

  // --- ГИПОТЕЗА А: НОВЫЙ РЕГИОНАЛЬНЫЙ ХАБ (Веерное расписание из базового аэропорта) ---
  // Хаб дает синергию трансферного потока при высокой частоте (>= 5 рейсов/нед),
  // но требует дисконта на сквозных тарифах (-7%) и несет постоянные расходы базы.
  const hubAnnualFlights = safeRoutes * safeFreq * 2 * weeksPerYear;
  const hubAnnualSeats = hubAnnualFlights * safeSeats;
  const hubSynergyBoost = safeFreq >= 6 ? 3.2 : safeFreq >= 4 ? 1.2 : -2.5;
  const hubEffectiveLoadPct = Number(
    Math.min(95, Math.max(52, (safeLoadPct + hubSynergyBoost) * scenarioDemandFactor)).toFixed(1)
  );
  const hubAnnualPassengers = Math.round(hubAnnualSeats * (hubEffectiveLoadPct / 100));
  const hubEffectiveFareRub = Math.round(safeFare * 0.935); // Трансферный дисконт 6.5%
  const hubTicketRevenueMln = (hubAnnualPassengers * hubEffectiveFareRub) / 1_000_000;
  const hubSubsidyMln = (hubAnnualFlights * 0.45 * subsidyPerFlightRub) / 1_000_000;
  const hubAnnualRevenueMlnRub = Number((hubTicketRevenueMln + hubSubsidyMln).toFixed(1));

  // Расходы Хаба: фиксированные косты линейной базы ТОиР + аэропортовое обслуживание волн
  const hubCostPerFlightRub = 645_000 * scenarioCostInflation * (safeSeats / 100);
  const hubFixedStationMln = params.scenario === 'base' ? 310 : 365;
  const hubOperatingCostMlnRub = Number(
    ((hubAnnualFlights * hubCostPerFlightRub) / 1_000_000 + hubFixedStationMln).toFixed(1)
  );
  const hubEbitdarMlnRub = Number((hubAnnualRevenueMlnRub - hubOperatingCostMlnRub).toFixed(1));
  const hubEbitdarMarginPct = Number(
    ((hubEbitdarMlnRub / Math.max(1, hubAnnualRevenueMlnRub)) * 100).toFixed(1)
  );
  const hubMarketShareDeltaPct = Number(
    ((hubAnnualPassengers / TOTAL_RF_MARKET_PAX_2025) * 100).toFixed(3)
  );
  const hubNewTotalSharePct = Number(
    (((RED_WINGS_BASE_PAX_2025 + hubAnnualPassengers) / TOTAL_RF_MARKET_PAX_2025) * 100).toFixed(2)
  );
  const hubRequiredAircraft = Math.max(3, Math.ceil((safeRoutes * safeFreq * 5.2) / 18));
  const hubBreakEvenLoadPct = Number(
    Math.min(
      96,
      Math.max(
        55,
        ((hubOperatingCostMlnRub - hubSubsidyMln) * 1_000_000) /
          Math.max(1, hubAnnualSeats * hubEffectiveFareRub) *
          100
      )
    ).toFixed(1)
  );

  // --- ГИПОТЕЗА Б: ПРЯМЫЕ МЕЖРЕГИОНАЛЬНЫЕ РЕЙСЫ (Point-to-Point в обход Москвы) ---
  // Прямые рейсы собирают премию за беспосадочность (+6.5% к среднему тарифу),
  // получают повышенную долю субсидий по ПП РФ №1242 (до 65% маршрутов) и не требуют затрат на новый хаб.
  const p2pAnnualFlights = safeRoutes * safeFreq * 2 * weeksPerYear;
  const p2pAnnualSeats = p2pAnnualFlights * safeSeats;
  // На умеренных частотах (2-5 раз в неделю) прямые рейсы заполняются лучше хабовых
  const p2pLoadAdjustment = safeFreq <= 5 ? 2.4 : -0.8;
  const p2pEffectiveLoadPct = Number(
    Math.min(95, Math.max(54, (safeLoadPct + p2pLoadAdjustment) * scenarioDemandFactor)).toFixed(1)
  );
  const p2pAnnualPassengers = Math.round(p2pAnnualSeats * (p2pEffectiveLoadPct / 100));
  const p2pEffectiveFareRub = Math.round(safeFare * 1.055); // Премия за прямой перелет без пересадки в МСК
  const p2pTicketRevenueMln = (p2pAnnualPassengers * p2pEffectiveFareRub) / 1_000_000;
  const p2pSubsidyMln = (p2pAnnualFlights * 0.65 * subsidyPerFlightRub) / 1_000_000;
  const p2pAnnualRevenueMlnRub = Number((p2pTicketRevenueMln + p2pSubsidyMln).toFixed(1));

  const p2pCostPerFlightRub = 635_000 * scenarioCostInflation * (safeSeats / 100);
  const p2pFixedStationMln = 115; // Только оборотные слоты в существующих аэропортах присутствия
  const p2pOperatingCostMlnRub = Number(
    ((p2pAnnualFlights * p2pCostPerFlightRub) / 1_000_000 + p2pFixedStationMln).toFixed(1)
  );
  const p2pEbitdarMlnRub = Number((p2pAnnualRevenueMlnRub - p2pOperatingCostMlnRub).toFixed(1));
  const p2pEbitdarMarginPct = Number(
    ((p2pEbitdarMlnRub / Math.max(1, p2pAnnualRevenueMlnRub)) * 100).toFixed(1)
  );
  const p2pMarketShareDeltaPct = Number(
    ((p2pAnnualPassengers / TOTAL_RF_MARKET_PAX_2025) * 100).toFixed(3)
  );
  const p2pNewTotalSharePct = Number(
    (((RED_WINGS_BASE_PAX_2025 + p2pAnnualPassengers) / TOTAL_RF_MARKET_PAX_2025) * 100).toFixed(2)
  );
  const p2pRequiredAircraft = Math.max(2, Math.ceil((safeRoutes * safeFreq * 4.6) / 18));
  const p2pBreakEvenLoadPct = Number(
    Math.min(
      96,
      Math.max(
        52,
        ((p2pOperatingCostMlnRub - p2pSubsidyMln) * 1_000_000) /
          Math.max(1, p2pAnnualSeats * p2pEffectiveFareRub) *
          100
      )
    ).toFixed(1)
  );

  const hubMetrics: HypothesisMetrics = {
    type: 'hub',
    title: `Гипотеза А: Региональный хаб (${params.selectedHubIata})`,
    subtitle: 'Веерная сеть со стыковочными волнами и базой ТОиР',
    annualFlights: hubAnnualFlights,
    annualSeats: hubAnnualSeats,
    effectiveLoadFactorPct: hubEffectiveLoadPct,
    annualPassengers: hubAnnualPassengers,
    avgEffectiveFareRub: hubEffectiveFareRub,
    annualRevenueMlnRub: hubAnnualRevenueMlnRub,
    operatingCostMlnRub: hubOperatingCostMlnRub,
    ebitdarMlnRub: hubEbitdarMlnRub,
    ebitdarMarginPct: hubEbitdarMarginPct,
    marketShareDeltaPct: hubMarketShareDeltaPct,
    newTotalMarketSharePct: hubNewTotalSharePct,
    requiredAircraftSj100: hubRequiredAircraft,
    breakEvenLoadFactorPct: hubBreakEvenLoadPct,
    riskIndex: params.scenario === 'conservative' ? 68 : 54,
  };

  const p2pMetrics: HypothesisMetrics = {
    type: 'p2p',
    title: 'Гипотеза Б: Прямые межрегиональные рейсы (P2P)',
    subtitle: 'Точечные маршруты в обход Москвы между городами Топ-3',
    annualFlights: p2pAnnualFlights,
    annualSeats: p2pAnnualSeats,
    effectiveLoadFactorPct: p2pEffectiveLoadPct,
    annualPassengers: p2pAnnualPassengers,
    avgEffectiveFareRub: p2pEffectiveFareRub,
    annualRevenueMlnRub: p2pAnnualRevenueMlnRub,
    operatingCostMlnRub: p2pOperatingCostMlnRub,
    ebitdarMlnRub: p2pEbitdarMlnRub,
    ebitdarMarginPct: p2pEbitdarMarginPct,
    marketShareDeltaPct: p2pMarketShareDeltaPct,
    newTotalMarketSharePct: p2pNewTotalSharePct,
    requiredAircraftSj100: p2pRequiredAircraft,
    breakEvenLoadFactorPct: p2pBreakEvenLoadPct,
    riskIndex: params.scenario === 'conservative' ? 34 : 28,
  };

  // Выбор победителя по комплексному критерию: рост доли рынка при положительной маржинальности EBITDAR
  const hubScore = hubMetrics.annualRevenueMlnRub * 0.45 + hubMetrics.ebitdarMlnRub * 0.55;
  const p2pScore = p2pMetrics.annualRevenueMlnRub * 0.45 + p2pMetrics.ebitdarMlnRub * 0.55;
  const winner: HypothesisType = p2pScore >= hubScore ? 'p2p' : 'hub';

  const paxDelta = Math.abs(p2pAnnualPassengers - hubAnnualPassengers);
  const revenueDeltaMlnRub = Number(
    Math.abs(p2pAnnualRevenueMlnRub - hubAnnualRevenueMlnRub).toFixed(1)
  );
  const marketShareDiffPct = Number(
    Math.abs(p2pMarketShareDeltaPct - hubMarketShareDeltaPct).toFixed(3)
  );

  const rationale =
    winner === 'p2p'
      ? `При частоте ${safeFreq} рейсов/нед. и сценарии «${
          params.scenario === 'base' ? 'Базовый' : 'Осторожный'
        }» прямые межрегиональные рейсы (Гипотеза Б) выигрывают за счет отсутствия постоянных затрат на содержание нового хаба (${hubFixedStationMln} млн ₽/год), более высокого прямого тарифа (${p2pEffectiveFareRub.toLocaleString('ru-RU')} ₽ против ${hubEffectiveFareRub.toLocaleString('ru-RU')} ₽) и меньшей потребности в дефицитных бортах SJ-100 (${p2pRequiredAircraft} шт. против ${hubRequiredAircraft} шт.).`
      : `При высокой частоте (${safeFreq} рейсов/нед.) региональный хаб в ${params.selectedHubIata} (Гипотеза А) выходит вперед за счет мультипликатора стыковочного трафика (загрузка ${hubEffectiveLoadPct}% против ${p2pEffectiveLoadPct}%), обеспечивая максимальный прирост пассажиропотока (+${hubAnnualPassengers.toLocaleString('ru-RU')} пасс./год).`;

  return {
    hub: hubMetrics,
    p2p: p2pMetrics,
    winner,
    winnerTitle: winner === 'p2p' ? p2pMetrics.title : hubMetrics.title,
    paxDelta,
    revenueDeltaMlnRub,
    marketShareDiffPct,
    rationale,
  };
}

export const NETWORK_ROUTES: RouteSpecification[] = [
  {
    id: 'r1',
    code: 'WZ-401',
    originIata: 'KUF',
    originCity: 'Самара',
    destIata: 'GOJ',
    destCity: 'Нижний Новгород',
    hypothesis: 'p2p',
    distanceKm: 560,
    flightTimeMin: 75,
    recommendedWeeklyFreq: 5,
    competitorFareRub: 9200,
    proposedFareRub: 7600,
    competitorCarriers: 'Только с пересадкой в МСК (Аэрофлот)',
    directCompetitorFlightsWeekly: 0,
    proofSource: 'Росстат (4,82 млн чел. в 2 агломерациях) + ж/д поток 145 тыс./год',
    estimatedAnnualPax: 44200,
    subsidyEligible: true,
    launchQuarter: 'Q3 2026',
  },
  {
    id: 'r2',
    code: 'WZ-403',
    originIata: 'KUF',
    originCity: 'Самара',
    destIata: 'PEE',
    destCity: 'Пермь',
    hypothesis: 'p2p',
    distanceKm: 690,
    flightTimeMin: 85,
    recommendedWeeklyFreq: 4,
    competitorFareRub: 10400,
    proposedFareRub: 8100,
    competitorCarriers: 'Отсутствуют прямые рейсы',
    directCompetitorFlightsWeekly: 0,
    proofSource: 'Росавиация: 82% трафика KUF-PEE летит через SVO со стыковкой > 4ч',
    estimatedAnnualPax: 35800,
    subsidyEligible: true,
    launchQuarter: 'Q3 2026',
  },
  {
    id: 'r3',
    code: 'WZ-405',
    originIata: 'GOJ',
    originCity: 'Нижний Новгород',
    destIata: 'UFA',
    destCity: 'Уфа',
    hypothesis: 'p2p',
    distanceKm: 770,
    flightTimeMin: 95,
    recommendedWeeklyFreq: 5,
    competitorFareRub: 11200,
    proposedFareRub: 8400,
    competitorCarriers: 'Икар (2 р/нед сезонно)',
    directCompetitorFlightsWeekly: 2,
    proofSource: 'Деловой трафик ПФО + дефицит емкости на E190/CRJ-200',
    estimatedAnnualPax: 44800,
    subsidyEligible: true,
    launchQuarter: 'Q4 2026',
  },
  {
    id: 'r4',
    code: 'WZ-407',
    originIata: 'GOJ',
    originCity: 'Нижний Новгород',
    destIata: 'MRV',
    destCity: 'Минеральные Воды',
    hypothesis: 'p2p',
    distanceKm: 1310,
    flightTimeMin: 155,
    recommendedWeeklyFreq: 6,
    competitorFareRub: 11900,
    proposedFareRub: 9800,
    competitorCarriers: 'Азимут (3 р/нед, загрузка 93%)',
    directCompetitorFlightsWeekly: 3,
    proofSource: 'Курортный спрос Кавминвод: неудовлетворенный спрос ~55 тыс. кресел/год',
    estimatedAnnualPax: 53600,
    subsidyEligible: false,
    launchQuarter: 'Q2 2027',
  },
  {
    id: 'r5',
    code: 'WZ-409',
    originIata: 'UFA',
    originCity: 'Уфа',
    destIata: 'VOG',
    destCity: 'Волгоград',
    hypothesis: 'p2p',
    distanceKm: 1040,
    flightTimeMin: 120,
    recommendedWeeklyFreq: 4,
    competitorFareRub: 10800,
    proposedFareRub: 8500,
    competitorCarriers: 'Нет прямого авиасообщения',
    directCompetitorFlightsWeekly: 0,
    proofSource: 'Время в пути ж/д > 26 часов; субсидия ПП РФ №1242 подтверждена',
    estimatedAnnualPax: 34900,
    subsidyEligible: true,
    launchQuarter: 'Q2 2027',
  },
  {
    id: 'r6',
    code: 'WZ-411',
    originIata: 'KUF',
    originCity: 'Самара',
    destIata: 'CEK',
    destCity: 'Челябинск',
    hypothesis: 'p2p',
    distanceKm: 765,
    flightTimeMin: 95,
    recommendedWeeklyFreq: 5,
    competitorFareRub: 9900,
    proposedFareRub: 7900,
    competitorCarriers: 'Отсутствуют прямые рейсы',
    directCompetitorFlightsWeekly: 0,
    proofSource: 'Промышленный коридор Самара — Южный Урал (4,3 млн жит.)',
    estimatedAnnualPax: 43900,
    subsidyEligible: true,
    launchQuarter: 'Q3 2027',
  },
  {
    id: 'r7',
    code: 'WZ-413',
    originIata: 'UFA',
    originCity: 'Уфа',
    destIata: 'OMS',
    destCity: 'Омск',
    hypothesis: 'p2p',
    distanceKm: 1290,
    flightTimeMin: 140,
    recommendedWeeklyFreq: 4,
    competitorFareRub: 12400,
    proposedFareRub: 9400,
    competitorCarriers: 'Только через Новосибирск/МСК',
    directCompetitorFlightsWeekly: 0,
    proofSource: 'Связка Приволжье — Западная Сибирь в обход перегруженного Толмачево',
    estimatedAnnualPax: 35100,
    subsidyEligible: true,
    launchQuarter: 'Q4 2027',
  },
  {
    id: 'r8',
    code: 'WZ-415',
    originIata: 'GOJ',
    originCity: 'Нижний Новгород',
    destIata: 'SVX',
    destCity: 'Екатеринбург',
    hypothesis: 'p2p',
    distanceKm: 1085,
    flightTimeMin: 125,
    recommendedWeeklyFreq: 6,
    competitorFareRub: 10500,
    proposedFareRub: 8700,
    competitorCarriers: 'Red Wings (действующая база SVX, усиление частоты)',
    directCompetitorFlightsWeekly: 4,
    proofSource: 'Встроенная синергия с технической базой Red Wings в Кольцово (SVX)',
    estimatedAnnualPax: 52800,
    subsidyEligible: false,
    launchQuarter: 'Q4 2026',
  },
  {
    id: 'r9',
    code: 'WZ-417',
    originIata: 'KUF',
    originCity: 'Самара',
    destIata: 'TJM',
    destCity: 'Тюмень',
    hypothesis: 'hub',
    distanceKm: 1120,
    flightTimeMin: 130,
    recommendedWeeklyFreq: 5,
    competitorFareRub: 10900,
    proposedFareRub: 8600,
    competitorCarriers: 'Utair (3 р/нед на ATR-72/B737)',
    directCompetitorFlightsWeekly: 3,
    proofSource: 'Нефтегазовый вахтовый и деловой трафик Поволжье — ХМАО/Тюмень',
    estimatedAnnualPax: 44100,
    subsidyEligible: true,
    launchQuarter: 'Q1 2028',
  },
  {
    id: 'r10',
    code: 'WZ-419',
    originIata: 'KZN',
    originCity: 'Казань',
    destIata: 'CEK',
    destCity: 'Челябинск',
    hypothesis: 'p2p',
    distanceKm: 760,
    flightTimeMin: 95,
    recommendedWeeklyFreq: 4,
    competitorFareRub: 9700,
    proposedFareRub: 8000,
    competitorCarriers: 'ЮВТ Аэро (CRJ-200 на 50 кресел)',
    directCompetitorFlightsWeekly: 2,
    proofSource: 'Замена малоразмерного CRJ-200 на SJ-100 снижает цену кресла на 22%',
    estimatedAnnualPax: 35400,
    subsidyEligible: true,
    launchQuarter: 'Q1 2028',
  },
  {
    id: 'r11',
    code: 'WZ-421',
    originIata: 'KUF',
    originCity: 'Самара',
    destIata: 'MRV',
    destCity: 'Минеральные Воды',
    hypothesis: 'hub',
    distanceKm: 1095,
    flightTimeMin: 135,
    recommendedWeeklyFreq: 7,
    competitorFareRub: 11400,
    proposedFareRub: 9200,
    competitorCarriers: 'Азимут / Уральские Авиалинии',
    directCompetitorFlightsWeekly: 5,
    proofSource: 'Фидерное плечо для пересадки пассажиров Урала через хаб Курумоч на Юг',
    estimatedAnnualPax: 61500,
    subsidyEligible: false,
    launchQuarter: 'Q3 2027',
  },
  {
    id: 'r12',
    code: 'WZ-423',
    originIata: 'GSV',
    originCity: 'Саратов',
    destIata: 'SVX',
    destCity: 'Екатеринбург',
    hypothesis: 'hub',
    distanceKm: 1110,
    flightTimeMin: 130,
    recommendedWeeklyFreq: 4,
    competitorFareRub: 10600,
    proposedFareRub: 8300,
    competitorCarriers: 'Отсутствуют прямые рейсы',
    directCompetitorFlightsWeekly: 0,
    proofSource: 'Росавиация: 29 тыс. пасс./год летают Саратов—Урал через Москву',
    estimatedAnnualPax: 34200,
    subsidyEligible: true,
    launchQuarter: 'Q2 2028',
  },
];
