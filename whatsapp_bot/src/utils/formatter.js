/**
 * Utilitários de formatação de mensagens para WhatsApp
 */

/**
 * Formata resultado de busca rápida
 */
export function formatFastSearchResult(result, query) {
  if (!result.found) {
    return `❌ *Nenhum resultado encontrado para:* _${query}_\n\nTente buscar com outros termos.`;
  }

  const lines = [
    `🔍 *Resultado para:* _${query}_`,
    '',
    `📦 *${result.product}*`,
    `💰 *Preço:* ${result.price}`,
  ];

  if (result.normalized_price) {
    lines.push(`📊 *Preço/unidade:* ${result.normalized_price}`);
  }

  lines.push(
    `🏪 *Mercado:* ${result.market}`,
    '',
    `🔗 ${result.url}`,
  );

  if (result.total_results > 1) {
    lines.push('', `_Encontrados ${result.total_results} resultados_`);
  }

  return lines.join('\n');
}

/**
 * Formata resultado de busca completa
 */
export function formatSearchResult(result) {
  if (result.status === 'error' || result.total_results === 0) {
    return `❌ *Nenhum resultado encontrado para:* _${result.query}_`;
  }

  const lines = [
    `🔍 *Busca:* _${result.query}_`,
    `📊 *${result.total_results} resultados encontrados*`,
    '',
  ];

  // Melhor oferta
  if (result.best_offer) {
    const best = result.best_offer;
    lines.push(
      '🏆 *MELHOR OFERTA:*',
      `├ ${best.title}`,
      `├ 💰 ${best.price_formatted}`,
    );

    if (best.normalized_price_formatted) {
      lines.push(`├ 📊 ${best.normalized_price_formatted}`);
    }

    lines.push(
      `├ 🏪 ${best.market_name}`,
      `└ 🔗 ${best.url}`,
      '',
    );
  }

  // Outras ofertas (top 5)
  const others = result.results.slice(1, 6);
  if (others.length > 0) {
    lines.push('📋 *Outras ofertas:*');

    others.forEach((offer, idx) => {
      const prefix = idx === others.length - 1 ? '└' : '├';
      lines.push(
        `${prefix} ${offer.title.substring(0, 40)}${offer.title.length > 40 ? '...' : ''}`,
        `  ${offer.price_formatted} - ${offer.market_name}`,
      );
    });
  }

  return lines.join('\n');
}

/**
 * Formata comparação de preços
 */
export function formatCompareResult(result) {
  if (!result.best_offer) {
    return `❌ *Nenhum resultado para comparar:* _${result.query}_`;
  }

  const lines = [
    `📊 *Comparação de preços:* _${result.query}_`,
    `📦 *${result.total_offers} ofertas* (${result.comparable_offers} comparáveis)`,
    '',
    '🏆 *MELHOR PREÇO:*',
    `├ ${result.best_offer.title}`,
    `├ 💰 ${result.best_offer.price_formatted}`,
  ];

  if (result.best_offer.normalized_price_formatted) {
    lines.push(`├ 📊 ${result.best_offer.normalized_price_formatted}`);
  }

  lines.push(`└ 🏪 ${result.best_offer.market_name}`, '');

  // Preços por mercado
  lines.push('🏪 *Por mercado:*');
  
  const markets = Object.entries(result.by_market)
    .sort((a, b) => (a[1].min_price || Infinity) - (b[1].min_price || Infinity));

  markets.forEach(([marketId, data], idx) => {
    const prefix = idx === markets.length - 1 ? '└' : '├';
    const price = data.min_price ? `R$ ${data.min_price.toFixed(2)}` : 'N/A';
    lines.push(`${prefix} ${data.market_name}: ${price} (${data.offers_count} ofertas)`);
  });

  // Economia potencial
  if (result.potential_savings?.length > 0) {
    lines.push('', '💰 *Economia potencial:*');
    result.potential_savings.slice(0, 3).forEach((saving, idx) => {
      const prefix = idx === result.potential_savings.length - 1 ? '└' : '├';
      lines.push(
        `${prefix} vs ${saving.compared_market}: R$ ${saving.savings_absolute.toFixed(2)} (${saving.savings_percentage.toFixed(1)}%)`
      );
    });
  }

  return lines.join('\n');
}

/**
 * Formata resultado de busca múltipla (lista de compras)
 */
