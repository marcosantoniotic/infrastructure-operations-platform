# Guia de captura sanitizada

## Padrão visual

- resolução recomendada: 1600 × 900 ou superior;
- tema consistente entre painéis;
- janela do navegador recortada para remover favoritos, perfil e outras abas;
- título da aplicação e conteúdo técnico visíveis;
- sem overlays, notificações pessoais ou ferramentas de edição;
- formato PNG otimizado, preferencialmente abaixo de 1 MB.

## Dados que devem ser removidos

- IPs, domínios e hostnames reais;
- nomes de pessoas, clientes, empregadores ou localidades;
- endereços de e-mail e identificadores de contas;
- tokens, chaves, cookies, QR codes e credenciais;
- números de série, MAC addresses e inventário físico identificável;
- dados de tráfego, logs ou nomes que revelem terceiros.

Use somente dados demonstrativos criados para o ambiente de validação. Prefira
alterar os dados na origem antes da captura; não cubra informações sensíveis
com retângulos que possam ser removidos posteriormente.

## Roteiro mínimo

1. confirmar que a aplicação usa dados demonstrativos;
2. abrir uma janela limpa e maximizada;
3. selecionar um intervalo que mostre atividade sem revelar histórico real;
4. revisar cada texto visível antes da captura;
5. salvar com o nome definido em `docs/evidence/README.md`;
6. executar `scripts/validate-publication.ps1`;
7. revisar a imagem manualmente em zoom de 100% antes do commit.

## Critério de aceitação

Cada imagem deve responder em poucos segundos a uma pergunta objetiva:

- qual problema foi resolvido;
- qual ferramenta está operando;
- qual resultado pode ser verificado;
- qual competência profissional está sendo demonstrada.
