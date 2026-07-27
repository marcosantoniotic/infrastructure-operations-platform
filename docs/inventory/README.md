# Atualização do inventário

O inventário público deve registrar versões, responsabilidades e capacidade sem incluir a topologia endereçável.

## Coleta

Execute no host:

```bash
sudo ./scripts/inventory-host.sh
```

O script não lê:

- arquivos `.env`;
- Docker secrets;
- variáveis de ambiente de containers;
- endereços e portas publicadas;
- dados de volumes;
- logs.

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
