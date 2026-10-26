# Migração coordenada da API GLPI e da sonda para HTTPS

## Escopo

Recursos opt-in sobre a baseline do PR #86. Não aplicar no ambiente operacional
apenas por atualizar o código. Os testes automatizados usam banco, volumes,
credenciais e PKI descartáveis no runner GitHub; não usam backup do OPS nem VMs
do laboratório. O caminho Traefik → GLPI permanece HTTP em rede de backend
restrita; isto não é TLS ponta a ponta até o Apache.

## Variáveis de ativação — exemplo sanitizado, não um inventário utilizável

```yaml
iop_internal_api_tls_network: iop_example_api_tls
iop_internal_api_tls_aliases:
  - glpi.lab.invalid
  - zabbix.lab.invalid
iop_internal_api_ca_certificate: "{{ lookup('file', '<PRIVATE_INVENTORY>/root-ca.crt') }}"

zabbix_glpi_bridge_glpi_url: https://glpi.lab.invalid/api.php
zabbix_glpi_bridge_zabbix_url: https://zabbix.lab.invalid/api_jsonrpc.php

observability_blackbox_tls_network: "{{ iop_internal_api_tls_network }}"
observability_blackbox_private_ca_certificate: "{{ iop_internal_api_ca_certificate }}"
observability_blackbox_targets:
  # Preservar todos os outros alvos do inventário; não substituir a lista por este exemplo.
  - name: glpi
    url: https://glpi.lab.invalid/
    require_https: true
    private_ca: true
    valid_status_codes: [200, 302]
```

`private_ca` e `require_https` pertencem ao alvo, não são opções globais. Os
demais alvos preservam `fail_if_not_ssl: false` e o trust store existente.
Alvos protegidos recusam `tls_insecure: true`, HTTP e Host diferente do hostname
da URL. Não há override de SNI: o nome da URL deve ser um SAN do certificado,
resolver para o Traefik e constar dos aliases coordenados. Mantenha os nomes dos
alvos: eles identificam módulos, séries e guards. Colisões após normalização
dos nomes também são recusadas.

Os padrões das novas variáveis são vazios/desativados. A CA do blackbox é
montada em `/etc/blackbox_exporter/ca/private-ca.crt`, somente para leitura e
somente no exporter. O template não adiciona portas. A rede deve existir e ser
interna; a automação da sonda não cria nem converte uma rede existente.

Para este caminho, fornecer uma única CA raiz PEM validada. O servidor deve
enviar os intermediários necessários. A ponte e os dois endpoints da API devem
ter cadeias compatíveis com a confiança explicitamente montada. Não colocar a
chave da CA no inventário de clientes ou no contêiner.

## Perfil da CA e pré-condições

Exigir Basic Constraints crítico `CA:TRUE` e Key Usage com `keyCertSign,cRLSign`.
Validar certificado da CA e cadeia do servidor com OpenSSL estrito, validade,
hostname e, quando configurada no ambiente, revogação. Não aceitar a conexão
com `--insecure`, `verify=false` ou desativação de verificação de hostname.

```bash
openssl verify -x509_strict -check_ss_sig -CAfile root-ca.crt root-ca.crt
openssl x509 -in root-ca.crt -noout -ext basicConstraints,keyUsage
openssl verify -x509_strict -verify_hostname glpi.lab.invalid \
  -CAfile root-ca.crt server-chain.pem
```

O guard valida estrutura da política, preservação da proteção instalada, rede
interna e aliases declarados. A CA proposta é validada em arquivo temporário
antes de substituir a confiança instalada. A checagem de rede não prova que
um alias ou router esteja realmente ativo: os testes de conexão posteriores
são obrigatórios. Não modificar a CA de um ambiente para passar nesse teste
sem inventário de consumidores e plano de confiança aprovado.

## Sequência de migração

1. **Aprovar o diagnóstico do ambiente:** versões/pins, URLs, CA/SAN, redes,
   aliases reais, routers, middlewares/ACLs e consumidores. Apresentar o diff
   exato e a janela; não executar provisionamento completo.
2. **Proteger o estado:** confirmar snapshots concluídos e backups restauráveis
   do GLPI/banco, configurações da ponte, blackbox/Prometheus e proxy. Registrar
   IDs de volumes e hashes em destino privado. Preservar tokens, OAuth e estado
   de correlação; nenhuma rotação é necessária apenas para mudar o transporte.
