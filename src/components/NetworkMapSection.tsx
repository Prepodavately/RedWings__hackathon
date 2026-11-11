import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  ScoredCity,
  RouteSpecification,
  HypothesisType,
} from '../utils/aviationModel';
import { ArrowRight, ShieldCheck, Layers, Compass, Sliders, Plane } from 'lucide-react';

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

export type AircraftTypeId = 'sj100_basic' | 'sj100_lr' | 'tu214' | 'crj200';

interface AircraftSpec {
  id: AircraftTypeId;
  name: string;
  seats: number;
  minEffectiveKm: number;
  optLowKm: number;
  optHighKm: number;
  maxRangeKm: number;
  caskNote: string;
  role: string;
}

// Характеристики типов ВС из модели Red Wings (Dev 2 range_weight + Dev 3 sj100_fleet / Волны до 2030)
const AIRCRAFT_SPECS: Record<AircraftTypeId, AircraftSpec> = {
  sj100_basic: {
    id: 'sj100_basic',
    name: 'SJ-100 Basic (100 мест)',
    seats: 100,
    minEffectiveKm: 350,
    optLowKm: 600,
    optHighKm: 1600,
    maxRangeKm: 2450,
    caskNote: 'Базовый CASK модели (-22% к CRJ-200)',
    role: 'Основной региональный борт 2027–2028 (поставки ОАК)',
  },
  sj100_lr: {
    id: 'sj100_lr',
    name: 'SSJ-100 / SJ-100 LR (100 мест)',
    seats: 100,
    minEffectiveKm: 400,
    optLowKm: 700,
    optHighKm: 2200,
    maxRangeKm: 3050,
    caskNote: 'Действующий резерв SSJ (до 6 бортов) + LR-версия',
    role: 'Дальние межрегиональные связки (Урал ↔ Юг / Сибирь)',
  },
  tu214: {
    id: 'tu214',
    name: 'Ту-214 (210 мест · Волна 3)',
    seats: 210,
    minEffectiveKm: 1100,
    optLowKm: 1400,
    optHighKm: 4200,
    maxRangeKm: 5200,
    caskNote: 'Высокая ёмкость, неэффективен на коротких плечах <1000 км',
    role: 'Магистральный флот Волны 3 (2029–2030: 8 бортов Ту-214 + 28 SJ-100)',
  },
  crj200: {
    id: 'crj200',
    name: 'CRJ-200 (50 мест · Конкуренты)',
    seats: 50,
    minEffectiveKm: 300,
    optLowKm: 450,
    optHighKm: 1200,
    maxRangeKm: 1450,
    caskNote: 'CASK на +19..24% дороже SJ-100 из-за малой ёмкости 50 кресел',
    role: 'Флот региональных конкурентов (ЮВТ Аэро и др.)',
  },
};

// Область кадрирования: Европейская часть РФ, Юг, Поволжье, Урал и Западная Сибирь
const CROP_X_MIN = 48;
const CROP_X_MAX = 488;
const CROP_Y_MIN = 185;
const CROP_Y_MAX = 675;
const CROP_W = CROP_X_MAX - CROP_X_MIN; // 440
const CROP_H = CROP_Y_MAX - CROP_Y_MIN; // 490

// Масштаб: 1 единица SVG ≈ 10.2 км в зоне ПФО/Урала
const KM_PER_SVG_UNIT = 10.2;

const RUSSIA_MAP_POS: Record<
  string,
  { x: number; y: number; labelDx: number; labelDy: number; anchor?: 'start' | 'end' }
> = {
  MOW: { x: 148, y: 472, labelDx: -8, labelDy: -8, anchor: 'end' },
  GOJ: { x: 184, y: 472, labelDx: 8, labelDy: -7 },
  KZN: { x: 215, y: 492, labelDx: 8, labelDy: -5 },
  KUF: { x: 222, y: 534, labelDx: -8, labelDy: 4, anchor: 'end' },
  GSV: { x: 186, y: 556, labelDx: 8, labelDy: 4 },
  VOG: { x: 165, y: 588, labelDx: 8, labelDy: 4 },
  MRV: { x: 142, y: 638, labelDx: 8, labelDy: 4 },
  PEE: { x: 266, y: 464, labelDx: 8, labelDy: -5 },
  UFA: { x: 258, y: 518, labelDx: -8, labelDy: -8, anchor: 'end' },
  SVX: { x: 304, y: 482, labelDx: 8, labelDy: -5 },
  CEK: { x: 302, y: 522, labelDx: 8, labelDy: 5 },
  TJM: { x: 348, y: 494, labelDx: 8, labelDy: 3 },
  OMS: { x: 408, y: 536, labelDx: 8, labelDy: 3 },
};

const RUSSIA_SILHOUETTE_PTS: [number, number][] = [
  [175, 225], [220, 215], [250, 270], [215, 310], [260, 290], [310, 255],
  [350, 175], [385, 165], [340, 240], [375, 275], [415, 235], [460, 240],
  [505, 195], [565, 145], [615, 175], [635, 240], [635, 635], [560, 625],
  [495, 645], [435, 605], [380, 565], [310, 555], [245, 565], [195, 595],
  [165, 655], [120, 650], [105, 605], [65, 585], [58, 535], [95, 485],
  [85, 410], [115, 355], [155, 330], [160, 265],
];

