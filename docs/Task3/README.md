# Задание 3. S3-кеш и CDN

- [API](../../reports-api/app/cache.py) проверяет JWT и наличие отчёта в закрытом MinIO. При промахе
  читает ClickHouse и сохраняет JSON; в обоих случаях возвращает CDN-ссылку на 5 минут.
- Ключ S3: `reports/v1/<snapshot_id>/<sha256(JSON([iss, sub]))>.json`.
  [ETL](../../airflow/dags/reports_etl.py) публикует `metadata/current.json` после EXCHANGE.
  Новая версия меняет путь, поэтому сброс CDN не нужен.
- [Nginx](nginx.conf) кеширует файлы на час, проверяя подпись и путь.
  Ключ кеша - URI без подписи; браузеру - `no-store`. [Lifecycle](minio/lifecycle.json) удаляет файлы через 7 дней.
- Порты S3/API закрыты, права API и ETL разделены. Ссылку нельзя передавать другим.
  Для эксплуатации нужны HTTPS и хранение данных в своём регионе.

## Запуск

Заполните `.env` по [примеру](../../.env.example), включая Task2 и Task3:

```bash
docker compose -f docker-compose.yaml -f docs/Task2/docker-compose.reports.yaml -f docs/Task3/docker-compose.cache.yaml up -d --build
```

Привяжите пользователей по [инструкции Task2](../Task2/README.md#запуск) и запустите DAG для создания S3-маркера.
На `http://localhost:3000` нажмите «Получить отчёт»: UI загрузит файл через CDN (`:8082`).
Повторная загрузка даёт `X-Cache-Status: HIT`, неверная/просроченная ссылка - 403, новая ETL-версия - MISS.
Task2 без S3 продолжает работать.
