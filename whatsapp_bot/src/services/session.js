class UserSessionService {
  constructor() {
    this.sessions = new Map();
  }

  getSession(userId) {
    if (!this.sessions.has(userId)) {
      this.sessions.set(userId, {
        cep: null,
        searchHistory: [],
        messageCount: 0,
        createdAt: Date.now(),
        lastActivity: Date.now(),
      });
    }

    const session = this.sessions.get(userId);
    session.lastActivity = Date.now();
    return session;
  }

  setCep(userId, cep) {
    const session = this.getSession(userId);
    session.cep = cep;
  }

  addSearchHistory(userId, query, result) {
    const session = this.getSession(userId);
    session.searchHistory.unshift({
      query,
      result,
      timestamp: Date.now(),
    });
    if (session.searchHistory.length > 10) {
      session.searchHistory.pop();
    }
  }

  incrementMessageCount(userId) {
    const session = this.getSession(userId);
    session.messageCount++;
  }

  get totalSessions() {
    return this.sessions.size;
  }

  cleanOldSessions(maxAge = 24 * 60 * 60 * 1000) {
    const now = Date.now();
    for (const [userId, session] of this.sessions) {
      if (now - session.lastActivity > maxAge) {
        this.sessions.delete(userId);
      }
    }
  }
}

export const userSessionService = new UserSessionService();
export default userSessionService;
