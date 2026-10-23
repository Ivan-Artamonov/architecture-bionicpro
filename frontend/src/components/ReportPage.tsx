import React, { useEffect, useState } from 'react';
import { sessionRequest } from '../api';

type Session = { user: { username: string }; csrf_token: string };

const ReportPage: React.FC = () => {
  const [session, setSession] = useState<Session | null>(null);
  const [initialized, setInitialized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    sessionRequest('/api/session')
      .then(async response => {
        if (response.status === 401) return null;
        if (!response.ok) throw new Error('Сервис авторизации недоступен');
        return response.json();
      })
      .then(value => { if (active) setSession(value); })
      .catch(err => { if (active) setError(err.message); })
      .finally(() => { if (active) setInitialized(true); });
    return () => { active = false; };
  }, []);

  const downloadReport = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await sessionRequest('/api/reports');
      if (response.status === 401) setSession(null);
      if (!response.ok) throw new Error('Отчёт недоступен');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = 'report.pdf';
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    if (!session) return;
    setLoading(true);
    try {
      const response = await sessionRequest('/auth/logout', {
        method: 'POST', headers: { 'X-CSRF-Token': session.csrf_token },
      });
      if (!response.ok && response.status !== 401) throw new Error('Не удалось полностью завершить выход');
      setSession(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка выхода');
    } finally {
      setLoading(false);
    }
  };

  if (!initialized) {
    return <div>Loading...</div>;
  }

  if (!session) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <button
          onClick={() => { window.location.href = '/auth/login'; }}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
        {error && <p role="alert">{error}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md">
        <h1 className="text-2xl font-bold mb-6">Usage Reports</h1>
        <p>{session.user.username}</p>
        <button onClick={logout} disabled={loading}>Logout</button>
        
        <button
          onClick={downloadReport}
          disabled={loading}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Generating Report...' : 'Download Report'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">
            {error}
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;
