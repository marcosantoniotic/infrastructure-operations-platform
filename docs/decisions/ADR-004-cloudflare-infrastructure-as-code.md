# ADR-004: Cloudflare gerenciada como código

- Status: aceito
- Data: 2026-07-30

## Contexto

DNS público, Cloudflare Tunnel e Cloudflare Access fazem parte do caminho crítico
de acesso à plataforma. Hoje esses componentes existem e funcionam, portanto uma
adoção de Infrastructure as Code não pode recriá-los nem interromper o tráfego.

Também é necessário manter o repositório público sem tokens, identificadores
reais, domínios privados ou conteúdo do estado do Terraform.

## Decisão

Terraform será a ferramenta declarativa para os recursos Cloudflare. A adoção
será incremental e começará por descoberta, modelagem e importação dos recursos
existentes. Nenhum recurso em funcionamento será recriado apenas para ingressar
no gerenciamento por código.

O escopo pretendido inclui:

- registros DNS públicos relacionados à plataforma;
- configuração e rotas publicadas pelo Cloudflare Tunnel;
- aplicações e políticas do Cloudflare Access.

O código reutilizável poderá ser público. Valores reais de conta, zona, domínio
e aplicação serão fornecidos fora do Git. O estado será criptografado,
versionado em backend privado e terá controle de acesso próprio.

Inicialmente, a integração contínua executará somente formatação, validação e
`terraform plan`. A execução de `terraform apply` permanecerá manual, após
revisão do plano e aprovação da mudança.

## Consequências

- alterações de borda passam a ter revisão, histórico e plano reproduzível;
- drift entre código e Cloudflare pode ser detectado antes da aplicação;
- recursos atuais exigem importação e conferência individual;
- o arquivo de estado se torna ativo crítico e não pode entrar no repositório;
- credenciais devem usar token de API com privilégio mínimo e injeção em tempo
  de execução;
- mudanças manuais no painel devem ser evitadas após cada recurso ser importado;
- a primeira implementação deve ocorrer em uma branch e sem `apply` automático.

## Alternativas consideradas

### Continuar somente pelo painel

Preserva a simplicidade imediata, mas não oferece revisão, detecção de drift nem
reprodutibilidade suficiente para o objetivo profissional do projeto.

### Automatizar diretamente por API

É viável, porém transfere para scripts próprios responsabilidades de estado,
dependências e planejamento que o Terraform já resolve.

### Recriar todos os recursos pelo Terraform

Foi rejeitado porque produziria risco desnecessário de indisponibilidade e
alteração de identificadores em uma configuração que já está operacional.

