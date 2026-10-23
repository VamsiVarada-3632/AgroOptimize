import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { lazyView } from './lazyView';

// React.lazy keeps the loader in _payload._result until first render.
const load = (component) => component._payload._result();

// The tests run in Node: provide the two browser globals lazyView touches.
function memoryStorage() {
  const items = new Map();
  return {
    getItem: (k) => (items.has(k) ? items.get(k) : null),
    setItem: (k, v) => items.set(k, String(v)),
    removeItem: (k) => items.delete(k),
  };
}

describe('lazyView', () => {
  let reload;
  beforeEach(() => {
    reload = vi.fn();
    vi.stubGlobal('window', { location: { reload } });
    vi.stubGlobal('sessionStorage', memoryStorage());
  });
  afterEach(() => vi.unstubAllGlobals());

  it('returns the module and clears the reload flag', async () => {
    sessionStorage.setItem('agro_chunk_reload', '1');
    const module = { default: () => null };
    await expect(load(lazyView(() => Promise.resolve(module)))).resolves.toBe(module);
    expect(sessionStorage.getItem('agro_chunk_reload')).toBeNull();
    expect(reload).not.toHaveBeenCalled();
  });

  it('reloads the page once when a chunk is missing', () => {
    load(lazyView(() => Promise.reject(new Error('Failed to fetch dynamically imported module'))));
    return vi.waitFor(() => {
      expect(reload).toHaveBeenCalledTimes(1);
      expect(sessionStorage.getItem('agro_chunk_reload')).toBe('1');
    });
  });

  it('rethrows when the chunk is still missing after the reload', async () => {
    sessionStorage.setItem('agro_chunk_reload', '1');
    const error = new Error('still missing');
    await expect(load(lazyView(() => Promise.reject(error)))).rejects.toBe(error);
    expect(reload).not.toHaveBeenCalled();
  });
});
