# Backup e restauração

## Estado comprovado

O backup local do NetBox foi automatizado e validado no ambiente de validação.
O controle inclui dump consistente do PostgreSQL, mídia, configuração Compose
não secreta, metadados e manifesto SHA-256. A restauração foi comprovada em um
PostgreSQL temporário e isolado, sem alterar o banco ativo.

Essa evidência não substitui uma cópia externa. Zabbix e os demais componentes
permanecem no roadmap até terem automação e restauração igualmente comprovadas.

## NetBox

O timer `netbox-backup.timer` executa diariamente e grava os conjuntos em:

```text
/var/backups/infrastructure-platform/netbox/<UTC_TIMESTAMP>/
|-- database.dump
|-- media.tar.gz
|-- compose.yaml
|-- metadata.txt
`-- SHA256SUMS
```

Comandos operacionais:

```bash
sudo systemctl status netbox-backup.timer
sudo systemctl list-timers netbox-backup.timer
sudo systemctl start netbox-backup.service
sudo journalctl -u netbox-backup.service
sudo /usr/local/sbin/netbox-backup verify
```

O modo `verify` valida checksums e mídia, sobe um PostgreSQL descartável,
restaura o dump com `--exit-on-error`, confirma a tabela de migrações do NetBox
e remove o container de teste.

## Escopo da plataforma

| Componente | Conteúdo |
|---|---|
| NetBox | PostgreSQL, mídia, configuração não secreta e metadados |
| Zabbix | MySQL, configuração, mapa e scripts auxiliares |
| Grafana | volume de dados e dashboards provisionados |
| Prometheus | configuração; TSDB conforme política de criticidade |
| Traefik | configuração dinâmica, estática e estado ACME |
| Portainer | volume de dados |
| Host | arquivos de serviço, timers, firewall e documentação |

## Política

- backup local diário;
- retenção local configurável;
- cópia externa criptografada;
- alerta para timer com falha ou backup antigo;
- teste mensal de restauração de banco;
- teste trimestral de reconstrução completa.

## Ordem de restauração

1. recriar host, armazenamento e Docker;
2. restaurar configurações sob `/opt`;
3. recriar redes e volumes;
4. restaurar bancos;
5. restaurar mídia e dados persistentes;
6. iniciar aplicações e workers;
7. restaurar observabilidade e proxy;
8. validar login, dados essenciais e integrações.

## Critério de sucesso

Um backup só é válido quando:

- os checksums correspondem;
- arquivos criptografados externos podem ser descriptografados;
- o banco restaura sem erro;
- a aplicação inicia;
- login e dados essenciais são validados;
- evidência sanitizada é registrada.

## Proibição

Nunca armazene dumps reais, chaves, arquivos `.env`, Vault passwords ou estado
ACME neste repositório público.
