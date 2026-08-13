# NetBox role

Implanta NetBox de forma independente com PostgreSQL, Valkey principal, Valkey de cache, worker e housekeeping.

## Dependências

- RHEL compatível;
- Docker Engine e Compose;
- collection `community.docker`;
- segredos fornecidos por Ansible Vault;
- 4 GiB de RAM no mínimo para o ambiente de validação.

## Modos

### Isolado

```yaml
netbox_enable_traefik: false
netbox_bind_address: 127.0.0.1
netbox_http_port: 8000
```

### Publicado pelo Traefik

```yaml
netbox_enable_traefik: true
netbox_traefik_hostname: "netbox.<BASE_DOMAIN>"
netbox_traefik_origin: "https://netbox.<BASE_DOMAIN>"
netbox_traefik_network: proxy
netbox_traefik_middlewares:
  - security-headers@file
netbox_allowed_hosts:
  - 127.0.0.1
  - "netbox.<BASE_DOMAIN>"
netbox_csrf_trusted_origins:
  - "https://netbox.<BASE_DOMAIN>"
  - "https://netbox-edge.<BASE_DOMAIN>"
```

A rede externa do proxy e o middleware informado devem existir antes da
implantação. O bind direto pode permanecer em loopback como acesso de
contingência sem exposição à rede. Mantenha `127.0.0.1` em
`netbox_allowed_hosts` para que o fallback por túnel SSH funcione no navegador.
Inclua também cada hostname público em `netbox_allowed_hosts` e sua origem HTTPS
completa, sem caminho, em `netbox_csrf_trusted_origins`. Isso é obrigatório
mesmo quando o túnel substitui o cabeçalho Host pelo nome interno do Traefik,
pois o navegador mantém o hostname público no cabeçalho `Origin` dos POSTs.

## Execução

```bash
ansible-playbook -i inventories/validation/hosts.yml playbooks/netbox.yml
```

O playbook instala Docker quando necessário, mas não implanta Zabbix, Grafana, Prometheus, Portainer ou Cloudflare.

## NetBox Topology Views

O plugin `netbox-topology-views` é instalado e habilitado por padrão em uma
imagem derivada e reproduzível. A versão do plugin é fixada para acompanhar a
versão suportada do NetBox:

```yaml
netbox_topology_views_enabled: true
netbox_topology_views_version: "4.5.1"
```

Defina `netbox_topology_views_enabled: false` somente quando a instalação não
dever oferecer visualizações de topologia. A role valida o pacote, o registro
em `PLUGINS` e a ausência de migrações pendentes.
O salvamento de coordenadas é habilitado na configuração do plugin para que
layouts ajustados na interface persistam entre acessos e reconvergências.
A imagem derivada também fornece um ícone genérico para papéis sem imagem
associada, evitando nós invisíveis em topologias recém-implantadas.
Após a implantação, a role coleta os arquivos estáticos do plugin e valida que
seu JavaScript principal responde com HTTP 200 antes de concluir.

## Inventário demonstrativo

`netbox_provision_demo_inventory` é desabilitado por padrão. Quando ativado
explicitamente no ambiente de validação, a role cria um conjunto sanitizado e
idempotente composto por um site, um hypervisor, um cluster, quatro máquinas
virtuais e três prefixos RFC 5737. Nenhum ativo ou endereço real é utilizado.

## Persistência

- PostgreSQL;
- dados persistentes do Valkey principal;
- mídia do NetBox.

O cache não é tratado como dado crítico.

## Validação

- configuração Compose válida;
- containers iniciados;
- healthchecks;
- endpoint `/login/` respondendo com HTTP 200 ou 302.
- NetBox Topology Views instalado, habilitado e sem migrações pendentes;
- rota HTTPS do Traefik respondendo com HTTP 200;
- HSTS e proteção contra content-type sniffing presentes;
- segundo passe do Ansible sem alterações.
- inventário demonstrativo completo quando sua provisão estiver habilitada.

## Remoção

O role não remove volumes. Uma remoção completa e destrutiva deve ser executada manualmente somente após backup validado.
