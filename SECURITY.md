# Política de segurança

## Dados que não pertencem ao repositório

- tokens de API e credenciais;
- chaves privadas e certificados exportáveis;
- conteúdo de `acme.json`;
- dumps de bancos e volumes;
- IDs de conta, túnel ou organização;
- endereços públicos e internos reais;
- arquivos `.env` de produção;
- inventário contendo dados pessoais.

Use os placeholders de `.env.example` e mantenha valores reais em um gerenciador de segredos.

## Comunicação de vulnerabilidades

Não abra uma issue pública contendo credenciais, logs completos ou topologia privada. Registre a ocorrência por canal privado com:

1. componente e versão;
2. impacto observado;
3. passos mínimos de reprodução;
4. evidências já sanitizadas;
5. ação de contenção aplicada.

## Controles adotados

- proxy do Docker Socket com operações restritas;
- acesso remoto protegido por identidade;
- redes Docker separadas por domínio;
- arquivos de segredo com permissões restritas;
- bancos e caches sem publicação direta;
- firewall ativo no host;
- monitoramento por Zabbix e Prometheus;
- configurações versionáveis separadas de dados persistentes.

## Controles pendentes

- automatizar e comprovar backups do NetBox e Zabbix;
- testar restauração em agenda definida;
- rotacionar tokens e credenciais por calendário;
- revisar a necessidade de publicar a porta do Zabbix Server;
- definir política de atualização e janela de manutenção.
