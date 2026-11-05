# Validação isolada — campo de monitoramento — 04/11/2026

Resultado: **APROVADO no escopo isolado**, com os limites abaixo.
Não é autorização nem aceite de implantação no LAB01 ou OPS.
[Evidência sanitizada da execução](../evidence/netbox-monitoring-field-20261104.json).

## Candidato e isolamento

Base Git: `5edd54052dfef3a8ef2335842078c3953deb34d5` (PR #93), mais diff local
não publicado. Hashes SHA-256 da cópia executada, normalizada para LF:

- Runtime: `2e904f8b82b15e199b306d76a5830c3f8fcd897e94732d434204eb9892db8627`.
- Harness: `4c2941cb4dd5491c74e59a28fc0e69186b4996f423cec37531e1f1f1928485b8`.

Ambos conferidos contra os arquivos locais finais; originais não foram
normalizados. A evidência histórica do PR #93 não foi sobrescrita.

VM descartável Rocky Linux 9 já autorizada, com NAT, SSH com chave de host fixada
e sem compartilhamentos/discos das VMs ativas. Bancos novos e credenciais/CA
fictícias, sem reutilizar dados de LAB01/OPS. A VM também contém containers
parados de uma verificação anterior; apenas seus IDs/estado foram comparados,
sem consultar bancos/volumes. Não houve acesso aos convidados LAB01/OPS.

O fixture verifica oito containers próprios, rede interna, nenhuma porta de
aplicação publicada e nenhum volume/rede externo. Seis objetos sintéticos
(Device/VM × Linux/Windows/ICMP), com endereços RFC 5737, permanecem desabilitados
no Zabbix. Não há ponte GLPI, notificações configuradas ou sincronizador agendado.
O wrapper encaminha chamadas para as APIs reais, limitando escritas aos IDs
criados no teste; não simula respostas da integração funcional.

## Resultado dos testes

| Verificação | Resultado observado |
| --- | --- |
| Regressão offline antiga | 19 testes aprovados |
| Perfis por plataforma offline | 21 testes aprovados |
| Campo explícito/múltiplos templates offline | 21 testes aprovados |
| Integridade de evidência histórica offline | 7 testes aprovados |
| Sintaxe Ansible e guards positivos/negativos | Aprovados; guards: ok=245, failed=0, rescued=17 (recusas esperadas) |
| Compatibilidade Compose antigo/default/VM/plataforma | Comparação byte a byte aprovada |
| Repetição da renderização Ansible | 42 tarefas, changed=0, failed=0 |
| Nova variante Compose/artefatos de serviços | Aprovados, incluindo promtool e blackbox config.check |
| Preparação do campo e repetição | Criado uma vez; mesmos IDs; objetos não preenchidos; sem token Zabbix |
| Conflito de esquema | Recusado, sem overwrite |
| Falha injetada após criação do esquema | Transação desfeita, sem sobras de campo/Choice Set |
| Matriz real de perfis | 6 hosts desabilitados, grupos/templates esperados; Windows ativo + ICMP |
| Adoção equivalente por campo | Mesmos 6 hosts/interfaces/grupos/templates; somente 6 atualizações de tags |
| Repetição após adoção | Zero escritas adicionais |
| Campo vazio, troca incompatível e downgrade | Recusados antes de escritas |
| Formulário real e opções AJAX | HTTP 200 em ambos; Linux/Windows/ICMP presentes |
| IP, identidade e dados locais | Mesmo host/interface; IP alterado; tag local preservada; sem duplicação |
| Fora do escopo/alertas | Configuração dos hosts de baseline e contagem de alertas preservadas |
| Limpeza | Oito containers próprios, rede e volumes removidos; baseline preservado |
| Desligamento da VM descartável | Confirmado; três containers anteriores continuam parados e preservados |

Os testes offline usam mocks. O ensaio funcional usa NetBox 4.6.10 com Topology
Views 4.5.1/QR Code 0.0.21 e Zabbix 7.4.13, com APIs HTTPS e validação normal de
CA/hostname. O template oficial Windows é consultado para comprovar a regra
ativa `service.discovery`, protótipos `service.info` e filtros por macros.
Isso comprova capacidade/configuração, **não coleta real em Windows**.

As 16 etapas funcionais passaram entre **21:02:34 e 21:03:04 BRT de 04/11/2026**
(00:02:34–00:03:04 UTC de 05/11). Docker 29.9.3, Compose 2.40.3,
Ansible-core 2.19.7 e Rocky 9.6. Digests/IDs das imagens executadas e logs/HTML
ficaram em pasta privada com ACL usuário/SYSTEM no E:, fora do repositório.
Tags de imagens não comprovam igualdade de digest com ambientes existentes.
O formulário foi exercitado pela view real e endpoint autenticado do Django;
não houve captura de navegador nem tela fabricada.

A VM descartável foi desligada após exportação. As onze VMs ligadas no início
continuaram ligadas. Cinco VMs adicionais fora do escopo apareceram em execução
durante a janela; não receberam comandos desta tarefa e não foram desligadas.
O inventário global final, portanto, não é idêntico ao inicial; não atribuir a
diferença ao ensaio nem tentar revertê-la. Discos da VM descartável e caches de
imagens permanecem no host de teste; a limpeza validada cobre os containers,
volumes e rede próprios da execução, não uma exclusão integral da VM.

## Intercorrência registrada

A primeira tentativa passou criação/idempotência do esquema, matriz dos seis
hosts, troca de IP com identidade/tag local preservadas, adoção por campo com
somente tags e zero escritas na repetição. Falhou na asserção de opções estáticas
no formulário. O NetBox usa APISelect e busca as opções pelo endpoint do Choice
Set; o teste foi corrigido para conferir o formulário e consultar esse endpoint
autenticado, sem remover a exigência dos três valores/rótulos. O runner removeu
somente seus oito containers, rede e volumes, preservando o baseline.

A rodada final usa cópia nova e também testa conflito de esquema sem overwrite e
rollback transacional mediante falha injetada após criação. Essa injeção é um
teste de falha controlada, não um erro real encontrado em produção.

## Reproduzir sem acesso ao laboratório

Em host Docker descartável, com dependências Ansible do projeto instaladas:

```sh
python scripts/tests/test_netbox_vm_sync.py
python scripts/tests/test_netbox_platform_mapping.py
python scripts/tests/test_netbox_monitoring_field.py
IOP_DISPOSABLE_PLATFORM_TEST=1 python scripts/ci/test-netbox-platform-mapping.py \
  --workspace /tmp/iop-monitoring-field-NEW-RUN --revision REVIEWED-REVISION
CI_ARTIFACT_DIR=/tmp/iop-monitoring-field-NEW-RUN/rendered \
  bash scripts/ci/validate-service-artifacts.sh
```

O workspace precisa ser inexistente; o runner não deve ser executado sobre
aplicações/bancos existentes. Artefatos privados podem conter tokens sintéticos
e HTML de sessão: não publique os logs/HTML brutos.

## Limites e próxima aprovação

- Nenhum agente Windows, descoberta efetiva de serviços, coleta, trigger ou
  notificação foi validado contra um Windows real. AD/DNS, IIS e SQL ficam fora.
- Não houve implantação/reaplicação completa da role em ambiente ativo. O
  ensaio cobre renderização, guards, esquema e reconciliação; não é aceite de deploy.
- A troca de perfil/template de host existente continua exigindo migração
  explícita. Não houve rollback de banco, limpeza de volumes reais ou retemplate.
- CI remoto não foi acionado; nada foi enviado ao GitHub nesta tarefa.
- Os cinco arquivos locais não relacionados foram preservados por hash. O
  validador global sinaliza IP privado em documento local preexistente do DC;
  a auditoria restrita ao candidato usa as mesmas regras e passou. Esse arquivo
  não faz parte da mudança e não deve ser incluído em futura publicação.
- [Diff conceitual, plano LAB01 e rollback](../deployment/netbox-monitoring-profile-field.md).
  Antes da aplicação: revisão, snapshot/backup e autorização da janela.

## Revisão local para publicação — sem novo deploy

Após a aplicação autorizada descrita no [registro LAB01 separado](netbox-monitoring-field-lab01-2026-11-04.md),
o candidato foi revisado para publicação. A base remota continuava no merge do
PR #93. Runtime e harness conservaram os hashes do ensaio isolado acima; não
foram repetidos acessos às APIs/hosts do LAB01 ou OPS nesta revisão.

Foram repetidos **85 testes offline**: 19 de sincronização legada, 21 de perfis,
21 do campo explícito, sete da evidência histórica, 13 da fronteira de proxy e
quatro de TLS da sonda. Todos passaram. Estrutura Ansible, governança de
credenciais, imagens fixadas, política de privilégios e referências imutáveis
das Actions também passaram conforme as políticas existentes. Isso não significa
ausência de findings já registrados no projeto.

A publicação usa lista explícita de arquivos: os cinco arquivos particulares
não relacionados, inventários privados, dumps, logs e backups ficam de fora.
O CI remoto deve ser conferido no PR; os resultados locais e históricos não
comprovam sua conclusão. Coleta Windows real continua pendente e não é
apresentada como resultado destes testes.
