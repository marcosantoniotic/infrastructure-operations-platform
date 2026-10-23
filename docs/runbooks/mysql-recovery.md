# Recuperação controlada do MySQL do Zabbix

## Quando usar

Incidente de banco com reinicialização repetida ou corrupção após interrupção
de alimentação. É um procedimento de recuperação, não manutenção rotineira.
A [revisão do laboratório](../testing/laboratory-operations-update.md) registra
o caso validado; identidades e artefatos reais permanecem privados.

## Preservar antes de tentar recuperar

1. Confirmar escopo, espaço no host/VM e consumidores do banco.
2. Registrar imagens/digests, nomes dos volumes, configurações e estado dos
   contêineres sem imprimir variáveis secretas.
3. Confirmar snapshot e criar cópia fria do volume original, com banco parado
   de forma controlada. Verificar leitura do arquivo e hash externo à VM.
4. Preservar o volume original sem reutilizá-lo em tentativas sucessivas.
   Não apagar redo, não executar prune e não inicializar outro banco sobre ele.

## Trabalhar em isolamento

Usar a mesma versão do motor, volumes independentes e rede sem portas de host,
sem cron, alertas ou integrações que escrevam no ambiente real. Fazer cada
tentativa em uma cópia apropriada, com logs privados e critérios de parada.

Um modo de recuperação forçada pode permitir extração lógica de dados, mas não
transforma o banco em íntegro. Usar o menor nível necessário e nunca mantê-lo
como operação normal. Não assumir que todas as transações recentes são
recuperáveis só porque o processo iniciou.

## Reconstruir e comparar

Exportar os dados legíveis, inicializar um volume novo no modo normal e
importar o dump. Antes da troca, verificar:

- término e leitura dos arquivos de backup;
- schema e presença das tabelas esperadas;
- contagens e checksums, onde aplicáveis, comparados com a origem recuperável;
- verificações de tabelas e ausência de erros relevantes;
- reinicialização do banco novo sem recovery forçado;
- frontend, API autenticada e consumidores, sem eventos sintéticos desnecessários.

Preservar anexos/arquivos e configurações correlatas quando fizerem parte do
conjunto de recuperação. Senhas e tokens não podem aparecer no relatório.

## Troca e proteção contra regressão

Trocar somente a referência do serviço aprovado para o volume novo. Preservar
o volume original, o dump e os artefatos de comparação. Confirmar o volume
efetivamente montado, não apenas o nome exibido no arquivo Compose.

Registrar a seleção no inventário privado e testar a automação que a consome.
Ela deve falhar se o volume recuperado estiver ausente ou se uma convergência
tentasse substituir silenciosamente sua identidade. Não criar um volume vazio
como fallback para uma seleção externa que não existe.

Esse bloqueio passou pela [consolidação da automação de validação](../testing/validation-automation-consolidation.md).
A identidade real do volume permanece no inventário privado; sua presença deve
ser verificada antes de qualquer novo deploy.

## Encerramento e rollback

Validar Zabbix, integrações, coleta, backup novo e estado dos serviços. Documentar
o limite da recuperação das últimas transações. Copiar os artefatos para destino
privado protegido, sem confundir cópia externa à VM com offsite.

Após a retomada de escritas, voltar ao volume anterior pode perder dados novos.
O plano de rollback precisa considerar essa divergência; não reverter snapshot
ou volume automaticamente. Encerrar motores de teste, mas remover evidências e
volumes preservados somente após aprovação e política de retenção aplicável.
