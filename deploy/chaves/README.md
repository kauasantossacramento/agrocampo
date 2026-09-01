# Chaves SSH de deploy

Esta pasta guarda as chaves privadas usadas para publicar no servidor.
**Nada aqui entra no Git** — o repositório é público.

Duas camadas protegem isso:

1. `deploy/chaves/` está no `.gitignore`, junto de `*.pem`, `*.key`,
   `id_rsa`, `id_ed25519` e afins.
2. Um gancho `pre-commit` em `.githooks/` lê o **conteúdo** do que está
   sendo commitado e recusa qualquer coisa com `-----BEGIN … PRIVATE KEY-----`.
   Ele pega até um arquivo renomeado, que passaria pelo `.gitignore`.

O gancho não vem ligado num clone novo. Em cada máquina, rode uma vez:

```bash
git config core.hooksPath .githooks
```

---

## Como copiar a chave para cá

A chave não foi copiada automaticamente: mover uma chave privada de root é
uma ação que precisa da sua mão. É um comando só, na máquina onde ela já
está:

**Windows (PowerShell ou Git Bash):**

```bash
cp "$USERPROFILE/.ssh/nuvem-center-prod" deploy/chaves/
```

**Linux ou macOS:**

```bash
cp ~/.ssh/nuvem-center-prod deploy/chaves/
chmod 600 deploy/chaves/nuvem-center-prod
```

Confira que o Git está mesmo ignorando:

```bash
git check-ignore -v deploy/chaves/nuvem-center-prod
# deve responder:  .gitignore:NN:deploy/chaves/  deploy/chaves/nuvem-center-prod
```

## Como levar para outra máquina

O que **não** serve: anexar em e-mail, mandar por WhatsApp, colar em chat,
subir para o Drive. Qualquer um desses deixa uma cópia num lugar que você
não controla.

O que serve:

- **Gerenciador de senhas** com campo de arquivo (Bitwarden, 1Password,
  KeePass). É o caminho mais simples e o que deixa registro de acesso.
- **Pendrive**, apagando o arquivo depois de instalar.
- **`scp` direto** entre as duas máquinas, se ambas já se enxergam.

Na máquina de destino:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cp nuvem-center-prod ~/.ssh/
chmod 600 ~/.ssh/nuvem-center-prod
ssh -i ~/.ssh/nuvem-center-prod root@<IP do servidor>
```

No Windows, o `chmod` não vale; se o OpenSSH reclamar de permissão, ajuste
pelo Explorer: Propriedades → Segurança → Avançadas → desativar herança e
deixar só o seu usuário.

---

## Um caminho melhor, quando você tiver tempo

Esta chave é a chave **root do servidor inteiro**. Quem a tem alcança o
Nuvem Center, o Traefik e todos os tenants — `conmac`, `matematica1`,
`lab-kaua`, os de teste. Não é uma chave "do AgroCampo": é a chave de tudo.

Cada máquina nova que recebe uma cópia é mais um lugar de onde ela pode
vazar, e revogá-la depois derruba o acesso de todo mundo de uma vez.

O arranjo mais saudável é **uma chave por máquina**, todas restritas:

```bash
# 1. na máquina nova, gere um par só dela
ssh-keygen -t ed25519 -f ~/.ssh/agrocampo-deploy -C "deploy agrocampo - notebook"

# 2. de uma máquina que já tem acesso, autorize a chave nova
ssh -i ~/.ssh/nuvem-center-prod root@<IP do servidor> \
  "echo 'CONTEUDO_DO_agrocampo-deploy.pub' >> ~/.ssh/authorized_keys"

# 3. teste antes de confiar
ssh -i ~/.ssh/agrocampo-deploy root@<IP do servidor> "hostname"
```

Ganhos: some uma máquina, você revoga só a linha dela em
`~/.ssh/authorized_keys` e as outras seguem funcionando; e o log do servidor
passa a dizer *qual* máquina entrou.

> O passo 2 escreve no `authorized_keys` do root — que é infraestrutura
> compartilhada do nuvem.center, fora do escopo do AgroCampo. Faça você
> mesmo, ou me autorize explicitamente antes.

Para restringir de verdade o que a chave pode fazer, o `authorized_keys`
aceita prefixos por chave:

```
from="203.0.113.10",no-agent-forwarding,no-X11-forwarding ssh-ed25519 AAAA... deploy agrocampo
```

`from=` trava a chave num IP de origem. Só use se o seu IP for fixo.
