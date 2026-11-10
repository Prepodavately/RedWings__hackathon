# Red Wings Network Strategy — Репозиторий команды ПМИ

## Распределение папок по разработчикам (Zero Merge Conflicts)

- **Tech Lead / Общий контракт**: `src/schemas/contracts.py`, `config/`
- **Dev 1 (Парсинг и данные)**: `src/parsers/`, `data/raw/`, `data/processed/`
- **Dev 2 (Скоринг городов)**: `src/scoring/`, `notebooks/02_scoring_check.ipynb`
- **Dev 3 (Финансовая модель SJ-100)**: `src/models/`, `tests/test_unit_economics.py`
- **Dev 4 (Streamlit UI и Карты)**: `app.py`, `src/ui/`, `src/mocks/`

## Быстрый старт

```bash
pip install -r requirements.txt
# Запуск дашборда на моках (пока бэкендеры пишут код):
USE_MOCKS=1 streamlit run app.py

# Запуск дашборда на реальных расчетах:
USE_MOCKS=0 streamlit run app.py
```
