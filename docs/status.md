# Фактический статус — 2026-09-18

**Не финальный релиз. Полная приёмка ТЗ не пройдена.**

## Проверено в этой среде

- Git 2.51.1, Python 3.12.14, Node 24.19.0, npm 11.9.0.
- 23 pytest-тест: API/права/CSRF, ограничения входа, атомарный импорт, нормализация и дубликаты номеров, расписание, opt-out после удаления и повторного импорта, ограничения очереди, состояния звонков, повторные события, удаление истории, RTP, barge-in, шифрование копий, ASGI-интеграция gateway→backend.
- Все 23 тест проходят, 2 предупреждения совместимости Starlette/httpx/anyio. Зависимости зафиксированы в requirements.lock.
- `ruff check backend voice-gateway tests`: PASS.
- `npm run build`: TypeScript и Vite PASS.
- Alembic SQLite upgrade → check → downgrade → upgrade: PASS.
- Генерация PostgreSQL DDL offline: PASS; SQL не выполнялся в PostgreSQL.
- Генерация .env и отказ от его перезаписи: PASS.
- Compose YAML разбирается, внутренние DB/Redis порты не публикуются. Это НЕ docker compose runtime validation.
- FastAPI и Vite запускаются локально; для тестового preview login limiter подменялся в отдельном временном файле вне репозитория, поскольку Redis отсутствует.

## Реализовано, но требует внешнего запуска

- Compose: postgres, redis, migrate, backend, frontend, voice-gateway, worker, maintenance, опциональный asterisk.
- PostgreSQL advisory locks, persistence named volumes и worker recovery.
- Asterisk 22.11.0 source build, конфигурация SIP/ARI, single-number test endpoint.
- Realtime WebSocket, PCMU/RTP, локальная очистка аудио при перебивании, cleanup каналов/мостов/сессий.
- Post-call analysis через Responses со строгой JSON-схемой, обработкой refusal/incomplete; по умолчанию отключён до выбора OPENAI_ANALYSIS_MODEL. Парсер проверен тестами, реальный API не вызывался.
- pg_dump → проверка каталога → Fernet encryption; ежедневный backup, retention; pg_restore в отдельную базу.
- PowerShell-скрипты и GitHub Actions workflow.

## Блокеры фактической проверки

- Docker/daemon и PostgreSQL/Redis не доступны здесь; установка системных пакетов не разрешена средой.
- Нет SIP-учётных данных, OPENAI_API_KEY и согласованного тестового номера. Реальных звонков не выполнялось.
- Playwright library присутствует, Chromium отсутствует; скачивание браузера не удалось (сетевые timeout/502). Browser E2E и визуальная проверка НЕ пройдены.
- Доступ на запись в публичный репозиторий gingie143-dotcom/AGRO_RingS подтверждён. Результат Compose CI требуется проверить в GitHub Actions.

## Ещё требуется разработка

- Voice tools: opt-out, корректное завершение и перевод живому оператору.
- Полные формы редактирования/удаления справочников и UI управления пользователями.
- Автоматический запуск callback-заданий (сейчас это задачи оператору).
- Опциональная запись аудио и защищённое воспроизведение.
- Полноценные latency-метрики, RTP jitter/reordering, fault/load tests.

## Следующая контрольная точка

Проверить GitHub Actions в gingie143-dotcom/AGRO_RingS, исправить реальные ошибки сборки/старта, пройти Windows acceptance, затем одиночный SIP/AI тест. Реальные кампании остаются заблокированы.
