/**
 * Handler de comandos do bot
 * Processa comandos e retorna respostas
 */

import { config, MESSAGES } from '../config.js';
import { apiService } from '../services/api.js';
import { userSessionService } from '../services/session.js';
import { rateLimiterService } from '../services/rateLimiter.js';
import {
  parseMessage,
  parseShoppingList,
  parseSearchQuery,
  parseCep,
  isShoppingList,
  cleanPhoneNumber,
} from '../utils/parser.js';
import {
  formatFastSearchResult,
  formatSearchResult,
  formatCompareResult,
  formatMultiSearchResult,
  formatMarketsList,
  formatHelp,
  formatStatus,
  formatError,
} from '../utils/formatter.js';

class CommandHandler {
  constructor() {
    // Estado para usuários esperando lista de compras
    this.awaitingList = new Map();
  }

  /**
   * Processa mensagem recebida
   */
  async handleMessage(message, jid) {
    const userId = cleanPhoneNumber(jid);
    const text = message?.conversation || message?.extendedTextMessage?.text || '';

    if (!text.trim()) {
      return null;
    }

    // Verifica se está esperando lista de compras
    if (this.awaitingList.has(userId)) {
      return this.handleShoppingListInput(text, userId);
    }

    // Faz parse da mensagem
    const parsed = parseMessage(text);

    // Se não é comando, verifica se é lista de compras
    if (!parsed.isCommand) {
      // Se parece ser uma lista (múltiplas linhas), processa
      if (isShoppingList(text)) {
        return this.handleShoppingListInput(text, userId);
      }
      return null; // Ignora mensagens que não são comandos
    }

    // Verifica rate limit
    const rateLimit = rateLimiterService.consume(userId);
    if (!rateLimit.allowed) {
      return `${MESSAGES.RATE_LIMITED}\n_Tente novamente em ${rateLimit.resetIn}s_`;
    }

    // Incrementa contador de mensagens
    userSessionService.incrementMessageCount(userId);

    // Processa comando
    switch (parsed.command) {
      case 'BUSCAR':
        return this.handleSearch(parsed.rawArgs, userId);
      
      case 'COMPARAR':
        return this.handleCompare(parsed.rawArgs, userId);
      
      case 'LISTA':
        return this.handleListCommand(parsed.rawArgs, userId);
      
      case 'MERCADOS':
        return this.handleMarkets();
      
      case 'CEP':
        return this.handleCep(parsed.rawArgs, userId);
      
      case 'AJUDA':
        return formatHelp(config.bot.prefix);
      
      case 'STATUS':
        return this.handleStatus(userId);
      
      default:
        if (parsed.commandWord) {
          return `${MESSAGES.INVALID_COMMAND}\n\n_Você digitou: ${parsed.commandWord}_`;
        }
        return null;
    }
  }

  /**
   * Comando de busca
   */
  async handleSearch(query, userId) {
    if (!query || query.trim().length < 2) {
      return `❌ *Informe o que deseja buscar*\n\nExemplo: _${config.bot.prefix}buscar arroz 5kg_`;
    }

    const session = userSessionService.getSession(userId);
    const cep = session.cep || config.bot.defaultCep;

    // Parse da query para extrair mercados e flags
    const { product, markets, flags } = parseSearchQuery(query);

    try {
      // Se flag de comparar, usa endpoint de comparação
      if (flags.compare) {
        return this.handleCompare(product, userId);
      }

      // Busca rápida (otimizada para bots)
      const result = await apiService.searchFast(product, cep, userId);

      if (result.error === 'rate_limited') {
        return MESSAGES.RATE_LIMITED;
      }

      // Registra no histórico
      userSessionService.addSearchHistory(userId, product, result);

      return formatFastSearchResult(result, product);

    } catch (error) {
      console.error('[Search Error]', error.message);
      return formatError(error, product);
    }
  }

  /**
   * Comando de comparação
   */
  async handleCompare(query, userId) {
    if (!query || query.trim().length < 2) {
      return `❌ *Informe o produto para comparar*\n\nExemplo: _${config.bot.prefix}comparar leite integral_`;
    }

    const session = userSessionService.getSession(userId);
    const cep = session.cep || config.bot.defaultCep;

    try {
      const result = await apiService.compare(query, cep, userId);
      return formatCompareResult(result);

    } catch (error) {
      console.error('[Compare Error]', error.message);
      return formatError(error, query);
    }
  }

