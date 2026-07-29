.PHONY: ingest backtest simulate publish check-gaps results resolve-teams understat fixtures load audit fit-dc

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

load:
	uv run python scripts/full_load.py --skip-download

audit:
	uv run python scripts/data_audit.py

fit-dc:
	uv run python scripts/fit_dixon_coles.py

backtest:
	@echo "not yet implemented (Day 11)"

simulate:
	@echo "not yet implemented (Day 20)"

publish:
	@echo "not yet implemented (Day 24)"
