import type { LoginRequest, LoginResponse, RegisterRequest, UserResponse } from '../types/api'
import { http } from './http'

export const authApi = {
  async login(request: LoginRequest): Promise<LoginResponse> {
    const { data } = await http.post<LoginResponse>('/api/auth/login', request)
    return data
  },

  async register(request: RegisterRequest): Promise<UserResponse> {
    const { data } = await http.post<UserResponse>('/api/auth/register', request)
    return data
  },
}