const COLOR_LUT = new Uint8Array(1024 * 3);
(() => {
  const stops: [number, [number, number, number]][] = [
    [-100, [58, 152, 219]],
    [-75, [76, 175, 220]],
    [-50, [102, 199, 198]],
    [-25, [138, 218, 168]],
    [0, [186, 232, 134]],
    [20, [238, 236, 108]],
    [40, [254, 196, 79]],
    [60, [252, 128, 56]],
    [80, [227, 38, 42]],
  ];
  for (let idx = 0; idx < 1024; idx++) {
    const val = -100 + (idx / 1023) * 180;
    const stepped = Math.round(val / 9) * 9;
    let rgb: [number, number, number] = stops[stops.length - 1][1];
    for (let i = 0; i < stops.length - 1; i++) {
      const [v0, c0] = stops[i];
      const [v1, c1] = stops[i + 1];
      if (stepped >= v0 && stepped <= v1) {
        const t = (stepped - v0) / (v1 - v0 || 1);
        rgb = [
          Math.round(c0[0] + (c1[0] - c0[0]) * t),
          Math.round(c0[1] + (c1[1] - c0[1]) * t),
          Math.round(c0[2] + (c1[2] - c0[2]) * t),
        ];
        break;
      }
    }
    COLOR_LUT[idx * 3] = rgb[0];
    COLOR_LUT[idx * 3 + 1] = rgb[1];
    COLOR_LUT[idx * 3 + 2] = rgb[2];
  }
})();

function pointInPolygon(x: number, y: number, poly: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-9) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

const FIELD_W = 110;
const FIELD_H = 100;
const RENDER_W = 660;
const RENDER_H = 600;

