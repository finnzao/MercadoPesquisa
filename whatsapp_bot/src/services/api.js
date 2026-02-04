/**
 * Serviço de comunicação com a API do Price Collector
 */

import axios from 'axios';
import { config } from '../config.js';

class ApiService {
  constructor() {
    this.client = axios.create({
      baseURL: config.api.baseUrl,
      timeout: config.api.timeout,
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': `${config.bot.name}/1.0`,
      },
    });

    // Interceptor para logging
    this.client.interceptors.response.use(
      response => response,
      error => {
        console.error('[API Error]', error.message);
        throw error;
      }
    );
  }

  /**
   * Busca rápida de produtos (otimizada para bots)
   */
  async searchFast(query, cep = null, userId = null) {
    try {
      const params = { q: query };
      if (cep) params.cep = cep;

      const headers = {};
      if (userId) headers['X-User-ID'] = userId;

      const response = await this.client.get('/search/fast', { params, headers });
      return response.data;
    } catch (error) {
      if (error.response?.status === 429) {
        return { error: 'rate_limited', message: 'Muitas requisições. Aguarde.' };
      }
      throw error;
    }
  }

  /**
   * Busca completa com mais resultados
   */
  async search(query, cep = null, markets = null, limit = 10, userId = null) {
    try {
      const params = { q: query, limit };
      if (cep) params.cep = cep;
      if (markets) params.markets = markets.join(',');

      const headers = {};
      if (userId) headers['X-User-ID'] = userId;

      const response = await this.client.get('/search', { params, headers });
      return response.data;
    } catch (error) {
      if (error.response?.status === 429) {
        return { error: 'rate_limited' };
      }
      throw error;
    }
  }

  /**
   * Comparação de preços entre mercados
   */
  async compare(query, cep = null, userId = null) {
    try {
      const params = { q: query };
      if (cep) params.cep = cep;

      const headers = {};
      if (userId) headers['X-User-ID'] = userId;

      const response = await this.client.get('/search/compare', { params, headers });
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Busca múltiplos itens (lista de compras)
   */
  async searchMulti(items, cep = null, singleMarket = false, userId = null) {
    try {
      const body = {
        items,
        single_market: singleMarket,
      };
      if (cep) body.cep = cep;

      const headers = {};
      if (userId) headers['X-User-ID'] = userId;

      const response = await this.client.post('/search/multi', body, { headers });
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Busca múltipla rápida (versão simplificada para bots)
   */
  async searchMultiQuick(items, cep = null, singleMarket = false, userId = null) {
    try {
      const body = {
        items,
        single_market: singleMarket,
      };
      if (cep) body.cep = cep;

      const headers = {};
      if (userId) headers['X-User-ID'] = userId;

      const response = await this.client.post('/search/multi/quick', body, { headers });
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Lista mercados disponíveis
   */
  async getMarkets() {
    try {
      const response = await this.client.get('/markets');
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Lista apenas mercados habilitados
   */
  async getEnabledMarkets() {
    try {
      const response = await this.client.get('/markets/enabled');
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Status dos mercados (circuit breakers)
   */
  async getMarketsStatus() {
    try {
      const response = await this.client.get('/markets/status');
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  /**
   * Health check da API
   */
  async healthCheck() {
    try {
      const response = await this.client.get('/health', {
        baseURL: config.api.baseUrl.replace('/api/v1', ''),
      });
      return response.data;
    } catch (error) {
      return { status: 'unhealthy', error: error.message };
    }
  }
}

// Singleton
export const apiService = new ApiService();
export default apiService;
