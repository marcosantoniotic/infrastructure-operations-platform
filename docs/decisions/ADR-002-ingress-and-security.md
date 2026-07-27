# ADR-002: Traefik como entrada única

- Status: aceito
- Data: 2026-07-27

## Contexto

Aplicações expostas por portas independentes dificultavam TLS, acesso por nome, proteção e limpeza do firewall.

## Decisão

Traefik é o ponto único para HTTP/HTTPS. Cloudflare Access protege o caminho externo, e DNS interno aponta os mesmos nomes diretamente ao proxy. O acesso ao Docker Socket ocorre por proxy restrito.

## Consequências

- certificados e middlewares são centralizados;
- bancos e caches continuam privados;
- falha do Traefik afeta todos os acessos por nome;
- acesso local depende de DNS interno correto;
- o proxy precisa de monitoramento e backup de configuração.
