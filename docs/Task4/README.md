# Задание 4. Разделение нагрузки CRM и отчётов

**PostgreSQL → Debezium → Kafka → ClickHouse → API**

[Debezium](debezium/connector.json) один раз копирует исходные данные, затем читает изменения
из журнала PostgreSQL и отправляет их в топик `bionicpro.cdc`. Настройка БД: [cdc.sql](postgres/cdc.sql).

В [ClickHouse](clickhouse/schema.sql) KafkaEngine принимает события, а MaterializedView сохраняет
актуальные записи без дублей, учитывая обновления и удаления. Другая MaterializedView каждую минуту
объединяет клиентов, историю владения и телеметрию в витрину `user_reports_cdc`.

[API](../../reports-api/app/main.py) читает эту витрину (`REPORTS_TABLE=user_reports_cdc`),
а не CRM. Пользователь по-прежнему видит только свой отчёт. Массовые чтения CRM через Airflow больше не нужны.

## Запуск

1. Заполните `.env` по [примеру](../../.env.example): секреты Task1, PostgreSQL/ClickHouse из Task2
   и отдельный `CDC_DB_PASSWORD`. Переменные Airflow и Task3 не нужны.
2. Остановите предыдущий стенд без удаления данных и запустите из корня:
   ```bash
   docker compose -f docker-compose.yaml -f docs/Task4/docker-compose.cdc.yaml up -d --build
   ```
3. Укажите ID пользователей Keycloak в `crm.customers.subject`, как в [Task2](../Task2/README.md#запуск),
   заменив Compose-файл Task2 на Task4.
4. Дождитесь первой загрузки и обновления витрины, затем получите отчёт на `http://localhost:3000`.
