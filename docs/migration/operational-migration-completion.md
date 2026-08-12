# Relatório de conclusão da migração operacional

## Estado

Migração de dados concluída em 2026-08-11/12. O ambiente legado foi congelado
em 2026-08-12T02:08:15Z e permanece preservado, com writers parados, para
rollback. O ambiente operacional novo é a origem ativa dos serviços internos.

## Carga final

O conjunto final foi criado em
`/var/tmp/iop-final-migration-20260812T020753Z`, com 525 MiB. Os oito arquivos
foram verificados no legado, no controller e no destino.

| Componente | Origem | Destino aceito |
|---|---:|---:|
| NetBox devices | 38 | 38 |
| NetBox virtual machines | 4 | 4 |
| NetBox IP addresses | 22 | 22 |
| Zabbix hosts antes dos objetos IOP | 421 | 421 |
| Zabbix hosts após provisionamento IOP | — | 422 |
| Zabbix items antes dos objetos IOP | 18.777 | 18.777 |
| Zabbix triggers antes dos objetos IOP | 7.191 | 7.191 |

Foram migrados PostgreSQL e mídia do NetBox, MySQL/histórico do Zabbix, banco e
plugins do Grafana e TSDB do Prometheus. Relatórios e scripts NetBox também
foram preservados no conjunto final.

## Ajustes de compatibilidade

- o Grafana legado usa o datasource `Prometheus` com UID
  `unifi-prometheus`; ele foi preservado;
- o datasource canônico passou a se chamar `Prometheus IOP`, UID
  `prometheus`, evitando quebrar dashboards legados;
- a senha administrativa do Grafana foi alinhada ao Vault;
- a senha administrativa do Zabbix foi alinhada ao Vault;
- o restore isolado Zabbix usa o nome original do banco, pois dumps MySQL podem
  conter `ALTER DATABASE zabbix`;
- a sincronização usa o grupo `NetBox - Managed` e o template `ICMP Ping`
  no inventário operacional privado.

## Aceite

- NetBox, Zabbix, Grafana, Prometheus e Portainer: HTTP 200;
- NetBox e Zabbix: convergência oficial com `changed=0`;
- observabilidade: 39 tarefas aprovadas, `changed=0`;
- sincronização NetBox-Zabbix: 2 dispositivos marcados, 2 hosts gerenciados,
  dry-run limpo e `changed=0`;
- nenhum contêiner unhealthy/restarting/exited;
- zero units systemd falhadas;
- timers NetBox, Zabbix e observabilidade ativos e habilitados;
- backups pós-migração e restores isolados aprovados para os três conjuntos.

## Rollback e acesso

O ponto de segurança pré-carga do destino está em
`/var/tmp/iop-pre-migration-20260812T020657Z`. O legado permanece desligado no
nível de aplicação e não deve voltar a receber escrita sem decisão formal de
rollback. A chave SSH temporária usada na migração foi removida.

Os serviços operacionais permanecem publicados somente em loopback e são
acessados pelos túneis documentados com nomes `*.ops.marnep.com.br`. O corte
DNS/Cloudflare público não foi executado porque não há credencial Cloudflare
configurada no projeto; isso é uma mudança externa separada, não um requisito
para o aceite interno da plataforma.
