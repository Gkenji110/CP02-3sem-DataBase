# The Grand Tech Gala — Motor de Promoção de Fila

---

## 📁 Estrutura do Projeto

```
gala_tech/
├── api/
│   └── index.py         ← API serverless Python (handler da Vercel)
├── public/
│   └── index.html       ← Frontend estático
├── setup_banco.sql      ← DDL + dados de exemplo (rodar 1x no SQL Developer)
├── requirements.txt     ← Dependência: oracledb
├── vercel.json          ← Configuração de rotas da Vercel
└── README.md
```

---

## Passo a Passo

### 1. Banco de dados
Execute `setup_banco.sql` **uma única vez** no SQL Developer.

### 2. Desenvolvimento local

```bash
pip install oracledb

export DB_USER="seu_usuario"
export DB_PASSWORD="sua_senha"
export DB_DSN="oracle.fiap.com.br:1521/orcl"

python -c "
from http.server import HTTPServer
from api.index import handler
HTTPServer(('localhost', 8000), handler).serve_forever()
"

```

### 3. Deploy na Vercel

```bash

npm i -g vercel


vercel

vercel env add DB_USER
vercel env add DB_PASSWORD
vercel env add DB_DSN

vercel --prod
```

---

## ⚙️ Por que essa estrutura funciona na Vercel?

| Ponto | Detalhe |
|-------|---------|
| **Sem Flask** | A Vercel usa funções serverless; Flask não é compatível nativamente. O handler usa `BaseHTTPRequestHandler` puro, que a Vercel suporta. |
| **oracledb modo Thin** | Não precisa do Oracle Instant Client instalado. Funciona diretamente no ambiente serverless. |
| **Frontend estático** | `public/index.html` é servido como arquivo estático pela Vercel — zero configuração extra. |
| **Variáveis de ambiente** | Credenciais lidas via `os.environ` — seguro para produção. |

---

## ✅ Requisitos Técnicos Atendidos

| Requisito | Onde |
|-----------|------|
| Cursor Explícito com JOIN | `api/index.py` → `CURSOR c_waitlist IS SELECT ... JOIN ...` |
| ORDER BY PRIORIDADE DESC + DATA_INSCRICAO ASC | `api/index.py` → cláusula ORDER BY do cursor |
| FOR UPDATE OF i.STATUS | `api/index.py` → última linha do cursor |
| Log em HISTORICO_STATUS | `api/index.py` → INSERT dentro do LOOP |
| Bloco Anônimo (sem Procedure/Trigger) | `api/index.py` → `DECLARE...BEGIN...END` |
| COMMIT / ROLLBACK | `api/index.py` → após o LOOP / na EXCEPTION |
| Tratamento de exceções Oracle | `api/index.py` → `oracledb.DatabaseError` |
