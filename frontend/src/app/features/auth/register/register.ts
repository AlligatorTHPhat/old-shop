import { Component, ElementRef, ViewChild, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common'; 
import { ReactiveFormsModule, FormBuilder, FormGroup, Validators, AbstractControl, ValidationErrors } from '@angular/forms';
import { AuthService } from '../../../core/services/auth.service';
declare var bootstrap: any;

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [ReactiveFormsModule, CommonModule],
  templateUrl: './register.html',
  styleUrls: ['./register.scss']
})
export class RegisterComponent {
  @ViewChild('closeButton') closeButton!: ElementRef;
  registerForm: FormGroup;
  isLoading = false;
  message: { type: 'success' | 'error', text: string } | null = null;

  constructor(
    private fb: FormBuilder, 
    private authService: AuthService,
    private cdr: ChangeDetectorRef 
  ) {
    this.registerForm = this.fb.group({
      username: ['', [Validators.required, Validators.minLength(4)]],
      full_name: ['', Validators.required],
      email: ['', [Validators.required, Validators.email]],
      address: [''],
      password: ['', [Validators.required, Validators.minLength(6)]],
      confirmPassword: ['', Validators.required],
      phone_number: ['', [Validators.required, Validators.pattern(/^[0-9]{9,10}$/)]]
    }, { validators: this.passwordMatchValidator });
  }

  passwordMatchValidator(g: any) {
    return g.get('password')?.value === g.get('confirmPassword')?.value ? null : { passwordMismatch: true };
  }

  onSubmit() {
    if (this.registerForm.invalid) {
      this.registerForm.markAllAsTouched();
      return;
    }

    this.isLoading = true;
    this.message = null; 

    this.authService.register(this.registerForm.value).subscribe({
      next: () => {
        this.message = { type: 'success', text: 'Đăng ký thành công! Đang đóng...' };
        this.isLoading = false;
        this.cdr.markForCheck();

        setTimeout(() => {
          const modal = bootstrap.Modal.getInstance(this.closeButton.nativeElement.closest('.modal'));
          modal?.hide();
          this.registerForm.reset();
          this.message = null;
          this.cdr.detectChanges();
        }, 2000);
      },
      error: (err) => {
        this.isLoading = false;
        this.message = { 
          type: 'error', 
          text: err.error?.detail || 'Đăng ký thất bại, kiểm tra lại thông tin!' 
        };
        this.cdr.markForCheck();
      }
    });
  }
}