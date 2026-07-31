# Contingência de DNS e proxy

Este runbook cobre falha isolada do DNS interno ou do Traefik. Ele não substitui
o runbook de recuperação integral quando o host ou os dados estiverem perdidos.

## Pré-requisitos

- segundo resolvedor em host e domínio de falha diferentes;
- mesmos registros internos publicados nos dois resolvedores;
- segundo Traefik provisionado pelo mesmo código;
- certificados e segredos entregues por canal privado;
- acesso administrativo direto aos dois nós;
- endpoint funcional para cada aplicação crítica;
- alteração de DNS com TTL operacional documentado.

## Teste de DNS secundário

1. Consultar cada resolvedor explicitamente para os nomes críticos.
2. Confirmar que ambos retornam o endereço atualmente aprovado.
3. Desativar temporariamente o resolvedor principal em janela de teste.
4. Renovar a configuração DNS de um cliente de validação.
5. Confirmar resolução e acesso HTTPS local sem usar DNS público.
6. Restaurar o principal e registrar tempo e resultado.

Não considerar o teste aprovado apenas porque um endereço permanece no cache do
cliente.

## Falha do Traefik principal

1. Confirmar que a falha está no proxy e que as aplicações de origem continuam
   saudáveis.
2. Preservar logs e evitar reinicializações repetidas.
3. Validar no standby:
   - configuração carregada sem erro;
   - certificado esperado;
   - middlewares de segurança ativos;
   - resposta funcional dos serviços críticos.
4. Alterar o registro interno para o endereço do standby.
5. Se existirem dois conectores do Tunnel, confirmar que o conector do standby
   alcança a origem correta.
6. Validar resposta HTTPS local, acesso externo e autenticação Access.
7. Registrar início, promoção, validação e tempo total.

## Falha total do host principal

1. Declarar incidente S1.
2. Confirmar que a falha não é apenas rede, DNS ou proxy.
3. Promover DNS e Traefik no standby.
4. Executar o runbook de recuperação integral para NetBox, Zabbix e
   observabilidade.
5. Não apontar usuários para aplicações antes de bancos e dependências passarem
   pelas verificações funcionais.

## Retorno ao nó principal

O retorno não deve ocorrer automaticamente quando o host reaparecer.

1. Corrigir a causa raiz e atualizar o código quando necessário.
2. Validar o nó principal isoladamente.
3. Conferir qual nó contém os dados válidos mais recentes.
4. Planejar a janela de retorno e o rollback.
5. Alterar DNS ou endereço virtual uma única vez.
6. Confirmar aplicações, monitoramento e backup.
7. Rebaixar o outro nó para standby somente após a validação.

## Critérios de aprovação do exercício

- DNS continuou resolvendo sem depender do cache;
- nenhum cliente foi direcionado simultaneamente a origens inconsistentes;
- TLS, cabeçalhos e autenticação permaneceram válidos;
- NetBox e Zabbix passaram por teste funcional;
- monitoramento detectou falha e recuperação;
- tempos medidos atenderam aos objetivos documentados;
- não houve exposição de credenciais nas evidências.

## Critérios de parada

- risco de split-brain ou escrita simultânea em bancos independentes;
- origem do standby sem dados consistentes;
- certificado, segredo ou política de acesso incorreta;
- alteração de DNS sem caminho de rollback;
- perda de acesso administrativo aos dois nós.
