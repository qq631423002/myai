/**
 * 浏览器语音识别（Web Speech API）的类型声明和获取函数。
 *
 * 为什么自己写类型：`SpeechRecognition` 是浏览器实验性 API，TypeScript 的
 * lib.dom.d.ts 里没有完整声明，所以这里自己声明一份最小够用的。
 *
 * ⚠️ 注意：这个 API **不是本地识别**，浏览器会把音频传给云端（Chrome 用 Google、
 * Edge 用微软）识别，所以**必须能连上那些服务器**，否则会触发
 * `onerror` 的 `"network"` 错误。
 */

export interface SpeechAlternative {
  readonly transcript: string
}

export interface SpeechResult {
  readonly isFinal: boolean
  readonly length: number
  readonly [index: number]: SpeechAlternative
}

export interface SpeechResultList {
  readonly length: number
  readonly [index: number]: SpeechResult
}

export interface SpeechResultEvent {
  readonly resultIndex: number
  readonly results: SpeechResultList
}

export interface SpeechErrorEvent {
  readonly error: string
}

export interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start(): void
  stop(): void
  abort(): void
  onstart: (() => void) | null
  onresult: ((event: SpeechResultEvent) => void) | null
  onerror: ((event: SpeechErrorEvent) => void) | null
  onend: (() => void) | null
}

export type SpeechRecognitionCtor = new () => SpeechRecognitionLike

/** 取浏览器里的语音识别实现（Chrome / Edge 上是 webkit 前缀那个） */
export function getSpeechRecognition(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}
