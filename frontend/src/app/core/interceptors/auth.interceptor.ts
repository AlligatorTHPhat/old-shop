import { HttpInterceptorFn } from '@angular/common/http';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const token = sessionStorage.getItem('token');
  const whiteList = ['/auth/login', '/auth/forgot-password', '/auth/verify-reset-password'];
  const isWhiteListed = whiteList.some(url => req.url.includes(url));

  if (token && !isWhiteListed) {
    const cloned = req.clone({
      setHeaders: { Authorization: `Bearer ${token}` }
    });
    return next(cloned);
  }
  return next(req);
};