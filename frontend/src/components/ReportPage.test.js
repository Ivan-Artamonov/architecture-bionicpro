import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ReportPage from './ReportPage';
import { sessionRequest } from '../api';

jest.mock('../api', () => ({ sessionRequest: jest.fn() }));

test('loads own report through BFF, shows metrics and downloads JSON', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const session = { user: { username: 'user1' }, csrf_token: 'csrf' };
  const report = { period_start: '2026-09-23', period_end: '2026-10-23T16:00:00Z',
    prepared_at: '2026-10-23T16:01:00Z', daily: [{ day: '2026-10-23', prosthesis_id: 'BP-001',
      model: 'Bionic Hand', samples: 10, avg_response_ms: 60, max_response_ms: 80,
      min_battery_percent: 70, successful_movements: 9 }] };
  sessionRequest.mockResolvedValueOnce({ ok: true, status: 200, json: async () => session })
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => report });
  URL.createObjectURL = jest.fn(() => 'blob:report');
  URL.revokeObjectURL = jest.fn();
  const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
    expect(this.download).toBe('report.json');
  });
  const container = document.createElement('div');
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ReportPage />));
    jest.useFakeTimers();
    const button = Array.from(container.querySelectorAll('button')).find(b => b.textContent === 'Получить отчёт');
    await act(async () => button.click());
    expect(sessionRequest).toHaveBeenLastCalledWith('/api/reports');
    expect(container.querySelector('tbody').textContent).toContain('BP-001');
    expect(container.querySelector('tbody').textContent).toContain('60');
    expect(click).toHaveBeenCalledTimes(1);
  } finally {
    act(() => root.unmount());
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    click.mockRestore();
    delete global.IS_REACT_ACT_ENVIRONMENT;
  }
});
