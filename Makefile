.PHONY: ingest backtest simulate publish check-gaps results resolve-teams understat fixtures

ingest:
	uv run python -m loaders.crowd_to_duck

results:
	uv run python -m collectors.results

resolve-teams:
	uv run python -m loaders.resolve_team

understat:
	uv run python -m collectors.understat

fixtures:
	uv run python -m collectors.fixtures

check-gaps:
	uv run python scripts/check_gaps.py

backtest:
	@echo "not yet implemented (Day 11)"

simulate:
	@echo "not yet implemented (Day 20)"

publish:
	@echo "not yet implemented (Day 24)"
