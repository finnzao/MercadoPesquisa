/**
 * Parser de mensagens do WhatsApp
 * Extrai comandos, argumentos e listas de compras
 */

import { config, COMMANDS } from '../config.js';

/**
 * Faz parse de uma mensagem e extrai comando e argumentos
 */
export function parseMessage(text) {
  if (!text || typeof text !== 'string') {
    return { isCommand: false, command: null, args: [], rawArgs: '' };
  }

  const trimmed = text.trim();
  const prefix = config.bot.prefix;

  // Verifica se começa com prefixo
  if (!trimmed.startsWith(prefix)) {
    return {
      isCommand: false,
      command: null,
      args: [],
      rawArgs: trimmed,
      text: trimmed,
    };
  }

  // Remove prefixo e divide
  const withoutPrefix = trimmed.slice(prefix.length);
  const parts = withoutPrefix.split(/\s+/);
  const commandWord = parts[0]?.toLowerCase();
  const args = parts.slice(1);
  const rawArgs = args.join(' ');

  // Identifica o comando
  const command = identifyCommand(commandWord);

  return {
    isCommand: true,
    command,
    commandWord,
    args,
    rawArgs,
    text: trimmed,
  };
}

/**
 * Identifica qual comando foi usado
 */
function identifyCommand(word) {
  if (!word) return null;

  for (const [commandName, aliases] of Object.entries(COMMANDS)) {
    if (aliases.includes(word)) {
      return commandName;
    }
  }

  return null;
}

/**
 * Faz parse de uma lista de compras (texto com múltiplos itens)
 */
export function parseShoppingList(text) {
  if (!text || typeof text !== 'string') {
    return [];
  }

  // Divide por quebras de linha ou vírgulas
  const lines = text
    .split(/[\n,;]+/)
    .map(line => line.trim())
    .filter(line => line.length > 0)
    .filter(line => !line.startsWith('#')); // Ignora comentários

  return lines.map(line => parseShoppingItem(line));
}

/**
 * Faz parse de um item de compras
 * Exemplos:
 * - "arroz 5kg"
 * - "2x leite 1L"
 * - "3 pacotes de café"
 */
export function parseShoppingItem(text) {
  const trimmed = text.trim();
  let quantity = 1;
  let item = trimmed;

  // Tenta extrair quantidade no início (2x, 3x, etc)
  const matchMultiplier = trimmed.match(/^(\d+)\s*[xX]\s*(.+)$/);
  if (matchMultiplier) {
    quantity = parseInt(matchMultiplier[1]);
    item = matchMultiplier[2];
  } else {
    // Tenta "3 pacotes de" ou "2 "
    const matchQty = trimmed.match(/^(\d+)\s+(?:(?:pacotes?|unidades?|latas?|caixas?|garrafas?)\s+(?:de\s+)?)?(.+)$/i);
    if (matchQty) {
      quantity = parseInt(matchQty[1]);
      item = matchQty[2];
    }
  }

  return {
    raw: trimmed,
    item: item.trim(),
    quantity: Math.min(quantity, 100), // Limita quantidade
  };
}

/**
 * Valida e limpa CEP
 */
export function parseCep(text) {
  if (!text) return null;

  // Remove tudo que não é número
  const cleaned = text.replace(/\D/g, '');

  // Deve ter 8 dígitos
  if (cleaned.length !== 8) {
    return null;
  }

  return cleaned;
}

/**
 * Extrai menções de mercados do texto
 * Exemplo: "arroz @carrefour @atacadao"
 */
export function parseMarketMentions(text) {
  if (!text) return { cleanText: text, markets: [] };

  const marketPattern = /@(\w+)/g;
  const markets = [];
  let match;

  while ((match = marketPattern.exec(text)) !== null) {
    markets.push(match[1].toLowerCase());
  }

  const cleanText = text.replace(marketPattern, '').trim();

  return { cleanText, markets };
}

/**
 * Extrai flags especiais do texto
 * Exemplo: "arroz /total" -> singleMarket: true
 */
export function parseFlags(text) {
  if (!text) return { cleanText: text, flags: {} };

  const flags = {
    singleMarket: false,
    compare: false,
    detailed: false,
  };

  let cleanText = text;

  // /total ou /unico - modo single market
  if (/\/(?:total|unico|único|single)/.test(text)) {
    flags.singleMarket = true;
    cleanText = cleanText.replace(/\/(?:total|unico|único|single)/gi, '').trim();
  }

  // /compare - modo comparação
  if (/\/(?:compare|comparar|comp)/.test(text)) {
    flags.compare = true;
    cleanText = cleanText.replace(/\/(?:compare|comparar|comp)/gi, '').trim();
  }

  // /detalhe - modo detalhado
  if (/\/(?:detalhe|detail|full)/.test(text)) {
    flags.detailed = true;
    cleanText = cleanText.replace(/\/(?:detalhe|detail|full)/gi, '').trim();
  }

  return { cleanText, flags };
}

/**
 * Faz parse completo de uma mensagem de busca
 * Extrai produto, mercados, flags, etc
 */
export function parseSearchQuery(text) {
  // Extrai flags
  const { cleanText: afterFlags, flags } = parseFlags(text);

  // Extrai menções de mercados
  const { cleanText: afterMarkets, markets } = parseMarketMentions(afterFlags);

  // O que sobrou é o produto
  const product = afterMarkets.trim();

  return {
    product,
    markets: markets.length > 0 ? markets : null,
    flags,
    original: text,
  };
}

/**
 * Verifica se mensagem é uma lista de compras
 * (múltiplos itens separados por linha)
 */
export function isShoppingList(text) {
  if (!text) return false;

  // Conta linhas não vazias
  const lines = text.split('\n').filter(l => l.trim().length > 0);

  return lines.length >= 2;
}

/**
 * Extrai número de telefone limpo
 */
export function cleanPhoneNumber(jid) {
  if (!jid) return null;
  return jid.replace('@s.whatsapp.net', '').replace('@g.us', '');
}

/**
 * Verifica se é um grupo
 */
export function isGroup(jid) {
  return jid?.endsWith('@g.us') || false;
}

/**
 * Verifica se é mensagem privada
 */
export function isPrivate(jid) {
  return jid?.endsWith('@s.whatsapp.net') || false;
}
