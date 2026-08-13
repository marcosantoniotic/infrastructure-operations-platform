# Observabilidade

## Modelo de responsabilidades

### Zabbix

- disponibilidade de infraestrutura e aplicações;
- triggers e severidades;
- mapa do ecossistema;
- eventos e futura notificação;
- monitoramento do host pelo Agent 2;
- sincronização de ativos selecionados pelo NetBox.

### Prometheus

- métricas do RHEL por Node Exporter;
- métricas de containers por cAdvisor;
- disponibilidade e certificados por Blackbox Exporter;
- métricas do Traefik quando a integração está habilitada;
- telemetria de equipamentos de rede pelo SNMP Exporter opcional.

#### SNMP Exporter

Defina `observability_snmp_enabled: true`, armazene a comunidade somente em
`vault_observability_snmp_community` e declare cada equipamento em
`observability_snmp_targets`. Para MikroTik, a configuração padrão combina os
módulos oficiais `system`, `if_mib`, `hrDevice`, `hrStorage`, `hrSystem` e
`mikrotik`; isso atende métricas `sys*`, `if*`, `hr*` e `mtxr*` usadas pelos
dashboards.

O papel cria os jobs `network-snmp` e `snmp-exporter`, testa a resolução e o
endpoint do exporter a partir do container Prometheus e falha quando qualquer
alvo configurado não retorna `up=1`. `observability_snmp_scrape_timeout` deve
permanecer menor ou igual ao intervalo global de coleta.

#### UniFi Poller

Defina `observability_unifi_poller_enabled: true`, informe a URL HTTPS interna
da API do controller, sem proxy de autenticação interativo, e use uma conta
local dedicada com perfil somente leitura. A senha
fica exclusivamente em `vault_observability_unifi_password`; o papel a
materializa em arquivo protegido e o container lê o valor por `file://`, sem
publicá-lo no Compose ou no ambiente do processo.

O papel provisiona a versão fixada do UniFi Poller, habilita a coleta
Prometheus no namespace `unpoller`, cria o job `unifi-poller` e valida que
`unpoller_device_info` contém ao menos um dispositivo. A implantação falha se o
endpoint não estiver acessível, se a autenticação for recusada ou se nenhuma
telemetria real for coletada. `observability_unifi_verify_ssl` deve permanecer
ativado quando o certificado do endpoint interno for confiável; para acesso
direto por IP com certificado próprio do appliance, desative-o explicitamente.

### Alertmanager

- recebe as regras avaliadas pelo Prometheus;
- agrupa alertas por nome, serviço e severidade;
- suprime avisos inferiores quando o mesmo incidente está crítico;
- envia abertura e resolução por SMTP sem gravar a chave no repositório.

Política padrão de notificação:

- críticos: espera de 15 segundos e repetição a cada quatro horas;
- avisos: agrupamento de dois minutos e repetição a cada 12 horas;
- recuperação: mensagem `RESOLVED` enviada pela mesma rota;
- certificados: o crítico de 15 dias suprime o aviso de 30 dias do mesmo serviço.
### Grafana

- visão consolidada do SRV01;
- dashboards de host, containers, Traefik, HTTP e certificados;
- dashboards de UDM/UniFi e MikroTik;
- correlação visual sem assumir a responsabilidade pela coleta.

## Mapa do ecossistema no Zabbix

O mapa de referência de produção contém:

- Internet;
- Cloudflare;
- UDM;
- SRV01-RHEL9;
- Traefik;
- Zabbix e MySQL;
- NetBox, PostgreSQL e Valkey/Redis;
- Grafana e Prometheus;
- Portainer;
- Cockpit.

No ambiente publicável de validação, dependências externas são consolidadas no
elemento informativo `External Access — Internet / Zero Trust`, sem simular
ativos que não pertencem ao laboratório. Os demais elementos são provisionados
pela API e vinculados a sete triggers reais:

- Traefik;
- host RHEL;
- Zabbix e MySQL;
- cadeia NetBox, PostgreSQL e Valkey;
- Grafana e Prometheus;
- Portainer;
- Cockpit.

O elemento do host usa `platform_hostname` como rótulo. Assim, o ambiente de
validação exibe `SRV01-VALIDATION`, enquanto cada nova implantação recebe seu
próprio nome sem alterar o código do mapa.

