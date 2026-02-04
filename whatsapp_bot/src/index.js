/**
 * Price Collector WhatsApp Bot
 * Integração com Baileys para WhatsApp Web
 */

import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  makeInMemoryStore,
  fetchLatestBaileysVersion,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import pino from 'pino';
import qrcode from 'qrcode-terminal';
import path from 'path';
import { fileURLToPath } from 'url';

import { config, MESSAGES } from './config.js';
import { commandHandler } from './handlers/commands.js';
import { userSessionService } from './services/session.js';
import { cleanPhoneNumber, isGroup } from './utils/parser.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Logger
const logger = pino({
  level: config.logging.level,
  transport: config.isDev
    ? { target: 'pino-pretty', options: { colorize: true } }
    : undefined,
});

// Store para armazenar dados em memória
const store = makeInMemoryStore({ logger: logger.child({ module: 'store' }) });

// Caminho para salvar autenticação
const AUTH_PATH = path.join(__dirname, '..', 'auth');

class WhatsAppBot {
  constructor() {
    this.socket = null;
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }

  /**
   * Inicia o bot
   */
  async start() {
    console.log('🚀 Iniciando Price Collector WhatsApp Bot...');
    console.log(`📡 API: ${config.api.baseUrl}`);

    try {
      // Carrega estado de autenticação
      const { state, saveCreds } = await useMultiFileAuthState(AUTH_PATH);

      // Obtém versão mais recente do Baileys
      const { version, isLatest } = await fetchLatestBaileysVersion();
      console.log(`📦 Baileys v${version.join('.')} ${isLatest ? '(latest)' : ''}`);

      // Cria socket
      this.socket = makeWASocket({
        version,
        auth: state,
        logger: logger.child({ module: 'socket' }),
        printQRInTerminal: false, // Vamos customizar
        browser: ['Price Bot', 'Chrome', '120.0.0'],
        syncFullHistory: false,
        markOnlineOnConnect: true,
        generateHighQualityLinkPreview: false,
      });

      // Vincula store ao socket
      store.bind(this.socket.ev);

      // Event handlers
      this.setupEventHandlers(saveCreds);

      console.log('✅ Bot inicializado. Aguardando conexão...');

    } catch (error) {
      console.error('❌ Erro ao iniciar bot:', error);
      process.exit(1);
    }
  }

