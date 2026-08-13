# Cloudflare Tunnel

Implanta um conector `cloudflared` remotamente gerenciado, sem publicar portas
no host. O conector compartilha somente a rede Docker externa do Traefik e
encaminha as rotas definidas no Cloudflare Zero Trust para a origem HTTPS.

## Segurança

- o token do túnel vem do Ansible Vault e é materializado com acesso exclusivo
  ao UID não privilegiado do container;
- a imagem é versionada e executada sem capabilities, com filesystem somente
  leitura e `no-new-privileges`;
- a CA privada é montada para validar o certificado do Traefik; não se usa
  `noTLSVerify`;
- o Compose não publica portas do host;
- Cloudflare Access e a validação do JWT no túnel devem ser configurados antes
  da criação dos registros DNS públicos.

## Hostnames de borda e origem

Valide a cobertura do certificado de borda antes de criar DNS. O certificado
Universal SSL não cobre automaticamente um segundo nível de subdomínio como
`app.ops.<BASE_DOMAIN>`; sem certificado compatível, prefira um nome de primeiro
nível como `app-ops.<BASE_DOMAIN>`.

O hostname público pode ser diferente do hostname interno. Nesse cenário, a
rota publicada deve usar o nome público no DNS, mas preservar em
`httpHostHeader` e `originServerName` o hostname interno configurado no Traefik
e coberto pelo certificado privado. Não habilite `noTLSVerify` como contorno.

Se a quantidade de destinos exceder o limite vigente de uma aplicação Access,
separe os serviços administrativos em outra aplicação com a mesma política de
menor privilégio e associe a cada rota somente o respectivo `audTag`.

## Variáveis obrigatórias

```yaml
cloudflare_tunnel_enabled: true
cloudflare_tunnel_token: "{{ vault_cloudflare_tunnel_token }}"
cloudflare_tunnel_origin_ca_source: /path/on/controller/iop-root-ca.crt
```

## Implantação

```bash
ansible-playbook -i inventories/operational/hosts.yml \
  playbooks/cloudflare-tunnel.yml --ask-vault-pass
```

## Validação e rollback

A role exige uma conexão registrada e confirma que o container não possui
portas publicadas. Para rollback, desative ou remova primeiro os CNAMEs públicos
e as rotas do túnel; depois execute `docker compose down` em
`/opt/cloudflare-tunnel`. A política Access deve ser preservada até a retirada
completa dos nomes públicos.
