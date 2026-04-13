import os
import subprocess
import sys


def instalar_dependencias():
    print("📦 Instalando dependências...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])
    print("✅ Dependências instaladas\n")


def verificar_env():
    from dotenv import load_dotenv
    load_dotenv()

    campos_obrigatorios = ["DB_USER", "DB_PASSWORD", "DB_DSN"]
    faltando = [c for c in campos_obrigatorios if not os.getenv(c)]

    if faltando:
        print("❌ Variáveis de ambiente faltando no .env:", ", ".join(faltando))
        print("   Copie o arquivo .env.example para .env e preencha os valores.")
        sys.exit(1)

    print("✅ Arquivo .env encontrado e configurado\n")


def configurar_banco():
    print("🗄️  Configurando banco de dados...")

    import oracledb
    from dotenv import load_dotenv
    load_dotenv()

    oracledb.defaults.fetch_lobs = False

    sql_path = os.path.join(os.path.dirname(__file__), "setupBanco.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        conteudo = f.read()

    blocos = []
    bloco_atual = []
    for linha in conteudo.splitlines():
        if linha.strip() == "/":
            bloco = "\n".join(bloco_atual).strip()
            if bloco:
                blocos.append(bloco)
            bloco_atual = []
        else:
            bloco_atual.append(linha)

    resto = "\n".join(bloco_atual)
    for stmt in resto.split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.upper().startswith("SELECT"):
            blocos.append(stmt)

    conn = oracledb.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dsn=os.getenv("DB_DSN"),
    )
    cursor = conn.cursor()
    for bloco in blocos:
        if bloco.strip():
            cursor.execute(bloco)
    conn.commit()
    cursor.close()
    conn.close()

    print("✅ Tabelas criadas e dados de exemplo inseridos\n")


def iniciar_flask():
    print("🚀 Iniciando o servidor Flask...")
    print("   Acesse: http://localhost:5000\n")
    print("   (Pressione Ctrl+C para parar)\n")

    app_path = os.path.join(os.path.dirname(__file__), "api", "app.py")
    os.execv(sys.executable, [sys.executable, app_path])


if __name__ == "__main__":
    print("=" * 50)
    print("  Grand Tech Gala — Setup e Inicialização")
    print("=" * 50)
    print()

    instalar_dependencias()
    verificar_env()
    configurar_banco()
    iniciar_flask()
