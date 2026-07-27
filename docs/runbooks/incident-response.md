# Resposta a incidentes

## Classificação

| Severidade | Exemplo |
|---|---|
| S1 | host ou plataforma inteira indisponível |
| S2 | aplicação crítica ou banco indisponível |
| S3 | degradação, alerta de capacidade ou integração |
| S4 | problema visual ou funcional sem impacto operacional relevante |

## Fluxo

1. reconhecer o alerta;
2. confirmar impacto pelo mapa Zabbix e dashboard Grafana;
3. identificar o primeiro componente com falha;
4. conter sem apagar evidências;
5. aplicar correção reversível;
6. validar dependências;
7. documentar causa, ação e prevenção.

## Diagnóstico inicial

```bash
systemctl --failed
docker compose ls
docker ps -a
docker stats --no-stream
df -hT
free -h
journalctl -p warning --since '1 hour ago'
```

## Aplicação isolada

```bash
cd /opt/<project>
docker compose ps
docker compose logs --since 30m <service>
docker inspect <container>
```

## Rollback

- restaure o arquivo anterior, não reescreva segredos;
- recrie somente o serviço afetado;
- preserve volumes;
- evite `down -v`;
- registre o ponto exato do rollback.

## Pós-incidente

- linha do tempo;
- causa raiz e fatores contribuintes;
- detecção e tempo de recuperação;
- lacunas de observabilidade;
- ação preventiva com responsável e prazo.
