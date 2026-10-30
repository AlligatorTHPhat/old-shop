import { Component } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

@Component({ standalone: true, template: '' })
class EmptyRoute {}

// Component smoke tests use an HTTP test backend and isolated routes, never the real API.
export const testProviders = [
  provideHttpClient(), provideHttpClientTesting(),
  provideRouter([{ path: '**', component: EmptyRoute }]),
];
