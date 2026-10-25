# OldShop frontend

Angular 21 standalone components, Bootstrap 5, Chart.js, SweetAlert2.

```bash
npm ci
npm start                                  # http://localhost:4200, talks to the API on :8000
npx ng build --configuration production    # uses src/environments/environment.prod.ts
```

| Folder | Content |
|---|---|
| `src/app/core` | auth service, guard, HTTP interceptor (JWT), models, shared utils |
| `src/app/features` | one folder per area: shop, cart/checkout, seller, moderator, admin, contact |
| `src/app/shared/services` | API clients per domain |
| `nginx.conf` | production server: SPA fallback, `/api` and `/media` reverse proxy, caching headers |

In production the SPA, `/api` and `/media` share one origin, so `environment.prod.ts` uses relative URLs.
