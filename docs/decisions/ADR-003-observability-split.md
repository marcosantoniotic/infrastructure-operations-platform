# ADR-003: Separação entre Zabbix e Prometheus

- Status: aceito
- Data: 2026-07-27

## Contexto

Zabbix e Prometheus possuem sobreposição, mas atendem modelos operacionais diferentes.

## Decisão

Zabbix permanece responsável por triggers, eventos, mapas e disponibilidade. Prometheus coleta métricas de alta frequência e exporters. Grafana consolida a visualização.

## Consequências

- evita forçar uma única ferramenta a todos os casos;
- dashboards podem combinar fontes;
- alertas devem ter proprietário claro para não duplicar ruído;
- retenção e capacidade são administradas separadamente.
