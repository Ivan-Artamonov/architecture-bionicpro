# BionicPRO — проектная работа, спринт 9

## Состав решения

- `docs/auth-architecture.drawio` — вход через Keycloak, LDAP и Яндекс ID; PKCE и серверные сессии.
- `bionicpro-auth` — backend for frontend: Authorization Code + PKCE S256, короткий access token, refresh на сервере, шифрование токенов в памяти, ротация session ID, cookie HttpOnly.
- `report-api` — отчёт только для `sub` текущей сессии. Проверяет watermark ETL, читает готовую витрину ClickHouse, сохраняет JSON в закрытом MinIO и отдаёт короткую подписанную ссылку.
- `airflow/dags` — ежедневное построение витрины из телеметрии и CRM mirror.
- `debezium` и `clickhouse/init` — CDC из CRM PostgreSQL через Kafka в ClickHouse KafkaEngine и Materialized View.
- `nginx` — эмуляция CDN, кеширующий reverse proxy для подписанных URL.
- `docs/reports-architecture.drawio` — поток данных и отчётов.

Keycloak, CRM и ClickHouse в этой схеме разворачиваются в одном локальном контуре представительства. При переносе в другую страну такой контур разворачивается отдельно: персональные и медицинские данные остаются в местных CRM и OLAP, а внешний IdP передаёт только идентификатор и разрешённые пользователем поля профиля. Добавление следующего провайдера не меняет сессионный контракт фронтенда.

## Локальный запуск

1. Установите Docker Engine с Compose. Файл `.env` не коммитьте: он уже исключён из Git. Для HTTPS вне localhost установите `COOKIE_SECURE=true` в сервисах `auth` и `api`, а также замените публичные адреса на HTTPS. Текущие настройки предназначены только для локального стенда.
2. Создайте приложение Яндекс ID с Redirect URI `http://localhost:8080/realms/reports-realm/broker/yandex/endpoint`. Запишите `YANDEX_CLIENT_ID` и `YANDEX_CLIENT_SECRET` в `.env` без кавычек.
3. Выполните `docker compose up -d --build`. Откройте приложение на http://localhost:3000 и Keycloak на http://localhost:8080. При первом входе локального пользователя Keycloak потребует настройку OTP.
   Для проверки запущенных сервисов выполните `scripts/check-stack.sh`; скрипт не выводит секреты из `.env`.
4. После запуска Keycloak выполните `python3 keycloak/configure_yandex.py` для включения брокера Яндекс ID. Секрет остаётся в локальном `.env`.
5. Зарегистрируйте Debezium: `curl -X POST -H 'Content-Type: application/json' --data @debezium/postgres-connector.json http://localhost:8083/connectors`.
6. Дождитесь CDC snapshot. Затем включите DAG `bionicpro_daily_reports` в Airflow на http://localhost:8085 и запустите его вручную для демонстрации; он также выполняется каждый день в 02:00 UTC. Пароль администратора Airflow создаётся командой `standalone` и сохраняется в `/opt/airflow/standalone_admin_password.txt` внутри контейнера.
7. Войдите как `user1` из исходного realm. В `crm/init/002_demo.sql` есть синтетическая запись, привязанная к его Keycloak `sub`. В `clickhouse/init/003_demo.sql` есть синтетическая телеметрия за вчера. После DAG отчёт за вчера должен скачиваться через кнопку в UI. Для аккаунта Яндекс ID потребуется создать CRM customer с фактическим Keycloak `sub` и связанный prosthesis.

## Границы стенда

Внешний профиль Яндекс ID сохраняется Keycloak при первом брокерском входе. Для настоящей среды потребуются HTTPS, секреты во внешнем менеджере, защищённое LDAP-соединение, отдельные учётные записи с минимальными правами, постоянное общее хранилище сессий, ограничения доступа к административным портам и резервное копирование. Все пароли и демоданные в исходном шаблоне являются учебными.

`keycloak/keycloak-results-export.json` содержит конфигурацию realm без OAuth-учётных данных Яндекса. После настройки Яндекс ID скрипт `configure_yandex.py` добавляет описание провайдера в этот файл с замаскированными client ID и secret; реальные значения остаются только в `.env` и в локальном Keycloak.
