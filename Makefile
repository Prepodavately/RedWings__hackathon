.PHONY: setup parse test mock run

setup:
	pip install -r requirements.txt

parse:
	python -m src.parsers.build_dataset

test:
	pytest tests/

mock:
	USE_MOCKS=1 streamlit run app.py

run:
	USE_MOCKS=0 streamlit run app.py
