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
  formatCompareResult,
  formatMultiSearchResult,
  formatMarketsList,
  formatHelp,
  formatStatus,
  formatError,
} from '../utils/formatter.js';

class CommandHandler {
  constructor() {
    this.awaitingList = new Map();
  }

  async handleMessage(message, jid) {
    const userId = cleanPhoneNumber(jid);
    const text = message?.conversation || message?.extendedTextMessage?.text || '';

    if (!text.trim()) {
      return null;
    }

    if (this.awaitingList.has(userId)) {
      return this.handleShoppingListInput(text, userId);
    }

    const parsed = parseMessage(text);

    if (!parsed.isCommand) {
      if (isShoppingList(text)) {
        return this.handleShoppingListInput(text, userId);
      }
      return null;
    }

    const rateLimit = rateLimiterService.consume(userId);
    if (!rateLimit.allowed) {
      return MESSAGES.RATE_LIMITED + '\nTente novamente em ' + rateLimit.resetIn + 's';
    }

    userSessionService.incrementMessageCount(userId);

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
          return MESSAGES.INVALID_COMMAND + '\n\nVoce digitou: ' + parsed.commandWord;
        }
        return null;
    }
  }

  async handleSearch(query, userId) {
    if (!query || query.trim().length < 2) {
      return 'Informe o que deseja buscar\n\nExemplo: ' + config.bot.prefix + 'buscar arroz 5kg';
    }

    const session = userSessionService.getSession(userId);
    const cep = session.cep || config.bot.defaultCep;
    const { product, flags } = parseSearchQuery(query);

    try {
      if (flags.compare) {
        return this.handleCompare(product, userId);
      }

      const result = await apiService.searchFast(product, cep, userId);

      if (result.error === 'rate_limited') {
        return MESSAGES.RATE_LIMITED;
      }

      userSessionService.addSearchHistory(userId, product, result);
      return formatFastSearchResult(result, product);
    } catch (error) {
      console.error('[Search Error]', error.message);
      return formatError(error, product);
    }
  }

  async handleCompare(query, userId) {
    if (!query || query.trim().length < 2) {
      return 'Informe o produto para comparar\n\nExemplo: ' + config.bot.prefix + 'comparar leite integral';
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

  async handleListCommand(args, userId) {
    if (args && args.trim().length > 0) {
      return this.handleShoppingListInput(args, userId);
    }

    this.awaitingList.set(userId, {
      timestamp: Date.now(),
      timeout: 120000,
    });

    setTimeout(() => {
      this.awaitingList.delete(userId);
    }, 120000);

    return `LISTA DE COMPRAS

Envie os itens da sua lista, um por linha:

Exemplo:
arroz 5kg
feijao 1kg
leite 1L
oleo 900ml

Ou use: 2x leite 1L para quantidade

Aguardando sua lista (2 min)...`;
  }

  async handleShoppingListInput(text, userId) {
    this.awaitingList.delete(userId);

    const session = userSessionService.getSession(userId);
    const cep = session.cep || config.bot.defaultCep;
    const items = parseShoppingList(text);

    if (items.length === 0) {
      return 'Nenhum item valido encontrado\n\nEnvie os itens um por linha.';
    }

    if (items.length > 20) {
      return 'Muitos itens\n\nMaximo de 20 itens por lista.';
    }

    const itemNames = items.map((i) => i.item);

    try {
      const result = await apiService.searchMulti(itemNames, cep, false, userId);
      return formatMultiSearchResult(result);
    } catch (error) {
      console.error('[List Error]', error.message);
      return formatError(error);
    }
  }

  async handleMarkets() {
    try {
      const markets = await apiService.getMarkets();
      return formatMarketsList(markets);
    } catch (error) {
      console.error('[Markets Error]', error.message);
      return formatError(error);
    }
  }

  handleCep(cepInput, userId) {
    if (!cepInput || cepInput.trim().length === 0) {
      const session = userSessionService.getSession(userId);
      const currentCep = session.cep;

      if (currentCep) {
        return 'Seu CEP atual: ' + this.formatCep(currentCep) + '\n\nPara alterar: ' + config.bot.prefix + 'cep 01310100';
      }

      return 'Nenhum CEP definido\n\nDefina seu CEP: ' + config.bot.prefix + 'cep 01310100';
    }

    const cep = parseCep(cepInput);

    if (!cep) {
      return 'CEP invalido\n\nInforme um CEP valido com 8 digitos.\nExemplo: 01310100 ou 01310-100';
    }

    userSessionService.setCep(userId, cep);
    return 'CEP definido!\n\n' + this.formatCep(cep) + '\n\nSuas buscas agora usarao este CEP.';
  }

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

  formatCep(cep) {
    if (!cep || cep.length !== 8) return cep;
    return cep.slice(0, 5) + '-' + cep.slice(5);
  }
}

export const commandHandler = new CommandHandler();
export default commandHandler;
