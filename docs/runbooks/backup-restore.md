# Backup e restauração

## Estado comprovado

O backup local do NetBox foi automatizado e validado no ambiente de validação.
O controle inclui dump consistente do PostgreSQL, mídia, configuração Compose
não secreta, metadados e manifesto SHA-256. A restauração foi comprovada em um
PostgreSQL temporário e isolado, sem alterar o banco ativo.

O Zabbix possui automação equivalente. Os conjuntos dos dois sistemas são
replicados para um repositório Restic criptografado no OneDrive. Uma recuperação
completa dos dados das aplicações foi comprovada em uma terceira VM isolada,
reconstruída por Ansible, sem alterar o ambiente principal.

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

## Zabbix

O timer `zabbix-backup.timer` executa diariamente e grava os conjuntos em:

```text
/var/backups/infrastructure-platform/zabbix/<UTC_TIMESTAMP>/
|-- database.sql
|-- server-data.tar.gz
|-- compose.yaml
|-- metadata.txt
`-- SHA256SUMS
```

Comandos operacionais:

```bash
sudo systemctl status zabbix-backup.timer
sudo systemctl list-timers zabbix-backup.timer
sudo systemctl start zabbix-backup.service
sudo journalctl -u zabbix-backup.service
sudo /usr/local/sbin/zabbix-backup verify
```

O modo `verify` confirma os checksums e o arquivo operacional, restaura o dump
em um MySQL temporário e valida as tabelas essenciais `dbversion` e `hosts`.
O banco ativo não é interrompido ou alterado.

## GLPI

O timer `glpi-backup.timer` executa diariamente e grava os conjuntos em:

```text
/var/backups/infrastructure-platform/glpi/<UTC_TIMESTAMP>/
|-- database.sql
|-- application-data.tar.gz
|-- compose.yaml
|-- custom-php.ini
|-- metadata.txt
`-- SHA256SUMS
```

O GLPI entra em manutenção apenas durante a captura consistente. O arquivo da
aplicação protege `glpicrypt.key`, `config_db.php`, documentos, anexos,
inventários, logs e marketplace; arquivos de segredo do Compose não são
copiados.

```bash
sudo systemctl status glpi-backup.timer
sudo systemctl start glpi-backup.service
sudo journalctl -u glpi-backup.service
sudo /usr/local/sbin/glpi-backup verify
```

O modo `verify` importa o banco em um MariaDB descartável, valida as tabelas
essenciais e extrai os dados em um volume Docker temporário. A chave e a
configuração precisam estar presentes e não vazias. Nenhum volume ativo é
montado ou alterado durante a restauração de teste.

## Escopo da plataforma

| Componente | Conteúdo |
|---|---|
| NetBox | PostgreSQL, mídia, configuração não secreta e metadados |
| Zabbix | MySQL, configuração, mapa e scripts auxiliares |
| GLPI | MariaDB, chave de criptografia, documentos, anexos, logs e marketplace |
| Grafana | volume de dados e dashboards provisionados |
| Prometheus | configuração; TSDB conforme política de criticidade |
| Traefik | configuração dinâmica, estática e estado ACME |
| Portainer | volume de dados |
| Host | arquivos de serviço, timers, firewall e documentação |

## Grafana e Prometheus

O timer `observability-backup.timer` produz diariamente:

