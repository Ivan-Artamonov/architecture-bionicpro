FROM apache/airflow:2.10.5-python3.12
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements.txt
COPY dags /opt/airflow/dags
