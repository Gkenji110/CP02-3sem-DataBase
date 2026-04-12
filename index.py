import json
import os
from http.server import BaseHTTPRequestHandler

import oracledb

DB_USER     = os.environ.get("DB_USER",     "seu_usuario")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "sua_senha")
DB_DSN      = os.environ.get("DB_DSN",      "oracle.fiap.com.br:1521/orcl")

oracledb.defaults.fetch_lobs = False


PLSQL_PROMOVER_FILA = """
DECLARE
    v_vagas_restantes  NUMBER  := :p_vagas;
    v_evento_id        NUMBER  := :p_evento_id;
    v_promovidos       NUMBER  := 0;

    -- ► Cursor Explícito com JOIN entre INSCRICOES e USUARIOS
    --   Ordenado por PRIORIDADE (DESC) e DATA_INSCRICAO (ASC)
    --   Bloqueado com FOR UPDATE OF i.STATUS para consistência
    CURSOR c_waitlist IS
        SELECT
            i.ID             AS inscricao_id,
            i.DATA_INSCRICAO,
            u.NOME,
            u.EMAIL,
            u.PRIORIDADE
        FROM
            INSCRICOES  i
            JOIN USUARIOS u ON u.ID = i.USUARIO_ID
        WHERE
            i.EVENTO_ID = v_evento_id
            AND i.STATUS = 'WAITLIST'
        ORDER BY
            u.PRIORIDADE     DESC,
            i.DATA_INSCRICAO ASC
        FOR UPDATE OF i.STATUS;

    r c_waitlist%ROWTYPE;

BEGIN
    IF v_evento_id IS NULL OR v_vagas_restantes <= 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Parâmetros inválidos.');
    END IF;

    OPEN c_waitlist;
    LOOP
        EXIT WHEN v_vagas_restantes = 0;
        FETCH c_waitlist INTO r;
        EXIT WHEN c_waitlist%NOTFOUND;

        UPDATE INSCRICOES
           SET STATUS = 'CONFIRMADO'
         WHERE CURRENT OF c_waitlist;

        INSERT INTO HISTORICO_STATUS (INSCRICAO_ID, STATUS_ANTES, STATUS_DEPOIS, MOTIVO)
        VALUES (
            r.inscricao_id,
            'WAITLIST',
            'CONFIRMADO',
            'Promoção automática — Prioridade ' || r.PRIORIDADE ||
            ' | ' || r.NOME || ' <' || r.EMAIL || '>'
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
        IF c_waitlist%ISOPEN THEN CLOSE c_waitlist; END IF;
        ROLLBACK;
        :p_promovidos := -1;
        :p_erro       := SQLERRM;
END;
"""

QUERY_LOG = """
SELECT
    h.ID, h.INSCRICAO_ID,
    u.NOME, u.EMAIL, u.PRIORIDADE,
    h.STATUS_ANTES, h.STATUS_DEPOIS,
    TO_CHAR(h.DATA_REGISTRO, 'DD/MM/YYYY HH24:MI:SS') AS DATA_REGISTRO
FROM
    HISTORICO_STATUS h
    JOIN INSCRICOES  i ON i.ID = h.INSCRICAO_ID
    JOIN USUARIOS    u ON u.ID = i.USUARIO_ID
WHERE
    i.EVENTO_ID     = :p_evento_id
    AND h.STATUS_DEPOIS = 'CONFIRMADO'
ORDER BY u.PRIORIDADE DESC, h.DATA_REGISTRO ASC
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

QUERY_WAITLIST_RESTANTE = """
SELECT COUNT(*) FROM INSCRICOES
WHERE EVENTO_ID = :p_evento_id AND STATUS = 'WAITLIST'
"""


def _executar_promocao(evento_id: int, n_vagas: int) -> dict:
    """Conecta ao Oracle (modo Thin) e executa o bloco PL/SQL."""
    conn   = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
    cursor = conn.cursor()

    out_promovidos = cursor.var(oracledb.NUMBER)
    out_erro       = cursor.var(oracledb.STRING)

    cursor.execute(
        PLSQL_PROMOVER_FILA,
        p_vagas      = n_vagas,
        p_evento_id  = evento_id,
        p_promovidos = out_promovidos,
        p_erro       = out_erro,
    )

    promovidos = int(out_promovidos.getvalue() or 0)
    erro       = out_erro.getvalue()

    if erro:
        cursor.close(); conn.close()
        return {"erro": erro}

    cursor.execute(QUERY_LOG,               p_evento_id=evento_id)
    rows = [list(r) for r in cursor.fetchall()]

    cursor.execute(QUERY_RESUMO,            p_evento_id=evento_id)
    resumo = list(cursor.fetchone())

    cursor.execute(QUERY_WAITLIST_RESTANTE, p_evento_id=evento_id)
    waitlist_restante = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return {
        "promovidos":        promovidos,
        "waitlist_restante": int(waitlist_restante),
        "resumo":            resumo,
        "rows":              rows,
        "erro":              None,
    }


class handler(BaseHTTPRequestHandler):

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path != "/api/executar":
            self._send_json(404, {"erro": "Rota não encontrada."})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body      = json.loads(self.rfile.read(length))
            evento_id = int(body.get("evento_id", 0))
            n_vagas   = int(body.get("n_vagas",   0))
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"erro": "JSON inválido."})
            return

        if not evento_id or n_vagas <= 0:
            self._send_json(400, {"erro": "Parâmetros inválidos."})
            return

        try:
            result = _executar_promocao(evento_id, n_vagas)
            self._send_json(200, result)
        except oracledb.DatabaseError as e:
            error, = e.args
            self._send_json(500, {"erro": f"Oracle {error.code}: {error.message}"})
        except Exception as e:
            self._send_json(500, {"erro": str(e)})

    def do_GET(self):
        self._send_json(405, {"erro": "Use POST em /api/executar"})