```text
/var/backups/infrastructure-platform/observability/<UTC_TIMESTAMP>/
|-- grafana-data.tar.gz
|-- prometheus-data.tar.gz
|-- compose.yaml
|-- metadata.txt
`-- SHA256SUMS
```

Comandos operacionais:

```bash
sudo systemctl status observability-backup.timer
sudo systemctl start observability-backup.service
sudo journalctl -u observability-backup.service
sudo /usr/local/sbin/observability-backup verify
```

Grafana e Prometheus são encerrados de forma limpa somente durante a cópia
consistente de seus volumes e são reiniciados imediatamente. A validação cria
volumes e containers descartáveis, restaura os dois arquivos e verifica as APIs
de saúde e o banco do Grafana. O conjunto é então incluído na réplica Restic
criptografada.

## Política

- backup local diário;
- retenção local configurável;
- cópia externa criptografada;
- alerta para timer com falha ou backup antigo;
- teste mensal de restauração de banco;
- teste trimestral de reconstrução completa.

O Prometheus recebe `infrastructure_backup_last_run_success` e
`infrastructure_backup_last_success_timestamp_seconds` pelo Node Exporter.
Consulte o dashboard `Infrastructure Operations — Backup Health` para verificar
as duas rotinas de forma centralizada.

Os objetivos formais e períodos de retenção estão definidos em
[Reliability objectives](../reliability-objectives.md).

## Réplica externa criptografada

Os conjuntos locais validados do NetBox, Zabbix, observabilidade e GLPI são replicados para um
repositório Restic criptografado, transportado pelo rclone para o OneDrive.
A senha do repositório e a configuração OAuth são fornecidas exclusivamente
por Ansible Vault.

Controles aplicados:

- execução diária pelo timer `infrastructure-external-backup.timer`;
- retenção de 14 cópias diárias, 8 semanais e 3 mensais;
- deduplicação e criptografia do lado do cliente pelo Restic;
- verificação de integridade de uma amostra de dados após cada execução;
- métricas sanitizadas no Node Exporter;
- alertas de falha e ausência de cópia recente;
- restauração com `restic restore --verify` comprovada no ambiente de validação.

Comandos operacionais:

```bash
sudo systemctl status infrastructure-external-backup.timer
sudo systemctl list-timers infrastructure-external-backup.timer
sudo systemctl start infrastructure-external-backup.service
sudo journalctl -u infrastructure-external-backup.service
```

Não exponha a senha Restic, o arquivo `rclone.conf`, tokens OAuth ou conteúdo
de snapshots em logs, capturas de tela ou commits.

## Ordem de restauração

1. recriar host, armazenamento e Docker;
2. restaurar configurações sob `/opt`;
3. recriar redes e volumes;
4. restaurar bancos;
5. restaurar mídia e dados persistentes;
6. iniciar aplicações e workers;
7. restaurar observabilidade e proxy;
8. validar login, dados essenciais e integrações.

## Teste completo em VM isolada

O teste exige uma terceira VM chamada exatamente `srv01-recovery`, endereço
distinto do ambiente principal, credenciais locais ignoradas pelo Git e
registro RHEL válido. Inicialize a configuração e a VM:

```powershell
.\automation\scripts\Initialize-Validation.ps1 `
  -ControllerAddress "<CONTROLLER_IP>" `
  -PlatformAddress "<PLATFORM_IP>" `
  -RecoveryAddress "<RECOVERY_IP>"

Set-Location .\automation\vagrant
vagrant up srv01-recovery --no-provision
Set-Location ..\..
```

Depois do registro RHEL, execute:

```powershell
.\automation\scripts\Run-DisasterRecoveryDrill.ps1
```

Para repetir somente a importação e os testes em uma VM já provisionada:

```powershell
.\automation\scripts\Run-DisasterRecoveryDrill.ps1 -SkipPlatformRebuild
```

O workflow recusa execução sem autorização explícita, em hostname diferente de
`srv01-recovery`, no mesmo endereço do ambiente principal ou fora de
`/var/tmp`. O timer externo permanece desativado nessa VM para impedir que o
teste publique novos snapshots. A evidência sanitizada local é gravada em
`.validation/recovery/evidence.json`, que é ignorado pelo Git.

Para testar as interfaces sem publicar o Traefik na rede, crie um túnel SSH
temporário da estação para `127.0.0.1:8443` da VM. O teste automatizado interno
usa SNI TLS real para `netbox.localhost` e `zabbix.localhost`.

## Critério de sucesso

Um backup só é válido quando:

- os checksums correspondem;
- arquivos criptografados externos podem ser descriptografados;
- o banco restaura sem erro;
- a aplicação inicia;
- login e dados essenciais são validados;
- evidência sanitizada é registrada.

Em 2026-07-30, a restauração de dados das duas aplicações foi concluída em 65
segundos, incluindo download e verificação do snapshot, validação SHA-256,
importação dos bancos, restauração dos dados persistentes e testes HTTP 200
através do Traefik. O workflow repetido completo, incluindo preparação e
verificação do repositório, terminou em 114 segundos.

No mesmo dia, a reconstrução integral foi exercitada a partir de uma VM RHEL
nova e não provisionada. Após o registro externo do sistema, a automação
reconstruiu todos os serviços e restaurou 106,612 MiB do snapshot criptografado.
A execução automatizada final levou 441 segundos, dos quais 88 segundos
corresponderam à restauração e validação dos dados. Medido desde a autorização
original, incluindo registro e reruns corretivos, o serviço utilizável foi
recuperado em 35 minutos e 28 segundos, dentro do RTO de quatro horas.

O exercício revelou e corrigiu três condições: normalização CRLF dos comandos
remotos enviados a partir do Windows, período de tolerância para as migrações
do NetBox em inicialização fria e retentativa da troca de senha administrativa
do Zabbix durante o bootstrap. Por isso, o registro representa um exercício de
engenharia bem-sucedido com desvios corretivos, e não uma execução limpa na
primeira tentativa.

Em uma extensão do exercício, o snapshot criptografado `ce35e743` incluiu o
estado do Grafana e a TSDB do Prometheus. O Restic restaurou e verificou 84
arquivos e diretórios (288,223 MiB), e 13 manifestos históricos SHA-256 foram
validados. A VM isolada substituiu os quatro conjuntos de dados, confirmou os
bancos do NetBox, Zabbix e Grafana, carregou checkpoint e WAL do Prometheus e
concluiu a recuperação das aplicações em 107 segundos.

## Proibição

Nunca armazene dumps reais, chaves, arquivos `.env`, Vault passwords ou estado
ACME neste repositório público.
