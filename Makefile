.PHONY: setup parse test verify mock run

setup:
	pip install -r requirements.txt

parse:
	python -m src.parsers.build_dataset

test:
	pytest tests/ src/scoring/tests/ -q

verify:
	python -m src.parsers.build_dataset
	python -c "from src.schemas.contracts import ScoringWeights, FinModelInput; from src.scoring.city_scorer import get_scored_cities; from src.models.unit_economics import evaluate_hypotheses; from src.parsers.build_dataset import get_network_routes; cities = get_scored_cities(ScoringWeights()); assert len(cities) == 12 and any(c.iata == 'SVX' for c in cities); bundle = evaluate_hypotheses(FinModelInput(), cities); assert bundle.winner == 'p2p'; r_p2p = get_network_routes('p2p'); r_hub = get_network_routes('hub', 'KUF'); assert 10 <= len(r_p2p) <= 12 and 10 <= len(r_hub) <= 12; print('E2E OK:', len(cities), 'cities,', bundle.winner, 'wins, EBITDAR P2P =', bundle.p2p.ebitdar_mln_rub, 'mln RUB')"
	pytest tests/ src/scoring/tests/ -q

mock:
	USE_MOCKS=1 streamlit run app.py

run:
	USE_MOCKS=0 streamlit run app.py

