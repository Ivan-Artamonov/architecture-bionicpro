import React, { useCallback, useEffect, useState } from 'react';
import { useKeycloak } from '@react-keycloak/web';

interface ReportItem {
  prosthesis_id: string;
  day: string;
  product_model: string;
  events_count: number;
  avg_reaction_time_ms: number;
  p95_reaction_time_ms: number;
  avg_battery_level: number;
  avg_signal_quality: number;
}

interface ReportResponse {
  period_from: string | null;
  period_to: string | null;
  processed_until: string;
  items: ReportItem[];
}

interface AvailableReport {
  day: string;
  prostheses_count: number;
  events_count: number;
  avg_reaction_time_ms: number;
  avg_battery_level: number;
  avg_signal_quality: number;
}

const ReportPage: React.FC = () => {
  const { keycloak, initialized } = useKeycloak();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [availableReports, setAvailableReports] = useState<AvailableReport[]>([]);

  const loadAvailableReports = useCallback(async () => {
    if (!keycloak?.authenticated || !keycloak.token) {
      return;
    }

    try {
      await keycloak.updateToken(30);
      const response = await fetch(`${process.env.REACT_APP_API_URL}/reports/available`, {
        headers: {
          Authorization: `Bearer ${keycloak.token}`
        }
      });
      if (!response.ok) {
        throw new Error('Не удалось получить список отчетов');
      }
      setAvailableReports(await response.json() as AvailableReport[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось получить список отчетов');
    }
  }, [keycloak]);

  useEffect(() => {
    if (initialized && keycloak.authenticated) {
      void loadAvailableReports();
    }
  }, [initialized, keycloak.authenticated, loadAvailableReports]);

  const getReport = async (from?: string, to?: string) => {
    if (!keycloak?.authenticated || !keycloak.token) {
      setError('Необходимо войти в систему');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setReport(null);

      await keycloak.updateToken(30);

      const query = new URLSearchParams();
      if (from) query.set('from', from);
      if (to) query.set('to', to);
      const queryString = query.toString();
      const response = await fetch(`${process.env.REACT_APP_API_URL}/reports${queryString ? `?${queryString}` : ''}`, {
        headers: {
          Authorization: `Bearer ${keycloak.token}`
        }
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const detail = body?.detail;
        const message = typeof detail === 'object' ? detail.message : detail;

        if (response.status === 401) {
          throw new Error('Сессия истекла. Выполните вход повторно');
        }
        if (response.status === 409) {
          throw new Error(message || 'Запрошенный период еще не обработан');
        }
        if (response.status === 422) {
          throw new Error(message || 'Некорректный период отчета');
        }
        throw new Error(message || 'Не удалось получить отчет');
      }

      setReport(await response.json() as ReportResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось получить отчет');
    } finally {
      setLoading(false);
    }
  };

  if (!initialized) {
    return <div>Loading...</div>;
  }

  if (!keycloak.authenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <button
          onClick={() => keycloak.login()}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center bg-gray-100 p-8">
      <div className="w-full max-w-6xl rounded-lg bg-white p-8 shadow-md">
        <h1 className="mb-6 text-2xl font-bold">Отчет о работе протеза</h1>

        <h2 className="mb-3 text-lg font-semibold">Доступные отчеты</h2>
        {availableReports.length === 0 ? (
          <p className="mb-6 text-gray-600">Отчеты отсутствуют.</p>
        ) : (
          <div className="mb-6 overflow-x-auto">
            <table className="min-w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b">
                  <th className="p-2">Дата</th>
                  <th className="p-2">Протезы</th>
                  <th className="p-2">События</th>
                  <th className="p-2">Средняя реакция, мс</th>
                  <th className="p-2">Батарея, %</th>
                  <th className="p-2">Сигнал</th>
                  <th className="p-2"></th>
                </tr>
              </thead>
              <tbody>
                {availableReports.map((item) => (
                  <tr key={item.day} className="border-b">
                    <td className="p-2">{item.day}</td>
                    <td className="p-2">{item.prostheses_count}</td>
                    <td className="p-2">{item.events_count}</td>
                    <td className="p-2">{item.avg_reaction_time_ms.toFixed(1)}</td>
                    <td className="p-2">{item.avg_battery_level.toFixed(1)}</td>
                    <td className="p-2">{item.avg_signal_quality.toFixed(2)}</td>
                    <td className="p-2">
                      <button
                        onClick={() => void getReport(item.day, item.day)}
                        className="text-blue-600 hover:underline"
                      >
                        Открыть
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <button
          onClick={() => void getReport()}
          disabled={loading}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Загрузка отчета...' : 'Получить отчет'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">
            {error}
          </div>
        )}

        {report && (
          <div className="mt-6 overflow-x-auto">
            <p className="mb-4 text-sm text-gray-600">
              Обработано по: {report.processed_until}
            </p>
            {report.items.length === 0 ? (
              <p className="text-gray-600">За обработанный период данных нет.</p>
            ) : (
              <table className="min-w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="p-2">Дата</th>
                    <th className="p-2">Протез</th>
                    <th className="p-2">Модель</th>
                    <th className="p-2">События</th>
                    <th className="p-2">Средняя реакция, мс</th>
                    <th className="p-2">P95 реакции, мс</th>
                    <th className="p-2">Батарея, %</th>
                    <th className="p-2">Качество сигнала</th>
                  </tr>
                </thead>
                <tbody>
                  {report.items.map((item) => (
                    <tr key={`${item.prosthesis_id}-${item.day}`} className="border-b">
                      <td className="p-2">{item.day}</td>
                      <td className="p-2">{item.prosthesis_id}</td>
                      <td className="p-2">{item.product_model}</td>
                      <td className="p-2">{item.events_count}</td>
                      <td className="p-2">{item.avg_reaction_time_ms.toFixed(1)}</td>
                      <td className="p-2">{item.p95_reaction_time_ms.toFixed(1)}</td>
                      <td className="p-2">{item.avg_battery_level.toFixed(1)}</td>
                      <td className="p-2">{item.avg_signal_quality.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;
