# Roadmap

## Fase 0 — Baseline documentado

- [x] inventário do host e containers;
- [x] arquitetura e dependências;
- [x] política de segredos;
- [x] runbooks principais;
- [x] catálogo de serviços;
- [x] documentação publicável.

## Fase 1 — Confiabilidade operacional

- [x] implantar e validar backup local automático do NetBox;
- [x] implantar e validar backups automáticos do Zabbix;
- [x] replicar backups para armazenamento externo criptografado;
- [x] monitorar idade e resultado dos backups;
- [x] realizar teste isolado de restauração do NetBox;
- [x] proteger e restaurar isoladamente o estado do Grafana e a TSDB do Prometheus;
- [x] definir RPO e RTO;
- [x] documentar retenção do Zabbix e Prometheus;
- [x] criar janela mensal de manutenção.

## Fase 2 — Segurança e governança

- [x] limitar a porta do Zabbix Server por origem;
- [ ] revisar permissões dos tokens;
- [ ] formalizar rotação de credenciais;
- [x] validar headers de segurança no gateway Traefik;
- [x] restringir descoberta Docker por Socket Proxy somente leitura;
- [x] proteger o dashboard do Traefik sem modo inseguro;
- [ ] revisar imagens privilegiadas;
- [ ] implantar análise de dependências e imagens.

## Fase 3 — Automação

- [ ] gerar inventário sanitizado automaticamente;
- [x] validar Compose e Prometheus em CI;
- [x] detectar tags não fixadas;
- [ ] automatizar teste HTTP 200/302;
- [ ] registrar mudanças por pull request;
- [ ] avaliar Infrastructure as Code para DNS e Access.

## Fase 4 — GLPI

- [ ] definir requisitos funcionais;
- [ ] escolher banco e estratégia de backup;
- [ ] publicar atrás do Traefik e Cloudflare Access;
- [ ] integrar alertas do Zabbix com tickets;
- [ ] integrar ativos sem duplicar o NetBox;
- [ ] criar dashboards e runbooks.

Consulte [Fase futura: GLPI](glpi-phase.md).

## Fase 5 — Resiliência

- [ ] avaliar segundo nó;
- [x] separar backups do host principal;
- [x] testar recuperação dos dados e aplicações em VM isolada;
- [x] medir reconstrução integral a partir de uma VM limpa, incluindo dependências externas;
- [ ] avaliar proxy e DNS de contingência;
- [ ] definir estratégia de alta disponibilidade orientada por requisitos de RTO, RPO e criticidade.
