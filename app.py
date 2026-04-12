"""
╔══════════════════════════════════════════════════════════════╗
║    THE GRAND TECH GALA — Interface Web Flask                 ║
║    FIAP | Mastering Databases | Checkpoint 2                 ║
╚══════════════════════════════════════════════════════════════╝

Execução:
    pip install flask oracledb
    python app.py
    Acesse: http://localhost:5000
"""

from flask import Flask, render_template_string, request, jsonify
import oracledb
from datetime import datetime

# ──────────────────────────────────────────────
# CONFIGURAÇÃO
# ──────────────────────────────────────────────
DB_USER     = "seu_usuario"
DB_PASSWORD = "sua_senha"
DB_DSN      = "oracle.fiap.com.br:1521/orcl"

app = Flask(__name__)

# ──────────────────────────────────────────────
# BLOCO PL/SQL (mesmo do script CLI)
# ──────────────────────────────────────────────
PLSQL_PROMOVER_FILA = """
DECLARE
    v_vagas_restantes  NUMBER        := :p_vagas;
    v_evento_id        NUMBER        := :p_evento_id;
    v_promovidos       NUMBER        := 0;
    v_erro_msg         VARCHAR2(500);

    CURSOR c_waitlist IS
        SELECT
            i.ID             AS inscricao_id,
            i.USUARIO_ID,
            i.STATUS,
            i.DATA_INSCRICAO,
            u.NOME,
            u.EMAIL,
            u.PRIORIDADE
        FROM
            INSCRICOES  i
            JOIN USUARIOS u ON u.ID = i.USUARIO_ID
        WHERE
            i.EVENTO_ID = v_evento_id
            AND i.STATUS  = 'WAITLIST'
        ORDER BY
            u.PRIORIDADE    DESC,
            i.DATA_INSCRICAO ASC
        FOR UPDATE OF i.STATUS;

    r_inscricao c_waitlist%ROWTYPE;

BEGIN
    IF v_vagas_restantes <= 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Número de vagas deve ser maior que zero.');
    END IF;

    IF v_evento_id IS NULL THEN
        RAISE_APPLICATION_ERROR(-20002, 'ID do evento não pode ser nulo.');
    END IF;

    OPEN c_waitlist;

    LOOP
        EXIT WHEN v_vagas_restantes = 0;
        FETCH c_waitlist INTO r_inscricao;
        EXIT WHEN c_waitlist%NOTFOUND;

        UPDATE INSCRICOES
        SET    STATUS = 'CONFIRMADO'
        WHERE  CURRENT OF c_waitlist;

        INSERT INTO HISTORICO_STATUS (
            INSCRICAO_ID,
            STATUS_ANTES,
            STATUS_DEPOIS,
            MOTIVO
        ) VALUES (
            r_inscricao.inscricao_id,
            'WAITLIST',
            'CONFIRMADO',
            'Promoção automática — Prioridade ' || r_inscricao.PRIORIDADE ||
            ' | Usuário: ' || r_inscricao.NOME ||
            ' (' || r_inscricao.EMAIL || ')'
        );

        v_promovidos      := v_promovidos + 1;
        v_vagas_restantes := v_vagas_restantes - 1;
    END LOOP;

    CLOSE c_waitlist;
    COMMIT;

    :p_promovidos := v_promovidos;
    :p_erro       := NULL;

EXCEPTION
    WHEN OTHERS THEN
        IF c_waitlist%ISOPEN THEN
            CLOSE c_waitlist;
        END IF;
        ROLLBACK;
        v_erro_msg    := SQLERRM;
        :p_promovidos := -1;
        :p_erro       := v_erro_msg;
END;
"""

QUERY_RELATORIO = """
SELECT
    h.ID, h.INSCRICAO_ID,
    u.NOME, u.EMAIL, u.PRIORIDADE,
    h.STATUS_ANTES, h.STATUS_DEPOIS,
    TO_CHAR(h.DATA_REGISTRO, 'DD/MM/YYYY HH24:MI:SS') AS data_registro
FROM
    HISTORICO_STATUS h
    JOIN INSCRICOES  i ON i.ID  = h.INSCRICAO_ID
    JOIN USUARIOS    u ON u.ID  = i.USUARIO_ID
WHERE
    i.EVENTO_ID     = :p_evento_id
    AND h.STATUS_DEPOIS = 'CONFIRMADO'
ORDER BY
    u.PRIORIDADE DESC, h.DATA_REGISTRO ASC
"""

