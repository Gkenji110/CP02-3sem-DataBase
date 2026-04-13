import os

import oracledb
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

load_dotenv()

DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_DSN      = os.getenv("DB_DSN")

oracledb.defaults.fetch_lobs = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
CORS(app)

GALA_NOME        = "Grand Tech Gala 2026"
GALA_LOCAL       = "Centro de Convencoes SP"
GALA_DATA        = "15/12/2026"
GALA_TOTAL_VAGAS = 100


PLSQL_PROMOVER_FILA = """
DECLARE
    v_vagas_restantes  NUMBER := :p_vagas;
    v_promovidos       NUMBER := 0;

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
            i.STATUS = 'WAITLIST'
        ORDER BY
            u.PRIORIDADE     DESC,
            i.DATA_INSCRICAO ASC
        FOR UPDATE OF i.STATUS;

    r c_waitlist%ROWTYPE;

BEGIN
    IF v_vagas_restantes <= 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Parametros invalidos.');
    END IF;

    OPEN c_waitlist;
    LOOP
        EXIT WHEN v_vagas_restantes = 0;
        FETCH c_waitlist INTO r;
        EXIT WHEN c_waitlist%NOTFOUND;

        UPDATE INSCRICOES
           SET STATUS = 'CONFIRMADO'
         WHERE CURRENT OF c_waitlist;

        INSERT INTO HISTORICO_STATUS (INSCRICAO_ID, STATUS_ANTERIOR, STATUS_NOVO, MOTIVO)
        VALUES (
            r.inscricao_id,
            'WAITLIST',
            'CONFIRMADO',
            'Promocao automatica - Prioridade ' || r.PRIORIDADE ||
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

QUERY_LOG_PROMOCOES = """
SELECT
    h.ID, h.INSCRICAO_ID,
    u.NOME, u.EMAIL, u.PRIORIDADE,
    h.STATUS_ANTERIOR, h.STATUS_NOVO,
    TO_CHAR(h.DATA, 'DD/MM/YYYY HH24:MI:SS') AS DATA
FROM
    HISTORICO_STATUS h
    JOIN INSCRICOES  i ON i.ID = h.INSCRICAO_ID
    JOIN USUARIOS    u ON u.ID = i.USUARIO_ID
WHERE
    h.STATUS_NOVO = 'CONFIRMADO'
ORDER BY u.PRIORIDADE DESC, h.DATA ASC
"""

QUERY_RESUMO_CONFIRMADOS = """
SELECT
    NVL(SUM(CASE WHEN u.PRIORIDADE = 3 THEN 1 ELSE 0 END), 0),
    NVL(SUM(CASE WHEN u.PRIORIDADE = 2 THEN 1 ELSE 0 END), 0),
    NVL(SUM(CASE WHEN u.PRIORIDADE = 1 THEN 1 ELSE 0 END), 0),
    COUNT(*)
FROM INSCRICOES i JOIN USUARIOS u ON u.ID = i.USUARIO_ID
WHERE i.STATUS = 'CONFIRMADO'
"""

QUERY_WAITLIST_RESTANTE = """
SELECT COUNT(*) FROM INSCRICOES
WHERE STATUS = 'WAITLIST'
"""

QUERY_CONTAGEM_GALA = """
SELECT
    COUNT(CASE WHEN STATUS = 'CONFIRMADO' THEN 1 END) AS CONFIRMADOS,
    COUNT(CASE WHEN STATUS = 'WAITLIST'   THEN 1 END) AS NA_FILA
FROM INSCRICOES
"""

QUERY_LISTAR_USUARIOS_DISPONIVEIS = """
SELECT ID, NOME, EMAIL, PRIORIDADE, SALDO
FROM USUARIOS
WHERE ID NOT IN (
    SELECT USUARIO_ID FROM INSCRICOES
    WHERE STATUS IN ('CONFIRMADO', 'WAITLIST')
)
ORDER BY PRIORIDADE DESC, NOME ASC
"""


QUERY_LISTAR_USUARIOS = """
SELECT ID, NOME, EMAIL, PRIORIDADE, SALDO
FROM USUARIOS
ORDER BY PRIORIDADE DESC, NOME ASC
"""

QUERY_FILA_WAITLIST = """
SELECT
    i.ID AS INSCRICAO_ID,
    u.NOME,
    u.EMAIL,
    u.PRIORIDADE,
    TO_CHAR(i.DATA_INSCRICAO, 'DD/MM/YYYY HH24:MI') AS DATA_INSCRICAO
