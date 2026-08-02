# Checklist de publicação

## Conteúdo

- [x] README representa o estado atual.
- [x] versões foram conferidas.
- [x] roadmap diferencia implementado de planejado.
- [x] documentação não promete backups ainda não comprovados.
- [ ] diagramas Mermaid renderizam no GitHub.
- [x] links relativos funcionam.

## Evidências visuais

- [x] diagrama sanitizado da arquitetura disponível;
- [x] captura do dashboard executivo do Grafana;
- [x] captura do mapa do ecossistema no Zabbix;
- [x] captura sanitizada do inventário no NetBox;
- [x] captura das stacks no Portainer;
- [x] evidência visual do backup e da restauração;
- [x] evidência visual de execução bem-sucedida da CI;
- [x] todas as capturas foram revisadas conforme o [guia de captura](evidence/capture-guide.md).

## Segredos e privacidade

- [x] nenhum token, senha ou chave.
- [x] nenhum conteúdo de `.env`.
- [x] nenhum `acme.json`.
- [x] nenhum dump ou backup.
- [x] nenhum ID de conta ou túnel.
- [x] nenhum endereço real.
- [x] nenhum e-mail ou nome pessoal.
- [x] nenhum log bruto.

## Git

```bash
git status
git diff --check
git grep -n -I -E '(password|passwd|secret|token|api[_-]?key)' -- .
git grep -n -I -E '([0-9]{1,3}\.){3}[0-9]{1,3}' -- .
```

Resultados legítimos como nomes de variáveis devem ser revisados manualmente.

## Repositório

- [x] escolher licença;
- [ ] definir visibilidade;
- [ ] habilitar proteção da branch principal;
- [ ] habilitar secret scanning;
- [ ] habilitar Dependabot quando houver dependências;
- [ ] configurar responsáveis;
- [ ] criar release inicial.

Tópicos recomendados: `ansible`, `rhel`, `docker`, `netbox`, `zabbix`,
`prometheus`, `grafana`, `traefik`, `infrastructure-as-code` e `devops`.

## Antes do push

Execute:

```powershell
./scripts/validate-publication.ps1
```
