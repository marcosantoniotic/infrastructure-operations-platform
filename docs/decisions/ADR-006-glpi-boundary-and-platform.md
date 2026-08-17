# ADR-006: Limites e baseline da plataforma GLPI

- Status: aceito
- Data: 2026-08-16

## Contexto

A plataforma já usa NetBox como fonte de verdade de infraestrutura, Zabbix para
estado e eventos, e Prometheus/Grafana para métricas e visualização. A inclusão
de um service desk é necessária, mas uma segunda autoridade sobre ativos
técnicos criaria divergência de serial, endereço, interface, rack e cabeamento.

O GLPI também introduz estado persistente, anexos, uma chave criptográfica,
integrações de e-mail e API, além de migrações de schema. Esses elementos
exigem uma fronteira explícita e o mesmo contrato de backup, acesso e validação
dos módulos existentes.

## Decisão

O GLPI será a autoridade para chamados, SLA, atendimento, catálogo, contratos,
garantias e vínculos de suporte. NetBox continuará sendo a autoridade para
DCIM/IPAM e relações físicas. Zabbix continuará sendo a autoridade sobre
problemas e recuperações; ele abrirá ou atualizará tickets usando uma integração
idempotente correlacionada pelo ID do evento.

A baseline inicial usará a imagem oficial `glpi/glpi:11.0.8` e MariaDB
`11.8.8` em instância exclusiva. Somente o container da aplicação ingressará na
rede do Traefik. O banco ficará em rede Docker interna, sem porta publicada.

Aplicação e banco terão versões fixadas. Atualizações, migrações de schema e
rollback serão operações explícitas, precedidas por backup. A persistência e o
backup incluirão banco, configuração, arquivos, logs, marketplace e a chave
`glpicrypt.key`. O objetivo inicial será RPO de 24 horas e RTO de 4 horas.

A rota externa opcional será protegida por Cloudflare Access, mas uma rota
interna e uma porta restrita ao loopback preservarão acesso independente da
Internet.

## Consequências

- o atendimento ganha contexto técnico sem criar duas fontes de verdade;
- integração e correlação exigem componente, credencial e testes próprios;
- banco e dados do GLPI entram no ciclo de backup e recuperação isolada;
- uma migração real de ambiente permanece procedimento operacional privado;
- o módulo pode ser implantado e removido sem alterar NetBox ou Zabbix;
- atualizações levam mais etapas, porém reinícios comuns não migram schema de
  forma implícita;
- indisponibilidade do GLPI não impede o monitoramento técnico nem a recuperação
  da plataforma.

## Alternativas consideradas

### Usar o inventário do GLPI como autoridade técnica

Foi rejeitado porque duplicaria objetos já mantidos no NetBox e permitiria
divergência em dados essenciais de rede e datacenter.

### Compartilhar o banco do Zabbix

Foi rejeitado para evitar acoplamento de ciclo de vida, privilégios, backup e
falhas. O GLPI terá banco e usuário dedicados.

### Atualizar automaticamente ao iniciar o container

Foi rejeitado porque um reinício não deve alterar schema sem ponto de
recuperação, janela aprovada e evidência de compatibilidade.

### Importar todo o ambiente legado no projeto público

Foi rejeitado porque dados reais, identificadores, contratos e histórico não
pertencem ao repositório. O projeto fornecerá somente automação genérica e
runbooks sanitizados.
