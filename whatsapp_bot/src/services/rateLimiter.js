import { config } from '../config.js';

class RateLimiterService {
  constructor() {
    this.requests = new Map();
  }

  consume(userId) {
    const now = Date.now();
    const windowMs = config.rateLimit.windowMs;
    const maxRequests = config.rateLimit.perUser;

    if (!this.requests.has(userId)) {
      this.requests.set(userId, []);
    }

    const userRequests = this.requests.get(userId);
    const validRequests = userRequests.filter((time) => now - time < windowMs);
    this.requests.set(userId, validRequests);

    if (validRequests.length >= maxRequests) {
      const oldestRequest = validRequests[0];
      const resetIn = Math.ceil((oldestRequest + windowMs - now) / 1000);
      return { allowed: false, resetIn };
    }

    validRequests.push(now);
    return { allowed: true, remaining: maxRequests - validRequests.length };
  }

  getStats() {
    return {
      activeUsers: this.requests.size,
    };
  }
}

export const rateLimiterService = new RateLimiterService();
export default rateLimiterService;
