.PHONY: dev test lint migrate logs down clean help

# ─────────────────────────────────────────────────────────────────────────────
# Переменные
# ─────────────────────────────────────────────────────────────────────────────
COMPOSE = docker-compose
PYTEST  = pytest tests/ -v --tb=short

# ─────────────────────────────────────────────────────────────────────────────
# Команды
# ─────────────────────────────────────────────────────────────────────────────

help:           ## Показать список доступных команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev:            ## Запустить весь стек через docker-compose
	$(COMPOSE) up --build

down:           ## Остановить docker-compose
	$(COMPOSE) down

test:           ## Запустить тесты (без Docker)
	$(PYTEST) --cov=app --cov-report=term-missing

lint:           ## Проверить стиль кода (ruff + mypy)
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports

migrate:        ## Применить миграции Alembic
	$(COMPOSE) run --rm migrate

logs:           ## Показать логи API и воркера
	$(COMPOSE) logs -f api worker

clean:          ## Удалить все контейнеры, тома и кэш
	$(COMPOSE) down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
