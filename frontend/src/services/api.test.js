import { describe, expect, it, vi } from 'vitest';
import { api, districtPath, resolveApiBase } from './api';

describe('resolveApiBase', () => {
  it('uses the page origin in a production build', () => {
    expect(resolveApiBase({ PROD: true }, 'https://agrooptimize.onrender.com')).toBe('https://agrooptimize.onrender.com');
  });

  it('uses the local backend in development', () => {
    expect(resolveApiBase({ PROD: false, DEV: true }, 'http://localhost:5173')).toBe('http://localhost:8000');
  });

  it('prefers VITE_API_BASE when it is set, without a trailing slash', () => {
    const env = { PROD: true, VITE_API_BASE: 'https://api.example.org/' };
    expect(resolveApiBase(env, 'https://app.example.org')).toBe('https://api.example.org');
  });

  it('ignores an empty VITE_API_BASE', () => {
    expect(resolveApiBase({ PROD: true, VITE_API_BASE: '' }, 'https://app.example.org')).toBe('https://app.example.org');
  });
});

describe('district paths', () => {
  it('lower-cases and encodes catalog district names', () => {
    expect(districtPath('Salem')).toBe('salem');
    expect(districtPath(' The Nilgiris ')).toBe('the%20nilgiris');
  });
});

describe('fuzzy models', () => {
  it('sends the chosen fuzzy model with a plan request and omits it when unset', async () => {
    const bodies = [];
    const store = {};
    vi.stubGlobal('localStorage', { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } });
    vi.stubGlobal('fetch', vi.fn(async (_url, init) => {
      bodies.push(JSON.parse(init.body));
      return { ok: true, json: async () => ({}) };
    }));
    try {
      await api.runOptimization({ location: 'Salem', fuzzy_model: 'improved' });
      await api.runOptimization({ location: 'Salem' });
    } finally {
      vi.unstubAllGlobals();
    }
    expect(bodies[0].fuzzy_model).toBe('improved');
    expect('fuzzy_model' in bodies[1]).toBe(false);
  });
});
