const TOKEN_KEY = 'ai-cooker.access-token'

let unauthorizedHandler: (() => void) | undefined

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function saveAccessToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearAccessToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function setUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler
}

export function notifyUnauthorized(): void {
  clearAccessToken()
  unauthorizedHandler?.()
}
