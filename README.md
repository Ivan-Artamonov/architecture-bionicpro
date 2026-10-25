# Первый запуск

1. Запустите Keycloak и frontend из корня проекта:

```
docker compose up -d --build
```

2. Запустите Reports stack:

```
docker compose -f reports/docker-compose.yaml up -d --build
```

В первый запуск `airflow-init` создает базу Airflow и пользователя:

```
Airflow: http://localhost:8081
Логин: admin
Пароль: admin
```

Keycloak доступен по адресу `http://localhost:8080`. Пользователь приложения:

```
Логин: user1
Пароль: password123
```

3. Разрешите запуск DAG и запустите первоначальную загрузку fixtures:

```
docker compose -f reports/docker-compose.yaml exec airflow-scheduler \
  airflow dags unpause reports_etl

docker compose -f reports/docker-compose.yaml exec airflow-scheduler \
  airflow dags trigger reports_etl
```

DAG должен последовательно выполнить задачи `load_fixtures`, `build_report_mart` и `update_processed_until`.
После этого можно открыть:

- Frontend: http://localhost:3000;
- Reports API: http://localhost:8000;
- Airflow UI: http://localhost:8081;
- ClickHouse HTTP: http://localhost:8123.

# Повторный запуск

Для обычного повторного запуска уже созданного окружения:

```bash
docker compose up -d
docker compose -f reports/docker-compose.yaml up -d
```

## Остановка

```bash
docker compose down
docker compose -f reports/docker-compose.yaml down
```