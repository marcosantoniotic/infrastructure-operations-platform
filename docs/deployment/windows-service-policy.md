# Windows: política de serviços intermitentes (opt-in)

**Candidato validado no motor e no recorte Windows nativo; aceite de implantação pendente.**
**Bloqueado para merge:** a [revisão de publicação](../testing/windows-service-policy-review-2026-11-05.md)
reproduziu gaps em elegibilidade de chamado na trigger e perda de ownership.
Os dois contratos de regressão falham no candidato atual; não aplicar.
Não aplicado no LAB01/OPS. Veja os [resultados e limites do ensaio](../testing/windows-service-policy-2026-11-05.md).
Atualização: o [recorte funcional Windows nativo](../testing/windows-service-native-2026-11-05.md)
foi executado com Agent 2 real e rollback; revisão de implantação e limites de
idioma/domínio, estabilidade e janelas completas continuam pendentes. Não
confundir essa execução com os dados sintéticos do primeiro ensaio.
Implementação separada da sincronização NetBox–Zabbix e desativada por padrão.
Não inicia serviços nem tarefas do Windows e não tenta corrigir estado remoto.

Veja a [role](../../roles/windows_service_policy/README.md) e a
[fixture inteiramente fictícia](../../scripts/fixtures/windows-service-policy.yml).
O playbook dedicado exige um único runner explicitamente escolhido; não pertence
ao provisionamento completo e não se seleciona por inferência de nome/plataforma.

## O que muda

Acrescenta 15 itens locais e dez triggers no host aprovado: snapshot WMI dos dois
serviços, métricas dependentes e contadores ativos de falhas SCM. Não cria outro
`service.discovery`, não substitui o template Windows oficial e não altera o host,
grupos, interfaces, TLS, macros ou credenciais.

| Observação | Política |
| --- | --- |
| Parado com códigos zero | Permanece visível; não é falha só por estar parado |
| Falha SCM ou erro de saída confirmado | Falha de execução; coleta posterior limpa e execução são necessárias para recuperar |
| Código 1077 (nunca iniciado) | Métrica distinta, não crash ou teste funcional aprovado |
| Transição prolongada | Aviso após o número configurado de amostras consecutivas |
| Serviço ausente/configuração divergente | Avisos próprios; sem remoção da descoberta existente |
| WMI/eventos sem dados, malformados ou estado desconhecido | Perda de observação; nunca substituir por zero saudável |
| Antigo resultado de tarefa Appraiser | Não usado como saúde contínua de InventorySvc |

O snapshot WMI usa apenas `SELECT` em Win32_Service. Os eventos usam
`eventlog.count`, fonte SCM, IDs específicos de falha, nome interno e nome de
exibição localizado escapado. Não filtrar todos os erros genéricos do `svchost`
nem tratar 7036 (mudança normal de estado) como crash. Não depender apenas de
mensagens em inglês. A leitura nativa em um Windows real deve ser validada antes
de propor implantação; amostras injetadas não comprovam esse caminho.

## Fases e guards

1. **Desativado:** nenhuma chamada à API, objeto ou arquivo de política criado
   pela role, além da inspeção de existência do ledger para impedir opt-out
   silencioso. Não desativar uma instalação retirando apenas a variável.
2. **Observe:** dry-run e criação explícita de itens, mantendo as dez novas
   triggers desabilitadas e as duas regras antigas habilitadas. Nesta fase
   observam-se dados; não é alegado teste de disparo dessas triggers no ambiente.
3. **Enforce:** aprovação de corte separada, ledger intacto, três amostras de cada
   fonte cobrindo dois intervalos, dados recentes/suportados e observações limpas.
   Habilita as substitutas e desabilita somente os dois IDs antigos confirmados.
   Isso é uma mudança explícita de regras, não uma correção de serviços.

Os IDs antigos precisam corresponder às regras descobertas do mesmo host e às
chaves exatas de estado; nome do alerta sozinho não autoriza escrita. Controles
recusam transporte ativo em texto claro, escopo/timings alterados, takeover de
chave, propriedade ambígua, edição externa, dados insuficientes e rota de
notificação desconhecida. Verificam-se também tags herdadas dos templates.

