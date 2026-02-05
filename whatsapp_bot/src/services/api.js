import axios from 'axios';
import { config } from '../config.js';

class ApiService {
  constructor() {
    this.client = axios.create({
      baseURL: config.api.baseUrl,
      timeout: config.api.timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  async searchFast(query, cep, userId) {
    try {
      const response = await this.client.get('/search/fast', {
        params: { q: query, cep, user_id: userId },
      });
      return response.data;
    } catch (error) {
      if (error.response?.status === 404) {
        return { found: false, query };
      }
      throw error;
    }
  }

  async search(query, cep, markets, userId) {
    try {
      const response = await this.client.get('/search', {
        params: { q: query, cep, markets, user_id: userId },
      });
      return response.data;
    } catch (error) {
      if (error.response?.status === 404) {
        return { status: 'error', total_results: 0, query };
      }
      throw error;
    }
  }

  async compare(query, cep, userId) {
    try {
      const response = await this.client.get('/search/compare', {
        params: { q: query, cep, user_id: userId },
      });
      return response.data;
    } catch (error) {
      if (error.response?.status === 404) {
        return { best_offer: null, query };
      }
      throw error;
    }
  }

  async searchMulti(items, cep, singleMarket, userId) {
    try {
      const response = await this.client.post('/search/multi', {
        items,
        cep,
        single_market: singleMarket,
        user_id: userId,
      });
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  async getMarkets() {
    try {
      const response = await this.client.get('/markets');
      return response.data;
    } catch (error) {
      return [];
    }
  }

  async healthCheck() {
    try {
      const response = await this.client.get('/health');
      return response.data;
    } catch (error) {
      return { status: 'unhealthy', error: error.message };
    }
  }
}

export const apiService = new ApiService();
export default apiService;
