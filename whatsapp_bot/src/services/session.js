/**
 * Gerenciador de sessões de usuários
 * Armazena CEP, preferências e estado da conversa
 */

class UserSessionService {
  constructor() {
    // Map de sessões: número -> dados da sessão
    this.sessions = new Map();
    
    // Tempo de expiração da sessão (24 horas)
    this.sessionTTL = 24 * 60 * 60 * 1000;
  }

  /**
   * Obtém ou cria sessão do usuário
   */
  getSession(userId) {
    const cleanId = this.cleanUserId(userId);
    
    if (!this.sessions.has(cleanId)) {
      this.sessions.set(cleanId, this.createSession(cleanId));
    }

    const session = this.sessions.get(cleanId);
    session.lastActivity = Date.now();
    
    return session;
  }

  /**
   * Cria nova sessão
   */
  createSession(userId) {
    return {
      userId,
      cep: null,
      preferredMarkets: [],
      lastSearch: null,
      lastActivity: Date.now(),
      searchHistory: [],
      messageCount: 0,
      createdAt: Date.now(),
    };
  }

  /**
   * Define CEP do usuário
   */
  setCep(userId, cep) {
    const session = this.getSession(userId);
    session.cep = this.cleanCep(cep);
    return session.cep;
  }

  /**
   * Obtém CEP do usuário
   */
  getCep(userId) {
    const session = this.getSession(userId);
    return session.cep;
  }

  /**
   * Define mercados preferidos
   */
  setPreferredMarkets(userId, markets) {
    const session = this.getSession(userId);
    session.preferredMarkets = markets;
  }

  /**
   * Adiciona busca ao histórico
   */
  addSearchHistory(userId, query, result) {
    const session = this.getSession(userId);
    
    session.searchHistory.unshift({
      query,
      timestamp: Date.now(),
      resultCount: result?.total_results || 0,
      bestPrice: result?.best_offer?.price || null,
    });

    // Mantém apenas últimas 20 buscas
    if (session.searchHistory.length > 20) {
      session.searchHistory = session.searchHistory.slice(0, 20);
    }

    session.lastSearch = query;
  }

  /**
   * Incrementa contador de mensagens
   */
  incrementMessageCount(userId) {
    const session = this.getSession(userId);
    session.messageCount++;
    return session.messageCount;
  }

  /**
   * Obtém estatísticas da sessão
   */
  getStats(userId) {
    const session = this.getSession(userId);
    return {
      cep: session.cep,
      searchCount: session.searchHistory.length,
      messageCount: session.messageCount,
      lastSearch: session.lastSearch,
      sessionAge: Date.now() - session.createdAt,
    };
  }

  /**
   * Limpa sessões expiradas
   */
  cleanExpiredSessions() {
    const now = Date.now();
    let cleaned = 0;

    for (const [userId, session] of this.sessions) {
      if (now - session.lastActivity > this.sessionTTL) {
        this.sessions.delete(userId);
        cleaned++;
      }
    }

    return cleaned;
  }

  /**
   * Limpa ID do usuário (remove @s.whatsapp.net)
   */
  cleanUserId(userId) {
    return userId.replace('@s.whatsapp.net', '').replace('@g.us', '');
  }

  /**
   * Limpa e valida CEP
   */
  cleanCep(cep) {
    const cleaned = cep.replace(/\D/g, '');
    if (cleaned.length === 8) {
      return cleaned;
    }
    return null;
  }

  /**
   * Total de sessões ativas
   */
  get totalSessions() {
    return this.sessions.size;
  }
}

// Singleton
export const userSessionService = new UserSessionService();
export default userSessionService;
