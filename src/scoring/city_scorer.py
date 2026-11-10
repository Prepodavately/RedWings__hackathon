"""Скоринг Dev 2: auto выбирает case или предварительный exploratory.

Общий контракт сохранён. Пятый вес задаёт moscow_transfer_weight.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import re
import warnings

import numpy as np
import pandas as pd

from src.schemas.contracts import CityScoreDTO, ScoringWeights
from src.scoring.normalizer import distance_sweet_spot_score, min_max_normalize

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data/processed/cities_features.parquet"
Mode = Literal["auto", "case", "exploratory"]
ResolvedMode = Literal["case", "exploratory"]
BASE_CRITERIA = ("population", "hub_distance", "competitor_gap", "tourism_demand")
METRICS = {
    "population": "population_mln",
    "hub_distance": "dist_to_mow_km",
    "competitor_gap": "competitor_gap_score",
    "tourism_demand": "tourism_demand_score",
    "moscow_transfer": "moscow_transfer_share_pct",
    "airport_pax": "airport_pax_mln",
    "airport_feasibility": "airport_feasible",
}
REFERENCE_HUBS = frozenset({"MOW", "SVO", "DME", "VKO", "ZIA", "SVX"})
CASE_REQUIRED_COLUMNS = frozenset(
    {"moscow_transfer_share_pct", "airport_feasible"}
    | {f"{prefix}_{criterion}" for criterion in METRICS
       for prefix in ("src", "status", "period", "method")}
)

# Согласованные сценарные времена, НЕ измеренные автомобильные изохроны.
# Ключ включает аэропорт: Волжский район Самары нельзя спутать с г. Волжским.
AIRPORT_ACCESS_HOURS = {
    "KUF": {"тольятти": 0.75},
    "GOJ": {"дзержинск": 0.55},
    "GSV": {"энгельс": 0.70},
    "VOG": {"волжский": 0.60},
    "MRV": {"пятигорск": 0.35, "ессентуки": 0.55, "кисловодск": 0.75},
}
DEFAULT_ACCESS_HOURS = 0.65
CATCHMENT_LIMIT_HOURS = 2.0
GRAVITY_DISTANCE_KNOTS_KM = (300.0, 800.0, 1500.0, 3000.0)


def _finite_parameter(value: float, name: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name}: нужно конечное число") from exc
    if isinstance(value, (bool, np.bool_)) or not np.isfinite(number) or number < 0 or (positive and number == 0):
        raise ValueError(f"{name}: нужно {'положительное' if positive else 'неотрицательное'} конечное число")
    return number


def _identified_cities(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "iata" not in df:
        raise ValueError("Нужна непустая таблица городов с iata")
    result = df.copy(deep=True)
    if not result["iata"].map(lambda value: isinstance(value, str)).all():
        raise ValueError("iata должен быть строкой")
    result["iata"] = result["iata"].str.strip().str.upper()
    if not result["iata"].str.fullmatch(r"[A-Z]{3}").all() or result["iata"].duplicated().any():
        raise ValueError("Нужны уникальные трёхбуквенные IATA-коды")
    return result


def _access_details(df: pd.DataFrame, lam: float) -> tuple[pd.DataFrame, list[float]]:
    lam = _finite_parameter(lam, "lam")
    cities = _identified_cities(df)
    _number_column(cities, "population_city_mln", 0)
    if "agglomeration_members" not in cities:
        raise ValueError("Нет agglomeration_members; пустая строка означает явно заданное отсутствие спутников")
    rows, totals = [], []
    # Запятая здесь — разделитель тысяч, а не десятичная запятая.
    population_pattern = r"(?:[0-9]{1,3}(?:[, \u00a0\u202f][0-9]{3})+|[0-9]+)"
    member_pattern = re.compile(rf"(?P<name>.+?)\s*\((?P<population>{population_pattern})\)\s*")
    for city in cities.itertuples(index=False):
        if not isinstance(city.agglomeration_members, str):
            raise ValueError(f"{city.iata}: agglomeration_members должен быть строкой; неизвестность не равна нулю")
        total = float(city.population_city_mln)
        seen = set()
        members = city.agglomeration_members.split(";") if city.agglomeration_members.strip() else []
        for member in members:
            match = member_pattern.fullmatch(member.strip())
            if match is None:
                raise ValueError(f"{city.iata}: неверная запись спутника {member!r}; ожидается Название (123,456)")
            name = match["name"].strip()
            key = " ".join(name.casefold().replace("ё", "е").split())
            if key in seen:
                raise ValueError(f"{city.iata}: спутник {name!r} указан повторно")
            seen.add(key)
            population = int(re.sub(r"[,\s\u00a0\u202f]", "", match["population"]))
            matches = [hours for token, hours in AIRPORT_ACCESS_HOURS.get(city.iata, {}).items() if token in key]
            if len(matches) > 1:
                raise ValueError(f"{city.iata}: неоднозначное время доезда для {name!r}")
            time_h = _finite_parameter(matches[0] if matches else DEFAULT_ACCESS_HOURS, "access_time_h")
            included = time_h <= CATCHMENT_LIMIT_HOURS
            weight = float(np.exp(-lam * time_h)) if included else 0.0
            contribution = population / 1_000_000 * weight
            total += contribution
            rows.append({
                "iata": city.iata, "satellite": name, "satellite_population": population,
                "access_time_h": time_h, "time_source": "scenario_override" if matches else "scenario_default",
                "within_two_hours": included, "decay_weight": weight,
                "effective_contribution_mln": contribution,
            })
        if not np.isfinite(total):
            raise ValueError(f"{city.iata}: эффективное население не является конечным числом")
        totals.append(total)
    columns = ["iata", "satellite", "satellite_population", "access_time_h", "time_source",
               "within_two_hours", "decay_weight", "effective_contribution_mln"]
    return pd.DataFrame(rows, columns=columns), totals


def calculate_effective_population(df: pd.DataFrame, lam: float = 0.45) -> pd.Series:
    """P_eff = P_city + sum(P_sat * exp(-lam*t)) для t <= 2 часов, млн чел.

    Численность спутников в скобках — люди, population_city_mln — миллионы.
    Основной город учитывается целиком; времена — сценарный словарь, без GIS.
    Возвращается Series с исходным индексом; входная таблица не изменяется.
    Детали включены в attrs['catchment_details'] для проверки каждого слагаемого.
    """
    details, values = _access_details(df, lam)
    result = pd.Series(values, index=df.index, name="effective_population_mln", dtype=float)
    result.attrs.update({
        "lam": float(lam), "limit_hours": CATCHMENT_LIMIT_HOURS,
        "default_access_time_h": DEFAULT_ACCESS_HOURS,
        "time_status": "scenario_assumptions_not_measured_isochrones",
        "catchment_details": details.to_dict("records"),
    })
    return result


def _gravity_range_weight(distances: np.ndarray) -> np.ndarray:
    """Сценарный фильтр: 0 до 300/от 3000, 1 на 800–1500, линейные склоны."""
    return np.interp(distances, GRAVITY_DISTANCE_KNOTS_KM, [0.0, 1.0, 1.0, 0.0], left=0.0, right=0.0)


def calculate_gravity_matrix(
    cities_df: pd.DataFrame, routes_df: pd.DataFrame | None = None, gamma: float = 1.15,
) -> pd.DataFrame:
    """G_ij = P_eff_i*P_eff_j*sqrt(q_i*q_j)*W(d)/(d**gamma*(1+F_ij)).

    q = зарплата региона / средняя зарплата городов-кандидатов. P_eff измеряется
    в млн человек; d — гаверсинус между аэропортами, км. Отсутствующие F_ij
    и NaN принимаются за 0 по сценарию, с явной маской отсутствия наблюдения.
    F_ij направленный: обратное направление не копируется автоматически.
    Возвращается квадратная матрица с нулевой диагональю. Сумма строки —
    gravity_hub_potential (в attrs и через .sum(axis=1)), не пассажиропоток.
    Входы не меняются. Если P_eff не передано, рассчитывается при lam=0.45.
    """
    gamma = _finite_parameter(gamma, "gamma", positive=True)
    cities = _identified_cities(cities_df)
    for column, low, high in (("lat", -90, 90), ("lon", -180, 180)):
        _number_column(cities, column, low, high)
    _number_column(cities, "avg_wage_rub_region", 0)
    if (cities["avg_wage_rub_region"] <= 0).any():
        raise ValueError("avg_wage_rub_region должен быть положительным")
    population_source = "provided_effective_population_mln"
    if "effective_population_mln" not in cities:
        cities["effective_population_mln"] = calculate_effective_population(cities)
        population_source = "derived_lam_0.45"
    _number_column(cities, "effective_population_mln", 0)
    codes = cities["iata"].tolist()
    index = {code: i for i, code in enumerate(codes)}
    n = len(codes)
    lat, lon = np.radians(cities["lat"].to_numpy()), np.radians(cities["lon"].to_numpy())
    a = np.sin((lat[:, None] - lat[None, :]) / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin((lon[:, None] - lon[None, :]) / 2) ** 2
    distances = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    range_weight = _gravity_range_weight(distances)
    frequencies = np.zeros((n, n), dtype=float)
    observed = np.zeros((n, n), dtype=bool)
    if routes_df is not None and not routes_df.empty:
        required = {"origin_iata", "dest_iata", "competitor_flights_weekly"}
        if not required <= set(routes_df.columns):
            raise ValueError(f"routes_df: нет колонок {sorted(required - set(routes_df.columns))}")
        routes = routes_df.loc[:, sorted(required)].copy(deep=True)
        for column in ("origin_iata", "dest_iata"):
            if not routes[column].map(lambda value: isinstance(value, str)).all():
                raise ValueError(f"{column}: нужны строковые IATA-коды")
            routes[column] = routes[column].str.strip().str.upper()
        routes = routes.loc[routes["origin_iata"].isin(codes) & routes["dest_iata"].isin(codes)]
        if routes.duplicated(["origin_iata", "dest_iata"]).any():
            raise ValueError("routes_df: повтор пары А→Б; сначала агрегируйте частоты по направлению")
        try:
            freq = pd.to_numeric(routes["competitor_flights_weekly"], errors="raise").astype(float)
        except (ValueError, TypeError) as exc:
            raise ValueError("competitor_flights_weekly: нужны числа или NaN") from exc
        values = freq.fillna(0).to_numpy()
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("competitor_flights_weekly: частоты должны быть конечными и неотрицательными")
        for origin, dest, value, known in zip(routes["origin_iata"], routes["dest_iata"], values, freq.notna()):
            frequencies[index[origin], index[dest]] = value
            observed[index[origin], index[dest]] = bool(known)
    population = cities["effective_population_mln"].to_numpy()
    wages = cities["avg_wage_rub_region"].to_numpy()
    # Масштабирование перед средним исключает переполнение суммы больших зарплат.
    wages_scaled = wages / wages.max()
    purchasing_power = wages_scaled / wages_scaled.mean()
    gravity = np.zeros((n, n), dtype=float)
    active = range_weight > 0  # также исключает диагональ и совпадающие координаты
    try:
        with np.errstate(over="raise", invalid="raise"):
            mass = (population[:, None] * population[None, :]
                    * np.sqrt(purchasing_power[:, None]) * np.sqrt(purchasing_power[None, :]))
        with np.errstate(over="ignore", under="ignore"):
            distance_decay = np.exp(-gamma * np.log(distances[active]))
        gravity[active] = (mass[active] * range_weight[active] * distance_decay
                           / (1.0 + frequencies[active]))
    except FloatingPointError as exc:
        raise ValueError("Переполнение гравитационного индекса; проверьте единицы населения и доходов") from exc
    if not np.isfinite(gravity).all():
        raise ValueError("Гравитационный индекс должен быть конечным")
    result = pd.DataFrame(gravity, index=pd.Index(codes, name="origin_iata"),
                          columns=pd.Index(codes, name="dest_iata"))
    off_diagonal = ~np.eye(n, dtype=bool)
    result.attrs.update({
        "model": "scenario_gravity_index_not_passenger_forecast", "gamma": gamma,
        "population_unit": "million_people", "population_source": population_source,
        "purchasing_power_method": "regional_wage / candidate_mean_regional_wage",
        "purchasing_power_index": dict(zip(codes, purchasing_power.tolist())),
        "distance_method": "airport_haversine_R_6371_km", "range_knots_km": list(GRAVITY_DISTANCE_KNOTS_KM),
        "competition_method": "directional_1_over_1_plus_F; missing_or_NaN_F_is_zero",
        "missing_competition_pairs": int((~observed & off_diagonal).sum()),
        "competition_observed": observed.tolist(), "competitor_flights_weekly": frequencies.tolist(),
        "distance_km": distances.tolist(), "range_weight": range_weight.tolist(),
        "gravity_hub_potential": result.sum(axis=1).to_dict(),
    })
    return result


@dataclass
class ScoringResult:
    table: pd.DataFrame
    audit: pd.DataFrame
    weights: dict[str, float]
    mode: str
    hypothesis: str
    limitations: list[str]
    normalization_bounds: dict[str, list[float]]

    @property
    def top3(self) -> pd.DataFrame:
        return self.table.loc[self.table["is_top3"]].copy()


def load_features(path: str | Path | None = None) -> pd.DataFrame:
    """Читать витрину; отсутствующий стандартный Parquet собрать загрузчиком Dev 1.

    Загрузчик читает локальные исходные CSV, не создаёт Parquet и не подставляет
    моки. Ошибка произвольного пути или повреждённого файла остаётся ошибкой.
    """
    path = Path(path) if path is not None else DEFAULT_DATA_PATH
    if not path.is_file():
        if path.resolve() == DEFAULT_DATA_PATH.resolve() and not path.exists():
            from src.parsers.rosstat_loader import load_rosstat_and_rosaviatsia

            features = load_rosstat_and_rosaviatsia()
            if not isinstance(features, pd.DataFrame) or features.empty:
                raise ValueError("Загрузчик Dev 1 должен вернуть непустой DataFrame")
            features = features.copy(deep=True)
            features.attrs["input_source"] = "src.parsers.rosstat_loader.load_rosstat_and_rosaviatsia"
            warnings.warn(
                "Стандартный cities_features.parquet отсутствует; использован загрузчик Dev 1 из локальных CSV.",
                UserWarning, stacklevel=2,
            )
            return features
        raise FileNotFoundError(
            f"Нет витрины {path}. Проверьте путь к CSV/Parquet Dev 1; "
            "загрузчик применяется только к отсутствующей стандартной витрине."
        )
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype={"iata": str})
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    raise ValueError("Входная витрина должна быть CSV или Parquet")


def _number_column(df: pd.DataFrame, column: str, low: float,
                   high: float | None = None) -> None:
    if column not in df:
        raise ValueError(f"Отсутствует колонка {column}")
    try:
        df[column] = pd.to_numeric(df[column], errors="raise").astype(float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{column}: ожидаются числа") from exc
    values = df[column].to_numpy()
    if not np.isfinite(values).all():
        raise ValueError(f"{column}: есть NaN/inf; заполните данные или метод оценки")
    if (values < low).any() or (high is not None and (values > high).any()):
        raise ValueError(f"{column}: значение вне диапазона [{low}, {high}]")


def _nonblank(value: object) -> bool:
    return pd.notna(value) and bool(str(value).strip())


def _feasible(value: object) -> bool | None:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if pd.isna(value) or str(value).strip().lower() in {"", "unknown"}:
        return None
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError("airport_feasible: нужны true/false/unknown, не числовые коды")


def prepare_features(features: pd.DataFrame) -> pd.DataFrame:
    """10+ кандидатов; для скоринга достаточно dist_to_mow_km от Dev 1.

    Дополнительные расстояния до SVX/ближайшего узла сохраняются для анализа,
    если они переданы либо есть координаты со строкой SVX. Они не участвуют
    в балле расстояния. Это признаки скрининга, не длина будущего рейса А→Б.
    """
    df = features.copy(deep=True).reset_index(drop=True)
    for col in ("iata", "city_name", "region"):
        if col not in df or not df[col].map(_nonblank).all():
            raise ValueError(f"Нужна непустая колонка {col}")
    if not df["iata"].map(lambda x: isinstance(x, str)).all():
        raise ValueError("iata должен быть строкой")
    df["iata"] = df["iata"].str.strip().str.upper()
    if not df["iata"].str.fullmatch(r"[A-Z]{3}").all() or df["iata"].duplicated().any():
        raise ValueError("Нужны уникальные трёхбуквенные IATA-коды")
    if len(df) < 10:
        raise ValueError(f"По ТЗ нужно не менее 10 кандидатов, получено {len(df)}")
    for col in ("population_mln", "airport_pax_mln", "dist_to_mow_km"):
        _number_column(df, col, 0)
    if (df["population_mln"] <= 0).any():
        raise ValueError("population_mln должен быть положительным")
    for col in ("competitor_gap_score", "tourism_demand_score"):
        _number_column(df, col, 0, 100)
    if "dist_to_svx_km" not in df and {"lat", "lon"} <= set(df.columns) and df["iata"].eq("SVX").any():
        for col, low, high in (("lat", -90, 90), ("lon", -180, 180)):
            _number_column(df, col, low, high)
        anchor = df.loc[df["iata"].eq("SVX")]
        lat, lon = np.radians(df["lat"].to_numpy()), np.radians(df["lon"].to_numpy())
        lat0, lon0 = np.radians(anchor.iloc[0][["lat", "lon"]].to_numpy(dtype=float))
        a = np.sin((lat - lat0) / 2) ** 2 + np.cos(lat) * np.cos(lat0) * np.sin((lon - lon0) / 2) ** 2
        df["dist_to_svx_km"] = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    if "dist_to_svx_km" in df:
        _number_column(df, "dist_to_svx_km", 0)
        df["distance_to_nearest_hub_km"] = df[["dist_to_mow_km", "dist_to_svx_km"]].min(axis=1)
    if "airport_feasible" not in df:
        df["airport_feasible"] = None
    df["airport_feasible"] = df["airport_feasible"].map(_feasible)
    return df


def audit_features(df: pd.DataFrame) -> pd.DataFrame:
    """Одна строка на город/критерий; отсутствующие метаданные видны явно."""
    rows = []
    for _, city in df.iterrows():
        for criterion, column in METRICS.items():
            rows.append({
                "iata": city["iata"], "criterion": criterion, "value": city.get(column),
                **{prefix: city.get(f"{prefix}_{criterion}")
                   for prefix in ("src", "status", "period", "method", "low", "high")},
            })
    return pd.DataFrame(rows)


def _validate_case(df: pd.DataFrame, audit: pd.DataFrame) -> None:
    _number_column(df, "moscow_transfer_share_pct", 0, 100)
    errors = []
    if df["airport_feasible"].isna().any():
        errors.append("airport_feasible: не подтверждена возможность работы аэропорта")
    for field in ("src", "status", "period", "method"):
        missing = ~audit[field].map(_nonblank)
        if missing.any():
            keys = sorted(audit.loc[missing, "criterion"].unique())
            errors.append(f"{field}: нет метаданных для {', '.join(keys)}")
    if not audit["status"].isin(["observed", "derived", "estimated"]).all():
        errors.append("status: допустимы observed/derived/estimated; demo и missing запрещены")
    for criterion, group in audit.groupby("criterion"):
        if group["period"].dropna().nunique() > 1:
            errors.append(f"period_{criterion}: периоды городов не совпадают")
    for row in audit.loc[audit["status"].eq("estimated")].itertuples():
        if row.criterion == "airport_feasibility":
            errors.append(f"{row.iata}: airport_feasible требует проверки, а не оценки")
            continue
        try:
            low, value, high = float(row.low), float(row.value), float(row.high)
            valid = np.isfinite([low, value, high]).all() and 0 <= low <= value <= high
            if row.criterion in {"moscow_transfer", "tourism_demand", "competitor_gap"}:
                valid = valid and high <= 100
        except (ValueError, TypeError):
            valid = False
        if not valid:
            errors.append(f"{row.iata}/{row.criterion}: нужен диапазон low <= value <= high")
    if errors:
        raise ValueError("Полный расчёт case невозможен:\n- " + "\n- ".join(errors))


def effective_weights(weights: ScoringWeights, *, mode: ResolvedMode,
                      moscow_transfer_weight: float = 0.20) -> dict[str, float]:
    if mode not in {"case", "exploratory"}:
        raise ValueError("mode должен быть case или exploratory")
    try:
        base = np.array([getattr(weights, f"w_{c}") for c in BASE_CRITERIA], dtype=float)
        transfer = float(moscow_transfer_weight)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Веса должны быть числами в ScoringWeights") from exc
    if not np.isfinite(base).all() or (base < 0).any() or not np.isfinite(base.sum()) or base.sum() <= 0:
        raise ValueError("Веса должны быть конечными, неотрицательными; сумма > 0")
    if not np.isfinite(transfer) or not 0 <= transfer <= 1:
        raise ValueError("moscow_transfer_weight должен лежать в [0, 1]")
    result = dict(zip(BASE_CRITERIA, (base / base.sum()).tolist()))
    if mode == "case":
        result = {key: value * (1 - transfer) for key, value in result.items()}
        result["moscow_transfer"] = transfer
    return result


def _resolve_mode(features: pd.DataFrame, mode: Mode) -> tuple[ResolvedMode, str | None]:
    if mode not in {"auto", "case", "exploratory"}:
        raise ValueError("mode должен быть auto, case или exploratory")
    if mode != "auto":
        return mode, None
    missing = sorted(CASE_REQUIRED_COLUMNS - set(features.columns))
    if not missing:
        return "case", None
    reason = (
        "Предварительный рейтинг: auto выбрал exploratory; нет полей для case: "
        + ", ".join(missing)
        + ". Используются четыре критерия; покажите этот статус в интерфейсе."
    )
    return "exploratory", reason


def score_cities(features: pd.DataFrame, weights: ScoringWeights | None = None, *,
                 mode: Mode = "auto", hypothesis: str = "hub",
                 moscow_transfer_weight: float = 0.20) -> ScoringResult:
    """Возвращает рейтинг, вклады критериев, аудит и ограничения.

    auto (по умолчанию): case при полной схеме, иначе exploratory с предупреждением.
    При полной схеме некорректные значения не маскируются сменой режима.
    Явный case: пять критериев, источники, методы, периоды, airport_feasible.
    exploratory: четыре имеющихся критерия; результат предварительный.
    Для нового хаба опорные Мск/Екб исключаются, для p2p могут быть концами маршрута.
    """
    if hypothesis not in {"hub", "p2p"}:
        raise ValueError("hypothesis должен быть hub или p2p")
    mode, auto_reason = _resolve_mode(features, mode)
    weight_map = effective_weights(weights or ScoringWeights(), mode=mode,
                                   moscow_transfer_weight=moscow_transfer_weight)
    df = prepare_features(features)
    audit = audit_features(df)
    if mode == "case":
        _validate_case(df, audit)
    if auto_reason:
        warnings.warn(auto_reason, UserWarning, stacklevel=2)
    limits = [
        "Веса — экспертное предположение; результат условен относительно данных и критериев.",
        "Рейтинг городов не доказывает спрос, прибыльность маршрутов или победу гипотезы.",
        "Источники записаны поставщиком данных; наличие ссылки не означает внешнюю проверку.",
    ]
    if mode == "exploratory":
        limits += [
            "ПРЕДВАРИТЕЛЬНО: доля пассажиров с пересадкой в Москве не участвует в формуле.",
            "Происхождение, сопоставимость периодов и возможности аэропортов требуют проверки.",
            "tourism_demand_score и competitor_gap_score используются в определении Dev 1; проверьте прокси.",
        ]
    if auto_reason:
        limits.append(auto_reason)
    limits.append("Расстояние: max(35, 100 - 65 * |dist_to_mow_km - 1150| / 1200), эвристика команды.")
    bounds = {}
    for criterion in weight_map:
        column = METRICS[criterion]
        if criterion == "population":
            df[f"score_{criterion}"] = min_max_normalize(df[column])
            bounds[criterion] = [float(df[column].min()), float(df[column].max())]
        elif criterion == "hub_distance":
            df[f"score_{criterion}"] = distance_sweet_spot_score(df[column])
            bounds[criterion] = [35.0, 100.0]
        else:
            df[f"score_{criterion}"] = df[column]
            bounds[criterion] = [0.0, 100.0]
        df[f"contribution_{criterion}"] = df[f"score_{criterion}"] * weight_map[criterion]
    df["total_score"] = df[[f"contribution_{c}" for c in weight_map]].sum(axis=1)
    df["exclusion_reason"] = ""
    if hypothesis == "hub":
        df.loc[df["iata"].isin(REFERENCE_HUBS), "exclusion_reason"] = "Опорный узел Мск/Екб: не кандидат на новый хаб"
    df.loc[df["airport_feasible"].eq(False), "exclusion_reason"] = "Аэропорт не прошёл проверку осуществимости"
    df["eligible"] = df["exclusion_reason"].eq("")
    if df["eligible"].sum() < 3:
        raise ValueError("После исключений осталось менее трёх допустимых кандидатов")
    df = df.sort_values(["eligible", "total_score", "iata"], ascending=[False, False, True]).reset_index(drop=True)
    df["rank"] = pd.Series(pd.NA, index=df.index, dtype="Int64")
    df.loc[df["eligible"], "rank"] = np.arange(1, int(df["eligible"].sum()) + 1)
    df["is_top3"] = (df["rank"] <= 3).fillna(False)
    cutoff = df.loc[df["rank"].eq(3), "total_score"].iloc[0]
    tied = df["eligible"] & np.isclose(df["total_score"], cutoff, rtol=0, atol=1e-10)
    df["cutoff_tie"] = tied & (tied.sum() > 1)
    if df["cutoff_tie"].any():
        limits.append("На границе топ-3 равенство баллов; порядок по IATA технический, превосходство не доказано.")
    df["result_status"] = "preliminary" if mode == "exploratory" else "conditional_on_supplied_evidence"
    return ScoringResult(df, audit, weight_map, mode, hypothesis, limits, bounds)


def get_scored_cities(weights: ScoringWeights, *, data: pd.DataFrame | None = None,
                      path: str | Path | None = None, mode: Mode = "auto",
                      hypothesis: str = "p2p", moscow_transfer_weight: float = 0.20) -> list[CityScoreDTO]:
    """API Dev 4: полный список DTO, включая SVX; выбор нового хаба — явный hub.

    В отличие от аналитического score_cities, по умолчанию p2p для полного
    списка городов карты/селектора. is_top3 по-прежнему отражает допустимость
    выбранной гипотезы. rank в DTO — позиция в полном списке, в том числе
    для исключённых строк; причины исключений доступны через score_cities.
    """
    result = score_cities(load_features(path) if data is None else data, weights,
                          mode=mode, hypothesis=hypothesis,
                          moscow_transfer_weight=moscow_transfer_weight)
    if mode == "exploratory":
        warnings.warn("Предварительный рейтинг: нет критерия пересадок через Москву; покажите ограничения в UI.",
                      UserWarning, stacklevel=2)
    return [CityScoreDTO(
        iata=row.iata, city_name=row.city_name, region=row.region,
        population_mln=round(float(row.population_mln), 2),
        airport_pax_mln=round(float(row.airport_pax_mln), 2),
        total_score=round(float(row.total_score), 2), rank=position, is_top3=bool(row.is_top3),
    ) for position, row in enumerate(result.table.itertuples(), start=1)]


def weight_sensitivity(result: ScoringResult, *, n_samples: int = 2000,
                       relative_change: float = 0.20, seed: int = 42) -> pd.DataFrame:
    """Вариация каждого веса ±20%, затем нормировка. Нулевые веса остаются 0.

    Частота топ-3 в эксперименте НЕ является вероятностью успеха.
    Данные/границы шкал фиксированы; их неопределённость здесь не моделируется.
    Равенства разрешаются по IATA, как в основном расчёте.
    """
    if isinstance(n_samples, bool) or not isinstance(n_samples, int) or n_samples < 1:
        raise ValueError("n_samples должен быть положительным целым")
    if not np.isfinite(relative_change) or not 0 <= relative_change < 1:
        raise ValueError("relative_change должен лежать в [0, 1)")
    table = result.table.loc[result.table["eligible"]].sort_values("iata").copy()
    criteria = list(result.weights)
    rng = np.random.default_rng(seed)
    base = np.array(list(result.weights.values()))
    sampled = base * rng.uniform(1 - relative_change, 1 + relative_change,
                                 size=(n_samples, len(base)))
    sampled /= sampled.sum(axis=1, keepdims=True)
    scores = sampled @ table[[f"score_{c}" for c in criteria]].to_numpy().T
    order = np.argsort(-scores, axis=1, kind="stable")
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(1, len(table) + 1)[None, :], axis=1)
    table = table[["iata", "city_name", "rank", "result_status"]].reset_index(drop=True)
    table["top3_frequency"] = (ranks <= 3).mean(axis=0)
    table["best_rank"] = ranks.min(axis=0)
    table["worst_rank"] = ranks.max(axis=0)
    table["mean_rank"] = ranks.mean(axis=0)
    table["n_samples"] = n_samples
    return table.sort_values(["top3_frequency", "mean_rank", "iata"], ascending=[False, True, True]).reset_index(drop=True)
