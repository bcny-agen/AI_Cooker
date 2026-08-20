import axios from 'axios'

import type { ApiErrorResponse } from '../types/api'

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError<ApiErrorResponse>(error)) {
    const message = error.response?.data?.message
    return message && /[\u3400-\u9fff]/.test(message) ? message : fallback
  }
  return error instanceof Error && /[\u3400-\u9fff]/.test(error.message) ? error.message : fallback
}
