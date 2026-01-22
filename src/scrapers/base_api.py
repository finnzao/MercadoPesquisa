"""
Base para scrapers que usam API HTTP - VERSÃO CORRIGIDA
Trata adequadamente respostas comprimidas (Brotli, gzip, deflate).

Usa: Carrefour, Atacadão, e outros com API REST/GraphQL.
Caminho: /src/scrapers/base_api.py
"""

import asyncio
import json
import gzip
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, Dict, List
import random

import httpx

from config.logging_config import LoggerMixin
from config.markets import MarketConfig
from config.settings import get_settings
from src.core.http_client import get_http_client
from src.core.models import RawProduct
from src.core.types import CollectionStatus
from src.scrapers.base_pooled import ScraperResult


# Tenta importar brotli (opcional)
try:
    import brotli
    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False


def safe_decode_response(response: httpx.Response) -> Any:
    """
    Decodifica a resposta HTTP de forma segura, tratando diferentes encodings.
    
    Args:
        response: Objeto Response do httpx
        
    Returns:
        Dados JSON parseados
        
    Raises:
        json.JSONDecodeError: Se não conseguir parsear o JSON
        UnicodeDecodeError: Se não conseguir decodificar o texto
    """
    content = response.content
    content_encoding = response.headers.get('content-encoding', '').lower()
    
    # Primeiro, tenta o método padrão do httpx
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    
    # Se o conteúdo está vazio, retorna None
    if not content:
        return None
    
    # Tenta decodificar o conteúdo de diferentes formas
    text_content = None
    
    # 1. Tenta Brotli (se disponível e parece ser br)
    if BROTLI_AVAILABLE and (content_encoding == 'br' or content[:2] in [b'\x1b\x37', b'\x1b\x36']):
        try:
            decompressed = brotli.decompress(content)
            text_content = decompressed.decode('utf-8')
        except Exception:
            pass
    
    # 2. Tenta gzip
    if text_content is None and (content_encoding == 'gzip' or content[:2] == b'\x1f\x8b'):
        try:
            decompressed = gzip.decompress(content)
            text_content = decompressed.decode('utf-8')
        except Exception:
            pass
    
    # 3. Tenta zlib (deflate)
    if text_content is None and content_encoding == 'deflate':
        try:
            decompressed = zlib.decompress(content)
            text_content = decompressed.decode('utf-8')
        except Exception:
            pass
        
        # Tenta zlib com wbits negativo (raw deflate)
        if text_content is None:
            try:
                decompressed = zlib.decompress(content, -zlib.MAX_WBITS)
                text_content = decompressed.decode('utf-8')
            except Exception:
                pass
    
    # 4. Tenta decodificação direta
    if text_content is None:
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                text_content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
    
    # 5. Fallback: decodifica com replace
    if text_content is None:
        text_content = content.decode('utf-8', errors='replace')
    
    # Agora tenta parsear o JSON
    if text_content:
        # Remove possíveis BOM ou caracteres inválidos no início
        text_content = text_content.lstrip('\ufeff\x00')
        return json.loads(text_content)
    
    raise json.JSONDecodeError("Não foi possível decodificar a resposta", "", 0)


