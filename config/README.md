# Configuração

Este diretório contém apenas exemplos sanitizados. Configurações reais permanecem no host sob `/opt/<projeto>` e são promovidas por um fluxo controlado.

## Convenções

- valores públicos podem ser versionados;
- valores específicos do ambiente usam placeholders;
- segredos são referenciados por arquivo;
- imagens usam versão ou digest;
- cada projeto possui backup antes de alterações;
- `docker compose config --quiet` é obrigatório;
- alterações de proxy devem ser testadas por acesso interno e externo.

## Placeholders

| Placeholder | Significado |
|---|---|
| `<BASE_DOMAIN>` | domínio das aplicações |
| `<LAN_IP>` | endereço do host na rede de gestão |
| `<PRODUCTION_IP>` | endereço do host para origem |
| `<UDM_IP>` | endereço do gateway |
| `<MIKROTIK_IP>` | endereço do roteador monitorado |

Não substitua placeholders neste repositório público. Materialize valores em um repositório privado, pipeline seguro ou diretamente no host.
