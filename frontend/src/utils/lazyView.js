import { lazy } from 'react';

const RELOAD_FLAG = 'agro_chunk_reload';

/**
 * React.lazy for a page component. After a redeploy, a tab opened on the old
 * build may ask for a chunk that no longer exists; the page then reloads once
 * to pick up the new build instead of failing. A second failure is real and
 * is rethrown.
 */
export function lazyView(loader) {
  return lazy(() =>
    loader()
      .then((module) => {
        try { sessionStorage.removeItem(RELOAD_FLAG); } catch { /* storage unavailable */ }
        return module;
      })
      .catch((error) => {
        let reloaded = false;
        try { reloaded = sessionStorage.getItem(RELOAD_FLAG) === '1'; } catch { /* storage unavailable */ }
        if (!reloaded) {
          try { sessionStorage.setItem(RELOAD_FLAG, '1'); } catch { /* storage unavailable */ }
          window.location.reload();
          return new Promise(() => {});
        }
        throw error;
      }),
  );
}
