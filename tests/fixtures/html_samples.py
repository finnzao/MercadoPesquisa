"""
Amostras de HTML para testes de scraping.
Simula respostas dos sites de mercados.
"""

CARREFOUR_PRODUCT_CARD = """
<article data-testid="product-card">
    <a data-testid="product-card-name" href="/produto/arroz-tio-joao-5kg-123">
        <span>Arroz Tipo 1 Tio João 5kg</span>
    </a>
    <span data-testid="product-card-price">29</span>
    <span data-testid="product-card-cents">90</span>
    <span data-testid="product-card-unit-price">R$ 5,98/kg</span>
    <img data-testid="product-card-image" src="https://example.com/arroz.jpg" />
    <div data-testid="product-availability">Disponível</div>
</article>
"""

CARREFOUR_SEARCH_PAGE = f"""
<!DOCTYPE html>
<html>
<head><title>Busca - Carrefour</title></head>
<body>
    <div class="search-results">
        {CARREFOUR_PRODUCT_CARD}
        <article data-testid="product-card">
            <a data-testid="product-card-name" href="/produto/arroz-camil-5kg-456">
                <span>Arroz Tipo 1 Camil 5kg</span>
            </a>
            <span data-testid="product-card-price">31</span>
            <span data-testid="product-card-cents">90</span>
            <span data-testid="product-card-unit-price">R$ 6,38/kg</span>
            <img data-testid="product-card-image" src="https://example.com/arroz2.jpg" />
            <div data-testid="product-availability">Disponível</div>
        </article>
    </div>
    <button data-testid="pagination-next">Próxima</button>
</body>
</html>
"""

ATACADAO_PRODUCT_CARD = """
<div class="product-card">
    <h3 class="product-card__title">Arroz Tipo 1 Tio João 5kg</h3>
    <span class="product-card__price">29</span>
    <span class="product-card__price-cents">90</span>
    <span class="product-card__unit-price">R$ 5,98/kg</span>
    <a class="product-card__link" href="/produto/arroz-5kg">Link</a>
    <img class="product-card__image" src="https://example.com/arroz.jpg" />
    <div class="product-card__availability">Disponível</div>
</div>
"""

BLOCKED_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Acesso Bloqueado</title></head>
<body>
    <div class="captcha-container">
        <h1>Verificação de segurança</h1>
        <p>Por favor, confirme que você não é um robô.</p>
    </div>
</body>
</html>
"""

EMPTY_SEARCH_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Busca - Nenhum resultado</title></head>
<body>
    <div class="search-results">
        <p>Nenhum produto encontrado para sua busca.</p>
    </div>
</body>
</html>
"""