QUERY_RESUMO = """
SELECT
    NVL(SUM(CASE WHEN u.PRIORIDADE = 3 THEN 1 ELSE 0 END), 0),
    NVL(SUM(CASE WHEN u.PRIORIDADE = 2 THEN 1 ELSE 0 END), 0),
    NVL(SUM(CASE WHEN u.PRIORIDADE = 1 THEN 1 ELSE 0 END), 0),
    COUNT(*)
FROM INSCRICOES i JOIN USUARIOS u ON u.ID = i.USUARIO_ID
WHERE i.EVENTO_ID = :p_evento_id AND i.STATUS = 'CONFIRMADO'
"""

QUERY_WAITLIST = """
SELECT COUNT(*) FROM INSCRICOES
WHERE EVENTO_ID = :p_evento_id AND STATUS = 'WAITLIST'
"""

# ──────────────────────────────────────────────
# HTML TEMPLATE
# ──────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Grand Tech Gala — Motor de Fila</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --gold:    #c9a84c;
    --gold-lt: #e8cc7a;
    --cream:   #f5efe0;
    --charcoal:#1a1814;
    --deep:    #0d0c0a;
    --muted:   #7a7060;
    --platinum:#e8e4dc;
    --vip:     #6ab0d4;
    --normal:  #8a9a7a;
    --confirm: #4caf7a;
    --glass:   rgba(201,168,76,0.07);
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--deep);
    color: var(--cream);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* ── noise grain overlay ── */
  body::before {
    content: '';
    position: fixed; inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
    pointer-events: none; z-index: 0; opacity: 0.4;
  }

  .wrapper { position: relative; z-index: 1; max-width: 960px; margin: 0 auto; padding: 40px 24px 80px; }

  /* ── header ── */
  header { text-align: center; padding: 60px 0 50px; border-bottom: 1px solid rgba(201,168,76,0.2); margin-bottom: 50px; }
  .badge {
    display: inline-block; font-size: 10px; letter-spacing: 3px; text-transform: uppercase;
    color: var(--gold); border: 1px solid rgba(201,168,76,0.4); padding: 6px 18px;
    margin-bottom: 28px;
  }
  header h1 {
    font-family: 'Cormorant Garamond', serif;
    font-size: clamp(2.4rem, 5vw, 4rem);
    font-weight: 300; letter-spacing: 2px; line-height: 1.1;
    color: var(--cream);
  }
  header h1 span { color: var(--gold); font-style: italic; }
  header p { color: var(--muted); margin-top: 14px; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; }

  /* ── cards ── */
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 32px; }
  @media(max-width:620px){ .grid{ grid-template-columns:1fr; } }

  .card {
    background: var(--glass);
    border: 1px solid rgba(201,168,76,0.15);
    padding: 28px 24px;
  }
  .card-label { font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: var(--gold); margin-bottom: 12px; }
  .card input {
    width: 100%; background: rgba(0,0,0,0.3); border: 1px solid rgba(201,168,76,0.2);
    color: var(--cream); font-family: 'JetBrains Mono', monospace; font-size: 18px;
    padding: 12px 14px; outline: none; transition: border-color .2s;
  }
  .card input:focus { border-color: var(--gold); }
  .card small { display: block; color: var(--muted); font-size: 10px; margin-top: 8px; }

  /* ── legend ── */
  .legend { display:flex; gap:24px; flex-wrap:wrap; margin-bottom:28px; }
  .legend-item { display:flex; align-items:center; gap:8px; font-size:11px; color: var(--muted); }
  .dot { width:10px; height:10px; border-radius:50%; }
  .dot.platinum { background: var(--gold); }
  .dot.vip      { background: var(--vip); }
  .dot.normal   { background: var(--normal); }

  /* ── button ── */
  .btn-exec {
    width:100%; padding: 18px;
    background: transparent;
    border: 1px solid var(--gold);
    color: var(--gold);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; letter-spacing: 3px; text-transform: uppercase;
    cursor: pointer; transition: all .25s; position: relative; overflow: hidden;
  }
  .btn-exec::before {
    content:''; position:absolute; inset:0;
    background: var(--gold); transform: scaleX(0); transform-origin: left;
    transition: transform .3s ease;
  }
  .btn-exec:hover::before { transform: scaleX(1); }
  .btn-exec:hover { color: var(--deep); }
  .btn-exec span { position:relative; z-index:1; }
  .btn-exec:disabled { opacity:.4; cursor:not-allowed; }

  /* ── status bar ── */
  #status-bar {
    margin: 28px 0;
    padding: 16px 20px;
    border-left: 3px solid var(--gold);
    background: rgba(201,168,76,0.06);
    font-size: 11px; letter-spacing: 1px;
    display: none;
  }
  #status-bar.error { border-color: #e05c5c; background: rgba(224,92,92,0.06); color: #e05c5c; }
  #status-bar.success { border-color: var(--confirm); }

  /* ── summary chips ── */
  #summary { display:none; margin-bottom:32px; }
  .chips { display:flex; gap:12px; flex-wrap:wrap; margin-top:16px; }
  .chip {
    padding: 10px 20px; font-size:11px; letter-spacing:1px;
    border: 1px solid;
  }
  .chip.platinum { border-color: var(--gold);    color: var(--gold); }
  .chip.vip      { border-color: var(--vip);     color: var(--vip); }
  .chip.normal   { border-color: var(--normal);  color: var(--normal); }
  .chip.total    { border-color: var(--confirm); color: var(--confirm); }
  .chip .num     { font-size:22px; display:block; font-family:'Cormorant Garamond',serif; font-weight:300; }

  /* ── table ── */
  #results { display:none; }
  .section-title {
    font-size: 9px; letter-spacing:3px; text-transform:uppercase;
    color: var(--gold); margin-bottom:16px;
    display:flex; align-items:center; gap:12px;
  }
  .section-title::after { content:''; flex:1; height:1px; background:rgba(201,168,76,0.15); }

  table { width:100%; border-collapse:collapse; }
  thead tr { border-bottom: 1px solid rgba(201,168,76,0.25); }
  thead th {
    text-align:left; padding:10px 12px;
    font-size:9px; letter-spacing:2px; text-transform:uppercase; color:var(--gold);
    font-weight:400;
  }
  tbody tr { border-bottom: 1px solid rgba(255,255,255,0.04); transition: background .15s; }
  tbody tr:hover { background: rgba(201,168,76,0.04); }
  tbody td { padding: 12px; font-size:12px; color: var(--cream); vertical-align:middle; }

  .prio-badge {
    display:inline-flex; align-items:center; gap:6px;
    padding:3px 10px; font-size:10px; letter-spacing:1px;
    border: 1px solid;
  }
  .prio-badge.p3 { border-color:var(--gold);   color:var(--gold); }
  .prio-badge.p2 { border-color:var(--vip);    color:var(--vip); }
  .prio-badge.p1 { border-color:var(--normal); color:var(--normal); }

  .status-pill {
    display:inline-block; padding:3px 10px; font-size:10px;
    background: rgba(76,175,122,0.12); color:var(--confirm);
    border: 1px solid rgba(76,175,122,0.3); letter-spacing:1px;
  }

  /* ── spinner ── */
  .spinner { display:inline-block; width:14px; height:14px; border:2px solid rgba(201,168,76,0.2); border-top-color:var(--gold); border-radius:50%; animation:spin .7s linear infinite; vertical-align:middle; margin-right:8px; }
  @keyframes spin { to{ transform:rotate(360deg); } }

  /* ── footer ── */
  footer { text-align:center; margin-top:70px; padding-top:30px; border-top:1px solid rgba(255,255,255,0.06); }
  footer p { color:var(--muted); font-size:10px; letter-spacing:1.5px; line-height:2; }

  /* ── plsql block ── */
  .code-block {
    margin-top:40px;
    background: rgba(0,0,0,0.4);
    border: 1px solid rgba(201,168,76,0.1);
    padding: 24px;
    overflow-x: auto;
  }
  .code-block pre {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    line-height: 1.8;
    color: #a89f8c;
    white-space: pre;
  }
  .kw  { color: #c9a84c; }
  .cm  { color: #5a5448; font-style:italic; }
  .str { color: #7aad8a; }
  .fn  { color: #7ab8d4; }
</style>
</head>
<body>
<div class="wrapper">

  <header>
    <div class="badge">FIAP · Mastering Databases · Checkpoint 2</div>
    <h1>The Grand<br><span>Tech Gala</span></h1>
    <p>Motor PL/SQL · Promoção Inteligente de Fila de Espera</p>
  </header>

  <!-- FORM -->
  <div class="grid">
    <div class="card">
      <div class="card-label">ID do Evento</div>
      <input type="number" id="evento_id" placeholder="Ex: 1001" min="1">
      <small>Identificador único do evento no banco Oracle</small>
    </div>
    <div class="card">
      <div class="card-label">Vagas para Liberar</div>
      <input type="number" id="n_vagas" placeholder="Ex: 5" min="1">
      <small>Quantas inscrições WAITLIST serão promovidas</small>
    </div>
  </div>

  <div class="legend">
    <div class="legend-item"><div class="dot platinum"></div> Platinum — Prioridade 3</div>
    <div class="legend-item"><div class="dot vip"></div> VIP — Prioridade 2</div>
    <div class="legend-item"><div class="dot normal"></div> Normal — Prioridade 1</div>
  </div>

  <button class="btn-exec" id="btn" onclick="executar()">
    <span>⚡ Executar Processo PL/SQL</span>
  </button>

  <!-- STATUS -->
  <div id="status-bar"></div>

  <!-- SUMMARY -->
  <div id="summary">
    <div class="section-title">Resumo de Confirmados — Evento</div>
    <div class="chips" id="chips"></div>
  </div>

  <!-- TABLE -->
  <div id="results">
    <div class="section-title" style="margin-top:36px">Log de Promoções — HISTORICO_STATUS</div>
    <table>
      <thead>
        <tr>
          <th>Log ID</th>
          <th>Inscrição</th>
          <th>Prioridade</th>
          <th>Nome</th>
          <th>Email</th>
          <th>Status</th>
          <th>Data/Hora</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <!-- CÓDIGO PL/SQL EXIBIDO NA PÁGINA -->
  <div class="code-block">
    <div class="section-title" style="margin-bottom:20px">Bloco Anônimo PL/SQL Executado</div>
    <pre><span class="cm">-- Cursor Explícito + JOIN + FOR UPDATE OF + HISTORICO_STATUS</span>
<span class="kw">DECLARE</span>
    v_vagas_restantes  <span class="fn">NUMBER</span>  := :p_vagas;
    v_evento_id        <span class="fn">NUMBER</span>  := :p_evento_id;
    v_promovidos       <span class="fn">NUMBER</span>  := 0;

    <span class="cm">-- ► CURSOR EXPLÍCITO com JOIN e ordenação obrigatória</span>
    <span class="kw">CURSOR</span> c_waitlist <span class="kw">IS</span>
        <span class="kw">SELECT</span> i.ID, i.USUARIO_ID, i.STATUS, i.DATA_INSCRICAO,
               u.NOME, u.EMAIL, u.PRIORIDADE
        <span class="kw">FROM</span>   INSCRICOES i
               <span class="kw">JOIN</span> USUARIOS u <span class="kw">ON</span> u.ID = i.USUARIO_ID
        <span class="kw">WHERE</span>  i.EVENTO_ID = v_evento_id
               <span class="kw">AND</span> i.STATUS = <span class="str">'WAITLIST'</span>
        <span class="kw">ORDER BY</span>
               u.PRIORIDADE    <span class="kw">DESC</span>,   <span class="cm">-- Platinum→VIP→Normal</span>
               i.DATA_INSCRICAO <span class="kw">ASC</span>    <span class="cm">-- FIFO dentro da prioridade</span>
        <span class="kw">FOR UPDATE OF</span> i.STATUS;   <span class="cm">-- Bloqueia para consistência</span>

    r_inscricao c_waitlist<span class="kw">%ROWTYPE</span>;

<span class="kw">BEGIN</span>
    <span class="kw">OPEN</span> c_waitlist;
    <span class="kw">LOOP</span>
        <span class="kw">EXIT WHEN</span> v_vagas_restantes = 0;
        <span class="kw">FETCH</span> c_waitlist <span class="kw">INTO</span> r_inscricao;
        <span class="kw">EXIT WHEN</span> c_waitlist<span class="kw">%NOTFOUND</span>;

        <span class="cm">-- Promove a inscrição</span>
        <span class="kw">UPDATE</span> INSCRICOES <span class="kw">SET</span> STATUS = <span class="str">'CONFIRMADO'</span>
        <span class="kw">WHERE CURRENT OF</span> c_waitlist;

        <span class="cm">-- Registra log automático</span>
        <span class="kw">INSERT INTO</span> HISTORICO_STATUS
            (INSCRICAO_ID, STATUS_ANTES, STATUS_DEPOIS, MOTIVO)
        <span class="kw">VALUES</span>
            (r_inscricao.ID, <span class="str">'WAITLIST'</span>, <span class="str">'CONFIRMADO'</span>,
             <span class="str">'Promoção automática — Prioridade '</span> || r_inscricao.PRIORIDADE);

        v_promovidos      := v_promovidos + 1;
        v_vagas_restantes := v_vagas_restantes - 1;
    <span class="kw">END LOOP</span>;
    <span class="kw">CLOSE</span> c_waitlist;
    <span class="kw">COMMIT</span>;                 <span class="cm">-- Persiste tudo</span>
<span class="kw">EXCEPTION</span>
    <span class="kw">WHEN OTHERS THEN</span>
        <span class="kw">IF</span> c_waitlist<span class="kw">%ISOPEN THEN CLOSE</span> c_waitlist; <span class="kw">END IF</span>;
        <span class="kw">ROLLBACK</span>;           <span class="cm">-- Desfaz em caso de falha</span>
        :p_erro := <span class="fn">SQLERRM</span>;
<span class="kw">END</span>;</pre>
  </div>

  <footer>
    <p>FIAP · Mastering Relational and Non Relational Databases<br>
    Professor Renê Mendes · 2026 · Checkpoint 2<br>
    Oracle: oracle.fiap.com.br:1521/orcl</p>
  </footer>
</div>

<script>
async function executar() {
  const eventoId = document.getElementById('evento_id').value;
  const nVagas   = document.getElementById('n_vagas').value;
  const btn      = document.getElementById('btn');
  const statusBar= document.getElementById('status-bar');

  if (!eventoId || !nVagas || parseInt(nVagas) <= 0) {
    mostrarStatus('⚠️  Preencha o ID do evento e um número de vagas válido.', 'error');
    return;
  }

  btn.disabled = true;
  btn.querySelector('span').innerHTML = '<span class="spinner"></span> Executando bloco PL/SQL...';
  mostrarStatus('<span class="spinner"></span> Conectando ao Oracle e executando...', '');

  document.getElementById('summary').style.display = 'none';
  document.getElementById('results').style.display  = 'none';

  try {
    const resp = await fetch('/executar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ evento_id: parseInt(eventoId), n_vagas: parseInt(nVagas) })
    });
    const data = await resp.json();

    if (data.erro) {
      mostrarStatus('❌  Erro Oracle: ' + data.erro, 'error');
    } else {
      mostrarStatus(
        `✅  Processo concluído — ${data.promovidos} inscrição(ões) promovida(s) | ${data.waitlist_restante} na fila restante`,
        'success'
      );
      renderizarSummary(data.resumo);
      renderizarTabela(data.rows);
    }
  } catch(e) {
    mostrarStatus('❌  Falha na requisição: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.querySelector('span').innerHTML = '⚡ Executar Processo PL/SQL';
  }
}

function mostrarStatus(msg, tipo) {
  const bar = document.getElementById('status-bar');
  bar.innerHTML = msg;
  bar.className = tipo;
  bar.style.display = 'block';
}

function renderizarSummary(resumo) {
  if (!resumo) return;
  const [platinum, vip, normal, total] = resumo;
  document.getElementById('chips').innerHTML = `
    <div class="chip platinum"><span class="num">${platinum}</span>🟡 Platinum</div>
    <div class="chip vip"><span class="num">${vip}</span>🔵 VIP</div>
    <div class="chip normal"><span class="num">${normal}</span>⚪ Normal</div>
    <div class="chip total"><span class="num">${total}</span>Total Confirmados</div>
  `;
  document.getElementById('summary').style.display = 'block';
}

function renderizarTabela(rows) {
  if (!rows || rows.length === 0) return;
  const prioLabel = {3:'Platinum', 2:'VIP', 1:'Normal'};
  const prioClass = {3:'p3', 2:'p2', 1:'p1'};
  const prioIcon  = {3:'🟡', 2:'🔵', 1:'⚪'};

  const html = rows.map(r => {
    const [logId, insId, nome, email, prio, antes, depois, data] = r;
    return `<tr>
      <td>${logId}</td>
      <td>${insId}</td>
      <td><span class="prio-badge ${prioClass[prio]}">${prioIcon[prio]} ${prioLabel[prio]}</span></td>
      <td>${nome}</td>
      <td style="color:var(--muted);font-size:11px">${email}</td>
      <td><span class="status-pill">CONFIRMADO</span></td>
      <td style="color:var(--muted);font-size:11px">${data}</td>
    </tr>`;
  }).join('');

  document.getElementById('tbody').innerHTML = html;
  document.getElementById('results').style.display = 'block';
}
</script>
</body>
</html>"""

# ──────────────────────────────────────────────
# ROTAS FLASK
# ──────────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/executar", methods=["POST"])
def executar():
    body      = request.get_json()
    evento_id = body.get("evento_id")
    n_vagas   = body.get("n_vagas")

    if not evento_id or not n_vagas or n_vagas <= 0:
        return jsonify({"erro": "Parâmetros inválidos."}), 400

    try:
        connection = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
        cursor     = connection.cursor()

        out_promovidos = cursor.var(oracledb.NUMBER)
        out_erro       = cursor.var(oracledb.STRING)

        cursor.execute(
            PLSQL_PROMOVER_FILA,
            p_vagas     = n_vagas,
            p_evento_id = evento_id,
            p_promovidos= out_promovidos,
            p_erro      = out_erro
        )

        promovidos = int(out_promovidos.getvalue() or 0)
        erro       = out_erro.getvalue()

        if erro:
            return jsonify({"erro": erro})

        # Relatório
        cursor.execute(QUERY_RELATORIO, p_evento_id=evento_id)
        rows = cursor.fetchall()

        cursor.execute(QUERY_RESUMO, p_evento_id=evento_id)
        resumo_row = cursor.fetchone()

        cursor.execute(QUERY_WAITLIST, p_evento_id=evento_id)
        wl = cursor.fetchone()
        waitlist_restante = wl[0] if wl else 0

        cursor.close()
        connection.close()

        return jsonify({
            "promovidos":        promovidos,
            "waitlist_restante": waitlist_restante,
            "resumo":            list(resumo_row) if resumo_row else None,
            "rows":              [list(r) for r in rows],
            "erro":              None
        })

    except oracledb.DatabaseError as e:
        error, = e.args
        return jsonify({"erro": f"Oracle {error.code}: {error.message}"})
    except Exception as e:
        return jsonify({"erro": str(e)})


if __name__ == "__main__":
    print("=" * 60)
    print("  THE GRAND TECH GALA — Interface Web")
    print("  Acesse: http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, port=5000)