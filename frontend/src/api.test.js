import { sessionRequest } from './api';

test('all protected requests include cookies and use a cross-tab lock', async () => {
  const response = { ok: true };
  global.fetch = jest.fn().mockResolvedValue(response);
  Object.defineProperty(navigator, 'locks', {
    configurable: true, value: { request: jest.fn((name, action) => action()) },
  });
  expect(await sessionRequest('/api/session')).toBe(response);
  expect(navigator.locks.request).toHaveBeenCalledWith('bionicpro-session', expect.any(Function));
  expect(fetch).toHaveBeenCalledWith('/api/session', { credentials: 'include' });
});

test('fails closed when cross-tab serialization is unsupported', async () => {
  Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined });
  await expect(sessionRequest('/api/reports')).rejects.toThrow('Web Locks');
});
