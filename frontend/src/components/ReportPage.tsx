import React, { useEffect, useState } from 'react';

type Session = { subject: string; username: string };

export default function ReportPage() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [through, setThrough] = useState(() => {
    const day = new Date();
    day.setDate(day.getDate() - 1);
    return day.toISOString().slice(0, 10);
  });

  useEffect(() => {
    fetch('/auth/session', { credentials: 'include' })
      .then(async response => response.ok ? setSession(await response.json()) : setSession(null))
      .catch(() => setError('Сервис авторизации недоступен'))
      .finally(() => setLoading(false));
  }, []);

  async function downloadReport() {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/reports?through=${encodeURIComponent(through)}`, { credentials: 'include' });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || 'Не удалось получить отчёт');
      }
      const { url } = await response.json();
      const link = document.createElement('a');
      link.href = url;
      link.download = `bionicpro-${through}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setLoading(false);
    }
  }

  if (loading && !session) return <main className="p-8">Загрузка…</main>;
  return <main className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
    <section className="p-8 bg-white rounded-lg shadow-md max-w-lg">
      <h1 className="text-2xl font-bold mb-6">Отчёт о работе протеза</h1>
      {session ? <>
        <p className="mb-4">Пользователь: {session.username}</p>
        <label className="block mb-4">Данные по дату
          <input className="block border p-2 mt-1" type="date" value={through}
            onChange={event => setThrough(event.target.value)} />
        </label>
        <button className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
          onClick={downloadReport} disabled={loading}>Скачать отчёт</button>
        <button className="ml-3 underline" onClick={async () => {
          await fetch('/auth/logout', { method: 'POST', credentials: 'include' });
          setSession(null);
        }}>Выйти</button>
      </> : <>
        <a className="px-4 py-2 bg-blue-500 text-white rounded" href="/auth/login">Войти</a>
        <a className="ml-3 underline" href="/auth/login?idp=yandex">Войти через Яндекс ID</a>
      </>}
      {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
    </section>
  </main>;
}
