# Consolidação da automação de validação

Esta revisão incorpora partes reutilizáveis dos ajustes do laboratório sem
executar deploy, reiniciar VMs ou alterar o ambiente operacional. A validação
de código não substitui uma reprodução completa do laboratório em ambiente limpo.

## O que a baseline passa a representar

| Área | Comportamento |
|---|---|
| MySQL Zabbix | Volume externo opcional, previamente existente; bloqueio se o inventário omitir ou trocar a seleção externa instalada |
| Cookies | Opções explícitas para GLPI, NetBox e frontend nginx do Zabbix, desativadas por padrão |
| PHP GLPI | Arquivo complementar de hardening; não substitui atualização do binário PHP nem publica imagens privadas |
| APIs internas | Rede TLS opcional, CA pública montada somente para leitura e contexto HTTPS restrito ao proxy autorizado |
| Rede VMware | Segmento de serviços opcional para controller, plataforma e standby; recovery não é migrado |
| Runners | Staging dos overrides privados com nomes válidos; autenticação SSH exige host keys previamente verificadas |
| Observabilidade | Contagem de falhas HTTP retorna zero quando todas as sondagens existentes estão saudáveis |

Os arquivos privados em `.validation/ansible/group_vars/all/*.yml` e `*.yaml`
são transferidos pelos runners de serviço, exceto `main` e `vault`, que mantêm
seu fluxo próprio. Links simbólicos não são aceitos como arquivos de override.
Os filtros de segurança são enviados junto com os playbooks. Falha de cópia
interrompe a execução; arquivos remotos adicionais não são apagados.

Antes de executar os runners, conferir e cadastrar as chaves SSH do controller
no cliente e dos alvos no controller por canal confiável. Não desativar a
verificação de host key para contornar esse requisito.

## Variáveis opt-in

- `zabbix_mysql_external_volume`: identidade privada do volume recuperado;
  vazio mantém o armazenamento legado somente onde ainda não há volume externo.
- `glpi_php_security_hardening`, `glpi_https_cookie_hardening`,
  `glpi_trusted_proxy_subnet` e `glpi_tls_ca_file`: hardening GLPI e validação TLS.
- `netbox_secure_cookies`: cookies CSRF e sessão Secure.
- `zabbix_trusted_https_proxy_enabled` e `zabbix_trusted_https_proxy_subnet`:
  contexto HTTPS para o frontend Alpine nginx compatível.
- `iop_internal_api_tls_network`, `iop_internal_api_tls_aliases` e
  `iop_internal_api_ca_certificate`: rede interna, aliases do proxy e certificado
  público da CA. Nunca colocar a chave privada nessa variável.

Revisar as URLs das integrações antes de habilitar TLS. Os clientes devem usar
HTTPS com hostname/SNI correspondente ao certificado e CA confiável. Não usar
`verify=false`, `--insecure` ou publicação adicional de portas para essa migração.

Os guards leem as definições instaladas antes de mudanças e recusam a remoção
silenciosa das proteções reconhecidas. Mudanças de conteúdo nos arquivos de
cookies/proxy recriam somente o frontend correspondente, sem dependências,
para atualizar os bind mounts; não recriam bancos para essa finalidade.

## Limites e particularidades privadas

O desenho completo de DNS, portas diretas, CRL, sidecar de PKI e entrypoints
particulares ainda exige reconciliação específica. O guard do Traefik interrompe
um deploy se encontrar serviços ou entrypoints extras não representados pelo
template. Esse bloqueio é intencional: não remover customizações para fazê-lo passar.

Não se publicam nomes/IPs reais, IDs de segmentos, nomes de volumes recuperados,
credenciais, certificados privados, pins de imagens derivadas ou evidências
brutas. Guias visuais e fichas pessoais continuam fora do repositório.

## Verificação e próximo deploy

Os testes de CI usam fixtures descartáveis: filtros de CIDR/volumes, staging
PowerShell sem rede, configuração Ruby sem VMs, validação de entrada shell,
guards Ansible contra configurações instaladas e renderização Compose com
opções desligadas/ligadas. Esses testes não executam a migração real nem
comprovam compatibilidade de todas as imagens privadas.

Para um futuro deploy autorizado: confirmar snapshots concluídos e backup
restaurável, comparar inventário privado com a configuração instalada, validar
o volume existente e os pins de imagens, testar as mudanças em isolamento e
revalidar os acessos direto/túnel e APIs após cada serviço. Não executar todos
os runners apenas para consultar o estado do laboratório.
