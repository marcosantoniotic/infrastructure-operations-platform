# Operação diária

## Saúde geral

```bash
hostnamectl
free -h
df -hT /
docker compose ls
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
systemctl --failed
```

## Consumo de containers

```bash
docker stats --no-stream
docker system df
```

## Projetos

```bash
cd /opt/traefik && docker compose ps
cd /opt/zabbix && docker compose ps
cd /opt/netbox && docker compose ps
cd /opt/observability && docker compose ps
cd /opt/portainer && docker compose ps
```

## Logs

```bash
docker logs --since 30m <container>
journalctl -u zabbix-agent2 --since '30 minutes ago'
journalctl -u docker --since '30 minutes ago'
```

Não publique logs sem remover tokens, cookies, nomes pessoais, endereços e cabeçalhos de autenticação.

## Validação de configuração

```bash
docker compose config --quiet
```

Para Prometheus:

```bash
docker exec <prometheus-container> promtool check config /etc/prometheus/prometheus.yml
```

## Critérios de saúde

- todos os projetos Compose em execução;
- containers críticos `healthy` quando healthcheck existir;
- todos os targets esperados do Prometheus em `UP`;
- mapa Zabbix sem problemas inesperados;
- acesso local e externo funcional;
- filesystem abaixo dos limites definidos;
- backup recente e verificável.

## Cuidados no laboratório corporativo

- Comparar VMs ligadas, interfaces e redes com o inventário privado, sem
  interpretar organização de pastas do hypervisor como configuração de rede.
- Distinguir contêiner operacional com falha de motor de teste intencionalmente
  parado. `Exited` em uma cópia isolada não implica incidente no ambiente ativo.
- Verificar `probe_success`, não somente `up`: exporter acessível pode estar
  reportando falha na aplicação ou no DNS consultado.
- Conferir espaço da raiz e resultado do Redis quando aplicações apresentarem
  falhas simultâneas. Não reiniciar tudo antes de preservar o diagnóstico.
- Verificar DNS, TLS/CRL e os caminhos direto e por túnel separadamente.
  Secure cookies tornam inadequado o fallback HTTP para login.
- Usar API autenticada de leitura e dry-run para verificar integrações; não
  criar chamados ou executar um deploy completo só para testar conectividade.
- Manter recovery e imagem-base desligados quando não forem necessários ao
  exercício aprovado. Não desligar roteadores, DNS/AD ou outras dependências
  compartilhadas sem conferir seus consumidores.

As contagens da [última rodada](../testing/laboratory-operations-update.md) são
referência datada, não valores fixos para um alarme ou garantia permanente.
