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
