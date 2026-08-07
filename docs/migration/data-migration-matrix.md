# Matriz de migração de dados

## Uso

Esta matriz define o que deve ser reconstruído por código, restaurado, exportado
ou deliberadamente iniciado vazio. A versão e o método exatos devem ser
confirmados na descoberta imediatamente anterior à migração.

| Componente | Estado a preservar | Método suportado | Não fazer | Validação | Estratégia de rollback |
|---|---|---|---|---|---|
| NetBox | PostgreSQL, mídia, relatórios, scripts, plugins e artefatos autorizados de integração | dump lógico consistente, arquivos arquivados, manifesto e checksum | copiar volume PostgreSQL ativo | login, contagens, objetos, mídia, plugins e jobs | manter dump final e ambiente anterior preservado |
| Zabbix | MySQL, hosts, templates, mapas, triggers, usuários e histórico conforme decisão | dump lógico consistente compatível com a versão alvo | copiar datadir MySQL ativo | schema, frontend, server, filas, hosts e triggers | manter dump final e reverter origin/notificações |
| Grafana | dashboards, pastas, datasources e configuração aprovada | preferir provisioning e JSON versionado; migrar banco somente se houver estado manual indispensável | usar o banco antigo sem avaliar plugins e versão | dashboards carregam e queries retornam dados | reaplicar provisioning ou restaurar exportação aprovada |
| Prometheus | regras, targets e, opcionalmente, histórico | configuração por código; iniciar TSDB novo; preservar snapshot antigo como arquivo somente leitura quando necessário | copiar TSDB em execução | targets, rules, retenção e queries | consultar arquivo antigo separadamente |
| Alertmanager | rotas, templates e silences que devam permanecer | configuração por código; recriar silences aprovados | ativar duas origens de alerta | teste controlado de roteamento | desativar novo e manter origem anterior |
| Traefik | configuração estática/dinâmica e middlewares | Ansible/Compose; emitir ou importar certificado apenas pelo processo aprovado | copiar socket, tokens ou ACME sem governança | routers, services, TLS e headers | devolver origin ao proxy anterior |
| Portainer | identidade administrativa e visão dos projetos | reconstruir a partir de Compose; restaurar dados apenas se o histórico for requisito | tratar Portainer como fonte de verdade do Compose | endpoint, stacks, containers e acesso | acessar projetos diretamente por Compose |
| Cockpit | configuração do serviço e políticas de acesso | Ansible | migrar sessão ou cache | login, serviço e proxy | acesso SSH e console VMware |
| Backups | pontos finais, manifestos e configuração de retenção | preservar repositório antigo e iniciar cadeia nova validada | misturar silenciosamente cadeias incompatíveis | checksum, listagem e restauração isolada | utilizar ponto anterior comprovado |
| Cloudflare | DNS, Tunnel origins, Access e políticas | mudança controlada/IaC conforme runbook | expor tokens ou trocar origin antes do aceite | resposta externa e desafio de autenticação | restaurar origin anterior |
| Segredos | somente valores ainda válidos e aprovados | recuperar do cofre e injetar em runtime | exportar segredos do host antigo para Git | autenticação sem exposição | rotacionar e reimplantar |
| UDM/UniFi | configuração do poller, dashboards e credencial no cofre | reconstruir exporter/poller por código; revalidar API | copiar credencial para arquivos públicos | coleta, labels e dashboards | manter monitoramento anterior desativado ou isolado |
| MikroTik | configuração SNMP/exporter e dashboards | reconstruir exporter por código; revalidar SNMP | duplicar polling com alertas concorrentes | interfaces, CPU, memória e disponibilidade | retornar coleta ao ambiente anterior |

## Decisões obrigatórias antes da carga final

- janela máxima sem escrita no NetBox;
- retenção ou descarte do histórico do Zabbix;
- necessidade real de histórico do Prometheus;
- dashboards do Grafana que ainda não estão provisionados;
- integrações que devem nascer desativadas;
- responsáveis pelo cutover e pelo rollback;
- duração do período de preservação do ambiente anterior;
- RPO e RTO aceitos para cada serviço.

## Evidência mínima

Para cada linha migrada, registre sem dados sensíveis:

1. versão de origem e destino;
2. timestamp do ponto de recuperação;
3. resultado do checksum;
4. duração do restore;
5. testes funcionais executados;
6. decisão de aceite ou rollback;
7. referência da mudança.
