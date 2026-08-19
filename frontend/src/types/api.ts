export interface ApiErrorResponse {
  code: string
  message: string
  status: number
  path: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  token: string
  expiresIn: number
}

export interface RegisterRequest {
  username: string
  password: string
}

export interface UserResponse {
  id: string
  username: string
  createdAt: string
}

export interface Conversation {
  id: string
  title: string
  modelId: ModelId
  createdAt: string
  updatedAt: string
}

export type MessageRole = 'USER' | 'ASSISTANT'

export interface ChatMessage {
  id: number
  role: MessageRole
  content: string
  imageId: string | null
  createdAt: string
  temporary?: boolean
  generatedImages?: GeneratedImage[]
  imageGenerationFailed?: boolean
  imageRetryPrompt?: string
}

export interface PageResponse<T> {
  content: T[]
  page: number
  size: number
  totalElements: number
  totalPages: number
}

export interface ChatRequest {
  conversationId?: string
  message: string
  imageId?: string
  modelId?: ModelId
}

export type ModelId = 'STEP_FLASH_3_7' | 'DEEPSEEK_V4_PRO'

export interface ModelInfo {
  id: ModelId
  displayName: string
  supportsText: boolean
  supportsTools: boolean
  supportsStreaming: boolean
  supportsImages: boolean
  available: boolean
}

export interface ChatResponse {
  conversationId: string
  answer: string
  generatedImages: GeneratedImage[]
}

export interface GeneratedImage {
  imageId: string
  url: string
  imageModel: string
  createdAt: string
}

export type ChatStreamStage =
  | 'thinking'
  | 'analyzing_image'
  | 'summarizing_context'
  | 'searching_recipes'
  | 'generating_image'
  | 'generating_answer'
  | 'completed'

export interface ChatStreamEvent {
  type: 'status' | 'token' | 'generated_image' | 'image_error' | 'done' | 'error'
  conversationId: string
  stage?: ChatStreamStage
  message?: string
  content?: string
  generatedImage?: GeneratedImage
}

export interface ImageResponse {
  imageId: string
  url: string
  originalFilename: string
  contentType: string
  size: number
}

export interface ForumAuthor {
  id: string
  username: string
}

export type ForumImageType = 'USER_UPLOAD' | 'AI_GENERATED'

export interface ForumPost {
  id: string
  title: string
  content: string
  author: ForumAuthor
  imageId: string | null
  imageType: ForumImageType | null
  createdAt: string
  updatedAt: string
  isOwner: boolean
}

export interface ForumPostRequest {
  title: string
  content: string
  imageId: string | null
  imageType: ForumImageType | null
  sourceConversationId?: string | null
}

export interface ForumDraft {
  sourceConversationId: string
  title: string
  content: string
  dishName: string
  suggestedImageId: string | null
  suggestedImageType: ForumImageType | null
  modelId: ModelId
}

export type MemoryType =
  | 'DIETARY_RESTRICTION'
  | 'FOOD_PREFERENCE'
  | 'CUISINE_PREFERENCE'
  | 'COOKING_PREFERENCE'
  | 'HOUSEHOLD_CONTEXT'
  | 'NUTRITION_GOAL'

export interface Memory {
  id: string
  memoryType: MemoryType
  key: string
  value: string
  createdAt: string
  updatedAt: string
}

export interface UpdateMemoryRequest {
  memoryType: MemoryType
  key: string
  value: string
}
