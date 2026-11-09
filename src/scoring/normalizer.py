"""
Функции Min-Max нормализации признаков в шкалу [0..100].
ВЛАДЕЛЕЦ ФАЙЛА: Dev 2 (Scoring Engine)
"""

import numpy as np
import pandas as pd


def min_max_normalize(series: pd.Series, *, reverse: bool = False) -> pd.Series:
    """Min-max в [0, 100]; равные значения получают 50. NaN/inf запрещены.

    Передавайте полный лонглист. Фильтровать таблицу для UI нужно после
    расчёта, иначе изменится шкала сравнения.
    """
    if series.empty:
        raise ValueError("Нельзя нормализовать пустую колонку")
    try:
        values = pd.to_numeric(series, errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{series.name}: ожидаются числа") from exc
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError(f"{series.name}: пропуски и бесконечности недопустимы")
    low, high = float(values.min()), float(values.max())
    if high == low:
        return pd.Series(50.0, index=series.index, name=series.name)
    result = (values - low) / (high - low) * 100.0
    return 100.0 - result if reverse else result
