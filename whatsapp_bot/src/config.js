import dotenv from 'dotenv';
dotenv.config();

export const config = {
  api: {
    baseUrl: process.env.API_BASE_URL || 'http://localhost:8000/api/v1',
    timeout: parseInt(process.env.API_TIMEOUT) || 30000,
  },
  bot: {
    name: process.env.BOT_NAME || 'PriceBot',
    prefix: process.env.BOT_PREFIX || '!',
    defaultCep: process.env.DEFAULT_CEP || '01310100',
    allowGroups: process.env.ALLOW_GROUPS === 'true',
  },
  rateLimit: {
    perUser: parseInt(process.env.RATE_LIMIT_PER_USER) || 10,
    windowMs: 60000,
  },
  auth: {
    allowedNumbers: process.env.ALLOWED_NUMBERS
      ? process.env.ALLOWED_NUMBERS.split(',').map((n) => n.trim())
      : [],
    adminNumbers: process.env.ADMIN_NUMBERS
      ? process.env.ADMIN_NUMBERS.split(',').map((n) => n.trim())
      : [],
  },
};

export const COMMANDS = {
  BUSCAR: ['buscar', 'b', 'search', 'procurar'],
  LISTA: ['lista', 'l', 'list', 'compras'],
  COMPARAR: ['comparar', 'c', 'compare'],
  MERCADOS: ['mercados', 'm', 'markets', 'lojas'],
  CEP: ['cep', 'local', 'localizacao'],
  AJUDA: ['ajuda', 'help', 'h', '?', 'comandos'],
  STATUS: ['status', 'stats'],
};

export const MESSAGES = {
  WELCOME: `Ola! Eu sou o ${config.bot.name}!

Eu ajudo voce a encontrar os melhores precos nos supermercados.

Comandos disponiveis:
${config.bot.prefix}buscar <produto> - Busca um produto
${config.bot.prefix}lista - Processa lista de compras
${config.bot.prefix}comparar <produto> - Compara precos
${config.bot.prefix}mercados - Lista mercados disponiveis
${config.bot.prefix}cep <cep> - Define seu CEP
${config.bot.prefix}ajuda - Mostra esta mensagem

Exemplo:
${config.bot.prefix}buscar arroz 5kg`,

  SEARCHING: 'Buscando...',
  NO_RESULTS: 'Nenhum resultado encontrado para',
  ERROR: 'Ocorreu um erro. Tente novamente.',
  RATE_LIMITED: 'Aguarde um momento antes de fazer outra busca.',
  NOT_AUTHORIZED: 'Voce nao esta autorizado a usar este bot.',
  INVALID_COMMAND: 'Comando nao reconhecido. Use !ajuda para ver os comandos.',
};

export default config;
