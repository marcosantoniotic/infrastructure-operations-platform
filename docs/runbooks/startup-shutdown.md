# Inicialização e desligamento

## Desligamento seguro do host

1. Verifique tarefas em andamento e backups.
2. Confirme que não há atualização de banco ou migração ativa.
3. Registre uma janela de manutenção no Zabbix.
4. Pare aplicações na ordem inversa das dependências.

```bash
cd /opt/portainer && docker compose stop
cd /opt/observability && docker compose stop
cd /opt/netbox && docker compose stop
cd /opt/zabbix && docker compose stop
cd /opt/traefik && docker compose stop
```

5. Confirme que os containers pararam.
6. Desligue pelo sistema operacional:

```bash
systemctl poweroff
```

Não desligue a máquina virtual pelo hypervisor sem permitir o encerramento do sistema, salvo em incidente onde o host não responda.

## Inicialização

Se as políticas `restart` estiverem configuradas, Docker recuperará os serviços automaticamente. A ordem de validação é:

1. Docker e redes;
2. bancos e caches;
3. Zabbix e NetBox;
4. Prometheus e Grafana;
5. Traefik e acessos;
6. Portainer, Cockpit e integrações.

```bash
systemctl is-active docker firewalld zabbix-agent2
docker compose ls
docker ps
```

## Pós-inicialização

- valide DNS local;
- valide um acesso por hostname;
- confira o mapa Zabbix;
- confira o dashboard consolidado;
- verifique filas e erros do NetBox;
- confirme targets Prometheus;
- encerre a manutenção no Zabbix.