export function getRouteRangeStatus(distanceKm: number, spec: AircraftSpec): {
  status: 'optimal' | 'suboptimal_short' | 'near_limit' | 'out_of_range';
  label: string;
  badgeClass: string;
  strokeColor: string;
} {
  if (distanceKm > spec.maxRangeKm) {
    return {
      status: 'out_of_range',
      label: `Превышает дальность (${spec.maxRangeKm} км)`,
      badgeClass: 'bg-red-100 text-red-800 border-red-300',
      strokeColor: '#dc2626',
    };
  }
  if (distanceKm < spec.minEffectiveKm) {
    return {
      status: 'suboptimal_short',
      label: `Слишком короткое (<${spec.minEffectiveKm} км, риск ЖД)`,
      badgeClass: 'bg-amber-100 text-amber-800 border-amber-300',
      strokeColor: '#d97706',
    };
  }
  if (distanceKm >= spec.optLowKm && distanceKm <= spec.optHighKm) {
    return {
      status: 'optimal',
      label: 'Оптимум плеча ВС',
      badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-300',
      strokeColor: '#2563eb',
    };
  }
  return {
    status: 'near_limit',
    label: 'Допустимо (вне пика CASK)',
    badgeClass: 'bg-sky-100 text-sky-800 border-sky-300',
    strokeColor: '#3b82f6',
  };
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
  // По умолчанию — режим «Маршруты»
  const [visualLayer, setVisualLayer] = useState<'routes' | 'gravity'>('routes');
  const [selectedAircraft, setSelectedAircraft] = useState<AircraftTypeId>('sj100_basic');
  const [showRangeRing, setShowRangeRing] = useState<boolean>(true);
  const [selectedRouteId, setSelectedRouteId] = useState<string>(routes[0]?.id || 'r1');
  const [hoveredRouteId, setHoveredRouteId] = useState<string | null>(null);
  const [subsidyFilter, setSubsidyFilter] = useState<'all' | 'subsidized'>('all');

  // Интерактивные параметры гравитации
  const [gravityGamma, setGravityGamma] = useState<number>(1.6);

  const aircraftSpec = AIRCRAFT_SPECS[selectedAircraft];
  // В режиме гравитации радиус притяжения синхронизирован с дальностью выбранного типа ВС
  const [sj100RadiusKm, setSj100RadiusKm] = useState<number>(1250);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [hiResMask, setHiResMask] = useState<Uint8Array | null>(null);

  const cityByIata = useMemo(() => {
    const map = new Map<string, ScoredCity>();
    scoredCities.forEach((c) => map.set(c.iata, c));
    return map;
  }, [scoredCities]);

  const top3Cities = scoredCities.filter((c) => c.isTop3);
  const hubCity = cityByIata.get(selectedHubIata) || top3Cities[0] || scoredCities[0];

  useEffect(() => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const off = document.createElement('canvas');
      off.width = RENDER_W;
      off.height = RENDER_H;
      const octx = off.getContext('2d');
      if (!octx) return;

      const sx = (CROP_X_MIN / 1000) * img.width;
      const sy = (CROP_Y_MIN / 750) * img.height;
      const sw = (CROP_W / 1000) * img.width;
      const sh = (CROP_H / 750) * img.height;

      octx.drawImage(img, sx, sy, sw, sh, 0, 0, RENDER_W, RENDER_H);
      const raw = octx.getImageData(0, 0, RENDER_W, RENDER_H).data;
      const mask = new Uint8Array(RENDER_W * RENDER_H);

      for (let py = 0; py < RENDER_H; py++) {
        for (let px = 0; px < RENDER_W; px++) {
          const p = (py * RENDER_W + px) * 4;
          const r = raw[p];
          const g = raw[p + 1];
          const b = raw[p + 2];
          if (b - r > 20 && b > 135 && g > 105) {
            mask[py * RENDER_W + px] = 1;
          }
        }
      }

      for (let py = 2; py < RENDER_H - 2; py++) {
        for (let px = 2; px < RENDER_W - 2; px++) {
          const idx = py * RENDER_W + px;
          if (mask[idx] === 1) continue;
          const p = idx * 4;
          if (raw[p] > 205 && raw[p + 1] > 215 && raw[p + 2] > 220) {
            const lr =
              (mask[idx - 1] === 1 || mask[idx - 2] === 1) &&
              (mask[idx + 1] === 1 || mask[idx + 2] === 1);
            const ud =
              (mask[idx - RENDER_W] === 1 || mask[idx - 2 * RENDER_W] === 1) &&
              (mask[idx + RENDER_W] === 1 || mask[idx + 2 * RENDER_W] === 1);
            if (lr || ud) mask[idx] = 2;
          }
        }
      }
      setHiResMask(mask);
    };
    img.src = '/assets/aistudio/____________9b78de56.png';
  }, []);

  const displayedRoutes = useMemo(() => {
    const baseSlice = routes.slice(0, activeRouteCount);
    const adapted = baseSlice.map((route, idx) => {
      const dynamicPax = Math.round(
        weeklyFreqPerRoute *
          2 *
          52 *
          aircraftSpec.seats *
          (loadFactorPct / 100) *
          (mapMode === 'hub' ? 0.98 : 1.02)
      );
      if (mapMode === 'hub' && hubCity) {
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
    aircraftSpec.seats,
  ]);

  const activeRoute =
    displayedRoutes.find((r) => r.id === selectedRouteId) || displayedRoutes[0];
  const hoveredRoute = hoveredRouteId
    ? displayedRoutes.find((r) => r.id === hoveredRouteId)
    : null;

  // Статистика маршрутов по дальности выбранного типа ВС
  const rangeSummary = useMemo(() => {
    let optimal = 0;
    let acceptable = 0;
    let outOfRange = 0;
    for (const r of displayedRoutes) {
      const st = getRouteRangeStatus(r.distanceKm, aircraftSpec).status;
      if (st === 'optimal') optimal++;
      else if (st === 'out_of_range') outOfRange++;
      else acceptable++;
    }
    return { optimal, acceptable, outOfRange };
  }, [displayedRoutes, aircraftSpec]);

  // При клике на город в режиме маршрутов: выбираем маршрут, проходящий через этот город (или меняем хаб в режиме Хаба)
  const handleCityClick = (iata: string) => {
    if (mapMode === 'hub') {
      onSelectHub(iata);
      return;
    }
    const matchingRoutes = displayedRoutes.filter(
      (r) => r.originIata === iata || r.destIata === iata
    );
    if (matchingRoutes.length > 0) {
      const currentIdx = matchingRoutes.findIndex((r) => r.id === selectedRouteId);
      const nextRoute = matchingRoutes[(currentIdx + 1) % matchingRoutes.length];
      setSelectedRouteId(nextRoute.id);
    }
  };

  const barycenter = useMemo(() => {
    let sumM = 0;
    let sumX = 0;
    let sumY = 0;
    for (const c of scoredCities) {
      const pos = RUSSIA_MAP_POS[c.iata];
      if (!pos) continue;
      const isHubBoost = mapMode === 'hub' && c.iata === selectedHubIata ? 1.45 : 1.0;
      const m = Math.pow(c.totalScore / 100, gravityGamma) * isHubBoost;
      sumM += m;
      sumX += m * pos.x;
      sumY += m * pos.y;
    }
    return sumM > 0
      ? { x: sumX / sumM, y: sumY / sumM }
      : { x: 245, y: 510 };
  }, [scoredCities, mapMode, selectedHubIata, gravityGamma]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const imgData = ctx.createImageData(RENDER_W, RENDER_H);
    const data = imgData.data;

    if (visualLayer === 'routes') {
      for (let py = 0; py < RENDER_H; py++) {
        const svgY = CROP_Y_MIN + (py / RENDER_H) * CROP_H;
        const rowOffset = py * RENDER_W;
        for (let px = 0; px < RENDER_W; px++) {
          const idx = rowOffset + px;
          const p = idx * 4;
          const mVal = hiResMask
            ? hiResMask[idx]
            : pointInPolygon(
                CROP_X_MIN + (px / RENDER_W) * CROP_W,
                svgY,
                RUSSIA_SILHOUETTE_PTS
              )
            ? 1
            : 0;

          if (mVal === 0) {
            data[p] = 248;
            data[p + 1] = 250;
            data[p + 2] = 252;
            data[p + 3] = 255;
          } else if (mVal === 2) {
            data[p] = 255;
            data[p + 1] = 255;
            data[p + 2] = 255;
            data[p + 3] = 255;
          } else {
            data[p] = 216;
            data[p + 1] = 232;
            data[p + 2] = 246;
            data[p + 3] = 255;
          }
        }
      }
      ctx.putImageData(imgData, 0, 0);
      return;
    }

    const routeCountByIata: Record<string, number> = {};
    for (const r of displayedRoutes) {
      routeCountByIata[r.originIata] = (routeCountByIata[r.originIata] || 0) + 1;
      routeCountByIata[r.destIata] = (routeCountByIata[r.destIata] || 0) + 1;
    }

    const cityNodes = scoredCities
      .map((city) => {
        const pos = RUSSIA_MAP_POS[city.iata];
        if (!pos) return null;
        const netBoost =
          1 +
          0.12 * (routeCountByIata[city.iata] || 0) +
          (mapMode === 'hub' && city.iata === selectedHubIata ? 0.38 : 0);
        const mass =
          (0.62 * Math.pow(city.totalScore / 100, 1.35) +
            0.38 * Math.pow(city.agglomerationPopMln * city.airportPax2025Mln, 0.38)) *
          netBoost;
        return { x: pos.x, y: pos.y, mass };
      })
      .filter((n): n is { x: number; y: number; mass: number } => n !== null);

    const radiusUnits = (sj100RadiusKm / 1250) * 68;
    const invKernelR2 = (gravityGamma * 0.85) / Math.max(400, radiusUnits * radiusUnits);
    const invHaloR2 = (gravityGamma * 0.42) / Math.max(900, radiusUnits * radiusUnits * 2.2);

    const coarse = new Float32Array(FIELD_W * FIELD_H);
    let fMin = Infinity;
    let fMax = -Infinity;

    for (let gy = 0; gy < FIELD_H; gy++) {
      const svgY = CROP_Y_MIN + (gy / (FIELD_H - 1)) * CROP_H;
      const gRow = gy * FIELD_W;
      for (let gx = 0; gx < FIELD_W; gx++) {
        const svgX = CROP_X_MIN + (gx / (FIELD_W - 1)) * CROP_W;
        let v = 0;
        for (let i = 0; i < cityNodes.length; i++) {
          const c = cityNodes[i];
          const dx = svgX - c.x;
          const dy = svgY - c.y;
          const d2 = dx * dx + dy * dy;
          const t1 = 1 + d2 * invKernelR2;
          const t2 = 1 + d2 * invHaloR2;
          v += c.mass * (1.55 / (t1 * t1) + 0.85 / t2);
        }
        coarse[gRow + gx] = v;
        if (v < fMin) fMin = v;
        if (v > fMax) fMax = v;
      }
    }

    const invSpan = 180 / (fMax - fMin || 1);
    for (let i = 0; i < coarse.length; i++) {
      coarse[i] = -100 + (coarse[i] - fMin) * invSpan;
    }

    const contourStep = 11.25;
    const scaleX = (FIELD_W - 1) / (RENDER_W - 1);
    const scaleY = (FIELD_H - 1) / (RENDER_H - 1);

    for (let py = 0; py < RENDER_H; py++) {
      const fy = py * scaleY;
      const y0 = fy | 0;
      const y1 = y0 + 1 < FIELD_H ? y0 + 1 : y0;
      const ty = fy - y0;
      const row0 = y0 * FIELD_W;
      const row1 = y1 * FIELD_W;
      const outRow = py * RENDER_W;

      for (let px = 0; px < RENDER_W; px++) {
        const idx = outRow + px;
        const p = idx * 4;
        const mVal = hiResMask ? hiResMask[idx] : 1;

        if (mVal === 0) {
          data[p] = 253;
          data[p + 1] = 251;
          data[p + 2] = 240;
          data[p + 3] = 255;
          continue;
        }

        if (mVal === 2) {
          data[p] = 255;
          data[p + 1] = 255;
          data[p + 2] = 255;
          data[p + 3] = 235;
          continue;
        }

        const fx = px * scaleX;
        const x0 = fx | 0;
        const x1 = x0 + 1 < FIELD_W ? x0 + 1 : x0;
        const tx = fx - x0;

        const v00 = coarse[row0 + x0];
        const v10 = coarse[row0 + x1];
        const v01 = coarse[row1 + x0];
        const v11 = coarse[row1 + x1];

        const top = v00 + (v10 - v00) * tx;
        const bot = v01 + (v11 - v01) * tx;
        const val = top + (bot - top) * ty;

        const lutIdx = Math.max(0, Math.min(1023, ((val + 100) * (1023 / 180)) | 0)) * 3;
        const r = COLOR_LUT[lutIdx];
        const g = COLOR_LUT[lutIdx + 1];
        const b = COLOR_LUT[lutIdx + 2];

        const phase = ((val + 100) / contourStep) % 1;
        const distToLine = phase < 0.5 ? phase : 1 - phase;

        if (distToLine < 0.042) {
          data[p] = (r * 0.42) | 0;
          data[p + 1] = (g * 0.42) | 0;
          data[p + 2] = (b * 0.42) | 0;
          data[p + 3] = 255;
        } else {
          data[p] = r;
          data[p + 1] = g;
          data[p + 2] = b;
          data[p + 3] = 255;
        }
      }
    }

    ctx.putImageData(imgData, 0, 0);
  }, [
    scoredCities,
    displayedRoutes,
    hiResMask,
    visualLayer,
    gravityGamma,
    sj100RadiusKm,
    mapMode,
    selectedHubIata,
  ]);

  // Центр кольца дальности ВС: из города вылета выбранного маршрута (или выбранного хаба)
  const rangeOriginIata = mapMode === 'hub' ? selectedHubIata : activeRoute?.originIata || 'KUF';
  const rangeOriginPos = RUSSIA_MAP_POS[rangeOriginIata] || RUSSIA_MAP_POS.KUF;
  const maxRangeSvgRadius = aircraftSpec.maxRangeKm / KM_PER_SVG_UNIT;
  const optHighSvgRadius = aircraftSpec.optHighKm / KM_PER_SVG_UNIT;

  return (
    <div className="space-y-6">
      {/* Панель управления картой сети и типом ВС */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              {visualLayer === 'routes'
                ? `Карта маршрутной сети и проверка дальности ВС (${displayedRoutes.length} маршрутов)`
                : 'Карта гравитационного поля притяжения пасспотока (Изолинии потенциала)'}
            </h2>
            <p className="text-sm text-slate-600 mt-0.5">
              {visualLayer === 'routes'
                ? 'Кликните прямо на любую линию маршрута или город на карте для проверки плеча, дальности ВС и крюка через Москву'
                : 'Динамическое поле гравитационного притяжения 12 агломераций внутри границ РФ'}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Переключатель режима карты: По умолчанию «Маршруты» ИЛИ «Гравитация» */}
            <div
              className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg border border-slate-200"
              role="group"
              aria-label="Режим карты"
            >
              <button
                type="button"
                onClick={() => setVisualLayer('routes')}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors flex items-center gap-1.5 whitespace-nowrap shrink-0 ${
                  visualLayer === 'routes'
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-700 hover:text-slate-900'
                }`}
              >
                <Compass className="w-3.5 h-3.5" />
                Маршруты (по умолчанию)
              </button>
              <button
                type="button"
                onClick={() => setVisualLayer('gravity')}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors flex items-center gap-1.5 whitespace-nowrap shrink-0 ${
                  visualLayer === 'gravity'
                    ? 'bg-rose-600 text-white shadow-xs'
                    : 'text-slate-700 hover:text-slate-900'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                Гравитация (Изолинии)
              </button>
            </div>

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
          </div>
        </div>

        {/* Панель выбора типа самолета (SJ-100 Basic / SJ-100 LR / Ту-214 / CRJ-200) и радиуса полета */}
        <div className="pt-3 border-t border-slate-200 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-slate-700 flex items-center gap-1.5 mr-1">
              <Plane className="w-4 h-4 text-rose-600" />
              Тип ВС и фильтр дальности:
            </span>
            {(Object.values(AIRCRAFT_SPECS) as AircraftSpec[]).map((spec) => (
              <button
                key={spec.id}
                type="button"
                onClick={() => {
                  setSelectedAircraft(spec.id);
                  setSj100RadiusKm(Math.min(2100, spec.optHighKm));
                }}
                className={`px-3 py-1.5 text-xs rounded-lg border transition-colors font-medium ${
                  selectedAircraft === spec.id
                    ? 'bg-slate-900 text-white border-slate-900 font-semibold'
                    : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                }`}
              >
                {spec.name} · до {spec.maxRangeKm} км
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label className="inline-flex items-center gap-1.5 cursor-pointer text-slate-700 font-medium">
              <input
                type="checkbox"
                checked={showRangeRing}
                onChange={(e) => setShowRangeRing(e.target.checked)}
                className="accent-rose-600 rounded"
              />
              Кольцо радиуса ВС из {rangeOriginIata}
            </label>
            <span className="px-2.5 py-1 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200 font-mono">
              В оптимуме ({aircraftSpec.optLowKm}–{aircraftSpec.optHighKm} км): {rangeSummary.optimal}
            </span>
            {rangeSummary.outOfRange > 0 && (
              <span className="px-2.5 py-1 rounded-md bg-red-50 text-red-800 border border-red-200 font-mono font-semibold">
                Вне радиуса (&gt;{aircraftSpec.maxRangeKm} км): {rangeSummary.outOfRange}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Сетка: Карта слева (7 колонок) + Пруф маршрута справа (5 колонок) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        <div
          className={`lg:col-span-7 border border-slate-300 rounded-xl p-5 flex flex-col justify-between text-slate-900 shadow-xs ${
            visualLayer === 'routes' ? 'bg-slate-50' : 'bg-[#fdfbf0]'
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-4 mb-2">
            <div>
              <span className="text-xs font-mono font-semibold text-rose-700">
                {visualLayer === 'routes'
                  ? `${aircraftSpec.name.toUpperCase()} · ОПТИМУМ ${aircraftSpec.optLowKm}–${aircraftSpec.optHighKm} КМ · МАКС. ${aircraftSpec.maxRangeKm} КМ`
                  : 'ДИНАМИЧЕСКОЕ ПОЛЕ ГРАВИТАЦИОННОГО ПРИТЯЖЕНИЯ (DEV 2)'}
              </span>
              <h3 className="text-base font-bold text-slate-900 mt-0.5">
                {hoveredRoute
                  ? `Наведение: ${hoveredRoute.originCity} (${hoveredRoute.originIata}) → ${hoveredRoute.destCity} (${hoveredRoute.destIata}) · ${hoveredRoute.distanceKm} км (кликните для выбора)`
                  : visualLayer === 'routes'
                  ? `Выбран: ${activeRoute?.originCity} (${activeRoute?.originIata}) → ${activeRoute?.destCity} (${activeRoute?.destIata}) · ${activeRoute?.distanceKm} км`
                  : `Полюс №1: ${scoredCities[0]?.name} (${scoredCities[0]?.totalScore} б.) · Барицентр сети`}
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <select
                id="hub-map-select"
                value={selectedHubIata}
                onChange={(e) => onSelectHub(e.target.value)}
                className="text-xs font-semibold bg-white border border-slate-300 rounded-lg px-2 py-1 text-slate-900"
                title="Базовый город хаба"
              >
                {scoredCities.map((c) => (
                  <option key={c.iata} value={c.iata}>
                    Хаб: {c.iata} ({c.name.split(' (')[0]})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Ползунки гравитации показываются только когда включен режим «Гравитация» */}
          {visualLayer === 'gravity' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3 p-3 rounded-lg bg-white/90 border border-slate-200/90">
              <div>
                <div className="flex items-center justify-between text-xs font-medium text-slate-700 mb-1">
                  <span className="flex items-center gap-1">
                    <Sliders className="w-3.5 h-3.5 text-rose-600" />
                    Затухание гравитации (γ):
                  </span>
                  <span className="font-mono font-bold text-slate-900">{gravityGamma.toFixed(1)}</span>
                </div>
                <input
                  type="range"
                  min={1.0}
                  max={2.6}
                  step={0.1}
                  value={gravityGamma}
                  onChange={(e) => setGravityGamma(parseFloat(e.target.value))}
                  className="w-full accent-rose-600 cursor-pointer h-1.5"
                />
              </div>

              <div>
                <div className="flex items-center justify-between text-xs font-medium text-slate-700 mb-1">
                  <span>Радиус притяжения ВС:</span>
                  <span className="font-mono font-bold text-slate-900">{sj100RadiusKm} км</span>
                </div>
                <input
                  type="range"
                  min={650}
                  max={2100}
                  step={50}
                  value={sj100RadiusKm}
                  onChange={(e) => setSj100RadiusKm(parseInt(e.target.value, 10))}
                  className="w-full accent-rose-600 cursor-pointer h-1.5"
                />
              </div>
            </div>
          )}

          {/* Карта высокого разрешения (660x600 Canvas + прецизионный векторный SVG с широкими зонами клика) */}
          <div className="relative w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
            <canvas
              ref={canvasRef}
              width={RENDER_W}
              height={RENDER_H}
              className="absolute inset-0 w-full h-[390px] object-fill pointer-events-none"
            />

            <svg
              viewBox={`${CROP_X_MIN} ${CROP_Y_MIN} ${CROP_W} ${CROP_H}`}
              preserveAspectRatio="none"
              shapeRendering="geometricPrecision"
              className="relative z-10 w-full h-[390px] select-none"
              role="img"
              aria-label="Прецизионная интерактивная карта маршрутов и гравитационного поля Red Wings"
            >
              {/* Кольца радиуса действия выбранного типа самолета (Оптимум + Макс. дальность) */}
              {visualLayer === 'routes' && showRangeRing && rangeOriginPos && (
                <g className="pointer-events-none">
                  {/* Кольцо максимальной практической дальности ВС */}
                  <circle
                    cx={rangeOriginPos.x}
                    cy={rangeOriginPos.y}
                    r={maxRangeSvgRadius}
                    fill="rgba(59, 130, 246, 0.04)"
                    stroke="#475569"
                    strokeWidth="1.1"
                    strokeDasharray="5 4"
                  />
                  {/* Кольцо верхнего оптимума плеча ВС */}
                  <circle
                    cx={rangeOriginPos.x}
                    cy={rangeOriginPos.y}
                    r={optHighSvgRadius}
                    fill="rgba(16, 185, 129, 0.05)"
                    stroke="#059669"
                    strokeWidth="1"
                    strokeDasharray="2.5 2.5"
                  />
                </g>
              )}

              {/* В режиме «Маршруты» рисуем кликабельные дуги с широкой невидимой зоной захвата мыши (strokeWidth=16) */}
              {visualLayer === 'routes' && (
                <>
                  {displayedRoutes.map((route) => {
                    const orig = RUSSIA_MAP_POS[route.originIata];
                    const dest = RUSSIA_MAP_POS[route.destIata];
                    if (!orig || !dest) return null;

                    const isSelected = activeRoute?.id === route.id;
                    const isHovered = hoveredRouteId === route.id;
                    const rangeInfo = getRouteRangeStatus(route.distanceKm, aircraftSpec);

                    const dx = dest.x - orig.x;
                    const dy = dest.y - orig.y;
                    const len = Math.hypot(dx, dy) || 1;
                    const nx = (-dy / len) * Math.min(14, len * 0.09);
                    const ny = (dx / len) * Math.min(14, len * 0.09);
                    const midX = (orig.x + dest.x) * 0.5 + nx;
                    const midY = (orig.y + dest.y) * 0.5 + ny;
                    const pathD = `M ${orig.x} ${orig.y} Q ${midX} ${midY} ${dest.x} ${dest.y}`;

                    return (
                      <g
                        key={route.id}
                        onClick={() => setSelectedRouteId(route.id)}
                        onMouseEnter={() => setHoveredRouteId(route.id)}
                        onMouseLeave={() => setHoveredRouteId(null)}
                        className="cursor-pointer"
                      >
                        {/* ШИРОКАЯ НЕВИДИМАЯ ЗОНА КЛИКА (16 ед.), чтобы любой клик мышкой по линии срабатывал мгновенно! */}
                        <path
                          d={pathD}
                          fill="none"
                          stroke="rgba(0,0,0,0.001)"
                          strokeWidth="16"
                          strokeLinecap="round"
                        />
                        {/* Видимая линия маршрута (цвет показывает соответствие дальности выбранного ВС) */}
                        {!isSelected && (
                          <path
                            d={pathD}
                            fill="none"
                            stroke={isHovered ? '#0f172a' : rangeInfo.strokeColor}
                            strokeWidth={isHovered ? '2.6' : '1.5'}
                            strokeOpacity={isHovered ? '1' : '0.78'}
                            strokeDasharray={
                              rangeInfo.status === 'out_of_range' ? '3 2.5' : undefined
                            }
                            strokeLinecap="round"
                          />
                        )}
                      </g>
                    );
                  })}

                  {/* Выбранный маршрут: рисуется поверх остальных с крюком через Москву */}
                  {activeRoute && (() => {
                    const orig = RUSSIA_MAP_POS[activeRoute.originIata];
                    const dest = RUSSIA_MAP_POS[activeRoute.destIata];
                    const mow = RUSSIA_MAP_POS.MOW;
                    if (!orig || !dest) return null;
                    const dx = dest.x - orig.x;
                    const dy = dest.y - orig.y;
                    const len = Math.hypot(dx, dy) || 1;
                    const nx = (-dy / len) * Math.min(14, len * 0.09);
                    const ny = (dx / len) * Math.min(14, len * 0.09);
                    const midX = (orig.x + dest.x) * 0.5 + nx;
                    const midY = (orig.y + dest.y) * 0.5 + ny;
                    const rangeInfo = getRouteRangeStatus(activeRoute.distanceKm, aircraftSpec);

                    return (
                      <g className="pointer-events-none">
                        {/* Крюк через Москву */}
                        <path
                          d={`M ${orig.x} ${orig.y} L ${mow.x} ${mow.y} L ${dest.x} ${dest.y}`}
                          fill="none"
                          stroke="#e11d48"
                          strokeWidth="1.75"
                          strokeDasharray="4.5 3.5"
                          strokeLinecap="round"
                        />
                        {/* Белая контрастная подложка */}
                        <path
                          d={`M ${orig.x} ${orig.y} Q ${midX} ${midY} ${dest.x} ${dest.y}`}
                          fill="none"
                          stroke="#ffffff"
                          strokeWidth="4.0"
                          strokeLinecap="round"
                        />
                        {/* Активная дуга прямого рейса */}
                        <path
                          d={`M ${orig.x} ${orig.y} Q ${midX} ${midY} ${dest.x} ${dest.y}`}
                          fill="none"
                          stroke={rangeInfo.status === 'out_of_range' ? '#dc2626' : '#059669'}
                          strokeWidth="2.5"
                          strokeLinecap="round"
                        />
                        {/* Плашка километража прямо на выбранной дуге */}
                        <rect
                          x={midX - 24}
                          y={midY - 7}
                          width="48"
                          height="13"
                          rx="3"
                          fill="#059669"
                        />
                        <text
                          x={midX}
                          y={midY + 2.5}
                          textAnchor="middle"
                          fill="#ffffff"
                          fontSize="8.2"
                          fontWeight="700"
                          fontFamily="JetBrains Mono"
                        >
                          {activeRoute.distanceKm} км
                        </text>
                      </g>
                    );
                  })()}
                </>
              )}

              {/* Москва (MOW) */}
              <g transform={`translate(${RUSSIA_MAP_POS.MOW.x}, ${RUSSIA_MAP_POS.MOW.y})`}>
                <circle r="3.6" fill="#0f172a" stroke="#ffffff" strokeWidth="1.4" />
                <text
                  x="-6"
                  y="-5"
                  textAnchor="end"
                  fill="#0f172a"
                  fontSize="9.5"
                  fontWeight="700"
                  fontFamily="JetBrains Mono"
                >
                  MOW
                </text>
              </g>

              {/* В режиме «Гравитация» показываем барицентр сети */}
              {visualLayer === 'gravity' && (
                <g transform={`translate(${barycenter.x}, ${barycenter.y})`}>
                  <circle r="8" fill="rgba(250, 204, 21, 0.35)" stroke="#b45309" strokeWidth="1.2" />
                  <polygon
                    points="0,-4.8 4.8,0 0,4.8 -4.8,0"
                    fill="#facc15"
                    stroke="#78350f"
                    strokeWidth="1.3"
                  />
                </g>
              )}

              {/* Узлы 12 городов-кандидатов (при клике выбирают маршрут этого города!) */}
              {scoredCities.map((city) => {
                const pos = RUSSIA_MAP_POS[city.iata];
                if (!pos) return null;
                const isHub = city.iata === selectedHubIata && mapMode === 'hub';
                const isTop3 = city.isTop3;
                const isRouteEndpoint =
                  visualLayer === 'routes' &&
                  activeRoute &&
                  (activeRoute.originIata === city.iata || activeRoute.destIata === city.iata);

                const radius =
                  visualLayer === 'gravity'
                    ? Math.max(4.2, Math.min(8.2, 3.2 + (city.totalScore / 100) * 4.6))
                    : isRouteEndpoint
                    ? 5.8
                    : isTop3
                    ? 5.0
                    : 3.8;

                const isEnd = pos.anchor === 'end';
                const badgeW = city.iata.length * 6.4 + 6;
                const badgeX = isEnd ? pos.labelDx - badgeW : pos.labelDx;
                const textX = isEnd ? pos.labelDx - 3 : pos.labelDx + 3;

                return (
                  <g
                    key={city.iata}
                    transform={`translate(${pos.x}, ${pos.y})`}
                    onClick={() => handleCityClick(city.iata)}
                    className="cursor-pointer"
                  >
                    {/* Расширенная зона клика по городу */}
                    <circle r="12" fill="rgba(0,0,0,0.001)" />
                    {isHub && (
                      <circle
                        r={radius + 3.8}
                        fill="none"
                        stroke="#e11d48"
                        strokeWidth="1.5"
                        strokeDasharray="2.5 2"
                      />
                    )}
                    <circle
                      r={radius}
                      fill={
                        isRouteEndpoint
                          ? '#059669'
                          : isHub
                          ? '#e11d48'
                          : isTop3
                          ? '#ef4444'
                          : '#ffffff'
                      }
                      stroke="#0f172a"
                      strokeWidth="1.4"
                    />
                    <rect
                      x={badgeX}
                      y={pos.labelDy - 8.8}
                      width={badgeW}
                      height="12"
                      rx="2.5"
                      fill={isRouteEndpoint ? '#065f46' : 'rgba(15, 23, 42, 0.88)'}
                    />
                    <text
                      x={textX}
                      y={pos.labelDy}
                      textAnchor={isEnd ? 'end' : 'start'}
                      fill={isTop3 ? '#fde047' : '#ffffff'}
                      fontSize="8.8"
                      fontWeight="700"
                      fontFamily="JetBrains Mono"
                    >
                      {city.iata}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Нижняя панель легенды */}
          <div className="pt-3 flex flex-wrap items-center justify-between gap-4">
            {visualLayer === 'gravity' ? (
              <div className="flex flex-col">
                <div className="w-60 grid grid-cols-9 h-2.5 rounded-xs overflow-hidden border border-slate-400">
                  <div className="bg-[#3a98db]" />
                  <div className="bg-[#4cafdc]" />
                  <div className="bg-[#66c7c6]" />
                  <div className="bg-[#8adaa8]" />
                  <div className="bg-[#bae886]" />
                  <div className="bg-[#eeec6c]" />
                  <div className="bg-[#fec44f]" />
                  <div className="bg-[#fc8038]" />
                  <div className="bg-[#e3262a]" />
                </div>
                <div className="w-60 flex justify-between text-[10px] font-mono text-slate-600 mt-0.5">
                  <span>-100</span>
                  <span>-50</span>
                  <span>0</span>
                  <span>+40</span>
                  <span>+80</span>
                </div>
              </div>
            ) : (
              <div className="text-xs font-mono text-slate-600">
                Кликайте прямо по дугам маршрутов или кружкам городов на карте
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-700">
              {visualLayer === 'routes' ? (
                <>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-4 h-0.5 bg-emerald-600 inline-block" />
                    Выбранный прямой рейс
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-4 h-0.5 border-b-2 border-dashed border-rose-600 inline-block" />
                    Крюк через МСК
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full border border-dashed border-emerald-600 inline-block" />
                    Оптимум ВС ({aircraftSpec.optHighKm} км)
                  </span>
                </>
              ) : (
                <span className="inline-flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rotate-45 bg-yellow-400 border border-amber-900 inline-block" />
                  Барицентр притяжения
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Пруф-панель выбранного маршрута А -> Б + Совместимость с выбранным типом самолета */}
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

              {/* Блок проверки соответствия плеча выбранному типу самолета */}
              {(() => {
                const rStatus = getRouteRangeStatus(activeRoute.distanceKm, aircraftSpec);
                return (
                  <div className={`p-3 rounded-lg border text-xs space-y-1 ${rStatus.badgeClass}`}>
                    <div className="flex items-center justify-between font-bold">
                      <span>Борт: {aircraftSpec.name}</span>
                      <span className="font-mono">{rStatus.label}</span>
                    </div>
                    <div className="text-[11px] opacity-90">
                      Плечо {activeRoute.distanceKm} км (оптимум {aircraftSpec.optLowKm}–{aircraftSpec.optHighKm} км, предел {aircraftSpec.maxRangeKm} км). {aircraftSpec.caskNote}
                    </div>
                  </div>
                );
              })()}

              {/* Ключевые параметры маршрута */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <div className="text-xs text-slate-500">Прямой рейс ({aircraftSpec.seats} кресел)</div>
                  <div className="text-base font-bold font-mono text-slate-900 mt-0.5 tabular-nums">
                    {activeRoute.distanceKm} км · {activeRoute.flightTimeMin} мин
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-rose-50/70 border border-rose-200">
                  <div className="text-xs text-rose-700">Крюк через Москву (пунктир)</div>
                  <div className="text-base font-bold font-mono text-rose-600 mt-0.5 tabular-nums">
                    ×{Math.max(1.35, 1450 / Math.max(400, activeRoute.distanceKm)).toFixed(2)} длиннее
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
                  <div className="text-xs text-slate-500">Ожидаемый поток (год)</div>
                  <div className="text-base font-bold font-mono text-emerald-700 mt-0.5 tabular-nums">
                    {activeRoute.estimatedAnnualPax.toLocaleString('ru-RU')} пасс.
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
              Выберите маршрут кликом на карте или кнопкой ниже:
            </div>
            <div className="flex flex-wrap gap-1.5">
              {displayedRoutes.map((r) => {
                const rStatus = getRouteRangeStatus(r.distanceKm, aircraftSpec);
                return (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setSelectedRouteId(r.id)}
                    className={`px-2.5 py-1 text-xs font-mono rounded-md border transition-colors whitespace-nowrap shrink-0 ${
                      activeRoute?.id === r.id
                        ? 'bg-slate-900 text-white border-slate-900 font-semibold'
                        : rStatus.status === 'out_of_range'
                        ? 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100'
                        : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    {r.originIata}→{r.destIata}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Таблица всех маршрутов + Проверка дальности под выбранный тип ВС */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">
              Ведомость маршрутной сети и проверка досягаемости по типам ВС ({aircraftSpec.name})
            </h3>
            <p className="text-xs text-slate-600 mt-0.5">
              {aircraftSpec.role} · {aircraftSpec.caskNote}
            </p>
          </div>
          <div className="text-xs font-mono text-slate-600">
            Частота модели: {weeklyFreqPerRoute} пар/нед. · Кресел: {aircraftSpec.seats} · SLF: {loadFactorPct}%
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs font-semibold text-slate-600">
                <th className="py-2.5 px-4">Рейс</th>
                <th className="py-2.5 px-4">Направление (А → Б)</th>
                <th className="py-2.5 px-4 text-right">Плечо, км</th>
                <th className="py-2.5 px-4">Статус дальности ({aircraftSpec.name.split(' (')[0]})</th>
                <th className="py-2.5 px-4 text-right">Прямые конк.</th>
                <th className="py-2.5 px-4 text-right">Тариф RW, ₽</th>
                <th className="py-2.5 px-4 text-right">Пассажиропоток/год</th>
                <th className="py-2.5 px-4">Этап запуска</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-xs">
              {displayedRoutes.map((route) => {
                const isSelected = activeRoute?.id === route.id;
                const rStatus = getRouteRangeStatus(route.distanceKm, aircraftSpec);
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
                    <td className="py-2.5 px-4 text-right font-mono tabular-nums font-semibold text-slate-800">
                      {route.distanceKm} км
                    </td>
                    <td className="py-2.5 px-4">
                      <span
                        className={`inline-block px-2 py-0.5 rounded border text-[11px] font-medium ${rStatus.badgeClass}`}
                      >
                        {rStatus.label}
                      </span>
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
