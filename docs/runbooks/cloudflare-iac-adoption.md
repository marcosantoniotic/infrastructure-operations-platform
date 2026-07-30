# Adoção segura de IaC para Cloudflare

Este runbook define como incorporar DNS, Tunnel e Access existentes ao Terraform
sem modificar a borda operacional durante a fase de descoberta.

## Princípios

- importar, nunca recriar, os recursos atuais;
- executar primeiro contra um inventário sanitizado;
- separar configuração pública, variáveis privadas e estado;
- revisar todo plano antes de qualquer aplicação;
- manter uma rota de acesso local que não dependa da Cloudflare;
- preservar exportação e evidências antes de cada lote de importação.

## Fronteira de dados

| Conteúdo | Destino |
|---|---|
| módulos, variáveis e documentação sem valores reais | GitHub |
| token da API | gerenciador de segredos ou variável de ambiente |
| IDs de conta, zona, túnel e aplicações | variáveis privadas fora do Git |
| domínios e endereços do ambiente | arquivo local ignorado |
| estado e planos do Terraform | backend privado criptografado |
| evidências sanitizadas de `plan` | artefato temporário da CI |

O token não deve ser declarado em arquivos `.tf`, `.tfvars`, comandos gravados
no histórico ou saídas de CI. Ele deve ter somente as permissões necessárias ao
lote que está sendo administrado.

## Fases de adoção

### 1. Descoberta somente leitura

1. Criar um token temporário de leitura com escopo mínimo.
2. Enumerar DNS, Tunnel, aplicações e políticas Access.
3. Registrar apenas nomes lógicos e dependências no inventário sanitizado.
4. Exportar uma evidência privada para rollback.
5. Revogar o token temporário após a descoberta.

Resultado esperado: nenhum recurso alterado.

### 2. Preparação do Terraform

1. Fixar versões compatíveis do Terraform e do provider Cloudflare.
2. Configurar backend remoto privado, criptografado e com versionamento.
3. Criar variáveis para IDs e nomes específicos do ambiente.
4. Executar `terraform fmt` e `terraform validate`.
5. Confirmar que `.tfstate`, planos e arquivos reais de variáveis estão
   ignorados pelo Git.

Resultado esperado: configuração válida, ainda sem recursos sob gerenciamento.

### 3. Importação incremental

Importar um domínio funcional por vez, nesta ordem:

1. um registro DNS de baixa criticidade;
2. demais registros DNS da plataforma;
3. configuração e rotas do Tunnel;
4. aplicações Access;
5. políticas Access.

Para cada recurso:

1. reproduzir no código exatamente a configuração existente;
2. executar `terraform import`;
3. executar `terraform plan -detailed-exitcode`;
4. aceitar somente um plano sem alterações;
5. investigar qualquer diferença antes de avançar.

Resultado esperado: o primeiro plano após importação apresenta zero mudanças.

### 4. Operação controlada

1. Abrir pull request para qualquer mudança.
2. Executar na CI somente `fmt`, `validate` e `plan`.
3. Sanitizar o plano antes de anexá-lo como evidência.
4. Aprovar a janela e validar o acesso local de contingência.
5. Aplicar manualmente com identidade humana auditável.
6. Validar DNS, resposta do Tunnel e desafio do Access.
7. Registrar resultado e rollback na mudança.

## Critérios de parada

Interromper a adoção se:

- o plano propuser destruir ou substituir recurso existente;
- houver diferença sem causa conhecida;
- o backend de estado não estiver protegido;
- a rota local de contingência falhar;
- o token possuir permissões maiores que as necessárias;
- o rollback não estiver documentado.

## Rollback

Uma importação não altera o recurso remoto. Se a modelagem estiver incorreta,
remover somente o vínculo desse recurso do estado e corrigir o código. Não
excluir o recurso na Cloudflare para corrigir um problema de importação.

Após uma aplicação real, o rollback deve usar uma mudança revisada que restaure
a configuração anterior. Alterações emergenciais pelo painel devem ser
imediatamente reconciliadas no código e no estado.

## Definição de pronto para implementação

- backend privado selecionado e testado;
- token de automação de privilégio mínimo armazenado fora do Git;
- inventário dos recursos atuais conferido;
- configuração inicial revisada por pull request;
- plano pós-importação sem mudanças;
- acesso externo e acesso local validados;
- procedimento de rollback testado em recurso não crítico.