class BaseAPIScraper(ABC, LoggerMixin):
    """
    Base para scrapers via API HTTP.
    Não usa browser - apenas requisições HTTP.
    
    VERSÃO CORRIGIDA - Trata respostas comprimidas adequadamente.
    """
    
    PRODUCTS_PER_PAGE = 20
    
    def __init__(self, config: MarketConfig):
        self.config = config
        self.settings = get_settings()
    
    @property
    def market_id(self) -> str:
        return self.config.id
    
    @abstractmethod
    def _build_request(self, query: str, page: int) -> Dict[str, Any]:
        """
        Retorna config da requisição.
        
        Returns:
            {
                "url": str,
                "method": "GET" | "POST",
                "headers": dict (opcional),
                "params": dict (opcional, para GET),
                "json": dict (opcional, para POST),
            }
        """
        pass
    
    @abstractmethod
    def _parse_response(self, data: Any, query: str, cep: Optional[str], page: int) -> tuple[List[RawProduct], int]:
        """
        Parseia resposta da API.
        
        Returns:
            (lista_produtos, total_disponivel)
        """
        pass
    
    async def search(self, query: str, cep: Optional[str] = None, max_pages: int = 1) -> ScraperResult:
        """Executa busca via API."""
        result = ScraperResult(
            market_id=self.market_id,
            search_query=query,
            status=CollectionStatus.FAILED,
        )
        
        self.logger.info("Iniciando busca API", market=self.market_id, query=query)
        
        try:
            http = await get_http_client()
            all_products = []
            total_available = None
            
            for page_num in range(max_pages):
                req = self._build_request(query, page_num)
                
                # Executa requisição
                if req.get("method", "GET").upper() == "POST":
                    response = await http.post(
                        req["url"],
                        market_id=self.market_id,
                        headers=req.get("headers"),
                        json=req.get("json"),
                    )
                else:
                    response = await http.get(
                        req["url"],
                        market_id=self.market_id,
                        headers=req.get("headers"),
                        params=req.get("params"),
                    )
                
                # CORREÇÃO: Usa decodificação segura
                try:
                    data = safe_decode_response(response)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    self.logger.error(
                        "Erro ao decodificar resposta",
                        error=str(e)[:200],
                        content_type=response.headers.get('content-type', 'unknown'),
                        content_encoding=response.headers.get('content-encoding', 'none'),
                        content_length=len(response.content),
                    )
                    result.status = CollectionStatus.FAILED
                    result.error_message = f"Erro de decodificação: {str(e)[:100]}"
                    break
                
                if data is None:
                    self.logger.warning("Resposta vazia da API")
                    if page_num == 0:
                        result.status = CollectionStatus.NO_RESULTS
                    break
                
                products, total = self._parse_response(data, query, cep, page_num)
                
                if total_available is None:
                    total_available = total
                
                if not products:
                    if page_num == 0:
                        result.status = CollectionStatus.NO_RESULTS
                    break
                
                all_products.extend(products)
                result.pages_scraped += 1
                
                self.logger.info("Página coletada", page=page_num + 1, products=len(products))
                
                # Verifica se há mais páginas
                if total_available and (page_num + 1) * self.PRODUCTS_PER_PAGE >= total_available:
                    break
                
                # Delay entre páginas
                if page_num < max_pages - 1:
                    await asyncio.sleep(random.uniform(0.3, 0.8))
            
            result.products = all_products
            result.status = CollectionStatus.SUCCESS if all_products else CollectionStatus.NO_RESULTS
            
        except httpx.HTTPStatusError as e:
            result.status = CollectionStatus.FAILED
            result.error_message = f"HTTP {e.response.status_code}"
            self.logger.error("Erro HTTP", status=e.response.status_code)
            
        except Exception as e:
            result.status = CollectionStatus.FAILED
            result.error_message = str(e)
            self.logger.error("Erro na busca", error=str(e), exc_info=True)
        
        finally:
            result.mark_finished()
        
        self.logger.info(
            "Busca finalizada",
            market=self.market_id,
            status=result.status.value,
            products=result.products_count,
            duration=f"{result.duration_seconds:.2f}s" if result.duration_seconds else "N/A",
        )
        
        return result
    
    # Helpers
    def _format_price_br(self, price: float) -> str:
        """Formata preço no padrão BR."""
        return f"R$ {price:.2f}".replace(".", ",")
    
    def _create_product(
        self,
        title: str,
        price: float,
        url: str,
        query: str,
        cep: Optional[str],
        position: int,
        image_url: Optional[str] = None,
        external_id: Optional[str] = None,
        unit_price_raw: Optional[str] = None,
        extra_data: Optional[Dict] = None,
    ) -> RawProduct:
        """Helper para criar RawProduct."""
        return RawProduct(
            market_id=self.market_id,
            external_id=external_id,
            title=title.strip(),
            price_raw=self._format_price_br(price),
            unit_price_raw=unit_price_raw,
            url=url,
            image_url=image_url,
            availability_raw="Disponível",
            search_query=query,
            cep=cep,
            collected_at=datetime.now(),
            extra_data={"position": position, "source": "api", **(extra_data or {})},
        )