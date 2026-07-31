# ADR-005: Resiliência por recuperação e standby aquecido

- Status: aceito
- Data: 2026-07-31

## Contexto

A plataforma opera em um único host. O código, os segredos protegidos e os
backups externos já permitem reconstrução, mas uma falha do host, do Traefik ou
do DNS interno interrompe o acesso. Replicação síncrona de todos os bancos e um
cluster completo aumentariam significativamente a complexidade operacional.

## Decisão

A estratégia inicial será recuperação automatizada combinada com um segundo nó
em modo standby aquecido. O segundo nó será independente do host principal e
terá capacidade para executar DNS secundário, Traefik e restaurar os serviços
críticos a partir dos backups externos.

O primeiro estágio não terá replicação ativa de MySQL ou PostgreSQL. Os dados
continuarão protegidos pelos RPOs documentados. A promoção do standby será uma
mudança controlada e verificável.

Para o acesso local, clientes receberão dois resolvedores DNS independentes. Os
nomes das aplicações apontarão para o proxy ativo. Enquanto não houver um
segundo nó validado, a troca do endereço será manual. Um endereço virtual com
Keepalived somente será adotado após validar domínio de camada 2, prevenção de
split-brain e monitoramento do processo de eleição.

Para o acesso externo, dois conectores do mesmo Cloudflare Tunnel poderão ser
executados em hosts diferentes quando ambos alcançarem uma origem saudável. O
Tunnel não substitui a contingência local nem torna os bancos altamente
disponíveis.

## Consequências

- falhas de DNS e proxy poderão ser tratadas sem reconstruir toda a plataforma;
- perda total do host continuará exigindo restauração dos serviços com estado;
- o RTO melhora sem introduzir imediatamente clusters de banco;
- DNS secundário deve manter os mesmos registros internos e ser testado;
- certificados, configuração e segredos do proxy devem ser reproduzíveis;
- promoção e retorno ao nó principal exigem runbook e evidência;
- alta disponibilidade automática só será adicionada quando justificada por
  medições de RTO, criticidade e capacidade operacional.

## Alternativas consideradas

### Dois registros A para hosts diferentes

Foi rejeitado como mecanismo de failover porque DNS round-robin não verifica a
saúde completa da aplicação e pode continuar direcionando clientes ao nó com
falha.

### Cluster ativo-ativo completo

Foi adiado. O custo de replicação de bancos, quórum, fencing e investigação de
falhas supera o benefício atual, dado o RTO de quatro horas já demonstrado.

### Somente restauração sob demanda

Continua sendo a última camada de recuperação, mas não resolve rapidamente a
falha isolada de DNS ou proxy.
