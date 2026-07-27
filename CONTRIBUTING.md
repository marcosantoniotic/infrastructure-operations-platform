# Contribuindo

## Fluxo de mudança

1. Abra uma issue descrevendo objetivo, risco e rollback.
2. Crie uma branch curta.
3. Altere exemplos e documentação sem incluir valores reais.
4. Execute `scripts/validate-publication.ps1`.
5. Valide a configuração no ambiente de teste ou com comandos `config`.
6. Registre evidências sanitizadas.
7. Solicite revisão antes de promover para produção.

## Convenções

- nomes de serviços em minúsculas e semanticamente estáveis;
- versões de imagens explicitamente fixadas;
- nenhuma tag `latest` em produção;
- arquivos secretos fornecidos fora do repositório;
- documentação atualizada no mesmo pull request;
- comandos destrutivos sempre acompanhados de backup e rollback.

## Commits

Prefira mensagens objetivas:

```text
docs: documenta dependências do NetBox
feat(observability): adiciona exporter
fix(traefik): corrige roteamento interno
chore(security): atualiza política de segredos
```
