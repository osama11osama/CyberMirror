import { HttpInterceptorFn } from '@angular/common/http';

const TOKEN_KEY = 'cybermirror_api_token';

export function storeApiToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getApiToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const token = getApiToken();
  if (token && req.url.includes('/api/') && !req.url.endsWith('/health')) {
    req = req.clone({ setHeaders: { 'X-CyberMirror-Token': token } });
  }
  return next(req);
};
