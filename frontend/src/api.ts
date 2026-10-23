// The lock spans tabs: each response must update the cookie before the next request.
export async function sessionRequest(path: string, options: RequestInit = {}): Promise<Response> {
  if (!navigator.locks) {
    throw new Error('Для работы требуется браузер с Web Locks API (HTTPS или localhost).');
  }
  return navigator.locks.request('bionicpro-session', () =>
    fetch(path, { ...options, credentials: 'include' })
  );
}
