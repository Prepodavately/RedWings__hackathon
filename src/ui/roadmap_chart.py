"""Dev 4: roadmap placeholder is never presented as a computed launch plan."""
import pandas as pd
import streamlit as st
from src.schemas.contracts import ComparisonBundleDTO


def render_sj100_roadmap(routes_df: pd.DataFrame, comparison: ComparisonBundleDTO) -> None:
    st.subheader('План запуска до 2028 года')
    st.caption('Шаблон для капитана. Сроки, бюджет и распределение бортов ещё не согласованы; из текущего контракта их рассчитать нельзя.')
    st.dataframe(pd.DataFrame([
        {'Этап':'Подготовка','Действия':'Проверить спрос, конкурентов, ограничения аэропортов и договорённости по флоту','Срок':'До запуска; уточняет команда'},
        {'Этап':'Пилот','Действия':'Запуск выбранных маршрутов при наличии самолётов и разрешений','Срок':'Новые SJ-100 по условию — не раньше II полугодия 2027'},
        {'Этап':'Расширение','Действия':'Оценить результаты пилота, скорректировать частоты и сеть','Срок':'До 2028 года; уточняет команда'},
    ]),hide_index=True,use_container_width=True)
