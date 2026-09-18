# SIP и одиночный AI-тест

Телефония экспериментальная: контейнер и реальный звонок не выполнялись в среде разработки.

## Конфигурация

В локальном `.env`: SIP_HOST (host без sip:), SIP_USERNAME, SIP_PASSWORD. Шаблон рассчитан на регистрационный UDP SIP-транк с G.711 mu-law (ulaw). IP-аутентификация, TLS/SRTP и специфические параметры оператора потребуют отдельного профиля.

`SIP_EXTERNAL_ADDRESS` — доступный оператору адрес вашей машины/маршрутизатора. `SIP_LOCAL_NET` — внутренние сети. По умолчанию SIP/RTP опубликованы только на loopback. Чтобы получать пакеты из LAN/от оператора, задайте конкретный локальный адрес интерфейса в SIP_BIND_ADDRESS и настройте firewall/NAT под адреса оператора. Не публикуйте ARI в интернет.

```powershell
docker compose --profile telephony up -d --build
docker compose exec asterisk asterisk -rx "pjsip show registrations"
docker compose exec asterisk asterisk -rx "http show status"
docker compose exec asterisk asterisk -rx "ari show users"
```

API-ключ хранится только в .env. Для одиночного теста задайте LIVE_CALLS_ENABLED=true и LIVE_TEST_NUMBER в формате +79991234567. Создайте контакт с тем же номером и основанием для теста. Пересоздайте backend и gateway после изменения .env.

Подготовлен endpoint POST /api/test-call (только admin); он требует остановленного worker, PostgreSQL, отсутствия активных звонков и совпадения номера с разрешённым. Удобный клиент: scripts/test-call.ps1. Параметры — ID контакта, сценария и агента, которые возвращают API/карточки. Скрипт запрашивает пароль, не сохраняет его.

```powershell
docker compose stop worker
./scripts/test-call.ps1 -ContactId <id> -ScenarioId <id> -AgentId <id>
```

Не запускайте повторно при ошибке dispatch_uncertain до проверки `core show channels`: запрос мог дойти до Asterisk, даже если подтверждение потерялось. Max call duration ограничен MAX_CALL_SECONDS. При срочной остановке теста: `docker compose stop voice-gateway asterisk`.

В текущей версии AI не выполняет бизнес-действия по голосу. Post-call анализ включается настройкой OPENAI_ANALYSIS_MODEL (модель Responses со strict JSON schema); без неё результат содержит analysis_status=disabled. Оценки помечены как uncertain_ai_estimate и не запускают действия автоматически. Тест предназначен для проверки двустороннего звука и перебивания.

## Использованные официальные источники

- https://docs.asterisk.org/Development/Reference-Information/Asterisk-Framework-and-API-Examples/External-Media-and-ARI/
- https://downloads.asterisk.org/pub/telephony/asterisk/
- https://developers.openai.com/api/docs/guides/realtime-conversations
- https://developers.openai.com/api/docs/guides/voice-websockets

Проверены 2026-09-17. Реализация использует Realtime API, а не новый GPT-Live API. Модель конфигурируема; доступность модели и голоса зависит от аккаунта и должна быть проверена реальным тестом.

- https://developers.openai.com/api/docs/guides/structured-outputs