  /**
   * Configura handlers de eventos
   */
  setupEventHandlers(saveCreds) {
    const sock = this.socket;

    // Evento de atualização de conexão
    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      // QR Code para escanear
      if (qr) {
        console.log('\n📱 Escaneie o QR Code abaixo com seu WhatsApp:\n');
        qrcode.generate(qr, { small: true });
        console.log('\n');
      }

      // Conexão estabelecida
      if (connection === 'open') {
        this.isConnected = true;
        this.reconnectAttempts = 0;
        console.log('✅ Conectado ao WhatsApp!');
        console.log(`📱 Número: ${sock.user?.id?.split(':')[0] || 'N/A'}`);
        console.log(`🤖 Bot: ${config.bot.name}`);
        console.log(`⌨️  Prefixo: ${config.bot.prefix}`);
        console.log('\n🎉 Bot pronto para receber mensagens!\n');
      }

      // Desconectado
      if (connection === 'close') {
        this.isConnected = false;
        const reason = new Boom(lastDisconnect?.error)?.output?.statusCode;

        console.log(`❌ Desconectado. Razão: ${DisconnectReason[reason] || reason}`);

        // Decide se reconecta
        if (reason === DisconnectReason.loggedOut) {
          console.log('🔐 Sessão encerrada. Delete a pasta /auth e escaneie novamente.');
          process.exit(1);
        } else if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          console.log(`🔄 Tentando reconectar (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
          setTimeout(() => this.start(), 5000);
        } else {
          console.log('💀 Máximo de tentativas de reconexão atingido.');
          process.exit(1);
        }
      }
    });

    // Salva credenciais quando atualizadas
    sock.ev.on('creds.update', saveCreds);

    // Mensagens recebidas
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
      // Ignora mensagens de histórico
      if (type !== 'notify') return;

      for (const msg of messages) {
        await this.handleIncomingMessage(msg);
      }
    });
  }

  /**
   * Processa mensagem recebida
   */
  async handleIncomingMessage(msg) {
    try {
      // Ignora mensagens enviadas por nós
      if (msg.key.fromMe) return;

      // Ignora mensagens de grupos (opcional)
      if (isGroup(msg.key.remoteJid) && !config.bot.allowGroups) {
        return;
      }

      // Extrai dados da mensagem
      const jid = msg.key.remoteJid;
      const messageContent = msg.message;

      // Ignora se não tem conteúdo
      if (!messageContent) return;

      // Verifica autorização
      if (!commandHandler.isAuthorized(jid)) {
        console.log(`🔒 Usuário não autorizado: ${cleanPhoneNumber(jid)}`);
        return;
      }

      // Log da mensagem recebida
      const text = messageContent.conversation || 
                   messageContent.extendedTextMessage?.text || '';
      
      if (text) {
        console.log(`📩 [${cleanPhoneNumber(jid)}]: ${text.substring(0, 50)}${text.length > 50 ? '...' : ''}`);
      }

      // Processa comando
      const response = await commandHandler.handleMessage(messageContent, jid);

      // Envia resposta se houver
      if (response) {
        await this.sendMessage(jid, response);
      }

    } catch (error) {
      console.error('❌ Erro ao processar mensagem:', error);
      
      try {
        await this.sendMessage(
          msg.key.remoteJid,
          MESSAGES.ERROR
        );
      } catch (sendError) {
        console.error('❌ Erro ao enviar mensagem de erro:', sendError);
      }
    }
  }

  /**
   * Envia mensagem
   */
  async sendMessage(jid, text) {
    if (!this.socket || !this.isConnected) {
      console.error('❌ Socket não conectado');
      return;
    }

    try {
      await this.socket.sendMessage(jid, { text });
      console.log(`📤 [${cleanPhoneNumber(jid)}]: Resposta enviada`);
    } catch (error) {
      console.error('❌ Erro ao enviar mensagem:', error);
      throw error;
    }
  }

  /**
   * Envia mensagem com reação (typing indicator)
   */
  async sendMessageWithTyping(jid, text, typingDuration = 1000) {
    if (!this.socket || !this.isConnected) return;

    try {
      // Mostra "digitando..."
      await this.socket.sendPresenceUpdate('composing', jid);
      
      // Aguarda
      await new Promise(resolve => setTimeout(resolve, typingDuration));
      
      // Para de digitar
      await this.socket.sendPresenceUpdate('paused', jid);
      
      // Envia mensagem
      await this.sendMessage(jid, text);
    } catch (error) {
      // Fallback: envia sem typing
      await this.sendMessage(jid, text);
    }
  }

  /**
   * Envia imagem com legenda
   */
  async sendImage(jid, imageUrl, caption = '') {
    if (!this.socket || !this.isConnected) return;

    try {
      await this.socket.sendMessage(jid, {
        image: { url: imageUrl },
        caption,
      });
    } catch (error) {
      console.error('❌ Erro ao enviar imagem:', error);
    }
  }

  /**
   * Envia botões (se suportado)
   */
  async sendButtons(jid, text, buttons) {
    if (!this.socket || !this.isConnected) return;

    try {
      await this.socket.sendMessage(jid, {
        text,
        buttons: buttons.map((btn, idx) => ({
          buttonId: `btn_${idx}`,
          buttonText: { displayText: btn },
          type: 1,
        })),
        headerType: 1,
      });
    } catch (error) {
      // Fallback: envia texto normal
      const buttonsText = buttons.map((b, i) => `${i + 1}. ${b}`).join('\n');
      await this.sendMessage(jid, `${text}\n\n${buttonsText}`);
    }
  }
}

// Limpa sessões expiradas periodicamente
setInterval(() => {
  const cleaned = userSessionService.cleanExpiredSessions();
  if (cleaned > 0) {
    console.log(`🧹 ${cleaned} sessões expiradas removidas`);
  }
}, 60 * 60 * 1000); // A cada hora

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n👋 Encerrando bot...');
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('\n👋 Encerrando bot...');
  process.exit(0);
});

// Inicia o bot
const bot = new WhatsAppBot();
bot.start();

export default bot;