export function formatMultiSearchResult(result) {
  const lines = [];

  if (result.mode === 'best_per_item') {
    lines.push(
      '🛒 *LISTA DE COMPRAS*',
      '',
      `📊 *Resumo:*`,
      `├ Itens buscados: ${result.summary.total_items}`,
      `├ Encontrados: ${result.summary.items_found}`,
      `├ Não encontrados: ${result.summary.items_not_found}`,
      `└ 💰 *Total estimado: ${result.summary.estimated_total_formatted}*`,
      '',
    );

    if (result.summary.markets_count > 1) {
      lines.push(
        `⚠️ _Preços de ${result.summary.markets_count} mercados diferentes_`,
        '',
      );
    }

    lines.push('📋 *Detalhes:*');

    result.items_results.forEach((item, idx) => {
      const prefix = idx === result.items_results.length - 1 ? '└' : '├';

      if (item.status === 'found' && item.best_offer) {
        lines.push(
          `${prefix} ✅ ${item.query}`,
          `   ${item.best_offer.price_formatted} - ${item.best_offer.market_name}`,
        );
      } else {
        lines.push(`${prefix} ❌ ${item.query} - não encontrado`);
      }
    });

  } else {
    // Modo single_market
    lines.push(
      '🏆 *MELHOR MERCADO PARA SUA LISTA*',
      '',
    );

    if (result.winner) {
      lines.push(
        `🥇 *${result.winner.market_name}*`,
        `├ Total: ${result.winner.total_formatted}`,
        `├ Itens encontrados: ${result.winner.items_found}/${result.summary.total_items}`,
        `└ Cobertura: ${result.winner.coverage_percent}%`,
        '',
      );

      if (result.winner.items_missing?.length > 0) {
        lines.push(
          `⚠️ *Itens não encontrados:*`,
          result.winner.items_missing.map(i => `  • ${i}`).join('\n'),
          '',
        );
      }
    }

    // Top 3 mercados
    if (result.comparison?.length > 1) {
      lines.push('📊 *Comparação:*');
      result.comparison.slice(0, 5).forEach((market, idx) => {
        const emoji = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '  ';
        lines.push(
          `${emoji} ${market.market_name}: ${market.total_formatted} (${market.items_found} itens)`
        );
      });
    }

    if (result.savings?.note) {
      lines.push('', `💡 ${result.savings.note}`);
    }
  }

  return lines.join('\n');
}

/**
 * Formata lista de mercados
 */
export function formatMarketsList(markets) {
  const lines = [
    '🏪 *MERCADOS DISPONÍVEIS*',
    '',
  ];

  const enabled = markets.filter(m => m.enabled);
  const disabled = markets.filter(m => !m.enabled);

  lines.push(`✅ *Ativos (${enabled.length}):*`);
  enabled.forEach(market => {
    const cepIcon = market.requires_cep ? '📍' : '';
    lines.push(`  • ${market.name} ${cepIcon}`);
  });

  if (disabled.length > 0) {
    lines.push('', `⏸️ *Inativos (${disabled.length}):*`);
    disabled.forEach(market => {
      lines.push(`  • ${market.name}`);
    });
  }

  lines.push('', '_📍 = requer CEP_');

  return lines.join('\n');
}

/**
 * Formata mensagem de ajuda
 */
export function formatHelp(prefix) {
  return `🛒 *PRICE BOT - AJUDA*

*Comandos de Busca:*
• *${prefix}buscar <produto>*
  Busca um produto nos mercados
  _Ex: ${prefix}buscar arroz 5kg_

• *${prefix}comparar <produto>*
  Compara preços entre mercados
  _Ex: ${prefix}comparar leite integral_

*Lista de Compras:*
• *${prefix}lista*
  Em seguida, envie os itens (um por linha)
  
  _Exemplo:_
  _arroz 5kg_
  _feijão 1kg_
  _leite 1L_

*Configurações:*
• *${prefix}cep <numero>*
  Define seu CEP para melhor precisão
  _Ex: ${prefix}cep 01310100_

• *${prefix}mercados*
  Lista mercados disponíveis

*Outros:*
• *${prefix}status*
  Status do sistema

*Dicas:*
• Inclua quantidade na busca (5kg, 1L, 500ml)
• Preços são atualizados em tempo real
• Use CEP para ver disponibilidade local`;
}

/**
 * Formata status do sistema
 */
export function formatStatus(health, sessionStats, rateLimitStats) {
  const statusEmoji = health.status === 'healthy' ? '🟢' : '🔴';
  
  return `📊 *STATUS DO SISTEMA*

${statusEmoji} *API:* ${health.status}
🔌 *Redis:* ${health.components?.redis || 'N/A'}
🏪 *Mercados:* ${health.components?.mercados_enabled || 0} ativos

📱 *Sessões:* ${sessionStats?.totalSessions || 0}
⏱️ *Rate Limit:* ${rateLimitStats?.activeUsers || 0} usuários

_Versão: ${health.version || 'N/A'}_`;
}

/**
 * Formata erro genérico
 */
export function formatError(error, query = null) {
  let message = '❌ *Ocorreu um erro*\n\n';
  
  if (error.response?.status === 429) {
    message = '⏳ *Limite de requisições atingido*\n\nAguarde um momento e tente novamente.';
  } else if (error.response?.status === 404) {
    message = `❌ *Nenhum resultado encontrado*${query ? ` para _${query}_` : ''}\n\nTente outros termos.`;
  } else if (error.code === 'ECONNREFUSED') {
    message = '🔌 *Servidor indisponível*\n\nTente novamente em alguns minutos.';
  } else {
    message += error.message || 'Erro desconhecido';
  }

  return message;
}

/**
 * Escapa caracteres especiais do WhatsApp
 */
export function escapeMarkdown(text) {
  return text.replace(/([_*~`])/g, '\\$1');
}

/**
 * Trunca texto com ellipsis
 */
export function truncate(text, maxLength = 50) {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength - 3) + '...';
}
