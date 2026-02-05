import pkg from '@whiskeysockets/baileys';
const {
  default: makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
} = pkg;
import { Boom } from '@hapi/boom';
import pino from 'pino';
import path from 'path';
import { fileURLToPath } from 'url';
import qrcode from 'qrcode-terminal';

import { config, MESSAGES } from './config.js';
import { commandHandler } from './handlers/commands.js';
import { cleanPhoneNumber } from './utils/parser.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_PATH = path.join(__dirname, '..', 'auth');

const logger = pino({ level: 'silent' });

async function startBot() {
  console.log('Iniciando bot...');

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_PATH);
  console.log('Auth state carregado');

  const sock = makeWASocket({
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    logger: logger,
    browser: ['Ubuntu', 'Chrome', '22.04.4'],
    printQRInTerminal: true,
    markOnlineOnConnect: false,
  });

  console.log('Socket criado');
  console.log('Aguardando QR Code...\n');

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('==========================================');
      console.log('   ESCANEIE O QR CODE COM SEU WHATSAPP');
      console.log('==========================================\n');
      qrcode.generate(qr, { small: true });
      console.log('\nInstrucoes:');
      console.log('1. Abra o WhatsApp no celular');
      console.log('2. Toque em "..." ou Configuracoes');
      console.log('3. Aparelhos conectados');
      console.log('4. Conectar um aparelho');
      console.log('5. Escaneie o QR Code acima\n');
    }

    if (connection === 'connecting') {
      console.log('Conectando ao WhatsApp...');
    }

    if (connection === 'open') {
      console.log('\n==========================================');
      console.log('        CONECTADO COM SUCESSO!');
      console.log('==========================================');
      const userId = sock.user?.id;
      if (userId) {
        console.log('Numero: ' + userId.split(':')[0].split('@')[0]);
      }
      console.log('Bot pronto para receber mensagens!\n');
    }

    if (connection === 'close') {
      const error = lastDisconnect?.error;
      const statusCode = new Boom(error)?.output?.statusCode;

      console.log('Conexao fechada. Codigo: ' + statusCode);

      if (statusCode === DisconnectReason.loggedOut) {
        console.log('Sessao encerrada. Delete a pasta auth/ e reinicie.');
        process.exit(1);
      } else if (statusCode === DisconnectReason.restartRequired) {
        console.log('Reinicio necessario. Reconectando...');
        startBot();
      } else if (statusCode === 405) {
        console.log('\nErro 405 detectado.');
        console.log('Tentando reconectar em 5 segundos...');
        setTimeout(startBot, 5000);
      } else {
        console.log('Reconectando em 3 segundos...');
        setTimeout(startBot, 3000);
      }
    }
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;

    for (const msg of messages) {
      // MODO TESTE: permite processar suas próprias mensagens
      // Para produção, descomente a linha abaixo:
      // if (msg.key.fromMe) continue;

      const jid = msg.key.remoteJid;
      const messageContent = msg.message;
      if (!messageContent) continue;

      const text =
        messageContent.conversation ||
        messageContent.extendedTextMessage?.text ||
        '';

      if (!text) continue;

      const sender = cleanPhoneNumber(jid);
      console.log('[' + sender + ']: ' + text);

      try {
        const response = await commandHandler.handleMessage(messageContent, jid);
        if (response) {
          await sock.sendMessage(jid, { text: response });
          console.log('Resposta enviada para ' + sender);
        }
      } catch (err) {
        console.log('Erro ao processar mensagem: ' + err.message);
      }
    }
  });
}

process.on('SIGINT', () => {
  console.log('\nEncerrando bot...');
  process.exit(0);
});

process.on('uncaughtException', (err) => {
  console.log('Erro nao tratado: ' + err.message);
});

process.on('unhandledRejection', (err) => {
  console.log('Promise rejeitada: ' + err);
});

startBot();