FROM INSCRICOES i
JOIN USUARIOS u ON u.ID = i.USUARIO_ID
WHERE i.STATUS = 'WAITLIST'
ORDER BY u.PRIORIDADE DESC, i.DATA_INSCRICAO ASC
"""

QUERY_VERIFICAR_INSCRICAO = """
SELECT COUNT(*) FROM INSCRICOES
WHERE USUARIO_ID = :p_usuario_id AND STATUS != 'CANCELADO'
"""

QUERY_CONFIRMADOS_EVENTO = """
SELECT
    i.ID AS INSCRICAO_ID,
    u.NOME,
    u.EMAIL,
    u.PRIORIDADE
FROM INSCRICOES i
JOIN USUARIOS u ON u.ID = i.USUARIO_ID
WHERE i.STATUS = 'CONFIRMADO'
ORDER BY u.PRIORIDADE DESC, i.DATA_INSCRICAO ASC
"""


def conectar():
    return oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/gala_info", methods=["GET"])
def gala_info():
    try:
        conn   = conectar()
        cursor = conn.cursor()
        cursor.execute(QUERY_CONTAGEM_GALA)
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        confirmados = int(row[0])
        na_fila     = int(row[1])
        return jsonify({
            "nome":              GALA_NOME,
            "local":             GALA_LOCAL,
            "data_evento":       GALA_DATA,
            "total_vagas":       GALA_TOTAL_VAGAS,
            "vagas_disponiveis": GALA_TOTAL_VAGAS - confirmados,
            "confirmados":       confirmados,
            "na_fila":           na_fila,
        })
    except oracledb.DatabaseError as e:
        erro, = e.args
        return jsonify({"erro": f"Oracle {erro.code}: {erro.message}"}), 500
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/executar", methods=["POST"])
def executar_promocao():
    dados = request.get_json()
    try:
        n_vagas = int(dados.get("n_vagas", 0))
    except (ValueError, TypeError):
        return jsonify({"erro": "JSON invalido."}), 400

    if n_vagas <= 0:
        return jsonify({"erro": "n_vagas deve ser maior que zero."}), 400

    try:
        conn   = conectar()
        cursor = conn.cursor()

        out_promovidos = cursor.var(oracledb.NUMBER)
        out_erro       = cursor.var(oracledb.STRING)

        cursor.execute(
            PLSQL_PROMOVER_FILA,
            p_vagas      = n_vagas,
            p_promovidos = out_promovidos,
            p_erro       = out_erro,
        )

        promovidos = int(out_promovidos.getvalue() or 0)
        erro       = out_erro.getvalue()

        if erro:
            cursor.close()
            conn.close()
            return jsonify({"erro": erro}), 500

        cursor.execute(QUERY_LOG_PROMOCOES)
        rows = [list(r) for r in cursor.fetchall()]

        cursor.execute(QUERY_RESUMO_CONFIRMADOS)
        resumo = list(cursor.fetchone())

        cursor.execute(QUERY_WAITLIST_RESTANTE)
        waitlist_restante = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return jsonify({
            "promovidos":        promovidos,
            "waitlist_restante": int(waitlist_restante),
            "resumo":            resumo,
            "rows":              rows,
            "erro":              None,
        })

    except oracledb.DatabaseError as e:
        erro, = e.args
        return jsonify({"erro": f"Oracle {erro.code}: {erro.message}"}), 500
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/usuarios", methods=["GET"])
def listar_usuarios():
    filtrar_gala = request.args.get("filtrar_gala", type=int)
    try:
        conn   = conectar()
        cursor = conn.cursor()
        if filtrar_gala:
            cursor.execute(QUERY_LISTAR_USUARIOS_DISPONIVEIS)
        else:
            cursor.execute(QUERY_LISTAR_USUARIOS)
        colunas  = [col[0].lower() for col in cursor.description]
        usuarios = [dict(zip(colunas, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(usuarios)
    except oracledb.DatabaseError as e:
        erro, = e.args
        return jsonify({"erro": f"Oracle {erro.code}: {erro.message}"}), 500
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/inscricoes", methods=["POST"])
def criar_inscricao():
    dados      = request.get_json()
    usuario_id = dados.get("usuario_id")

    if not usuario_id:
        return jsonify({"erro": "usuario_id é obrigatório."}), 400

    try:
        conn   = conectar()
        cursor = conn.cursor()

        cursor.execute(QUERY_VERIFICAR_INSCRICAO, p_usuario_id=usuario_id)
        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            return jsonify({"erro": "Usuário já está inscrito ou confirmado neste evento."}), 409

        cursor.execute(
            "INSERT INTO INSCRICOES (USUARIO_ID, STATUS) VALUES (:p_usuario_id, 'WAITLIST')",
            p_usuario_id=usuario_id,
        )
        conn.commit()

        cursor.execute("SELECT NOME FROM USUARIOS WHERE ID = :id", id=usuario_id)
        nome = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({"nome": nome}), 201
    except oracledb.DatabaseError as e:
        erro, = e.args
        return jsonify({"erro": f"Oracle {erro.code}: {erro.message}"}), 500
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/inscricoes/<int:inscricao_id>", methods=["DELETE"])
def cancelar_inscricao(inscricao_id):
    try:
        conn   = conectar()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE INSCRICOES SET STATUS = 'CANCELADO' WHERE ID = :p_id AND STATUS != 'CANCELADO'",
            p_id=inscricao_id,
        )
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"erro": "Inscricao nao encontrada ou ja cancelada."}), 404
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"ok": True})
    except oracledb.DatabaseError as e:
        erro, = e.args
        return jsonify({"erro": f"Oracle {erro.code}: {erro.message}"}), 500
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/gala_estado", methods=["GET"])
def gala_estado():
    try:
        conn   = conectar()
        cursor = conn.cursor()

        cursor.execute(QUERY_FILA_WAITLIST)
        colunas  = [col[0].lower() for col in cursor.description]
        waitlist = [dict(zip(colunas, row)) for row in cursor.fetchall()]

        cursor.execute(QUERY_CONFIRMADOS_EVENTO)
        colunas     = [col[0].lower() for col in cursor.description]
        confirmados = [dict(zip(colunas, row)) for row in cursor.fetchall()]

        cursor.close()
        conn.close()
        return jsonify({"waitlist": waitlist, "confirmados": confirmados})
    except oracledb.DatabaseError as e:
        erro, = e.args
        return jsonify({"erro": f"Oracle {erro.code}: {erro.message}"}), 500
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/usuarios", methods=["POST"])
def criar_usuario():
    dados      = request.get_json()
    nome       = dados.get("nome", "").strip()
    email      = dados.get("email", "").strip()
    prioridade = int(dados.get("prioridade", 1))
    saldo      = float(dados.get("saldo", 0))

    if not nome or not email:
        return jsonify({"erro": "Nome e email são obrigatórios."}), 400
    if prioridade not in (1, 2, 3):
        return jsonify({"erro": "Prioridade deve ser 1, 2 ou 3."}), 400

    try:
        conn   = conectar()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO USUARIOS (NOME, EMAIL, PRIORIDADE, SALDO) VALUES (:nome, :email, :prio, :saldo)",
            nome=nome, email=email, prio=prioridade, saldo=saldo,
        )
        conn.commit()
        cursor.execute("SELECT MAX(ID) FROM USUARIOS WHERE EMAIL = :email", email=email)
        novo_id = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({"id": novo_id, "nome": nome, "email": email}), 201
    except oracledb.DatabaseError as e:
        erro, = e.args
        return jsonify({"erro": f"Oracle {erro.code}: {erro.message}"}), 500
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/usuarios/<int:usuario_id>", methods=["PUT"])
def editar_usuario(usuario_id):
    dados      = request.get_json()
    nome       = dados.get("nome", "").strip()
    email      = dados.get("email", "").strip()
    prioridade = int(dados.get("prioridade", 1))
    saldo      = float(dados.get("saldo", 0))

    if not nome or not email:
        return jsonify({"erro": "Nome e email são obrigatórios."}), 400
    if prioridade not in (1, 2, 3):
        return jsonify({"erro": "Prioridade deve ser 1, 2 ou 3."}), 400

    try:
        conn   = conectar()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE USUARIOS SET NOME=:nome, EMAIL=:email, PRIORIDADE=:prio, SALDO=:saldo WHERE ID=:id",
            nome=nome, email=email, prio=prioridade, saldo=saldo, id=usuario_id,
        )
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"erro": "Usuário não encontrado."}), 404
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"id": usuario_id, "nome": nome})
    except oracledb.DatabaseError as e:
        erro, = e.args
        return jsonify({"erro": f"Oracle {erro.code}: {erro.message}"}), 500
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/usuarios/<int:usuario_id>", methods=["DELETE"])
def apagar_usuario(usuario_id):
    try:
        conn   = conectar()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM USUARIOS WHERE ID = :id", id=usuario_id)
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"erro": "Usuário não encontrado."}), 404
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"ok": True})
    except oracledb.DatabaseError as e:
        erro, = e.args
        if erro.code == 2292:
            return jsonify({"erro": "Não é possível apagar usuário com inscrições ativas."}), 409
        return jsonify({"erro": f"Oracle {erro.code}: {erro.message}"}), 500
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
