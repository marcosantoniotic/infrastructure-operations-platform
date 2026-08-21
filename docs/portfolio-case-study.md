# Estudo de caso — Infrastructure Operations Platform

## Resumo executivo

O projeto consolida ferramentas utilizadas em operações de infraestrutura em uma plataforma integrada, segura e observável. Trata-se de uma implementação autoral e reproduzível em ambiente controlado de validação, baseada em desafios, padrões operacionais e necessidades observados ao longo da experiência profissional.

## Contexto

Ferramentas como NetBox, Zabbix, GLPI, Grafana, Prometheus, Traefik, Portainer e Cockpit resolvem problemas diferentes. Quando implantadas isoladamente, surgem desafios de identidade, exposição, inventário duplicado, monitoramento fragmentado, segredos dispersos e operação baseada em conhecimento informal.

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

Projetos Compose independentes organizam entrada, monitoramento, inventário, ITSM, observabilidade, integrações e administração. Serviços nativos do RHEL complementam a plataforma.

### Segurança em camadas

Cloudflare Access fornece identidade na borda. Traefik centraliza TLS e roteamento. O Docker Socket é consumido por proxy restrito. Bancos e caches permanecem em redes internas.

### Observabilidade híbrida

Zabbix cuida de estado, triggers, mapas e eventos. Prometheus coleta métricas do host, containers, rede e aplicações. Grafana consolida dashboards executivos e técnicos.

### Fonte de verdade

NetBox mantém DCIM/IPAM e fornece contexto de ativos. Uma integração dedicada atualiza o Zabbix de forma controlada, evitando acoplamento direto ao banco.

### Fluxo de incidentes

Eventos qualificados do Zabbix abrem incidentes idempotentes no GLPI e atualizam
o chamado correspondente quando o evento é recuperado. O GLPI mantém apenas a
referência necessária ao atendimento; o NetBox continua sendo a fonte técnica
de verdade dos ativos.

### Governança operacional

ADRs, runbooks, inventário, política de segurança, roadmap e validação automatizada tornam as decisões rastreáveis e o conhecimento transferível.

## Resultados alcançados

- plataforma funcional sobre RHEL;
- workloads containerizados organizados por domínio e redes restritas;
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
- GLPI implantado com backup, validações e integração idempotente Zabbix–GLPI;
- roadmap claro para exercícios periódicos e evolução da resiliência.

## Decisões relevantes

| Decisão | Justificativa |
|---|---|
| projetos Compose separados | isolamento e atualização independente |
| Traefik como entrada única | TLS, roteamento e política uniformes |
| Docker Socket Proxy | redução do acesso direto ao daemon |
| Zabbix + Prometheus | eventos e métricas com responsabilidades distintas |
| NetBox como fonte de verdade | evitar inventário técnico fragmentado |
| DNS dividido | manter o mesmo hostname dentro e fora |
| GLPI como fase própria concluída | preservar limites entre ITSM e DCIM/IPAM |

## Maturidade e transparência

O projeto registra também lacunas atuais. Backup, restauração, CI e alertas possuem implementação versionada e validação operacional. O pacote visual sanitizado foi concluído com evidências observadas no ambiente funcional, mantendo separação clara entre resultados comprovados e evoluções planejadas. Tornar riscos e pendências explícitos faz parte da qualidade profissional da solução.

## Próximos passos

1. executar exercícios periódicos de recuperação e registrar tendências de RTO;
2. ampliar módulos opcionais de telemetria para equipamentos de rede;
3. ampliar, de forma controlada, os eventos elegíveis ao fluxo Zabbix–GLPI;
4. exercitar periodicamente o ciclo completo de abertura e recuperação de incidentes;
5. evoluir resiliência multi-nó somente quando os requisitos justificarem a complexidade.

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
