"""Укрупненная оценка потребности в SJ-100 (Dev 3).

Сохраняет плановые допущения прототипа src/utils/aviationModel.ts:
5.2 ч на оборот для хаба, 4.6 ч для P2P и 18 доступных часов на борт
в неделю именно для новой сети. Это допущения, не нормативы производителя:
18 ч — выделенный ресурс проекта, а не полный недельный налет самолета.
Минимум 3/2 борта включает резерв малой сети; дополнительный процент резерва
не добавляется. Оценка требует уточнения по расписанию и длительностям плеч.

Результат — потребность, а не подтвержденная доступность: новые SJ-100
ожидаются не ранее 2027-H2. Годовая экономика соответствует полному году
работы сети (например, 2028), а не неполному году начала поставок.
"""

from math import ceil

ALLOCATED_HOURS_PER_AIRCRAFT_WEEK = 18.0
HUB_ROUND_TRIP_HOURS = 5.2
P2P_ROUND_TRIP_HOURS = 4.6


def calculate_required_sj100_fleet(routes_count: int, weekly_freq: int, is_hub: bool) -> int:
    """Частота задается парами рейсов; при нулевой программе нужен 0 бортов."""
    for name, value in (("routes_count", routes_count), ("weekly_freq", weekly_freq)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} должен быть неотрицательным целым числом")
    if not isinstance(is_hub, bool):
        raise ValueError("is_hub должен быть bool")
    if routes_count == 0 or weekly_freq == 0:
        return 0
    hours = HUB_ROUND_TRIP_HOURS if is_hub else P2P_ROUND_TRIP_HOURS
    return max(
        3 if is_hub else 2,
        ceil(routes_count * weekly_freq * hours / ALLOCATED_HOURS_PER_AIRCRAFT_WEEK),
    )
