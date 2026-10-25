import { environment } from '../../../environments/environment';

/**
 * Resolve a media path returned by the API (e.g. `/media/users/x.png`) to a URL the browser can load.
 * In production `imageBaseUrl` is empty and Nginx proxies `/media/` on the same origin.
 */
export function mediaUrl(path: string | null | undefined, fallback = 'assets/images/default-avt.png'): string {
  if (!path) return fallback;
  if (/^(https?:|data:)/.test(path)) return path;
  const base = environment.imageBaseUrl.replace(/\/$/, '');
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}
