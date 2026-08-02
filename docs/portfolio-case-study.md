# Estudo de caso — Infrastructure Operations Platform

## Resumo executivo

O projeto consolida ferramentas utilizadas em operações de infraestrutura em uma plataforma integrada, segura e observável. Trata-se de uma implementação autoral e reproduzível em ambiente controlado de validação, baseada em desafios, padrões operacionais e necessidades observados ao longo da experiência profissional.

## Contexto

Ferramentas como NetBox, Zabbix, Grafana, Prometheus, Traefik, Portainer e Cockpit resolvem problemas diferentes. Quando implantadas isoladamente, surgem desafios de identidade, exposição, inventário duplicado, monitoramento fragmentado, segredos dispersos e operação baseada em conhecimento informal.

O objetivo foi tratá-las como uma única plataforma operacional, sem criar um monólito.

## Desafios de engenharia

- preservar responsabilidades claras entre inventário, eventos e métricas;
- expor aplicações com TLS e autenticação consistentes;
- manter acesso local durante indisponibilidade da Internet;
- evitar publicação direta de bancos e caches;
- monitorar equipamentos, host, containers e aplicações;
- integrar NetBox e Zabbix sem sincronização irrestrita;
- organizar mudanças com rollback;
- transformar o ambiente em documentação publicável sem vazar dados.

## Solução

### Arquitetura modular

Cinco projetos Compose independentes organizam entrada, monitoramento, inventário, observabilidade e administração. Serviços nativos do RHEL complementam a plataforma.

### Segurança em camadas

Cloudflare Access fornece identidade na borda. Traefik centraliza TLS e roteamento. O Docker Socket é consumido por proxy restrito. Bancos e caches permanecem em redes internas.

### Observabilidade híbrida

Zabbix cuida de estado, triggers, mapas e eventos. Prometheus coleta métricas do host, containers, rede e aplicações. Grafana consolida dashboards executivos e técnicos.

### Fonte de verdade

NetBox mantém DCIM/IPAM e fornece contexto de ativos. Uma integração dedicada atualiza o Zabbix de forma controlada, evitando acoplamento direto ao banco.

### Governança operacional

ADRs, runbooks, inventário, política de segurança, roadmap e validação automatizada tornam as decisões rastreáveis e o conhecimento transferível.

## Resultados alcançados

- plataforma funcional sobre RHEL;
- 19 containers organizados por domínio;
- publicação centralizada por hostname;
- acesso externo protegido e acesso local preservado;
- monitoramento completo do ecossistema;
- mapa Zabbix com dependências e triggers reais;
- dashboards para host, Docker, proxy, certificados, UDM e MikroTik;
- inventário técnico e configuração sanitizada;
- repositório preparado para revisão pública;
- construção reproduzível com Packer, Vagrant e Ansible;
- CI para PowerShell, Ansible, Compose, Prometheus, inventário de imagens e segurança;
- backups consistentes com réplica externa criptografada e restauração isolada;
- alertas por severidade com Alertmanager e entrega de e-mail validada;
- roadmap claro para GLPI e evolução da resiliência.

## Decisões relevantes

| Decisão | Justificativa |
|---|---|
| projetos Compose separados | isolamento e atualização independente |
| Traefik como entrada única | TLS, roteamento e política uniformes |
| Docker Socket Proxy | redução do acesso direto ao daemon |
| Zabbix + Prometheus | eventos e métricas com responsabilidades distintas |
| NetBox como fonte de verdade | evitar inventário técnico fragmentado |
| DNS dividido | manter o mesmo hostname dentro e fora |
| GLPI em fase própria | preservar limites entre ITSM e DCIM/IPAM |

## Maturidade e transparência

O projeto registra também lacunas atuais. Backup, restauração, CI e alertas possuem implementação versionada e validação operacional. O pacote visual sanitizado foi concluído com evidências observadas no ambiente funcional, mantendo separação clara entre resultados comprovados e evoluções planejadas. Tornar riscos e pendências explícitos faz parte da qualidade profissional da solução.

## Próximos passos

1. publicar a primeira release do marco funcional;
2. formalizar política de atualização e rotação de credenciais;
3. integrar alertas ao futuro fluxo ITSM;
4. desenvolver a fase GLPI;
5. avaliar resiliência multi-nó conforme requisitos.

## Evidências verificáveis

- [pacote de resultados e evidências](evidence/README.md);
- [matriz requisito–implementação–prova](evidence/evidence-matrix.md);
- [arquitetura sanitizada](evidence/assets/architecture-overview.svg);
- [backup e restauração](runbooks/backup-restore.md);
- [objetivos de confiabilidade](reliability-objectives.md);
- [workflows de CI](../.github/workflows/).

## Competências evidenciadas

- Linux e RHEL;
- containers e redes Docker;
- reverse proxy e PKI;
- Zero Trust;
- observabilidade e monitoração;
- DCIM/IPAM;
- automação e APIs;
- segurança operacional;
- troubleshooting;
- documentação e governança;
- desenho evolutivo de plataforma.
