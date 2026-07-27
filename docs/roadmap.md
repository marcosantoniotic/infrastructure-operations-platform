# Roadmap

## Fase 0 — Baseline documentado

- [x] inventário do host e containers;
- [x] arquitetura e dependências;
- [x] política de segredos;
- [x] runbooks principais;
- [x] catálogo de serviços;
- [x] documentação publicável.

## Fase 1 — Confiabilidade operacional

- [ ] implantar backups automáticos de NetBox e Zabbix;
- [ ] monitorar idade e resultado dos backups;
- [ ] realizar teste de restauração;
- [ ] definir RPO e RTO;
- [ ] documentar retenção do Zabbix e Prometheus;
- [ ] criar janela mensal de manutenção.

## Fase 2 — Segurança e governança

- [ ] limitar a porta do Zabbix Server por origem;
- [ ] revisar permissões dos tokens;
- [ ] formalizar rotação de credenciais;
- [ ] validar headers de segurança;
- [ ] revisar imagens privilegiadas;
- [ ] implantar análise de dependências e imagens.

## Fase 3 — Automação

- [ ] gerar inventário sanitizado automaticamente;
- [ ] validar Compose e Prometheus em CI;
- [ ] detectar tags não fixadas;
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
- [ ] separar backups do host principal;
- [ ] testar recuperação total;
- [ ] avaliar proxy e DNS de contingência;
- [ ] definir estratégia de alta disponibilidade orientada por requisitos de RTO, RPO e criticidade.
