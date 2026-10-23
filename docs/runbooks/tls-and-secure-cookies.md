# HTTPS, confiança da CA, CRL e cookies Secure

## Objetivo e limites

Manter acesso direto e por túnel SSH sem relaxar a validação TLS, sem expor
bancos e sem interromper integrações. Este procedimento consolida a validação
local descrita na [revisão do laboratório](../testing/laboratory-operations-update.md);
não é um comando de implantação da baseline pública.

TLS termina no Traefik no desenho validado. O último trecho até os backends
Docker permanece HTTP. Não descrever esse caminho como criptografia ponta a
ponta; confiar em uma rede de proxy é uma fronteira de segurança explícita.

## 1. Preservar e inventariar

1. Confirmar ambiente e hosts, excluindo o ambiente operacional do escopo.
2. Inventariar nomes DNS/SAN, portas, túneis, origens CSRF, CA, CRL e clientes
   que consomem APIs. Não listar valores de segredos em relatórios públicos.
3. Confirmar conclusão dos snapshots; copiar configurações e dumps para
   destino privado com espaço, permissões restritas e checksums.
4. Planejar rollback conjunto de cookies, contexto HTTPS e URLs dos clientes.
   Não restaurar só uma dessas partes deixando a API inconsistente.

## 2. Validar a cadeia, não contornar erros

- Verificar validade, SAN/hostname, Basic Constraints e Key Usage da CA.
  Uma CA de assinatura precisa dos usos apropriados de assinatura de
  certificados e CRLs, com extensões coerentes.
- Testar com o runtime real do cliente. A validação estrita do Python pode
  rejeitar uma CA que outro cliente aceita.
- Não usar `verify=False`, `--insecure`, desabilitação de verificação de hostname
  ou remoção de flags estritas para fazer o teste passar.
- Corrigir a CA em uma etapa própria, com backup e distribuição controlada da
  confiança. Reemitir o certificado da CA com a mesma chave não é rotação de
  chave; preservar certificados dependentes exige testes explícitos.
- Distribuir somente o certificado público aos clientes; a chave da CA fica
  no emissor e em backups privados autorizados.

Usar os nomes de serviço que constam no SAN, inclusive por túnel. Abrir pelo IP
ou por outro nome não corrige um erro de hostname do certificado.

## 3. Preservar os dois caminhos

| Caminho | Requisitos |
|---|---|
| Direto | DNS interno, rota/ACL aprovada, listener HTTPS e CA confiável |
| Túnel SSH | Forward local ativo, nome/SNI correto e CA confiável |
| Integração interna | URL HTTPS, resolução interna do nome do certificado e CA no processo cliente |

Não é necessário fechar um túnel para usar o acesso direto por outro endereço.
DNS não cria roteamento e não abre portas por si só. Não trocar o DNS global
do cliente ou relaxar firewall de outras redes como solução genérica.

Para integrações, testar uma rede Docker interna dedicada, sem novas portas
publicadas. Um cabeçalho HTTPS não cifra uma chamada HTTP: trocar o transporte
real do cliente antes de exigir HTTPS na aplicação.

## 4. Configurar cookies e contexto do proxy

- **GLPI:** Secure exige contexto HTTPS também para a API. O ini precisa ser
  legível pelo usuário efetivo do contêiner. Ativar um ini antes ilegível pode
  mudar memória, uploads e outras opções; preferir um arquivo específico para
  o ajuste aprovado. Preservar HttpOnly e SameSite adequados à aplicação.
- **Zabbix:** a aplicação usa o contexto HTTPS recebido pelo PHP para definir
  Secure. No frontend nginx, conferir o parâmetro FastCGI e aceitar
  X-Forwarded-Proto somente da origem de proxy explicitamente confiada.
  Não alterar o código PHP da aplicação só para acrescentar o atributo.
- **NetBox:** configurar `CSRF_COOKIE_SECURE` e `SESSION_COOKIE_SECURE` no
  frontend. Manter origens CSRF, plugins, segredos e nomes de cookies. Não
  habilitar redirecionamento global sem validar o contexto do proxy, evitando
  loops e quebra de healthchecks.

Não aceitar cabeçalhos de proxy de qualquer origem. Após habilitar Secure,
login em fallback HTTP não funciona: usar HTTPS direto ou HTTPS pelo túnel.
Renovar cookies antigos com logout/login, sem apagar sessões de terceiros
ou trocar senhas desnecessariamente.

## 5. Renovar e verificar a CRL

Testar assinatura, validade, ponto de distribuição e acesso dos clientes à
CRL. Manter renovação agendada, atualização atômica e observação do resultado
do serviço. Um timer ativo sozinho não comprova que a última renovação passou.
Prever repetição controlada quando a VM de destino estiver temporariamente
indisponível; não confundir falha de entrega com necessidade de trocar a CA.

## 6. Critérios de aceite

- validar em isolamento antes de recriar apenas os frontends necessários;
- conferir Set-Cookie sem registrar valores de sessão;
- testar Secure/HttpOnly diretamente e pelo túnel;
- testar login e CSRF do NetBox com a identidade já configurada, sem tentativas
  repetidas ou reset automático se a credencial não autenticar;
- autenticar e ler a API com os clientes reais, sem criar incidentes de teste;
- verificar que um cabeçalho HTTPS de origem não confiável não é aceito;
- verificar que certificado/hostname incorreto é rejeitado;
- confirmar targets, sondagens, serviços, volumes e caminho de rollback;
- registrar limites: a correção Secure do Zabbix não acrescentou SameSite
  explícito ao cookie gerenciado pela aplicação.
