"""Укрупненная оценка потребности в SJ-100 (Dev 3).

По уточненному ТЗ от 10.11.2026: до 18 парных оборотов на борт в неделю,
коэффициенты потребности 5.2 для хаба и 4.6 для P2P, минимум 3/2 борта.
Это укрупненная калибровка команды, не нормативы производителя.
Коэффициенты безразмерные; длительности рейсов в формулу не передаются.
Оценка требует проверки по расписанию, ТОиР и реальной утилизации.

Результат — потребность, а не подтвержденная доступность: новые SJ-100
ожидаются не ранее 2027-H2. Годовая экономика соответствует полному году
работы сети (например, 2028), а не неполному году начала поставок.
"""

from math import ceil

from src.schemas.contracts import AircraftModelId, AircraftSpecDTO

# Плановые ограничения и относительные расходы из ТЗ команды.
# Диапазоны не заменяют РЛЭ, ограничения конкретного борта/аэропорта и payload-range.
AIRCRAFT_CATALOG: dict[AircraftModelId, AircraftSpecDTO] = {
    "crj200": AircraftSpecDTO(
        id="crj200", name="CRJ-200 (50 мест · Конкуренты)", seats=50,
        min_km=300, opt_low_km=450, opt_high_km=1200, max_km=1450,
        cask_multiplier=1.22, short_haul_penalty=1.10,
    ),
    "sj100_basic": AircraftSpecDTO(
        id="sj100_basic", name="SJ-100 Basic (100 мест · Волна 1-2)", seats=100,
        min_km=350, opt_low_km=600, opt_high_km=1600, max_km=2450,
        cask_multiplier=1.00, short_haul_penalty=1.15,
    ),
    "sj100_lr": AircraftSpecDTO(
        id="sj100_lr", name="SSJ-100 / SJ-100 LR (100 мест · Резерв)", seats=100,
        min_km=400, opt_low_km=700, opt_high_km=2200, max_km=3050,
        cask_multiplier=1.03, short_haul_penalty=1.15,
    ),
    "tu214": AircraftSpecDTO(
        id="tu214", name="Ту-214 (210 мест · Волна 2-3)", seats=210,
        min_km=1100, opt_low_km=1400, opt_high_km=4200, max_km=5200,
        cask_multiplier=0.86, short_haul_penalty=1.28,
    ),
    "mc21_310": AircraftSpecDTO(
        id="mc21_310", name="МС-21-310 (211 мест · Волна 3 до 2030)", seats=211,
        min_km=1100, opt_low_km=1400, opt_high_km=4500, max_km=5100,
        cask_multiplier=0.78, short_haul_penalty=1.25,
    ),
}


def get_aircraft_spec(aircraft_id: AircraftModelId) -> AircraftSpecDTO:
    """Неизменяемый DTO выбранного ВС; неизвестный идентификатор — ошибка."""
    if not isinstance(aircraft_id, str) or aircraft_id not in AIRCRAFT_CATALOG:
        raise ValueError(f"Неизвестный aircraft_id: {aircraft_id!r}")
    return AIRCRAFT_CATALOG[aircraft_id]


def get_aircraft_gravity_knots(
    aircraft_id: AircraftModelId,
) -> tuple[float, float, float, float]:
    """Четыре границы дальности (км) для гравитационной модели Dev 2."""
    spec = get_aircraft_spec(aircraft_id)
    return (float(spec.min_km), float(spec.opt_low_km),
            float(spec.opt_high_km), float(spec.max_km))


ROUND_TRIPS_PER_AIRCRAFT_WEEK = 18.0
HUB_FLEET_FACTOR = 5.2
P2P_FLEET_FACTOR = 4.6


def calculate_required_sj100_fleet(routes_count: int, weekly_freq: int, is_hub: bool) -> int:
    """Частота задается парами рейсов; маршруты и частота строго положительные."""
    for name, value in (("routes_count", routes_count), ("weekly_freq", weekly_freq)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} должен быть положительным целым числом")
    if not isinstance(is_hub, bool):
        raise ValueError("is_hub должен быть bool")
    factor = HUB_FLEET_FACTOR if is_hub else P2P_FLEET_FACTOR
    return max(
        3 if is_hub else 2,
        ceil(routes_count * weekly_freq * factor / ROUND_TRIPS_PER_AIRCRAFT_WEEK),
    )


def build_sj100_delivery_roadmap(required_sj100: int, scenario: str = "base") -> list[dict]:
    """Плановый, не подтвержденный поставщиками график 2026-Q3..2028-Q4.

    До 2027-Q2 новых бортов нет. Резерв текущего SSJ постепенно выделяется
    до 6 (base) / 4 (conservative) машин; его наличие требует проверки.
    Новые SJ-100 заменяют временный резерв, поэтому сумма не превышает
    required_sj100 и замена не учитывается дважды. Потребность закрывается
    новыми поставками к концу 2028 в обоих сценариях; conservative отстает.
    supported_routes_count — максимум P2P-маршрутов при 5 парах/неделю,
    вычисленный обратной формулой calculate_required_sj100_fleet. Это не
    обещание поддержки любой частоты: она отсутствует во входном контракте.
    """
    if isinstance(required_sj100, bool) or not isinstance(required_sj100, int) or required_sj100 <= 0:
        raise ValueError("required_sj100 должен быть положительным целым числом")
    if scenario not in ("base", "conservative"):
        raise ValueError("scenario должен быть 'base' или 'conservative'")
    quarters = ["2026 Q3", "2026 Q4", "2027 Q1", "2027 Q2", "2027 Q3",
                "2027 Q4", "2028 Q1", "2028 Q2", "2028 Q3", "2028 Q4"]
    reserve_plan = [2, 4, 6, 6] + [6] * 6 if scenario == "base" else [2, 3, 4, 4] + [4] * 6
    # Целые проценты исключают накопление ошибок округления по кварталам.
    delivery_pct = [0, 0, 0, 0, 15, 30, 45, 65, 85, 100] if scenario == "base" else [0, 0, 0, 0, 0, 10, 25, 45, 70, 100]
    rows = []
    for quarter, reserve_limit, percent in zip(quarters, reserve_plan, delivery_pct):
        new = required_sj100 * percent // 100
        reserve = min(reserve_limit, required_sj100 - new)
        total = reserve + new
        routes = int(total * ROUND_TRIPS_PER_AIRCRAFT_WEEK / (5 * P2P_FLEET_FACTOR)) if total >= 2 else 0
        rows.append({
            "quarter": quarter, "existing_ssj_reserve_allocated": reserve,
            "new_sj100_delivered_cumulative": new, "total_available_fleet": total,
            "supported_routes_count": routes, "assumed_weekly_freq_per_route": 5,
            "is_planning_assumption": True,
        })
    return rows
