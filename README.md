# The Grand Tech Gala — Motor de Promoção de Fila

**Checkpoint 2 — Mastering Relational and Non Relational Databases**  
FIAP 2026 · Professor Renê Mendes

Sistema de gerenciamento de fila de espera para o evento **Grand Tech Gala 2026**, com promoção automática de inscritos via bloco anônimo PL/SQL, priorizando usuários Platinum > VIP > Normal.

---

## Pré-requisitos

Antes de rodar o projeto, você precisa ter instalado:

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)

Não é necessário instalar nada mais — o `run.py` cuida do restante automaticamente.

---

## Como rodar localmente

### 1. Clone o repositório

```bash
git clone https://github.com/Gkenji110/CP02-3sem-DataBase.git
cd CP02-3sem-DataBase
```

### 2. Configure as credenciais

```bash
cp .env.example .env
```

Abra o `.env` e preencha com suas credenciais Oracle:

```
DB_USER=seu_usuario
DB_PASSWORD=sua_senha
DB_DSN=oracle.fiap.com.br:1521/orcl
```

### 3. Execute o projeto

```bash
python run.py
```

Esse único comando vai:
1. Instalar todas as dependências (`requirements.txt`)
2. Criar as tabelas no banco e inserir os dados de exemplo
3. Subir o servidor Flask automaticamente

Acesse em: **http://localhost:5000**

---

## Estrutura do projeto

```
CP02-3sem-DataBase/
├── api/
│   └── app.py          ← Backend Flask + lógica PL/SQL
├── templates/
│   └── index.html      ← Interface HTML
├── static/
│   └── style.css       ← Estilos
├── .env                ← Credenciais reais (não sobe ao git)
├── .env.example        ← Modelo de variáveis de ambiente
├── .gitignore
├── requirements.txt    ← Dependências Python
├── run.py              ← Script de setup e inicialização
├── setupBanco.sql      ← DDL + dados de exemplo
├── vercel.json
└── README.md
```

---

## Requisitos do desafio atendidos

| Requisito | Como foi atendido |
|---|---|
| Bloco anônimo PL/SQL | `PLSQL_PROMOVER_FILA` em `app.py` — sem Procedures ou Triggers |
| Cursor Explícito | `CURSOR c_waitlist` com JOIN entre `INSCRICOES` e `USUARIOS` |
| Ordenação por prioridade | `ORDER BY u.PRIORIDADE DESC, i.DATA_INSCRICAO ASC` |
| Bloqueio de registros | `FOR UPDATE OF i.STATUS` no cursor |
| Registro de promoções | Cada promoção insere uma linha em `HISTORICO_STATUS` |
| Tratamento de exceções | Bloco `EXCEPTION WHEN OTHERS` com `ROLLBACK` explícito |
| Conexão via `oracledb` | Thin mode, credenciais carregadas do `.env` |
| Secrets via `.env` | `python-dotenv`; `.env` no `.gitignore` |

---

## Deploy na Vercel

```bash
npm i -g vercel
vercel
```

Defina `DB_USER`, `DB_PASSWORD` e `DB_DSN` nas variáveis de ambiente do painel da Vercel.

