import { HttpInterceptorFn } from '@angular/common/http';

const TOKEN_KEY = 'cybermirror_api_token';
let initialized = false;

function initializeApiToken(): void {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;

  const injected = (window as any).cyberMirror?.apiToken;
  if (typeof injected === 'string' && injected) {
    storeApiToken(injected);
    return;
  }

  const rawHash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash;
  const params = new URLSearchParams(rawHash);
  const token = params.get('api_token');
  if (!token) return;

  storeApiToken(token);
  params.delete('api_token');

  const remainingHash = params.toString();
  const cleanUrl =
    window.location.pathname +
    window.location.search +
    (remainingHash ? `#${remainingHash}` : '');
  window.history.replaceState(null, document.title, cleanUrl);
}

export function storeApiToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function getApiToken(): string | null {
  initializeApiToken();
  return sessionStorage.getItem(TOKEN_KEY);
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const token = getApiToken();
  if (token && req.url.includes('/api/') && !req.url.endsWith('/health')) {
    req = req.clone({ setHeaders: { 'X-CyberMirror-Token': token } });
  }
  return next(req);
};
