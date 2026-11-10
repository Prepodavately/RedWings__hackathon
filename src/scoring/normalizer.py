"""
Шкалы признаков: Min-Max и максимум оценки расстояния на 1150 км.
ВЛАДЕЛЕЦ ФАЙЛА: Dev 2 (Scoring Engine)
"""

import numpy as np
import pandas as pd


def _finite_values(series: pd.Series) -> pd.Series:
    if series.empty:
        raise ValueError("Нельзя нормализовать пустую колонку")
    try:
        values = pd.to_numeric(series, errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{series.name}: ожидаются числа") from exc
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError(f"{series.name}: пропуски и бесконечности недопустимы")
    return values


def min_max_normalize(series: pd.Series, *, reverse: bool = False) -> pd.Series:
    """Min-max в [0, 100]; равные значения получают 50. NaN/inf запрещены.

    Передавайте полный лонглист. Фильтровать таблицу для UI нужно после
    расчёта, иначе изменится шкала сравнения.
    """
    values = _finite_values(series)
    low, high = float(values.min()), float(values.max())
    if high == low:
        return pd.Series(50.0, index=series.index, name=series.name)
    result = (values - low) / (high - low) * 100.0
    return 100.0 - result if reverse else result


def distance_sweet_spot_score(
    dist_km_series: pd.Series, optimal_km: float = 1150.0,
) -> pd.Series:
    """Оценка расстояния до Москвы по правилу src/utils/aviationModel.ts.

    max(35, 100 - 65 * |d - optimal_km| / 1200): кусочно-линейный максимум,
    а не гауссиана. Близкие и далёкие города получают штраф относительно
    оптимума. Это сценарная эвристика команды, не оценка дальности самолёта
    или доказательство спроса; границы лонглиста не меняют эту шкалу.
    Сам балл расстояния округляется до 2 знаков по дополнению к ТЗ;
    взвешенная сумма и ранжирование дополнительного округления не используют.
    """
    distances = _finite_values(dist_km_series)
    if (distances < 0).any():
        raise ValueError("Расстояния не могут быть отрицательными")
    try:
        optimal = float(optimal_km)
    except (ValueError, TypeError) as exc:
        raise ValueError("optimal_km должен быть положительным конечным числом") from exc
    if isinstance(optimal_km, bool) or not np.isfinite(optimal) or optimal <= 0:
        raise ValueError("optimal_km должен быть положительным конечным числом")
    return (100.0 - (distances - optimal).abs() / 1200.0 * 65.0).clip(35.0, 100.0).round(2)