3. **Preparar o proxy:** certificado e cadeia válidos, rede interna e aliases
   exclusivos apontando ao Traefik. Preservar routers, CA/CRL, allowlists,
   entrypoints e acessos existentes. O guard do Traefik continua bloqueando
   customizações não representadas; não contorná-lo com um deploy completo.
4. **Migrar a ponte:** URL HTTPS, rede e CA somente leitura. Executar no contêiner
   da ponte `python /usr/local/libexec/zabbix-glpi-bridge.py check-glpi-oauth`.
   Este comando só obtém um token OAuth; não configura Zabbix, não cria chamado,
   evento, acompanhamento nem arquivo de correlação. Não usar
   `validate-event-flow`, pois esse comando cria chamados sintéticos.
5. **Migrar a sonda:** preservar o nome `glpi`, alterar sua URL e ativar as opções
   por alvo. Validar configuração blackbox, Compose e promtool antes de
   recriar somente o consumidor necessário. A configuração/CA mudada exige
   reload/recriação do exporter; a role considera alterações da CA.
6. **Conferir coleta:** OAuth válido, `up` do exporter, `probe_success=1` e
   `probe_http_ssl=1` para GLPI, todos os demais alvos preservados e nenhum
   aumento de portas publicadas. Testes negativos devem falhar especificamente
   por TLS/política, não por credencial, DNS quebrado ou arquivo ausente.
7. **Só então habilitar cookies HTTPS do GLPI**, se aprovados: manter proxy CIDR
   restrito, CA de validação e os acessos direto/túnel corretos. Revalidar OAuth,
   sonda e cookies Secure/HttpOnly. Não alterar banco ou credenciais para isso.
8. Reaplicar no escopo aprovado e verificar ausência de mudanças, IDs de volumes,
   contagens e integrações. Não assumir que o teste descartável prova
   idempotência de um provisionamento completo em inventário privado.

## Restauração e modo de manutenção

Um dump pode preservar `maintenance_mode=1`. Em uma **cópia restaurada isolada**,
conferir esse estado antes de interpretar HTML como erro de senha/OAuth. Se o
teste exigir API disponível, desabilitar manutenção somente na cópia, limpar
cache conforme a versão e repetir a autenticação. Registrar estado anterior e
destino exato; nunca desabilitar manutenção da origem/OPS por causa do teste.

A ponte relata JSON inválido com indicação de verificar manutenção e routing.
Isso não identifica sozinho a causa: HTML pode vir também do proxy, redirect,
SSO ou página de erro. O CI restaura um backup de seu GLPI recém-criado em um
banco distinto e verifica que o ajuste de manutenção não altera o banco origem.
Não é uma restauração do backup real do OPS.

## Rollback controlado

Os guards bloqueiam remoção silenciosa de alvos protegidos, CA e rede. Não há
flag genérica para ignorá-los. Para rollback aprovado, restaurar o conjunto de
configurações pré-mudança a partir dos backups, sob revisão e fora de um deploy
automático que tentaria sobrepor esse estado. Manter o estado desejado privado
coerente para não reaplicar versões contraditórias depois.

Se for necessário voltar a API/sonda para HTTP, **primeiro** restaurar o estado
anterior dos cookies HTTPS e do contexto de proxy do GLPI; depois restaurar em
conjunto URLs, módulos e rede/CA dos consumidores. Não tentar usar OAuth HTTP
enquanto o GLPI exige HTTPS. Preferir reverter o router/certificado mantendo
HTTPS sempre que possível. Não remover redes em uso nem CA de outros clientes.

Validar continuidade dos demais alvos e retomada da sonda GLPI; registrar a
lacuna de coleta durante a recriação. Esse desenho de uma única instância não
promete migração sem interrupção. Não fazer `down -v`, prune ou restauração do
banco para uma mudança apenas de transporte. Preservar volumes e credenciais.

## Evidências e limites

O job **Isolated GLPI API and blackbox HTTPS migration** usa templates reais,
GLPI/MariaDB, Traefik e blackbox fixados no projeto. Gera PKI nova, verifica CA
sem Key Usage como controle negativo, testa OAuth sem chamados, CA errada,
hostname errado, HTTP obrigatório, downgrade de redirect, coleta HTTP legada,
guards Ansible, cookies, reaplicação e rollback em ambiente descartável.

TLS de backend, publicação DNS real, ACLs, CRL/renovação do ambiente, todos os
consumidores privados e failover continuam fora dessa prova. Antes de qualquer
mudança no LAB01, apresentar diagnóstico/diff/impactos, snapshots, backups e
rollback para aprovação. OPS não faz parte da execução deste trabalho.
