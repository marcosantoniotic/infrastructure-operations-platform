# OCSP: CertID configurável e frescor explícito — candidato local

Data: 06/11/2026, America/Sao_Paulo (UTC−03).

**Candidato validado em isolamento, sem aprovação de integração ou implantação.** Base:
`5e83144ca83cebfda31558441e9a7c4ea10111dc`, mais o diff local delimitado.
Sem acesso a OPS/LAB01, certificados operacionais, mudança de CA/controlador ou
ativação de OCSP/sincronização em inventários operacionais.

## Desenho e risco

- CertID SHA-256 continua padrão; SHA-1 exige seleção por inventário, sem retry
  automático. Assinatura de resposta SHA-1 continua recusada. Digest da resposta
  deve corresponder ao da consulta, além de serial/emissor/assinatura corretos.
- `strict` mantém idade máxima de 3600 s. Candidato `bounded-24h` exige
  `freshness_risk_accepted: true` e idade explícita >3600 e <=86400 s. Sem aumento
  de cache (teto 300 s) nem de tolerância de relógio (teto 120 s).
- Ambos `producedAt` e `thisUpdate` devem cumprir a idade. `nextUpdate`, ordenação
  temporal, validade dos certificados e autorização do respondente continuam
  obrigatórios, sem grace period após expiração.
- Maior idade tolerada amplia a janela de descoberta de revogação. O teto de
  24 h é proposta para revisão, não escolha de valor operacional. Sem aceite
  desse risco, preservar strict e a recusa de respostas antigas.
- Cache é revalidado após mudança de política. Identidade persistente de
  revogação continua SHA-256 de leaf DER + issuer DER, independente do CertID;
  nenhuma troca de perfil/digest pode apagar esse histórico.
- Opções não padrão exigem capability label em imagem imutável testada; o guard
  recusa imagem antiga antes de escrever políticas. Labels não são proveniência.

## Versões e fronteira de evidência

UnPoller 3.4.1 com unifi/v5 5.30.0, transporte Go existente sem mudanças,
Python 3.13.12 e cryptography 50.0.2 na imagem Linux. asn1crypto 1.5.1 somente
na imagem de testes. Ambas executam como UID/GID 10001.

Host Linux descartável separado, sem VMs/dados operacionais. Matrizes executadas
com `--network none`, raiz read-only, capacidades removidas e recursos limitados.
Controller/OCSP fictícios usam TLS/HTTP/assinaturas reais em loopback. Não há
mock do socket TLS, verificador criptográfico ou transporte Go. A entrada
Docker-inspect auxiliar é substituída por configuração sintética explícita.
Não é teste contra firmware/controlador real.

## Matriz e comandos

```sh
python scripts/tests/test_unifi_ocsp_durability.py
python scripts/tests/test_unifi_ocsp_policy.py
IOP_OCSP_FIXTURE_DIR=<FIXTURE_PRIVADA> python scripts/tests/test_unifi_ocsp_fixtures.py
IOP_OCSP_FIXTURE_DIR=<FIXTURE_PRIVADA> python scripts/tests/test_unifi_ocsp_options.py
python scripts/ci/test-unifi-ocsp-connections.py \
  --fixture <FIXTURE_SHA256> --binary /usr/bin/unpoller --certid-hash sha256 --extended
python scripts/ci/test-unifi-ocsp-connections.py \
  --fixture <FIXTURE_SHA1> --binary /usr/bin/unpoller --certid-hash sha1 --extended
```

Fixtures são novas a cada execução; nunca regenerar em diretório existente.
Negativas têm assinaturas reais, inclusive timestamps antigos reassinados.

| Camada | Cobertura | Estado |
| --- | --- | --- |
| Durabilidade Linux | Escrita/sync/replace e recusa após erro de fsync | 4 PASS, 0 falhas/skips |
| Guards | Opt-in, limites, imagem, mounts e preservação de outros serviços | 7 PASS, 0 falhas/skips |
| Fixtures | CA/KeyUsage, assinaturas, identidade, tempos e TLS cadeia/hostname | 9 PASS, 0 falhas/skips |
| Opções | Paridade em 448 combinações, inteiro marcado Ansible, defaults, CertID vs assinatura, idade exata e nextUpdate | 4 PASS, 0 falhas/skips |
| Dois coletores × dois digests | GOOD/delegado, REVOKED/UNKNOWN, identidade/assinatura, TLS, tempos, transporte, cache, rotação, reinício e métricas | 140 PASS: 70 por digest (34 Python + 36 UnPoller); 0 falhas/skips |
| Novos casos, incluídos nos 140 | HTTP 500/internalError sem fallback; digest errado; assinatura SHA-1; 2 h recusada em strict e aceita só no perfil; 25 h recusada; aperto de perfil invalida cache; revogação persiste após mudança de algoritmo/perfil | PASS; recusas sem requisições de aplicação ao controlador fictício |