O ledger privado registra os IDs criados, estados originais e intenção da
alteração antes de atualizar status. Uma resposta perdida após commit pode ser
reconciliada pelos estados antigo/novo registrados, ou revertida por rollback.
O lock local não impede escritores em outra máquina: usar um único runner e
janela sem edição concorrente. Não há transação distribuída ou compare-and-swap
na API; uma interrupção exige conferir o journal, nunca apagar o ledger.

O journal de intenção cobre mudanças de status. Uma criação de item/trigger cuja
resposta se perca antes de registrar o ID exige inspeção manual do estado parcial:
não há adoção automática por nome/tag nem exclusão compensatória de objetos.
O rollback também valida o escopo, a propriedade e a rota de notificações; se
esses dados mudaram fora da janela, ele pode recusar a escrita até revisão.

Retirar o alerta genérico só é aceitável após validar a substituição. Eventos
antigos não são reconhecidos, suprimidos, apagados ou fechados manualmente pelo
reconciliador. Seu estado/exibição no corte deve ser conferido na versão exata,
preservando referências e distinguindo substituição da regra de recuperação real.

## Limites e recuperação

Intervalo padrão 60 s, janela de falhas 600 s, transição 600 s e ausência de dados
300 s. A transição usa `ceil(janela/intervalo)+1` amostras; não é um relógio
monotônico de segurança e pressupõe produtor respeitando o intervalo. Não
classificar uma lacuna de observação como continuidade de um estado saudável.

Uma falha de execução só recupera após três observações de execução com códigos
limpos, dados atuais e janela sem novas falhas. Apenas silêncio não recupera.
Se o serviço permanecer ocioso depois de uma falha real, o alerta pode aguardar
sua próxima execução natural; não iniciar o serviço para zerar um alarme.
Isso não equivale a validar implantação AppX ou resultado funcional do inventário.

Não habilitar SLAs de frequência de inventário sem acordar sua periodicidade.
Logs rotacionados, permissões insuficientes e variantes de localização precisam
ser tratados como limitações/observabilidade, não ausência garantida de erro.
`skip` evita replay inicial de falhas antigas nos itens novos, mas exige baseline
privado histórico antes de qualquer corte; não apaga eventos do Windows/Zabbix.

### Aceite nativo ainda necessário

Antes de autorizar aplicação no LAB01, validar em um Windows descartável sem
dados/domínio do ambiente: mesma versão de Agent 2, formato e tipos do JSON WMI,
nomes localizados, leitura dos eventos SCM, avanço do cursor `skip`, permissões,
retenção/rotação do log e recuperação da conexão ativa criptografada. A aceitação
de chaves pela API não prova que o leitor Windows as executou corretamente.

Não iniciar AppXSvc/InventorySvc no DC para obter uma execução limpa. Para testes
de crash/start/stop, usar somente serviços sintéticos numa VM Windows própria;
confirmar separadamente as leituras passivas dos dois serviços reais. Verificar
também as janelas padrão em tempo real e a carga do agente: o ensaio acelerado
não é teste de estabilidade prolongada.

## Aplicação futura, somente após aprovação

Antes de escrever no laboratório: apresentar diff final/IDs/impactos, proteger
banco e configuração Zabbix, ledger e recovered MySQL; preparar snapshot da VM
que será alterada na janela aprovada. Não desligar o DC ou reiniciar seu agente
automaticamente: os itens nativos não exigem um script de acionamento no agente.
Qualquer necessidade adicional exige aprovação própria.

Exportar estados e interferência de sincronizador/ponte. O reconciliador recusa
rotas de alertas desconhecidas e hosts/templates com elegibilidade de chamados;
não muda filtros/credenciais para contornar isso. Validar observe antes do corte
e confirmar ausência de chamados no escopo acordado.

Rollback: com mesma configuração habilitada e ledger, executar o reconciliador
dedicado com `--apply --rollback` pelo runner aprovado. Desabilita somente as
triggers novas registradas e restaura o status original das duas antigas. Não
apaga itens, dados, eventos, volumes ou templates e não restaura banco/VM.
Depois, voltar a `observe` explicitamente antes de outro corte.

Referências: [chaves Windows](https://www.zabbix.com/documentation/7.4/en/manual/config/items/itemtypes/zabbix_agent/win_keys),
[parâmetros de chaves](https://www.zabbix.com/documentation/7.4/en/manual/config/items/item/key),
[API de triggers](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/trigger/update).
