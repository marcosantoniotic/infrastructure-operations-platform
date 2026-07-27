# Backup e restauração

## Estado atual

Na coleta de 2026-07-27 não havia timers de backup do NetBox ou Zabbix ativos. Este runbook define o estado desejado; sua existência não comprova que o controle foi implantado.

## Escopo mínimo

| Componente | Conteúdo |
|---|---|
| NetBox | PostgreSQL, mídia, configuração e imagem customizada |
| Zabbix | MySQL, configuração, mapa e scripts auxiliares |
| Grafana | volume de dados e dashboards provisionados |
| Prometheus | configuração; TSDB conforme política de criticidade |
| Traefik | configuração dinâmica, estática e estado ACME |
| Portainer | volume de dados |
| Host | arquivos de serviço, timers, firewall e documentação |

## Política recomendada

- backup diário;
- retenção diária, semanal e mensal;
- uma cópia fora do host;
- criptografia antes da cópia externa;
- alerta quando não houver backup recente;
- teste mensal de restauração de banco;
- teste trimestral de reconstrução completa.

## Ordem de restauração

1. recriar host, armazenamento e Docker;
2. restaurar configurações sob `/opt`;
3. recriar redes e volumes;
4. restaurar MySQL e PostgreSQL;
5. restaurar Redis/Valkey apenas se necessário;
6. restaurar NetBox e Zabbix;
7. restaurar observabilidade;
8. restaurar proxy e acessos;
9. validar integrações.

## Critério de sucesso

Um backup só é considerado válido quando:

- o arquivo pode ser descriptografado;
- o checksum corresponde;
- o banco restaura sem erro;
- a aplicação inicia;
- login e dados essenciais são validados;
- evidência sanitizada é registrada.

## Proibição

Nunca armazene dumps reais, chaves ou arquivos ACME neste repositório público.
