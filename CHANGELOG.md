# Changelog

Todas as mudanças relevantes deste projeto são documentadas neste arquivo. O
versionamento segue [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Adicionado

- baseline funcional e arquitetural da Fase 4 GLPI, com MariaDB dedicado,
  fronteiras de autoridade, segurança, integrações, RPO/RTO e gates de aceite;
- role GLPI reproduzível com imagens fixadas, administrador dedicado, contas
  padrão desativadas, persistência separada e validação de schema e HTTPS;
- conta administrativa dedicada e governada por Vault para acesso ao Cockpit,
  mantendo a identidade de automação restrita a chave SSH;
- instalação reproduzível e validação do NetBox Topology Views compatível com
  NetBox 4.5;
- role e playbook dedicados para sincronização controlada NetBox-Zabbix;
- provisionamento idempotente do campo `zabbix_hostid`, token via Vault e
  validação dry-run;
- documentação reutilizável da integração e de seus critérios de validação;
- SNMP Exporter opcional com módulos oficiais, segredo no Vault e validação de
  todos os alvos configurados;
- UniFi Poller opcional e reproduzível, com conta somente leitura, segredo no
  Vault, coleta Prometheus e validação obrigatória de telemetria real.

### Corrigido

- raiz do hostname do Traefik redirecionada para `/dashboard/`, eliminando o
  `404` ao acessar o endereço público sem caminho;
- autorização de origens HTTPS/WSS adicionais no Cockpit para aliases publicados
  pelo Traefik, evitando falha da sessão interativa após o login;
- imagens de tipos de dispositivo e anexos do NetBox restauradas ao publicar o
  volume persistente `/media` pelo Granian e validar a rota em cada convergência;
- publicação HTTPS interna agora documenta certificado privado, portas de
  validação por serviço, origem CSRF do NetBox e fallback por túnel SSH;
- observabilidade pode provisionar o datasource Zabbix por rede externa e
  segredo montado, com validação prévia da dependência;
- rotas estáticas do host e redes externas do mapa Zabbix são declarativas,
  validadas e idempotentes;
- janela de manutenção agora chama o executável realmente instalado para a
  réplica externa criptografada;
- documentada a preservação obrigatória de repositórios Restic existentes
  quando a chave configurada não corresponde ao destino;
- definido o ensaio operacional seguro e a cadência recomendada para a janela
  mensal de manutenção;
- documentada a rotação segura da chave SMTP e a validação completa dos
  estados firing e resolved do Alertmanager;
- dashboard de aplicações agora monitora serviços internos por redes Docker
  declaradas e só exibe validade TLS quando há alvos HTTPS reais;
- dashboard DNS agora oculta métricas específicas do AdGuard quando o coletor
  opcional não está habilitado e mantém os probes portáveis por resolvedor;
- persistência dos layouts do NetBox Topology Views ao habilitar oficialmente
  a gravação de coordenadas;
- nós invisíveis no Topology Views quando um papel não possui imagem associada;
- mapa vazio no Topology Views ao coletar e validar os arquivos estáticos do
  plugin após a inicialização do NetBox;
- compatibilidade de datasource Grafana ao preservar o UID legado e provisionar
  o datasource canônico separadamente;
- restore isolado Zabbix para dumps que contêm `ALTER DATABASE` com o nome do
  schema original;
- recriação automática do sincronizador após rotação do token ou mudança dos
  artefatos implantados.

## [1.0.0] - 2026-08-05

### Adicionado

- baseline RHEL reproduzível com Packer, Vagrant e Ansible;
- implantação modular de Traefik, NetBox, Zabbix, Portainer, Cockpit e da stack
  de observabilidade;
- inventário demonstrativo, integração NetBox–Zabbix e mapa operacional com
  triggers reais;
- dashboards de host, containers, aplicações, TLS, DNS, backups e manutenção;
- backups consistentes de NetBox, Zabbix e observabilidade, réplica externa
  criptografada e verificações isoladas de restauração;
- nó de recuperação e nó de standby para validação de continuidade;
- Alertmanager com políticas de severidade e notificação externa;
- CI para Ansible, Compose, Prometheus, PowerShell, imagens e segurança;
- pacote sanitizado de evidências para publicação e apresentação profissional.

### Segurança e governança

- Docker Socket Proxy restrito e middlewares de segurança no Traefik;
- imagens de containers fixadas por versão ou digest;
- catálogo de credenciais sem valores sensíveis;
- proteção da branch principal, `CODEOWNERS`, Dependabot e varreduras Trivy;
- ADRs, runbooks, matriz de criticidade, RPO/RTO e gestão de mudanças.

### Limites da versão

- GLPI permanece como fase futura independente;
- failover multi-nó automático e replicação síncrona de bancos não fazem parte
  desta baseline;
- inventários reais, segredos, backups e dados operacionais não são publicados.

## [0.2.0] - 2026-08-02

- consolidação da validação operacional e do pacote de evidências;
- mapa do ecossistema no Zabbix e inventário sanitizado no NetBox;
- fortalecimento das verificações de publicação e segurança;
- adoção da licença Apache 2.0.

## [0.1.0] - 2026-07-28

- fundação reproduzível RHEL, Packer, Vagrant e Ansible;
- implantação modular inicial do NetBox;
- backup e restauração isolada do PostgreSQL;
- primeira pipeline de validação e segurança de publicação.

[1.0.0]: https://github.com/marcosantoniotic/infrastructure-operations-platform/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/marcosantoniotic/infrastructure-operations-platform/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/marcosantoniotic/infrastructure-operations-platform/releases/tag/v0.1.0
