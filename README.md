
# BionicPRO

## Требования
- Docker
- Docker Compose

## Запуск

### 1. Запустить все сервисы
```shell
docker compose up -d
```

### 2. Подождать 60 секунд пока Keycloak и базы данных инициализируются

### 3. Инициализировать данные CRM
```shell
docker compose cp airflow/dags/init_crm.sql crm_db:/tmp/init_crm.sql
docker compose exec crm_db psql -U crm_user -d crm_db -f /tmp/init_crm.sql
```

### 4. Создать bucket в MinIO
```shell
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc mb local/reports
```

### 5. Установить зависимости в Airflow
```shell
docker compose exec airflow python -m pip install psycopg2-binary clickhouse-connect==0.6.23 --user
```

### 6. Зарегистрировать Debezium коннектор (подождать пока kafka-connect запустится ~30 сек)
```shell
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @debezium/debezium-connector.json
```

### 7. Настроить ClickHouse
```shell
docker compose exec clickhouse clickhouse-client --multiquery --queries-file /tmp/setup.sql
```
Предварительно скопировать файл:
```shell
docker compose cp debezium/clickhouse-kafka-setup.sql clickhouse:/tmp/setup.sql
```

## Доступные сервисы

| Сервис | URL | Логин |
|--------|-----|-------|
| Frontend | http://localhost:3000 | prothetic1 / prothetic123 |
| Keycloak Admin | http://localhost:8080/admin | admin / admin |
| Airflow | http://localhost:8081 | admin / admin |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| phpLDAPadmin | http://localhost:8090 | cn=admin,dc=example,dc=com / admin |

## Тестовые пользователи

| Пользователь | Пароль | Роль |
|-------------|--------|------|
| prothetic1 | prothetic123 | prothetic_user |
| prothetic2 | prothetic123 | prothetic_user |
| prothetic3 | prothetic123 | prothetic_user |