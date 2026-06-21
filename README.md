# Booking Service

REST API для записи на встречи с асинхронной обработкой через Celery и Redis.

## Стек технологий

| Компонент | Технология | Почему |
|-----------|-----------|--------|
| API | FastAPI | Автогенерация OpenAPI-документации, нативная Pydantic-валидация, высокая производительность |
| ORM | SQLAlchemy 2.0 | Мощный ORM, поддержка Alembic-миграций, type hints |
| Миграции | Alembic | Стандарт для SQLAlchemy, version control схемы БД |
| БД | PostgreSQL 16 | ACID, нативный UUID-тип, проверенное решение |
| Очереди | Celery + Redis | Зрелый инструмент, retry с backoff из коробки, мониторинг через Flower |
| Брокер/Backend | Redis | Быстро, просто, хорошо работает с Celery |
| Логирование | JSON | Structured logging — легко парсить в ELK/Loki/Datadog |
| Контейнеры | Docker + Compose | Весь стек одной командой |

---

## Быстрый старт

### Предварительные требования

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (включает Docker Compose)
- Python 3.12+ (для запуска тестов локально)
- Git

### 1. Клонировать репозиторий

```bash
git clone https://github.com/glock17l33/booking-service.git
cd booking-service
```

### 2. Создать .env файл

```bash
cp .env.example .env
# Файл уже содержит рабочие значения для локальной разработки
```

### 3. Запустить сервис

```bash
docker-compose up --build
```

Это запустит:
- **PostgreSQL** на порту `5432`
- **Redis** на порту `6379`
- **Миграции** (автоматически, один раз)
- **FastAPI** на порту `8000`
- **Celery Worker** (фоновая обработка броней)

### 4. Проверить работу

- **API документация (Swagger):** http://localhost:8000/docs
- **Альтернативная документация (ReDoc):** http://localhost:8000/redoc
- **Health check:** http://localhost:8000/health

---

## API Endpoints

### POST /bookings — Создать бронь

```bash
curl -X POST http://localhost:8000/bookings \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"Ivan Petrov\", 
  \"datetime\": \"2025-12-01T10:00:00Z\", 
  \"service_type\": \"consultation\"}"
```

**Ответ (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Иван Петров",
  "datetime": "2025-12-01T10:00:00Z",
  "service_type": "consultation",
  "status": "pending",
  "created_at": "2025-01-15T12:00:00Z",
  "updated_at": "2025-01-15T12:00:00Z"
}
```

### GET /bookings/{id} — Статус брони

```bash
curl http://localhost:8000/bookings/550e8400-e29b-41d4-a716-446655440000
```

Статусы: `pending` → `confirmed` или `failed`

### GET /bookings — Список броней

```bash
# Все брони
curl http://localhost:8000/bookings

# Только подтверждённые, 2-я страница
curl "http://localhost:8000/bookings?status=confirmed&page=2&page_size=10"
```

### DELETE /bookings/{id} — Отменить бронь

```bash
curl -X DELETE http://localhost:8000/bookings/550e8400-e29b-41d4-a716-446655440000
```

> ⚠️ Отмена работает только для статуса `pending`. Для `confirmed`/`failed` вернётся `409 Conflict`.

---

## Как работает подтверждение брони

Подтверждение происходит **автоматически в фоне** через Celery worker.

### Процесс:

1. **POST /bookings** → создаётся бронь со статусом `pending`
2. **Celery задача** автоматически запускается в фоне
3. Через 1-5 секунд статус меняется на:
   - `confirmed` (85% вероятность) — успех
   - `failed` (15% вероятность) — имитация сбоя внешнего сервиса

### Проверить статус:

```bash
# Создать бронь и запомнить ID из ответа
curl -X POST http://localhost:8000/bookings \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"Ivan Petrov\", \"datetime\": \"2025-12-01T10:00:00Z\", \"service_type\": \"consultation\"}"

# Подождать 2-3 секунды и проверить статус
curl http://localhost:8000/bookings/{id}
```

### Посмотреть логи воркера:

```bash
docker compose logs -f worker
```

---

## Запуск тестов

Тесты используют SQLite in-memory и не требуют запущенного Docker.

### 1. Создать виртуальное окружение

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\activate
```

