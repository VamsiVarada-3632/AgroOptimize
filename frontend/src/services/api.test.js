import { describe, expect, it } from 'vitest';
import { resolveApiBase } from './api';

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
