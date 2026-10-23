# Inicialização e desligamento

## Desligamento seguro do host

Primeiro identifique se a janela cobre apenas a plataforma ou também a
infraestrutura compartilhada. Não desligar outro ambiente, AD/DNS ou roteadores
por conveniência. Confirmar os consumidores antes de parar dependências.

1. Verifique tarefas em andamento e backups.
2. Confirme que não há atualização de banco ou migração ativa.
3. Registre uma janela de manutenção no Zabbix.
4. Pare aplicações na ordem inversa das dependências.

```bash
cd /opt/zabbix-glpi-bridge && docker compose stop
cd /opt/netbox-zabbix-sync && docker compose stop
cd /opt/portainer && docker compose stop
cd /opt/observability && docker compose stop
cd /opt/glpi && docker compose stop
cd /opt/netbox && docker compose stop
cd /opt/zabbix && docker compose stop
cd /opt/traefik && docker compose stop
```

Execute somente as linhas correspondentes aos projetos implantados no alvo.
Esses comandos param os projetos; não os removem e não apagam volumes.

5. Confirme que os containers pararam.
6. Desligue pelo sistema operacional:

```bash
systemctl poweroff
```

Não desligue a máquina virtual pelo hypervisor sem permitir o encerramento do sistema, salvo em incidente onde o host não responda.

## Inicialização

As políticas `restart` permitem recuperar os serviços quando Docker volta a
operar, respeitando o estado anterior dos contêineres.

Essa recuperação automática depende da política e do estado anterior. Após
`docker compose stop`, contêineres com `unless-stopped` ficam explicitamente
parados. Retome os projetos existentes com `docker compose start`, em ordem de
dependências, e valide-os; não assumir que o reboot desfez o stop. `up`,
provisionamento e build não são sinônimos de simplesmente ligar o ambiente.

A ordem de validação é:

1. Docker e redes;
2. bancos e caches;
3. Zabbix, NetBox e GLPI;
4. Prometheus e Grafana;
5. Traefik e acessos;
6. Portainer, Cockpit e integrações.

```bash
systemctl is-active docker firewalld zabbix-agent2
docker compose ls
docker ps
```

## Pós-inicialização

Em laboratório virtualizado, primeiro validar roteadores/uplink e AD/DNS;
depois controller, standby e plataforma, conforme o inventário. Recovery é
iniciado separadamente para o exercício aprovado, não como requisito de uso
diário. Manter os dados concretos e atalhos de administração no guia privado.

- valide DNS local;
- valide um acesso por hostname;
- confira o mapa Zabbix;
- confira o dashboard consolidado;
- verifique filas e erros do NetBox;
- confirme targets Prometheus;
- encerre a manutenção no Zabbix.

Verifique também a última execução da renovação de CRL e o teste HTTP/DNS real,
além do estado do timer ou exporter. Após queda de alimentação, confirme bridge,
DHCP, rota e montagens antes de recriar serviços. Consulte a
[revisão do laboratório](../testing/laboratory-operations-update.md).