**Windows (Git Bash):**
```bash
python -m venv venv
source venv/Scripts/activate
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Запустить тесты

```bash
# Все тесты
pytest

# С отчётом о покрытии
pytest --cov=app --cov-report=term-missing

# Или через Makefile
make test
```

### 4. Деактивировать окружение (когда закончите)

```bash
deactivate
```

**Что тестируется:**

| Файл | Что покрывает |
|------|--------------|
| `tests/test_bookings_api.py` | Все 4 эндпоинта: happy path + граничные кейсы |
| `tests/test_worker.py` | Логика воркера: успех, сбой, идемпотентность, уведомления |

---

## Makefile команды

```bash
make dev      # Запустить docker-compose up --build
make test     # Запустить pytest с coverage
make lint     # Проверить стиль кода (ruff + mypy)
make migrate  # Применить миграции
make logs     # Следить за логами api и worker
make down     # Остановить контейнеры
make clean    # Удалить контейнеры, тома, кэш
```

---

## Архитектурные решения

### Идемпотентность задачи

При создании брони Celery-задача отправляется с детерминированным `task_id`:

```python
confirm_booking.apply_async(
    args=[str(booking.id)],
    task_id=f"confirm-{booking.id}",
)
```

Внутри задачи первым делом проверяется текущий статус брони:
- Если статус уже `confirmed` или `failed` — задача завершается с `{"status": "skipped"}`
- Это гарантирует, что повторный запуск не изменит данные

### Retry с экспоненциальным backoff

```python
@celery_app.task(
    max_retries=3,
    retry_backoff=True,       # 2s, 4s, 8s...
    retry_backoff_max=300,    # максимум 5 минут
    retry_jitter=True,        # случайный разброс против thundering herd
)
```

### Вероятность сбоя ~15%

```python
def _simulate_external_service() -> bool:
    return random.random() > 0.15  # True в 85% случаев
```

### Structured JSON Logging

Все события логируются в JSON-формате для удобной интеграции с системами мониторинга:

```json
{
  "message": "NOTIFICATION SENT",
  "event": "notification_sent",
  "booking_id": "550e8400-...",
  "name": "Иван Петров",
  "level": "INFO",
  "time": "2025-01-15T12:00:05Z"
}
```

### Rate Limiting

POST `/bookings` ограничен 10 запросами в минуту с одного IP (настраивается через `RATE_LIMIT_PER_MINUTE` в `.env`). Реализован через Redis sliding window counter. При недоступности Redis — fail open (запрос пропускается).

### Выбор FastAPI vs Django

Выбран FastAPI, потому что:
1. Задание — небольшой сервис без admin-панели и ORM из коробки
2. FastAPI даёт автоматическую OpenAPI-документацию
3. Pydantic v2 — быстрая и строгая валидация
4. Меньше boilerplate, чем в Django REST Framework

---

## Структура проекта

```
booking-service/
├── app/
│   ├── main.py              # FastAPI приложение, lifespan, middleware
│   ├── config.py            # Настройки через pydantic-settings + .env
│   ├── database.py          # SQLAlchemy engine, session, Base
│   ├── celery_app.py        # Celery конфигурация
│   ├── tasks.py             # Celery-задача confirm_booking
│   ├── middleware.py        # Rate limiting middleware
│   ├── logging_config.py    # Structured JSON logging
│   ├── models/
│   │   └── booking.py       # SQLAlchemy модель Booking
│   ├── schemas/
│   │   └── booking.py       # Pydantic схемы (request/response)
│   └── routers/
│       └── bookings.py      # Все 4 эндпоинта
├── alembic/
│   ├── env.py               # Конфигурация Alembic
│   └── versions/
│       └── 0001_create_bookings_table.py
├── tests/
│   ├── conftest.py          # SQLite in-memory fixtures
│   ├── test_bookings_api.py # Тесты API
│   └── test_worker.py       # Тесты воркера
├── .env.example             # Шаблон переменных окружения
├── docker-compose.yml       # Весь стек одной командой
├── Dockerfile
├── Makefile
├── pytest.ini
├── requirements.txt
└── README.md
```
