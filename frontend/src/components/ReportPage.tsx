import React, { useEffect, useState } from 'react';
import { sessionRequest } from '../api';

type YandexProfile = { consent: 'pending' | 'accepted' | 'declined'; profile: Record<string, string> | null };
type Session = { user: { username: string }; csrf_token: string; yandex?: YandexProfile };

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

  const decideProfile = async (accepted: boolean) => {
    if (!session) return;
    setLoading(true);
    setError(null);
    try {
      const response = await sessionRequest('/api/profile/yandex/consent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token },
        body: JSON.stringify({ accepted }),
      });
      if (response.status === 401) setSession(null);
      if (!response.ok) throw new Error('Не удалось сохранить решение. Повторите попытку или войдите через Яндекс заново.');
      const yandex: YandexProfile = await response.json();
      setSession(current => current ? { ...current, yandex } : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка импорта профиля');
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
        <a href="/auth/login?provider=yandex">Войти через Яндекс ID</a>
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
        {session.yandex && (
          <section aria-label="Согласие на использование профиля Яндекса">
            <p>Разрешить BionicPRO получить из Яндекса и сохранить ID, логин, имя и email
              для заполнения вашего профиля? Отказ не мешает работе с сервисом.
              Дата рождения, пол, телефон и фото не сохраняются.</p>
            <button onClick={() => decideProfile(true)} disabled={loading}>
              {session.yandex.consent === 'accepted' ? 'Обновить профиль' : 'Разрешить'}
            </button>
            <button onClick={() => decideProfile(false)} disabled={loading}>
              {session.yandex.consent === 'accepted' ? 'Отозвать согласие и удалить профиль' : 'Отказать'}
            </button>
            {session.yandex.consent === 'accepted' && <p>Профиль сохранён: {session.yandex.profile?.display_name}
              {' '}{session.yandex.profile?.default_email}</p>}
            {session.yandex.consent === 'declined' && <p>Использование профиля запрещено, данные профиля не хранятся.</p>}
          </section>
        )}
        
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
