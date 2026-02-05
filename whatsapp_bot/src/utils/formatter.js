export function formatFastSearchResult(result, query) {
  if (!result.found) {
    return 'Nenhum resultado encontrado para: ' + query + '\n\nTente buscar com outros termos.';
  }

  const lines = ['Resultado para: ' + query, '', result.product, 'Preco: ' + result.price];

  if (result.normalized_price) {
    lines.push('Preco/unidade: ' + result.normalized_price);
  }

  lines.push('Mercado: ' + result.market, '', result.url);

  if (result.total_results > 1) {
    lines.push('', 'Encontrados ' + result.total_results + ' resultados');
  }

  return lines.join('\n');
}

export function formatCompareResult(result) {
  if (!result.best_offer) {
    return 'Nenhum resultado para comparar: ' + result.query;
  }

  const lines = [
    'Comparacao de precos: ' + result.query,
    result.total_offers + ' ofertas (' + result.comparable_offers + ' comparaveis)',
    '',
    'MELHOR PRECO:',
    '- ' + result.best_offer.title,
    '- ' + result.best_offer.price_formatted,
  ];

  if (result.best_offer.normalized_price_formatted) {
    lines.push('- ' + result.best_offer.normalized_price_formatted);
  }

  lines.push('- ' + result.best_offer.market_name, '');

  lines.push('Por mercado:');

  const markets = Object.entries(result.by_market).sort(
    (a, b) => (a[1].min_price || Infinity) - (b[1].min_price || Infinity)
  );

  markets.forEach(([marketId, data]) => {
    const price = data.min_price ? 'R$ ' + data.min_price.toFixed(2) : 'N/A';
    lines.push('- ' + data.market_name + ': ' + price + ' (' + data.offers_count + ' ofertas)');
  });

  if (result.potential_savings?.length > 0) {
    lines.push('', 'Economia potencial:');
    result.potential_savings.slice(0, 3).forEach((saving) => {
      lines.push(
        '- vs ' +
          saving.compared_market +
          ': R$ ' +
          saving.savings_absolute.toFixed(2) +
          ' (' +
          saving.savings_percentage.toFixed(1) +
          '%)'
      );
    });
  }

  return lines.join('\n');
}

export function formatMultiSearchResult(result) {
  const lines = [];

  if (result.mode === 'best_per_item') {
    lines.push(
      'LISTA DE COMPRAS',
      '',
      'Resumo:',
      '- Itens buscados: ' + result.summary.total_items,
      '- Encontrados: ' + result.summary.items_found,
      '- Nao encontrados: ' + result.summary.items_not_found,
      '- Total estimado: ' + result.summary.estimated_total_formatted,
      ''
    );

    if (result.summary.markets_count > 1) {
      lines.push('Precos de ' + result.summary.markets_count + ' mercados diferentes', '');
    }

    lines.push('Detalhes:');

    result.items_results.forEach((item) => {
      if (item.status === 'found' && item.best_offer) {
        lines.push(
          '- [OK] ' + item.query,
          '  ' + item.best_offer.price_formatted + ' - ' + item.best_offer.market_name
        );
      } else {
        lines.push('- [X] ' + item.query + ' - nao encontrado');
      }
    });
  } else {
    lines.push('MELHOR MERCADO PARA SUA LISTA', '');

    if (result.winner) {
      lines.push(
        result.winner.market_name,
        '- Total: ' + result.winner.total_formatted,
        '- Itens encontrados: ' + result.winner.items_found + '/' + result.summary.total_items,
        '- Cobertura: ' + result.winner.coverage_percent + '%',
        ''
      );

      if (result.winner.items_missing?.length > 0) {
        lines.push(
          'Itens nao encontrados:',
          result.winner.items_missing.map((i) => '  - ' + i).join('\n'),
          ''
        );
      }
    }

    if (result.comparison?.length > 1) {
      lines.push('Comparacao:');
      result.comparison.slice(0, 5).forEach((market, idx) => {
        const pos = idx + 1;
        lines.push(
          pos +
            '. ' +
            market.market_name +
            ': ' +
            market.total_formatted +
            ' (' +
            market.items_found +
            ' itens)'
        );
      });
    }

    if (result.savings?.note) {
      lines.push('', result.savings.note);
    }
  }

  return lines.join('\n');
}

export function formatMarketsList(markets) {
  const lines = ['MERCADOS DISPONIVEIS', ''];

  const enabled = markets.filter((m) => m.enabled);
  const disabled = markets.filter((m) => !m.enabled);

  lines.push('Ativos (' + enabled.length + '):');
  enabled.forEach((market) => {
    const cepIcon = market.requires_cep ? ' (requer CEP)' : '';
    lines.push('  - ' + market.name + cepIcon);
  });

  if (disabled.length > 0) {
    lines.push('', 'Inativos (' + disabled.length + '):');
    disabled.forEach((market) => {
      lines.push('  - ' + market.name);
    });
  }

  return lines.join('\n');
}

export function formatHelp(prefix) {
  return `PRICE BOT - AJUDA

Comandos de Busca:
${prefix}buscar <produto>
  Busca um produto nos mercados
  Ex: ${prefix}buscar arroz 5kg

${prefix}comparar <produto>
  Compara precos entre mercados
  Ex: ${prefix}comparar leite integral

Lista de Compras:
${prefix}lista
  Em seguida, envie os itens (um por linha)

  Exemplo:
  arroz 5kg
  feijao 1kg
  leite 1L

Configuracoes:
${prefix}cep <numero>
  Define seu CEP para melhor precisao
  Ex: ${prefix}cep 01310100

${prefix}mercados
  Lista mercados disponiveis

Outros:
${prefix}status
  Status do sistema

Dicas:
- Inclua quantidade na busca (5kg, 1L, 500ml)
- Precos sao atualizados em tempo real
- Use CEP para ver disponibilidade local`;
}

export function formatStatus(health, sessionStats, rateLimitStats) {
  const statusText = health.status === 'healthy' ? 'OK' : 'ERRO';

  return `STATUS DO SISTEMA

API: ${statusText}
Redis: ${health.components?.redis || 'N/A'}
Mercados: ${health.components?.mercados_enabled || 0} ativos

Sessoes: ${sessionStats?.totalSessions || 0}
Rate Limit: ${rateLimitStats?.activeUsers || 0} usuarios

Versao: ${health.version || 'N/A'}`;
}

export function formatError(error, query = null) {
  let message = 'Ocorreu um erro\n\n';

  if (error.response?.status === 429) {
    message = 'Limite de requisicoes atingido\n\nAguarde um momento e tente novamente.';
  } else if (error.response?.status === 404) {
    message = 'Nenhum resultado encontrado' + (query ? ' para ' + query : '') + '\n\nTente outros termos.';
  } else if (error.code === 'ECONNREFUSED') {
    message = 'Servidor indisponivel\n\nTente novamente em alguns minutos.';
  } else {
    message += error.message || 'Erro desconhecido';
  }

  return message;
}
