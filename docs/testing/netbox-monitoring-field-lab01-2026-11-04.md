# Aplicação LAB01 — perfil de monitoramento — 04/11/2026

Resultado: **APROVADO no escopo autorizado**. Aplicação posterior ao
[ensaio isolado](netbox-monitoring-field-2026-11-04.md), sem publicação no GitHub.
Base PR #93 mais candidato local; runtime SHA-256 (LF):
`2e904f8b82b15e199b306d76a5830c3f8fcd897e94732d434204eb9892db8627`.

## Escopo e proteção

Autorização explícita para a janela controlada de controller e plataforma,
incluindo pausa temporária do sincronizador e da ponte de chamados.
Os convidados standby, roteadores e DC não receberam comandos de parada/configuração.
OPS não foi acessado nem alterado.

Backups mínimos anteriores de bancos/configurações da plataforma e de
inventário/PKI do controller foram copiados para destino privado no E: e
verificados por tamanho, SHA-256 e leitura dos membros. Um backup adicional
protegeu a role e suas fontes privadas. Dois snapshots frios foram criados,
uma VM por vez, após parada graciosa; sem desligamento forçado ou exclusão de
snapshots existentes. Os bancos foram lidos/verificados, não restaurados neste
ensaio. Backup mínimo online não equivale a uma restauração integral testada.

Após a aplicação, novos backups mínimos da plataforma e do controller/PKI e
uma cópia das fontes atualizadas também foram verificados; os anteriores foram mantidos.

Os artefatos privados têm ACL usuário/SYSTEM e não são criptografados.
Nenhum segredo, dump, chave privada ou topologia foi incluído no candidato público.

## Aplicado

- Campo `monitoring_profile`, rótulo **Perfil de monitoramento**, seleção única
  Linux/Windows/ICMP, visível/editável, sem valor padrão, em Device e VM.
- Linux nos dois servidores já preparados com agente ativo; ICMP nos três
  objetos que já usavam esse perfil. Cinco valores explícitos, sem inferência
  pelo nome ou plataforma e sem mudar os IPs ou o campo de vínculo do host.
- Catálogo Windows preparado com grupo vazio e template oficial ativo + ICMP.
  Nenhum host existente foi migrado para Windows, nem agente instalado no DC.
- Cinco atualizações exclusivamente da tag de origem nos mesmos hosts Zabbix.
- Role e override privado do controller alinhados ao candidato, preservando
  ajustes locais, Vault, caminho e bytes da CA, mapas antigos e escopo existente.
- Somente runtime/Compose do sincronizador foram substituídos e somente esse
  container foi recriado. Não houve provisionamento completo.

## Evidências verificadas

| Verificação | Resultado |
| --- | --- |
| Sintaxe/lista de tarefas e render com inventário real | Aprovadas; repetição changed=0 |
| Credencial, CA e transporte | Mesmo segredo por hash; mesmos bytes da CA; TLS não relaxado |
| Compose normalizado | Mesmas redes, portas, volumes, imagem e comando; somente ambiente de seleção/perfis atualizado |
| Campo | Preparação explícita repetida com mesmos IDs; três escolhas válidas e inválida recusada |
| Dry-run controlado | Cinco alterações planejadas, zero escritas |
| Aplicação protegida por IDs/whitelist | Cinco host.update, somente tags |
| Repetição controlada | Zero alterações planejadas/escritas |
| Proteção de origem | Downgrade para plataforma recusado antes de escritas |
| Identidade e preservação | Mesmos sete hosts, interfaces, templates, macros, TLS e tags locais; sem duplicação |
| NetBox | Somente cinco valores de campo alterados; demais objetos/dados preservados |
| Coleta | Dois agentes Linux ativos com dados recentes; três hosts respondendo ICMP |
| Operação automática | Cinco ciclos recentes sem alterações; reaplicação Compose sem recriação |
| Serviços | 23 containers em execução e saudáveis nas verificações configuradas |
| Prometheus/sondas | 14/14 alvos disponíveis; oito probe_success=1 |
| Chamados/alertas | Contagem de chamados permaneceu em três; nenhum alerta enviado na janela observada |
| Acesso direto HTTPS | Sete ferramentas aprovadas com TLS/revogação do Windows habilitados; 401 do dashboard protegido é esperado |
| Túnel | Porta 8443 sem listener; não exercitado nem criado/alterado; configuração anterior preservada |
| Limpeza da janela | Somente manutenção e container temporário próprios removidos; ponte e sincronizador retomados |

Horários: janela registrada a partir de **21:09 BRT de 04/11/2026**
(00:09 UTC de 05/11). Validação dos serviços após retomada às 21:26 BRT.
Logs, IDs, ledger, recibos e hashes completos permanecem privados no destino
de backup, fora do repositório. As VMs inicialmente ligadas fora do escopo
continuaram em execução.

## Intercorrências e limites

- A conferência inicial da manutenção teve um erro no auxiliar de seleção da
  fase; a manutenção já criada foi identificada por ID e reutilizada, sem
  duplicação. Sua ativação foi confirmada antes das paradas.
- A comparação do Compose distingue valores explícitos e os herdados do
  env_file; os mapas JSON foram comparados semanticamente, sem tratar espaços
  de serialização como mudança de política. Nenhum critério funcional foi removido.
- A ordem dos mounts retornada pelo Docker mudou após o reboot. A comparação
  final conferiu todos os atributos, independentemente da ordem; nenhuma imagem,
  porta ou origem/destino de volume foi trocada.
- Com a ponte intencionalmente pausada, seu alvo de métricas ficou indisponível
  (13/14). Após retomada, a validação exigiu novamente 14/14.
- O aviso esperado de reboot do controller recuperou naturalmente, ainda sob
  manutenção; não se alteraram triggers, limites, relógio ou dados para ocultá-lo.
- Nenhum teste de coleta/LLD/alertas em Windows real ocorreu. O DC continua em
  ICMP até preparação autorizada do agente/canal. AD/DNS, IIS e SQL não foram adicionados.
- Um alerta antigo do host padrão Zabbix não constitui aceite geral do ambiente
  e permanece fora desta alteração.

## Operação e reversão

No NetBox: Dispositivo/VM → Editar → Campos Personalizados →
**Perfil de monitoramento**. A seleção expressa como o objeto será monitorado,
não necessariamente seu sistema operacional. Um Windows ainda pode usar ICMP.

Não troque o perfil de host existente esperando retemplate automático. Essa
conversão requer migração explícita e revisão para preservar histórico e dados
locais. Campo vazio/desconhecido em objeto elegível bloqueia a reconciliação.

Em falha, congele somente a reconciliação pelo procedimento aprovado e preserve
o esquema/valores/tags aditivos. Não execute o sincronizador antigo sobre hosts
adotados, não restaure bancos ou exclua volumes para reverter arquivos. Use o
ledger/recibos privados para qualquer reversão seletiva previamente revisada.
O [plano genérico](../deployment/netbox-monitoring-profile-field.md) continua
descrevendo os guards e limites. OPS não foi acessado nem alterado.
