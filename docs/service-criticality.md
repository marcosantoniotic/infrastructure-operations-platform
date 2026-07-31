# Criticidade e estratégia de continuidade

Esta matriz orienta investimento, monitoramento, recuperação e futuros testes
de contingência. A classificação mede impacto operacional, não importância
comercial isolada da ferramenta.

| Componente | Classe | Dependência crítica | Estratégia inicial | Objetivo |
|---|---|---|---|---|
| DNS interno | C1 | rede local | dois resolvedores independentes | nomes locais disponíveis durante falha isolada |
| Traefik | C1 | host, Docker e DNS | configuração reproduzida em standby | recuperar acesso por nome sem restaurar bancos |
| SRV01/RHEL | C1 | hipervisor, rede e armazenamento | reconstrução automatizada e segundo nó | restaurar plataforma dentro do RTO |
| NetBox/PostgreSQL | C1 | proxy, banco e armazenamento | backup externo e restauração testada | RPO 24 h, RTO 4 h |
| Zabbix/MySQL | C1 | proxy, banco e agentes | backup externo e restauração testada | RPO 24 h, RTO 4 h |
| Cloudflare Tunnel/Access | C2 | Internet, conector e origem | conectores redundantes e acesso local independente | preservar caminho externo quando possível |
| Prometheus | C2 | exporters e armazenamento | backup da TSDB e restauração | RPO 24 h, RTO 8 h |
| Grafana | C2 | Prometheus e estado local | dashboards em Git e backup do estado | RPO 24 h, RTO 4 h |
| Portainer | C3 | Docker API | reconstrução por Ansible | administração alternativa por CLI |
| Cockpit | C3 | RHEL | reconstrução pelo baseline | administração alternativa por SSH |

## Classes

- **C1 — essencial:** indisponibilidade impede operação ou recuperação normal;
- **C2 — operacional:** indisponibilidade reduz visibilidade ou acesso externo,
  mas existe caminho alternativo;
- **C3 — administrativo:** facilita a operação, porém possui alternativa por
  linha de comando ou automação.

## Regras de promoção

Um componente só pode ser promovido ao nó de contingência quando:

- a configuração veio do Git e foi validada pela CI;
- os segredos foram entregues sem entrar no repositório;
- dependências e dados foram restaurados ou confirmados saudáveis;
- DNS e proxy apontam somente para a origem validada;
- monitoramento confirma disponibilidade funcional, não apenas processo ativo;
- o operador registrou horário, motivo e resultado da promoção.
