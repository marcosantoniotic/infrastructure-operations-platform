# ADR-001: Limite da plataforma

- Status: aceito
- Data: 2026-07-27

## Contexto

Os serviços cresceram em projetos independentes. Era necessário um nome e uma documentação principal sem transformar tudo em um único Compose.

## Decisão

`infrastructure-operations-platform` será o projeto guarda-chuva. Cada domínio mantém seu próprio ciclo de vida e persistência, enquanto arquitetura, padrões, inventário, runbooks e roadmap ficam centralizados.

## Consequências

- mudanças de um componente não exigem reiniciar toda a plataforma;
- documentação ganha uma entrada única;
- redes e integrações precisam ser explicitamente registradas;
- a plataforma continua sendo nó único até uma fase futura.
