# AI Caller

Локальная платформа AI-телефонии по ТЗ: FastAPI, React/TypeScript, PostgreSQL, Redis, отдельный Voice Gateway и Asterisk.

**Статус: рабочая основа с проверенной симуляцией; не финальный продукт по ТЗ.** Реальный SIP/AI-путь экспериментальный и требует приёмки на вашем компьютере. Подробности: [docs/status.md](docs/status.md), [docs/acceptance.md](docs/acceptance.md).

## Быстрый запуск — Windows 11

Требуются Git, Docker Desktop с Linux containers/WSL2 и свободный порт 3000. Python/Node на хосте для Docker-запуска не требуются.

Откройте PowerShell в папке репозитория:

```powershell
./scripts/preflight.ps1
./scripts/setup.ps1
./scripts/start.ps1
```

Откройте http://localhost:3000. Логин `admin`, пароль — значение ADMIN_PASSWORD в созданном локально `.env`. Скрипт не печатает секреты. Если выполнение PowerShell-скриптов запрещено вашей политикой, используйте разрешённый администратором способ запуска; не меняйте общесистемную политику ради проекта.

Альтернатива при наличии Python:

```powershell
python scripts/setup.py
docker compose up -d --build
```

Создайте сценарий → агента → контакт с основанием для звонка → кампанию → добавьте контакты → запустите в разрешённое время → откройте «Звонки». Используйте кнопку обновления: автоматический polling пока не реализован. Симуляция не обращается к SIP/AI и содержит явно искусственную транскрипцию.

## Возможности

- CRM: компании, контакты, сценарии, агенты, кампании, звонки, беседы, сообщения, перезвоны, пользователи, аудит.
- API создания/изменения справочников; web-формы создания, история контактов и звонков.
- CSV/XLSX импорт с предварительной проверкой и атомарным сохранением.
- Кампании: расписание IANA timezone, лимиты, пауза/остановка, ограниченные повторы busy/no_answer, остановка по ошибкам.
- Блокировка отказавшихся номеров сохраняется после удаления карточки. Перед запуском проверяется основание для контакта.
- Авторизация, роли admin/operator/viewer, Argon2, HttpOnly cookie, CSRF/Origin, rate limiting, аудит без секретов.
- Отдельный gateway: симуляция, экспериментальные ARI + Realtime + PCMU/RTP, очередь аудио с прерыванием.
- Опциональный post-call JSON-анализ через отдельный адаптер Responses (нужно задать OPENAI_ANALYSIS_MODEL); ошибки и отказы модели не маскируются успешной оценкой.
- Зашифрованные копии PostgreSQL, ежедневный maintenance, восстановление в отдельную новую базу, срок хранения звонков.

## Одиночный реальный звонок

Следуйте [docs/sip.md](docs/sip.md). Требуются свои SIP-настройки, API-ключ и разрешённый тестовый номер. Никакие секреты не нужно присылать в чат или сохранять в Git. Реальные кампании программно заблокированы до приёмки одиночного звонка.

## Данные и обновления

Named volumes: ai-caller_postgres-data, ai-caller_redis-data, ai-caller_backups. `docker compose down` сохраняет данные; `docker compose down -v` удаляет volumes — не используйте при обновлении.

Перед обновлением создавайте и проверяйте резервную копию. BACKUP_KEY храните отдельно от компьютера: без него копии не расшифровать. Сам `.env` в backup не входит. Административный password hash входит в зашифрованный DB dump; паролей в открытом виде в БД нет.

```powershell
./scripts/backup.ps1
./scripts/restore.ps1 -File caller-<timestamp>.dump.enc -Database restore_check
```

Восстановление **не переключает** приложение на новую базу автоматически. Сначала проверьте данные; затем запланируйте переключение DATABASE_URL/Compose с остановленными worker/backend. Скрипт намеренно не затирает рабочую базу.

Для переноса на другой компьютер: исходники + зашифрованный dump + отдельно переданный BACKUP_KEY и локальные секреты. Копии можно извлечь командой `docker compose cp maintenance:/backups ./backups-export`. Сохраняйте их за пределами Docker volume.

## Проверки

```powershell
./scripts/test.ps1
```

Для разработки без Docker:

```powershell
python -m venv .venv
./.venv/Scripts/python -m pip install -r requirements.lock
./.venv/Scripts/python -m pytest -q
cd frontend
npm ci
npm run build
```

Pytest использует изолированный SQLite для бизнес-логики и ASGI-интеграции. Это не тест PostgreSQL advisory lock или реальной телефонии. CI содержит отдельный Compose job, но его выполнение ещё нужно подтвердить после публикации на GitHub.

## GitHub

Репозиторий и история созданы локально; публикация на GitHub не подтверждена. Архив содержит исходники и `ai-caller.git.bundle` со снимком истории. Восстановить репозиторий из bundle:

```powershell
git clone ./ai-caller.git.bundle ./ai-caller-from-git
```

Для создания нового приватного GitHub-репозитория через установленный GitHub CLI:

```powershell
gh auth login
./scripts/publish.ps1 -Repository YOUR_LOGIN/ai-caller
```

Не используйте force push. `.env`, данные, записи и зависимости исключены из Git. Правила дальнейшей работы — [AGENTS.md](AGENTS.md).
