/**
 * Serviço de Rate Limiting
 * Controla quantidade de requisições por usuário
 */

import { config } from '../config.js';

class RateLimiterService {
  constructor() {
    // Map de contadores: userId -> { count, windowStart }
    this.counters = new Map();
    
    this.limit = config.rateLimit.perUser;
    this.windowMs = config.rateLimit.windowMs;

    // Limpa contadores antigos a cada minuto
    setInterval(() => this.cleanup(), 60000);
  }

  /**
   * Verifica se usuário pode fazer requisição
   * @returns {Object} { allowed: boolean, remaining: number, resetIn: number }
   */
  check(userId) {
    const cleanId = this.cleanUserId(userId);
    const now = Date.now();

    let counter = this.counters.get(cleanId);

    // Se não existe ou janela expirou, cria novo
    if (!counter || (now - counter.windowStart) >= this.windowMs) {
      counter = {
        count: 0,
        windowStart: now,
      };
      this.counters.set(cleanId, counter);
    }

    const remaining = Math.max(0, this.limit - counter.count);
    const resetIn = Math.ceil((counter.windowStart + this.windowMs - now) / 1000);

    return {
      allowed: counter.count < this.limit,
      remaining,
      resetIn: Math.max(0, resetIn),
    };
  }

  /**
   * Consome uma requisição do rate limit
   * @returns {Object} { allowed: boolean, remaining: number, resetIn: number }
   */
  consume(userId) {
    const result = this.check(userId);
    
    if (result.allowed) {
      const cleanId = this.cleanUserId(userId);
      const counter = this.counters.get(cleanId);
      counter.count++;
      result.remaining = Math.max(0, this.limit - counter.count);
    }

    return result;
  }

  /**
   * Reseta o contador de um usuário (para admins)
   */
  reset(userId) {
    const cleanId = this.cleanUserId(userId);
    this.counters.delete(cleanId);
  }

  /**
   * Limpa contadores expirados
   */
  cleanup() {
    const now = Date.now();
    let cleaned = 0;

    for (const [userId, counter] of this.counters) {
      if ((now - counter.windowStart) >= this.windowMs) {
        this.counters.delete(userId);
        cleaned++;
      }
    }

    return cleaned;
  }

  /**
   * Limpa ID do usuário
   */
  cleanUserId(userId) {
    return userId.replace('@s.whatsapp.net', '').replace('@g.us', '');
  }

  /**
   * Estatísticas do rate limiter
   */
  getStats() {
    return {
      activeUsers: this.counters.size,
      limit: this.limit,
      windowMs: this.windowMs,
    };
  }
}

// Singleton
export const rateLimiterService = new RateLimiterService();
export default rateLimiterService;