  /**
   * Comando de lista de compras
   */
  async handleListCommand(args, userId) {
    // Se já tem itens nos argumentos, processa
    if (args && args.trim().length > 0) {
      return this.handleShoppingListInput(args, userId);
    }

    // Marca que está esperando lista
    this.awaitingList.set(userId, {
      timestamp: Date.now(),
      timeout: 120000, // 2 minutos
    });

    // Limpa após timeout
    setTimeout(() => {
      this.awaitingList.delete(userId);
    }, 120000);

    return `🛒 *LISTA DE COMPRAS*

Envie os itens da sua lista, um por linha:

_Exemplo:_
\`\`\`
arroz 5kg
feijão 1kg
leite 1L
óleo 900ml
\`\`\`

_Ou use: 2x leite 1L para quantidade_

⏳ _Aguardando sua lista (2 min)..._`;
  }

  /**
   * Processa entrada de lista de compras
   */
  async handleShoppingListInput(text, userId) {
    // Remove do estado de espera
    this.awaitingList.delete(userId);

    const session = userSessionService.getSession(userId);
    const cep = session.cep || config.bot.defaultCep;

    // Faz parse da lista
    const items = parseShoppingList(text);

    if (items.length === 0) {
      return '❌ *Nenhum item válido encontrado*\n\nEnvie os itens um por linha.';
    }

    if (items.length > 20) {
      return '❌ *Muitos itens*\n\nMáximo de 20 itens por lista.';
    }

    // Extrai apenas os nomes dos itens
    const itemNames = items.map(i => i.item);

    try {
      // Envia feedback de processamento
      const processingMsg = `🔍 *Buscando ${items.length} itens...*\n_Isso pode levar alguns segundos_`;

      // Usa busca múltipla
      const result = await apiService.searchMulti(itemNames, cep, false, userId);

      return formatMultiSearchResult(result);

    } catch (error) {
      console.error('[List Error]', error.message);
      return formatError(error);
    }
  }

  /**
   * Comando de mercados
   */
  async handleMarkets() {
    try {
      const markets = await apiService.getMarkets();
      return formatMarketsList(markets);

    } catch (error) {
      console.error('[Markets Error]', error.message);
      return formatError(error);
    }
  }

  /**
   * Comando de CEP
   */
  handleCep(cepInput, userId) {
    if (!cepInput || cepInput.trim().length === 0) {
      const session = userSessionService.getSession(userId);
      const currentCep = session.cep;

      if (currentCep) {
        return `📍 *Seu CEP atual:* ${this.formatCep(currentCep)}\n\nPara alterar: _${config.bot.prefix}cep 01310100_`;
      }

      return `📍 *Nenhum CEP definido*\n\nDefina seu CEP: _${config.bot.prefix}cep 01310100_`;
    }

    const cep = parseCep(cepInput);

    if (!cep) {
      return '❌ *CEP inválido*\n\nInforme um CEP válido com 8 dígitos.\n_Exemplo: 01310100 ou 01310-100_';
    }

    userSessionService.setCep(userId, cep);

    return `✅ *CEP definido!*\n\n📍 ${this.formatCep(cep)}\n\nSuas buscas agora usarão este CEP.`;
  }

  /**
   * Comando de status
   */
  async handleStatus(userId) {
    try {
      const health = await apiService.healthCheck();
      const sessionStats = { totalSessions: userSessionService.totalSessions };
      const rateLimitStats = rateLimiterService.getStats();

      return formatStatus(health, sessionStats, rateLimitStats);

    } catch (error) {
      return formatStatus(
        { status: 'unhealthy', error: error.message },
        { totalSessions: 0 },
        { activeUsers: 0 }
      );
    }
  }

  /**
   * Formata CEP para exibição
   */
  formatCep(cep) {
    if (!cep || cep.length !== 8) return cep;
    return `${cep.slice(0, 5)}-${cep.slice(5)}`;
  }

  /**
   * Verifica se usuário está autorizado
   */
  isAuthorized(jid) {
    const { allowedNumbers } = config.auth;

    // Se lista vazia, todos são permitidos
    if (!allowedNumbers || allowedNumbers.length === 0) {
      return true;
    }

    const phoneNumber = cleanPhoneNumber(jid);
    return allowedNumbers.includes(phoneNumber);
  }

  /**
   * Verifica se é admin
   */
  isAdmin(jid) {
    const { adminNumbers } = config.auth;
    const phoneNumber = cleanPhoneNumber(jid);
    return adminNumbers.includes(phoneNumber);
  }
}

// Singleton
export const commandHandler = new CommandHandler();
export default commandHandler;
