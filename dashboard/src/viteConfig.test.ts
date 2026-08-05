import type { ProxyOptions, UserConfig } from 'vite';
import { describe, expect, it } from 'vitest';

import config from '../vite.config';

describe('dashboard Vite backend proxy', () => {
  it('forwards the dashboard API prefix to FastAPI without the prefix', () => {
    const userConfig = config as UserConfig;
    const proxy = userConfig.server?.proxy as Record<string, ProxyOptions> | undefined;
    const backendProxy = proxy?.['/__peso_api'];

    expect(backendProxy).toBeDefined();
    expect(backendProxy?.target).toBe('http://127.0.0.1:8000');
    expect(backendProxy?.rewrite?.('/__peso_api/dev/analysis-runs')).toBe('/dev/analysis-runs');
  });
});
