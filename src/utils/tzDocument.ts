export const FULL_TEAM_TZ_MARKDOWN = `# ГЕНЕРАЛЬНОЕ ТЕХНИЧЕСКОЕ ЗАДАНИЕ (ТЗ) КОМАНДЫ ПМИ
## Проект: Интерактивная система стратегического планирования маршрутной сети а/к Red Wings (2026–2028)

---

# ЧАСТЬ 1. ЧТО ЭТО ЗА ПРОЕКТ И ЗАЧЕМ МЫ ЕГО ДЕЛАЕМ (КОНТЕКСТ ДЛЯ ВСЕЙ КОМАНДЫ)

## 1.1. В чем реальная бизнес-проблема авиакомпании Red Wings?
Российский рынок авиаперевозок достиг потолка — 108,9 млн пассажиров по итогам 2025 года и перестал расти органически. Одновременно перед Red Wings стоят три жестких ограничения:
1. Дефицит флота и сдвиг поставок: серийные поставки новых импортозамещенных региональных самолетов SJ-100 (~100 кресел, дальность 2 000–3 000 км) сдвинуты на вторую половину 2027 года.
2. Сокращение государственных субсидий (ПП РФ №1242): маршруты должны быть коммерчески окупаемыми даже при снижении господдержки.
3. Сверхконцентрация в Москве: более 60% межрегиональных пассажиров вынуждены летать через Москву, теряя по 5–8 часов в пути.

Чтобы увеличить свою долю рынка (сейчас у Red Wings ~4,465 млн пасс./год, или ~4,10% рынка РФ), нужно математически выбрать одну из двух стратегий:
- ГИПОТЕЗА А: Открытие нового регионального хаба (Hub & Spoke) в одном из городов Топ-3 со стыковочными волнами.
- ГИПОТЕЗА Б: Запуск прямых межрегиональных рейсов (Point-to-Point, P2P) в обход Москвы между городами Топ-3 без затрат на содержание нового хаба.

---

# ЧАСТЬ 2. ПОДРОБНОЕ ТЗ ДЛЯ РАЗРАБОТЧИКА №1 (DATA ENGINEERING & ПАРСИНГ)

- Ветка Git: feat/data-parsers
- Твои папки (редактируешь ТОЛЬКО их): data/raw/, data/processed/, src/parsers/
- Чужие файлы НЕ ТРОГАТЬ: app.py, src/ui/, src/scoring/, src/models/

## Команды для старта (в терминале VS Code / PyCharm):
git checkout main
git pull origin main
git checkout -b feat/data-parsers
pip install -r requirements.txt

## ПЛАН МИНИМУМ (к 20:00):
1. В src/parsers/rosstat_loader.py реализовать load_rosstat_and_rosaviatsia() -> pd.DataFrame для 12 городов (KUF, GOJ, UFA, KZN, MRV, PEE, SVX, CEK, TJM, VOG, GSV, OMS) со строгими колонками:
   iata, city_name, region, lat, lon, population_mln, airport_pax_mln, dist_to_mow_km, competitor_gap_score, tourism_demand_score, main_competitor.
2. В src/parsers/build_dataset.py реализовать get_network_routes(hypothesis: str, hub_iata: str = "KUF") -> pd.DataFrame для 10–12 маршрутов со строгими колонками:
   route_code, origin_iata, origin_city, dest_iata, dest_city, lat_o, lon_o, lat_d, lon_d, distance_km, flight_time_min, competitor_flights_weekly, competitor_fare_rub, subsidy_eligible, launch_quarter, proof_source.

## ПЛАН МАКСИМУМ (Киллер-фичи):
1. Коэффициент крюка через Москву (moscow_detour_ratio = (Dist(A, MOW) + Dist(MOW, B)) / Dist(A, B)).
2. Время в пути на поезде (rail_travel_hours) — доказательство преимущества самолета при поездке > 12 часов.

## Команды для сдачи работы:
python -m src.parsers.build_dataset
git add data/ src/parsers/
git commit -m "feat(data): add 12 candidate cities and 12 routes with Rosstat/Rosaviatsia proofs"
git push origin feat/data-parsers

---

# ЧАСТЬ 3. ПОДРОБНОЕ ТЗ ДЛЯ РАЗРАБОТЧИКА №2 (СКОРИНГ ГОРОДОВ + ПРИТЯЖЕНИЕ НЬЮТОНА)

- Ветка Git: feat/city-scoring
- Твои файлы (редактируешь ТОЛЬКО их): src/scoring/normalizer.py, src/scoring/city_scorer.py, notebooks/02_scoring_check.ipynb

## Команды для старта:
git checkout main
git pull origin main
git checkout -b feat/city-scoring
pip install -r requirements.txt

## ПЛАН МИНИМУМ (к 20:00):
1. В src/scoring/normalizer.py реализовать min_max_normalize(series) в шкалу [0..100] и функцию оптимума дальности SJ-100 от Москвы (пик баллов на 800–1500 км).
2. В src/scoring/city_scorer.py реализовать get_scored_cities(weights: ScoringWeights) -> List[CityScoreDTO], которая считает взвешенный балл по 4 весам из ползунков, сортирует города по убыванию и ставит первым трем is_top3 = True.

## ПЛАН МАКСИМУМ (Киллер-фича ПМИ — Гравитационная модель Ньютона):
1. 2-часовая изохрона аэропорта (Catchment Area): P_eff = P_city + sum(P_sat * exp(-0.45 * t_hours)), например Самара + Тольятти = 2.74 млн чел.
2. Матрица гравитационного притяжения пар городов:
   G_ij = K * ((P_i * W_i)^0.85 * (P_j * W_j)^0.85) / (D_ij^gamma * (1 + 0.3 * C_ij))
   Сумма гравитаций дает лучший город под Хаб, а топ-10 пар G_ij дают лучшие прямые маршруты!

## Команды для сдачи работы:
pytest tests/test_contracts.py
git add src/scoring/ notebooks/
git commit -m "feat(scoring): implement weighted city scorer and Newton gravity model"
git push origin feat/city-scoring

---

# ЧАСТЬ 4. ПОДРОБНОЕ ТЗ ДЛЯ РАЗРАБОТЧИКА №3 (ФИНМОДЕЛЬ SJ-100 И ЮНИТ-ЭКОНОМИКА)

- Ветка Git: feat/fin-model
- Твои файлы (редактируешь ТОЛЬКО их): src/models/unit_economics.py, src/models/sj100_fleet.py, tests/test_unit_economics.py

## Команды для старта:
git checkout main
git pull origin main
git checkout -b feat/fin-model
pip install -r requirements.txt

## ПЛАН МИНИМУМ (к 20:00):
Реализовать в src/models/unit_economics.py функцию evaluate_hypotheses(params: FinModelInput, top_cities: List[CityScoreDTO]) -> ComparisonBundleDTO.
- На входе: load_factor_pct (%), avg_fare_rub (руб.), weekly_freq_per_route (рейсов/нед), aircraft_seats (100 кресел SJ-100), active_routes_count (8..12), scenario ("base" / "conservative"), hub_iata.
- На выходе для Гипотезы А (Хаб) и Гипотезы Б (Прямые рейсы P2P):
  1. Пассажиропоток в год (annual_passengers)
  2. Выручка в млн руб. (annual_revenue_mln_rub)
  3. Операционная прибыль EBITDAR (ebitdar_mln_rub) и маржа (%)
  4. Прирост доли рынка РФ в % от 108,9 млн пасс. (market_share_delta_pct)
  5. Потребность в бортах SJ-100 (required_aircraft_sj100) и точка безубыточности (breakeven_load_factor_pct)

## ПЛАН МАКСИМУМ (Киллер-фичи):
1. Ценовая эластичность спроса: SLF(Fare) = SLF_0 * (Fare / 8400)^(-0.65) и поиск оптимального тарифа, максимизирующего прибыль.
2. Стресс-тест безубыточности борта SJ-100 при отмене госсубсидий ПП РФ №1242.

## Команды для сдачи работы:
pytest tests/
git add src/models/ tests/
git commit -m "feat(models): add SJ-100 unit economics and break-even calculator"
git push origin feat/fin-model

---

# ЧАСТЬ 5. ПОДРОБНОЕ ТЗ ДЛЯ РАЗРАБОТЧИКА №4 (STREAMLIT ДАШБОРД И КАРТА СЕТИ)

- Ветка Git: feat/streamlit-dashboard
- Твои файлы (редактируешь ТОЛЬКО их): app.py, src/ui/*, src/mocks/mock_provider.py

## Команды для старта:
git checkout main
git pull origin main
git checkout -b feat/streamlit-dashboard
pip install -r requirements.txt
USE_MOCKS=1 streamlit run app.py

## ПЛАН МИНИМУМ (к 20:00):
1. src/ui/sidebar_controls.py — ползунки весов скоринга (4 шт.) и параметров финмодели (SLF %, тариф, частота, число маршрутов, сценарий Base/Conservative).
2. src/ui/kpi_cards.py — плашка победителя + сравнение Гипотезы А и Гипотезы Б бок о бок.
3. src/ui/map_renderer.py — интерактивная карта России (Plotly Scattergeo) с 12 городами, 8–12 маршрутами и таблицей пруфов под картой.

## ПЛАН МАКСИМУМ (Визуальные киллер-фичи):
1. Отрисовка на карте сравнения «Красный пунктир крюка через Москву vs Зеленая дуга прямого рейса Red Wings» при выборе маршрута.
2. Тепловая карта (Heatmap) Частота × Тариф, показывающая зоны победы Хаба и P2P.

## Команды для сдачи работы:
git add app.py src/ui/ src/mocks/
git commit -m "feat(ui): build interactive Streamlit dashboard and Plotly route map"
git push origin feat/streamlit-dashboard
`;

export function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function downloadTeamTzWordDoc() {
  const htmlDoc = `<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
  <head><meta charset='utf-8'><title>ТЗ Команды Red Wings (ПМИ)</title>
  <style>
    body { font-family: Calibri, Arial, sans-serif; line-height: 1.45; color: #111827; }
    h1 { color: #be123c; border-bottom: 2px solid #be123c; padding-bottom: 4px; margin-top: 24px; }
    h2 { color: #0f172a; margin-top: 16px; }
    pre { background: #f1f5f9; padding: 10px; border: 1px solid #cbd5e1; font-family: Consolas, monospace; font-size: 10pt; white-space: pre-wrap; }
  </style>
  </head>
  <body>
    <pre>${FULL_TEAM_TZ_MARKDOWN.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
  </body></html>`;

  downloadFile(htmlDoc, 'TZ_Komandy_Red_Wings.doc', 'application/msword;charset=utf-8');
}
