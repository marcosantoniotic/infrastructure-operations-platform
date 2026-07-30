# Atualização do inventário

O inventário público deve registrar versões, responsabilidades e capacidade sem incluir a topologia endereçável.

## Coleta

Execute no host:

```bash
sudo ./scripts/inventory-host.sh \
  --logical-name platform-production \
  --output .validation/inventory/current-state.md
```

O resultado é um documento Markdown pronto para revisão. O caminho
`.validation/` é ignorado pelo Git; copie o conteúdo aprovado para
`docs/inventory/current-state.md` somente depois das validações.

O script não lê:

- arquivos `.env`;
- Docker secrets;
- variáveis de ambiente de containers;
- endereços e portas publicadas;
- dados de volumes;
- logs.

Além disso, o gerador usa uma lista positiva de campos e interrompe a execução
se o documento de origem contiver chaves relacionadas a endereços, redes,
portas, variáveis de ambiente, labels, mounts ou segredos.

## Teste reproduzível

A CI executa o mesmo gerador com dados sintéticos:

```bash
./scripts/inventory-host.sh \
  --source-json scripts/fixtures/sanitized-inventory-source.json \
  --output /tmp/sanitized-current-state.md
```

Isso valida a renderização e a ausência de indicadores sensíveis sem acessar o
host de produção.

## Revisão

Antes de atualizar `current-state.md`:

1. remova nomes pessoais;
2. substitua domínio e endereços por placeholders;
3. confira se nomes de imagens privadas podem ser publicados;
4. não inclua saída bruta;
5. execute a validação de publicação.

## Frequência

Atualize o inventário:

- após mudanças de versão;
- após inclusão ou remoção de serviço;
- após mudança de capacidade;
- antes de cada release da documentação;
- no mínimo trimestralmente.
