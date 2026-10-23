# Revisão operacional do laboratório — 23/10/2026

## Escopo e estado da publicação

Este documento consolida resultados do laboratório corporativo posteriores à
release v1.1.3. O laboratório é um ambiente próprio, independente do ambiente
operacional: não é uma réplica continuamente sincronizada nem um cluster de
produção. Dados de acesso, nomes reais, endereços, identificadores de volumes,
chaves, exports e logs permanecem no inventário privado.

**Estado validado não equivale a funcionalidade publicada.** Esta atualização é
documental. Ajustes recentes de roles, runners, imagens derivadas e inventários
continuam locais, pendentes de revisão e publicação próprias. Executar a
baseline pública não reproduz automaticamente todas as configurações abaixo.
Não executar um provisionamento completo apenas para testar um acesso.

## O que foi consolidado

| Área | Resultado observado | Limite |
|---|---|---|
| Redes | VMs de uso diário na rede de serviços, com caminho administrativo preservado | Recovery mantém segmentação própria/transicional; sondagens não comprovam failover |
| Saída do laboratório | Bridge dedicado para o uplink autorizado dos roteadores virtuais | Nenhuma alteração na rede física real; a VLAN de transporte não pertence ao projeto |
| Inventário | Site corporativo independente no NetBox do laboratório, com VMs, redes e relacionamentos | Importar não autoriza remover dados da origem nem tratar redes planejadas como implantadas |
| Acessos | HTTPS direto pelo DNS interno e HTTPS por túnel SSH | Ambos dependem de roteamento, listeners e confiança de certificados corretos |
| Recuperação | MySQL do Zabbix recuperado em volume separado e validado antes de uso | Últimas transações não legíveis do redo não podem ser garantidas |
| Runtime PHP | PHP atualizado no GLPI e no frontend Zabbix sem mudar suas versões de aplicação | Imagem derivada e pins do laboratório não constituem uma release pública |
| PKI | CA corrigida para validação estrita, CRL renovável e confiança nos clientes testados | Outros computadores/perfis exigem instalação controlada da CA pública |
| Cookies | Secure no GLPI, Zabbix e cookies CSRF/sessão do NetBox | Não representa auditoria completa de segurança; SameSite do Zabbix não foi ampliado |

## Inventário e migração sem misturar ambientes

O site do laboratório representa a infraestrutura corporativa como um todo;
projetos individuais são organizados por cluster, papel e tags. O domínio AD
é metadado do ambiente, não o identificador do site.

A cópia de uma base existente exige escopo aprovado, snapshot e backup do
destino. Criar identidades independentes e remapear relacionamentos, em vez de
copiar IDs de banco. Contas, credenciais e tokens não devem migrar junto com o
inventário. Mídias, templates e notas históricas exigem revisão específica;
preservar datas e proveniência, sem confundir notas importadas com o change log
completo da origem.

Validar recursos das VMs, interfaces, IPs primários, VLANs, prefixos e grupos
VRRP contra as configurações observadas. Redes futuras permanecem planejadas
ou reservadas. Um uplink que dá acesso à rede real deve ficar associado ao
domínio administrativo correto, não ser convertido em rede interna do projeto.

A separação de inventários não autoriza exclusão do site antigo: concluir
backup, arquivo histórico, revisão de consumidores externos e aprovação da
mudança antes de remover qualquer cadastro da origem.

## Segurança e recuperação

As mudanças de aplicação foram precedidas por snapshots com conclusão
confirmada e backups copiados para destino privado externo à VM, com hashes
conferidos. Snapshot solicitado ou arquivo de memória existente não comprovam
que a captura terminou. Cópia fora da VM também não equivale, sozinha, a offsite.

O volume original do MySQL foi preservado. A recuperação ocorreu em cópias
isoladas, seguida de exportação lógica e importação em banco novo no modo
normal. Tabelas, contagens, checksums e reinicialização foram verificados antes
da troca. O nome do volume recuperado foi fixado no inventário privado; a
automação local foi protegida contra retorno silencioso ao volume anterior.
Consulte o [procedimento de recuperação](../runbooks/mysql-recovery.md).

No TLS, a CA existente não satisfazia a validação estrita do cliente Python.
A correção das extensões de uso da chave preservou a chave de assinatura e a
validade dos certificados dos serviços. Isso não é rotação da chave da CA.
Foram testadas cadeia, hostname e revogação, sem contornar a verificação.
Consulte [HTTPS e cookies](../runbooks/tls-and-secure-cookies.md).

## Verificação final registrada

Em 23/10/2026, após as correções de cookies, a rodada registrou:

- 23 contêineres operacionais ativos, nenhum unhealthy;
- 14 targets Prometheus up e 8 sondagens HTTP/DNS com probe_success=1;
- sete portais acessíveis diretamente e sete pelo túnel, com TLS e revogação
  ativos no cliente Windows;
- Secure/HttpOnly nos cookies observados do Zabbix e no cookie CSRF do NetBox
  pelos dois caminhos;
- login real do NetBox por HTTPS com CSRF válido, sessão Secure e logout;
- leitura autenticada no GLPI e Zabbix e dry-run da sincronização
  NetBox→Zabbix, sem criação de chamados ou eventos sintéticos;
- somente os frontends NetBox/Zabbix recriados na última rodada, com imagens,
  volumes e contêineres de banco preservados.

Esses números são uma observação pontual, não monitoramento contínuo nem um
SLA. Testes de API e páginas não substituem todas as jornadas visuais no
gerenciador de conexões. Não foi realizado novo teste de failover dos
roteadores nessa rodada. Os arquivos de evidência bruta não são públicos.

## Próximas consolidações

- revisar e publicar separadamente a automação local, mantendo opções novas
  desativadas nos inventários não aprovados;
- reconciliar integralmente as customizações de DNS, Traefik, CRL e portas
  antes de uma convergência completa do laboratório;
- repetir reprodução em ambiente limpo e os testes adequados ao escopo dessa
  futura publicação;
- concluir a revisão dos consumidores antes de qualquer exclusão na origem;
- tratar segmentação definitiva de recovery, failover e TLS até os backends
  como decisões e validações específicas, não como resultados já comprovados.
