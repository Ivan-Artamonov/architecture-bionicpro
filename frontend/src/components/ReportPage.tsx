import React, { useEffect, useState } from 'react';

type User = { id: string; name: string; yandex: boolean; consent: boolean | null };

// Запросы идут последовательно: каждый защищённый ответ меняет session cookie.
let queue: Promise<unknown> = Promise.resolve();
function api(path: string, options: RequestInit = {}): Promise<Response> {
  const result = queue.then(() => fetch(path, { ...options, credentials: 'include' }));
  queue = result.catch(() => undefined);
  return result;
}

export default function ReportPage() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  const [start, setStart] = useState(yesterday);
  const [end, setEnd] = useState(today);

  useEffect(() => {
    api('/auth/me').then(async response => {
      if (response.ok) setUser(await response.json());
      else if (response.status !== 401) setError('Не удалось получить профиль');
    }).catch(() => setError('Сервер недоступен')).finally(() => setReady(true));
  }, []);

  async function check(response: Response) {
    if (response.status === 401) {
      setUser(null);
      throw new Error('Сессия завершилась. Войдите заново');
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail :
        body.detail?.message || 'Не удалось выполнить запрос');
    }
    return response;
  }

  async function consent(allowed: boolean) {
    setBusy(true); setError('');
    try {
      await check(await api('/auth/consent', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ allowed }) }));
      setUser(current => current && { ...current, consent: allowed });
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function download() {
    setBusy(true); setError(''); setStatus('');
    try {
      const response = await check(await api(`/reports?start=${start}&end=${end}`));
      const report = await response.json();
      const file = await check(await api(report.url));
      const url = URL.createObjectURL(await file.blob());
      const link = document.createElement('a');
      link.href = url; link.download = `bionicpro-${start}-${end}.json`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setStatus(report.cached ? 'Отчёт скачан из кеша.' : 'Отчёт подготовлен и скачан.');
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function logout() {
    setBusy(true); setError('');
    try { await check(await api('/auth/logout', { method: 'POST' })); setUser(null); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return <main>
    <p className="brand">BionicPRO</p>
    <h1>Отчёт о работе протеза</h1>
    {!ready ? <p>Загружаем профиль…</p> : !user ? <>
      <p>Войдите, чтобы скачать данные о своих протезах.</p>
      <a className="button" href="/auth/login">Войти</a>
      <a className="secondary" href="/auth/login?provider=yandex">Войти через Яндекс ID</a>
    </> : <>
      <p>Пользователь: {user.name}</p>
      {user.yandex && <section>
        <h2>Данные Яндекс ID</h2>
        <p>Разрешить сохранить логин, отображаемое имя и email из Яндекса в профиле BionicPRO?
          Отчёты доступны и без согласия. При отзыве удаляем сохранённые данные профиля.</p>
        <p>Согласие: {user.consent === null ? 'не выбрано' : user.consent ? 'дано' : 'отклонено'}</p>
        <button disabled={busy || user.consent === true} onClick={() => consent(true)}>Разрешить</button>
        <button className="secondary" disabled={busy || user.consent === false}
          onClick={() => consent(false)}>{user.consent ? 'Отозвать согласие' : 'Отказаться'}</button>
      </section>}
      <section>
        <p>Выберите от 1 до 31 завершённого дня по UTC. Конечная дата не включается в отчёт.</p>
        <div className="dates">
          <label>С <input type="date" value={start} disabled={busy}
            onChange={event => setStart(event.target.value)} /></label>
          <label>До <input type="date" value={end} disabled={busy}
            onChange={event => setEnd(event.target.value)} /></label>
        </div>
        <button disabled={busy || !start || !end} onClick={download}>
          {busy ? 'Подождите…' : 'Скачать отчёт JSON'}</button>
        <p role="status">{status}</p>
      </section>
      <button className="secondary" onClick={logout} disabled={busy}>Выйти</button>
    </>}
    {error && <p className="error" role="alert">{error}</p>}
  </main>;
}
