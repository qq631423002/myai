/**
 * 麦克风音量计 —— 只负责读取实时音量，给界面画声波条用。
 *
 * 识别本身由浏览器的 Web Speech API 负责（见 utils/speech.ts），和这里无关。
 * 参数参考 deepai 那版的 startVisualizer：
 *   fftSize = 128、smoothingTimeConstant = 0.7、每根条取一段频段求平均。
 */

export class MicMeter {
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private analyser: AnalyserNode | null = null
  // 显式写成 Uint8Array<ArrayBuffer>：新版 TS 里 Uint8Array 带泛型参数，
  // 而 getByteFrequencyData 只接受背后是 ArrayBuffer（不是 SharedArrayBuffer）的那种
  private buffer: Uint8Array<ArrayBuffer> | null = null

  get running(): boolean {
    return this.ctx !== null
  }

  async start(): Promise<void> {
    if (this.ctx) return

    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    this.ctx = new AudioContext()
    this.analyser = this.ctx.createAnalyser()
    this.analyser.fftSize = 128
    this.analyser.smoothingTimeConstant = 0.7
    this.ctx.createMediaStreamSource(this.stream).connect(this.analyser)
    this.buffer = new Uint8Array(this.analyser.frequencyBinCount)
  }

  /**
   * 返回 count 个 0.22 ~ 1 的高度值（静音时也有 0.22，免得声波条整个消失）。
   * 从低音到高音依次排列。
   */
  getLevels(count: number): number[] {
    const analyser = this.analyser
    const buffer = this.buffer
    if (!analyser || !buffer) return new Array<number>(count).fill(0.22)

    analyser.getByteFrequencyData(buffer)

    const levels: number[] = []
    const total = buffer.length
    for (let i = 0; i < count; i++) {
      const start = Math.floor((i * total) / count)
      const end = Math.max(start + 1, Math.floor(((i + 1) * total) / count))
      let sum = 0
      for (let j = start; j < end; j++) sum += buffer[j] ?? 0
      const avg = sum / (end - start)
      levels.push(Math.max(0.22, Math.min(1, 0.18 + avg / 130)))
    }
    return levels
  }

  async stop(): Promise<void> {
    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null
    this.analyser = null
    this.buffer = null
    const ctx = this.ctx
    this.ctx = null
    if (ctx) await ctx.close().catch(() => undefined)
  }
}
