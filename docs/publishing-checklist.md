# Checklist de publicação

## Conteúdo

- [ ] README representa o estado atual.
- [ ] versões foram conferidas.
- [ ] roadmap diferencia implementado de planejado.
- [ ] documentação não promete backups ainda não comprovados.
- [ ] diagramas Mermaid renderizam no GitHub.
- [ ] links relativos funcionam.

## Segredos e privacidade

- [ ] nenhum token, senha ou chave.
- [ ] nenhum conteúdo de `.env`.
- [ ] nenhum `acme.json`.
- [ ] nenhum dump ou backup.
- [ ] nenhum ID de conta ou túnel.
- [ ] nenhum endereço real.
- [ ] nenhum e-mail ou nome pessoal.
- [ ] nenhum log bruto.

## Git

```bash
git status
git diff --check
git grep -n -I -E '(password|passwd|secret|token|api[_-]?key)' -- .
git grep -n -I -E '([0-9]{1,3}\.){3}[0-9]{1,3}' -- .
```

Resultados legítimos como nomes de variáveis devem ser revisados manualmente.

## Repositório

- [ ] escolher licença;
- [ ] definir visibilidade;
- [ ] habilitar proteção da branch principal;
- [ ] habilitar secret scanning;
- [ ] habilitar Dependabot quando houver dependências;
- [ ] configurar responsáveis;
- [ ] criar release inicial.

## Antes do push

Execute:

```powershell
./scripts/validate-publication.ps1
```