Evidências privadas: `acceptance.private.log`,
`options-sha256-final/connection-results-sha256.json` e
`options-sha1-final/connection-results-sha1.json`. As 448 combinações são subcasos
de um teste, não 448 testes independentes. API real de transporte contra emulador
não é validação de compatibilidade com o respondente operacional.

## Automação real isolada

Somente a role dedicada e Compose de dois coletores fictícios. Emulador e
exporter bindam apenas loopback da VM descartável; nenhuma porta publicada
para a rede externa. SELinux Enforcing, UID 10001 e credencial original root
0600 preservados. Não se executou provisionamento completo.

| Etapa | Recap Ansible |
| --- | --- |
| Strict, primeira aplicação | ok=42, changed=16, failed=0, skipped=3 |
| Strict, repetição | ok=44, changed=0, failed=0, skipped=1 |
| SHA-1 + bounded-24h, primeira alteração | ok=45, changed=2, failed=0, skipped=0 |
| SHA-1 + bounded-24h, repetição | ok=45, changed=0, failed=0, skipped=0 |
| Guard de proteção instalada | ok=7, changed=0, failed=0, rescued=1 |
| Imagem antiga sem capability, duas opções negativas | ok=26, changed=0, failed=0, rescued=2; ambas as políticas iguais antes/depois |

Skips do Ansible são condições esperadas de primeira instalação e capability
desnecessária no perfil padrão, não testes criptográficos omitidos. Os rescues
são recusas esperadas, conferidas pelo nome exato da tarefa. Sintaxe do playbook,
Compose real, YAML e validações locais de imagens/privilégios/Actions passaram.

## Rollback e limites

Rollback somente de configuração/imagem OCSP-capaz, coordenado nos dois
coletores, preservando confiança, journals e locks atuais. Não retornar a binário
sem OCSP, restaurar banco/VM ou limpar deny list. Retorno a strict/SHA-256 pode
interromper a coleta por incompatibilidade real; isso é fail-closed, não motivo
para afrouxar TLS.

Pendentes: escolha operacional de algoritmo/idade, medição de escala/custo,
aceitação ECDSA, revogação de intermediários/respondente delegado e proveniência/
notices antes de publicação operacional. Não se prova revogação de toda a cadeia
ou recuperação de desastre por snapshot. Rollback não apaga conhecimento novo.

Falhas de preparação preservadas: faltou pasta-pai na primeira fixture local;
empacotamento herdou modos privados dos fontes/diretórios da cópia descartável.
Dockerfile passou a criar diretórios traversáveis e definir modos públicos dos
scripts/binário, com gate de leitura não-root. Somente a cópia de teste foi
normalizada; segredos/journals mantêm permissões. Não se alterou SELinux nem
se executou o verificador como root para aprovar.

## Fechamento e identidade do candidato

**APROVADO NO RECORTE ISOLADO; aguardando revisão antes de publicação.**
24 testes Python Linux e 140 casos dos coletores aprovados, zero falhas/skips.
Verificador SHA-256 LF:
`c8b58df8a9267cbc11e7f001fb9a14b61b9bcb22046fe1617a00126e44318510`.
Imagem runtime local, não publicada:
`sha256:03d3dfce3caecbd7f3e565bee5509182ba8ce1c07f95b384f0f998a2f6ab8d3c`.
O ensaio compara os fontes empacotados com o checkout antes de executar.

Rollback real de configuração passou: indisponibilidade transitória recuperou;
ambos os journals preservaram revogação confirmada após recriação e GOOD
posterior. Não houve restauração de banco/volume/VM nem retorno a binário sem
OCSP. Evidência: `rollback.private.log` e snapshots privados da fixture.

A CA fictícia contém Key Usage, SKI/AKI e Basic Constraints; a cadeia da fixture
também passou em `openssl verify -x509_strict`. Nenhuma CA foi instalada nos
clientes ou trocada em ambiente operacional.

Arquivo privado com logs, fixtures e backup da configuração de teste, verificado
na origem e no E: por SHA-256:
`a46fd6e800ae92b459bcfbf7283ea999cf417435f5ad53b1f9b376dee36f09cd`.
Não publicar esse arquivo: contém chaves e credenciais **fictícias**. O resumo
`evidence.sanitized.json` registra horários UTC, versões, contagens, hashes e
recaps sem tokens/chaves/endpoints operacionais. A cópia no E: é privada.

Coletores/emulador foram parados, mantendo os journals, configurações, imagens e
volumes. Não foram apagadas evidências das tentativas anteriores. A VM
descartável é devolvida desligada; nenhum serviço operacional foi acessado.
Alterações locais não relacionadas preservadas. A etapa de testes não executou
commit, push, PR ou CI remoto. A publicação posterior foi solicitada apenas como
PR em rascunho, com nova conferência do CI e sem merge ou implantação implícitos.
As imagens locais de teste e os arquivos privados não são publicados com o código.
