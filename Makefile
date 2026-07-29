.PHONY: ingest backtest simulate publish check-gaps

ingest:
	uv run python -m loaders.crowd_to_duck

check-gaps:
	uv run python scripts/check_gaps.py

backtest:
	@echo "not yet implemented (Day 11)"

simulate:
	@echo "not yet implemented (Day 20)"

publish:
	@echo "not yet implemented (Day 24)"
