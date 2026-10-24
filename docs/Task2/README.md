# Задание 2. Сервис отчётов

## 1. Архитектура

- [Схема draw.io](BionicPRO_reports.drawio.xml):
- [Схема JPG](BionicPRO_reports.jpg):

## 2. ETL и витрина

- [DAG](../../airflow/dags/reports_etl.py) `bionicpro_reports` запускается каждый час (`0 * * * *`, UTC).
- [SQL](../../airflow/dags/sql/build_reports.sql) объединяет CRM и телеметрию с учётом истории владельцев протезов.
- [Витрина](clickhouse/schema.sql) хранит готовый отчёт на клиента: дневные замеры, отклик, заряд и успешные движения
  за 30 полных суток и текущий день до границы запуска. Поиск — по `(issuer, subject)`.

## 3–4. API и доступ

[Сервис FastAPI](../../reports-api/app/main.py): `GET /reports` возвращает готовый JSON из ClickHouse без расчётов.
API проверяет JWT Keycloak и выбирает отчёт по `(iss, sub)` из токена. API имеет доступ только на чтение витрины, ETL
только на чтение источников.

## 5. UI

Кнопка **Получить отчёт** вызывает `/api/reports` через BFF, показывает таблицу и скачивает `report.json`.
Токены остаются на сервере.

## Запуск

1. Заполните `.env` по [примеру](../../.env.example), включая переменные Task2.
   `COOKIE_SECURE=false` допустим только для localhost HTTP; в эксплуатации нужен HTTPS.
2. Запустите из корня:
   ```bash
   docker compose -f docker-compose.yaml -f docs/Task2/docker-compose.reports.yaml up -d --build
   ```
3. В стенде используются [тестовые CRM и телеметрия](sources/schema.sql). Скопируйте ID `user1` и `user2`
   из Keycloak Admin Console и подставьте их вместо `KEYCLOAK_USER1_ID` и `KEYCLOAK_USER2_ID`:
   ```bash
   docker compose -f docker-compose.yaml -f docs/Task2/docker-compose.reports.yaml exec report-sources \
     psql -U sources_admin -d sources -c "UPDATE crm.customers SET subject='KEYCLOAK_USER1_ID' WHERE customer_id=1; UPDATE crm.customers SET subject='KEYCLOAK_USER2_ID' WHERE customer_id=2;"
   ```
4. Откройте Airflow: `http://localhost:8081`, `admin` / `AIRFLOW_ADMIN_PASSWORD`. Запустите `bionicpro_reports`
   кнопкой Trigger DAG. После успешного `publish` войдите на `http://localhost:3000` и получите отчёт.

Для существующего realm нужен audience-mapper `reports-api` из `keycloak/realm-export.json`.
Для реальных источников замените подключения `CRM_DATABASE_URL`/`TELEMETRY_DATABASE_URL` и запросы DAG.
Начальные SQL-скрипты выполняются только для новых томов.