Dez verificações simples são executadas pelo Zabbix Server a cada 60 segundos.
O servidor participa da rede compartilhada do proxy apenas para iniciar essas
checagens; nenhum listener adicional é publicado. A role valida oito elementos,
sete vínculos e idempotência do mapa.

O host gerenciado também recebe o template `Linux by Zabbix agent active`.
O Agent 2 é instalado diretamente no RHEL e envia CPU, memória, filesystem,
rede, processos e disponibilidade ao listener do Zabbix Server publicado apenas
em loopback. A automação exige o recebimento real de `system.uptime`; portanto,
a conclusão do playbook comprova coleta ativa e não apenas serviço iniciado.

## Dashboards do Grafana

| Dashboard | Objetivo |
|---|---|
| SRV01-RHEL9 — Ecossistema | visão executiva do host e aplicações |
| Node Exporter Full | CPU, memória, disco e rede do RHEL |
| Docker Monitoring | consumo e comportamento dos containers |
| Traefik Official | requisições, latência e respostas |
| Blackbox HTTP | disponibilidade e tempo de resposta |
| SSL Certificate Monitor | validade dos certificados |
| Application & TLS Health | disponibilidade, HTTP, latência e validade TLS |
| UniFi/UDM | gateway, clientes e dispositivos |
| MikroTik | interfaces, CPU, memória e tráfego |

## Sinais mínimos

| Categoria | Sinal |
|---|---|
| Host | uptime, CPU, memória, swap e filesystem |
| Docker | estado, reinícios, CPU e memória |
| Aplicação | disponibilidade, latência e status HTTP |
| Banco/cache | disponibilidade TCP e uso de recursos |
| Proxy | requisições, erros e latência |
| Certificado | dias até expiração |
| Rede | perda, latência, interfaces e tráfego |

## Inventário de probes HTTP

O ambiente de validação comprova probes para:

- Prometheus e Grafana na rede interna de métricas;
- NetBox com cabeçalho `Host` específico;
- Zabbix frontend;
- Portainer;
- endpoint interno de métricas do Traefik.

Cada alvo gera um módulo Blackbox próprio e pode declarar URL, cabeçalho
`Host`, códigos HTTP aceitos e política TLS. O Cockpit utiliza o endpoint
`/ping` do serviço nativo e também participa dos probes HTTP centralizados.

## Alertas recomendados

- host indisponível;
- aplicação indisponível por três coletas;
- filesystem acima de 80% e 90%;
- memória acima de 90% por período sustentado;
- container reiniciando repetidamente;
- certificado com menos de 30 e 15 dias;
- falha de backup ou ausência de arquivo recente;

## Saúde dos backups

As rotinas de backup do NetBox, Zabbix e da própria camada de observabilidade
publicam métricas no textfile collector
do Node Exporter. O dashboard `Infrastructure Operations — Backup Health`
apresenta o resultado da última execução e a idade do último backup válido.

O backup da observabilidade interrompe Grafana e Prometheus de forma limpa pelo
menor intervalo possível, arquiva os volumes persistentes e reinicia os
serviços antes de finalizar o conjunto. A verificação restaura os arquivos em
volumes descartáveis, inicia containers isolados com as mesmas imagens e exige
saúde do banco do Grafana e da TSDB do Prometheus. Nenhum volume ativo é usado
como destino de teste.

Os alertas `PlatformBackupFailed` e `PlatformBackupStale` sinalizam,
respectivamente, uma execução malsucedida e a ausência de backup válido nas
últimas 26 horas. As métricas contêm apenas nome lógico, estado e timestamp;
arquivos, conteúdo e credenciais de backup não são expostos.
- Prometheus target down;
- sincronização NetBox-Zabbix sem execução recente.

O mesmo dashboard apresenta a réplica externa criptografada no OneDrive por
meio das métricas `infrastructure_external_backup_last_run_success`,
`infrastructure_external_backup_last_run_duration_seconds` e
`infrastructure_external_backup_last_success_timestamp_seconds`. Os painéis
consolidam estado, idade do ponto de recuperação, duração, RPO observado e
alertas ativos sem expor nomes de arquivos ou credenciais.

## Retenção atual

Prometheus está configurado para retenção limitada por tempo e tamanho. A retenção do Zabbix deve ser documentada junto ao housekeeping após a primeira revisão de capacidade.
