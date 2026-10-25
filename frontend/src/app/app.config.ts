import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';
import { provideHttpClient, withInterceptors } from '@angular/common/http'; // Thêm withInterceptors vào đây
import { authInterceptor } from './core/interceptors/auth.interceptor'; // Import đúng đường dẫn file interceptor
import { APP_INITIALIZER } from '@angular/core';
import { AuthService } from './core/services/auth.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    // MỞ DÒNG NÀY VÀ GẮN INTERCEPTOR VÀO
    provideHttpClient(withInterceptors([authInterceptor])), 
    
    {
      provide: APP_INITIALIZER,
      useFactory: (authService: AuthService) => () => {
        // Nếu vẫn không chạy, hãy tạm comment cả cái khối APP_INITIALIZER này
        // để xem trang Forgot Password có tự sống lại không.
        return new Promise((resolve) => {
          const interval = setInterval(() => {
            if (authService.isInitialized()) {
              clearInterval(interval);
              resolve(true);
            }
          }, 50);
          // Thêm cái timeout sau 3 giây để nếu lỗi nó vẫn cho vào app
          setTimeout(() => { clearInterval(interval); resolve(true); }, 3000);
        });
      },
      deps: [AuthService],
      multi: true
    }
  ]
};
