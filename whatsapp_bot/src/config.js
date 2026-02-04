/**
 * Configuração do Bot WhatsApp
 * Carrega variáveis de ambiente e define constantes
 */

import dotenv from 'dotenv';
dotenv.config();

export const config = {
  // API do Price Collector
  api: {
    baseUrl: process.env.API_BASE_URL || 'http://localhost:8000/api/v1',
    timeout: parseInt(process.env.API_TIMEOUT) || 30000,
  },

  // Configurações do Bot
  bot: {
    name: process.env.BOT_NAME || 'PriceBot',
    prefix: process.env.BOT_PREFIX || '!',
    defaultCep: process.env.DEFAULT_CEP || '01310100',
  },

  // Rate Limiting
  rateLimit: {
    perUser: parseInt(process.env.RATE_LIMIT_PER_USER) || 10,
    windowMs: 60000, // 1 minuto
  },

  // Autorização
  auth: {
    allowedNumbers: process.env.ALLOWED_NUMBERS
      ? process.env.ALLOWED_NUMBERS.split(',').map(n => n.trim())
      : [],
    adminNumbers: process.env.ADMIN_NUMBERS
      ? process.env.ADMIN_NUMBERS.split(',').map(n => n.trim())
      : [],
  },

  // Logging
  logging: {
    level: process.env.LOG_LEVEL || 'info',
  },

  // Ambiente
  isDev: process.env.NODE_ENV === 'development',
};

// Comandos disponíveis
export const COMMANDS = {
  BUSCAR: ['buscar', 'b', 'search', 'procurar'],
  LISTA: ['lista', 'l', 'list', 'compras'],
  COMPARAR: ['comparar', 'c', 'compare'],
  MERCADOS: ['mercados', 'm', 'markets', 'lojas'],
  CEP: ['cep', 'local', 'localizacao'],
  AJUDA: ['ajuda', 'help', 'h', '?', 'comandos'],
  STATUS: ['status', 'stats'],
};

// Mensagens padrão
export const MESSAGES = {
  WELCOME: `🛒 *Olá! Eu sou o ${config.bot.name}!*

Eu ajudo você a encontrar os melhores preços nos supermercados.

*Comandos disponíveis:*
• *${config.bot.prefix}buscar <produto>* - Busca um produto
• *${config.bot.prefix}lista* - Processa lista de compras
• *${config.bot.prefix}comparar <produto>* - Compara preços
• *${config.bot.prefix}mercados* - Lista mercados disponíveis
• *${config.bot.prefix}cep <cep>* - Define seu CEP
• *${config.bot.prefix}ajuda* - Mostra esta mensagem

*Exemplo:*
_${config.bot.prefix}buscar arroz 5kg_`,

  SEARCHING: '🔍 Buscando...',
  NO_RESULTS: '❌ Nenhum resultado encontrado para',
  ERROR: '❌ Ocorreu um erro. Tente novamente.',
  RATE_LIMITED: '⏳ Aguarde um momento antes de fazer outra busca.',
  NOT_AUTHORIZED: '🔒 Você não está autorizado a usar este bot.',
  INVALID_COMMAND: '❓ Comando não reconhecido. Use *!ajuda* para ver os comandos.',
};

export default config;
