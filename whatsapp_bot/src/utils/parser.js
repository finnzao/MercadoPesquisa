import { config, COMMANDS } from '../config.js';

export function parseMessage(text) {
  if (!text || typeof text !== 'string') {
    return { isCommand: false, command: null, args: [], rawArgs: '' };
  }

  const trimmed = text.trim();
  const prefix = config.bot.prefix;

  if (!trimmed.startsWith(prefix)) {
    return {
      isCommand: false,
      command: null,
      args: [],
      rawArgs: trimmed,
      text: trimmed,
    };
  }

  const withoutPrefix = trimmed.slice(prefix.length);
  const parts = withoutPrefix.split(/\s+/);
  const commandWord = parts[0]?.toLowerCase();
  const args = parts.slice(1);
  const rawArgs = args.join(' ');

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

function identifyCommand(word) {
  if (!word) return null;

  for (const [commandName, aliases] of Object.entries(COMMANDS)) {
    if (aliases.includes(word)) {
      return commandName;
    }
  }

  return null;
}

export function parseShoppingList(text) {
  if (!text || typeof text !== 'string') {
    return [];
  }

  const lines = text
    .split(/[\n,;]+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .filter((line) => !line.startsWith('#'));

  return lines.map((line) => parseShoppingItem(line));
}

export function parseShoppingItem(text) {
  const trimmed = text.trim();
  let quantity = 1;
  let item = trimmed;

  const matchMultiplier = trimmed.match(/^(\d+)\s*[xX]\s*(.+)$/);
  if (matchMultiplier) {
    quantity = parseInt(matchMultiplier[1]);
    item = matchMultiplier[2];
  } else {
    const matchQty = trimmed.match(
      /^(\d+)\s+(?:(?:pacotes?|unidades?|latas?|caixas?|garrafas?)\s+(?:de\s+)?)?(.+)$/i
    );
    if (matchQty) {
      quantity = parseInt(matchQty[1]);
      item = matchQty[2];
    }
  }

  return {
    raw: trimmed,
    item: item.trim(),
    quantity: Math.min(quantity, 100),
  };
}

export function parseCep(text) {
  if (!text) return null;

  const cleaned = text.replace(/\D/g, '');

  if (cleaned.length !== 8) {
    return null;
  }

  return cleaned;
}

export function parseSearchQuery(text) {
  const { cleanText: afterFlags, flags } = parseFlags(text);
  const { cleanText: afterMarkets, markets } = parseMarketMentions(afterFlags);
  const product = afterMarkets.trim();

  return {
    product,
    markets: markets.length > 0 ? markets : null,
    flags,
    original: text,
  };
}

export function parseFlags(text) {
  if (!text) return { cleanText: text, flags: {} };

  const flags = {
    singleMarket: false,
    compare: false,
    detailed: false,
  };

  let cleanText = text;

  if (/\/(?:total|unico|single)/.test(text)) {
    flags.singleMarket = true;
    cleanText = cleanText.replace(/\/(?:total|unico|single)/gi, '').trim();
  }

  if (/\/(?:compare|comparar|comp)/.test(text)) {
    flags.compare = true;
    cleanText = cleanText.replace(/\/(?:compare|comparar|comp)/gi, '').trim();
  }

  if (/\/(?:detalhe|detail|full)/.test(text)) {
    flags.detailed = true;
    cleanText = cleanText.replace(/\/(?:detalhe|detail|full)/gi, '').trim();
  }

  return { cleanText, flags };
}

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

export function isShoppingList(text) {
  if (!text) return false;
  const lines = text.split('\n').filter((l) => l.trim().length > 0);
  return lines.length >= 2;
}

export function cleanPhoneNumber(jid) {
  if (!jid) return null;
  return jid.replace('@s.whatsapp.net', '').replace('@g.us', '');
}

export function isGroup(jid) {
  return jid?.endsWith('@g.us') || false;
}

export function isPrivate(jid) {
  return jid?.endsWith('@s.whatsapp.net') || false;
}
