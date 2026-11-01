"""Escreve mcp-config.json com os caminhos desta pasta, no formato que Claude Desktop,
Claude Code, LM Studio, Cursor e VS Code aceitam ("mcpServers"), e o mostra na tela.

Depois oferece registrar a Bridge sozinho nos clientes encontrados (LM Studio e Claude
Desktop): so acrescenta a entrada "blender-bridge", mantem os outros servidores e guarda
uma copia .bak do arquivo antes. BRIDGE_TESTE_HOME troca a pasta do usuario (testes).
"""
import json
import os
import pathlib
import shutil

PASTA = pathlib.Path(__file__).resolve().parent
NOME = "blender-bridge"
ENTRADA = {
    "command": str(PASTA / ".venv" / "Scripts" / "python.exe"),
    "args": ["-m", "blender_bridge_mcp"],
    "env": {"PYTHONPATH": str(PASTA), "EDITOR_URL": "http://127.0.0.1:8600"},
}


def clientes() -> list[tuple[str, pathlib.Path]]:
    """Os clientes MCP instalados neste PC e o arquivo de configuracao de cada um."""
    casa = pathlib.Path(os.environ.get("BRIDGE_TESTE_HOME") or pathlib.Path.home())
    roaming = pathlib.Path(os.environ.get("APPDATA") or casa / "AppData" / "Roaming")
    if os.environ.get("BRIDGE_TESTE_HOME"):
        roaming = casa / "AppData" / "Roaming"
    achados = []
    if (casa / ".lmstudio").is_dir():
        achados.append(("LM Studio", casa / ".lmstudio" / "mcp.json"))
    if (roaming / "Claude").is_dir():
        achados.append(("Claude Desktop", roaming / "Claude" / "claude_desktop_config.json"))
    return achados


def registrar(arquivo: pathlib.Path) -> str:
    dados = {}
    if arquivo.exists():
        texto = arquivo.read_text(encoding="utf-8").strip()
        if texto:
            dados = json.loads(texto)  # JSON quebrado: para aqui e nao estraga nada
        shutil.copy2(arquivo, arquivo.with_name(arquivo.name + ".bak"))
    servidores = dados.setdefault("mcpServers", {})
    acao = "updated" if NOME in servidores else "added"
    servidores[NOME] = ENTRADA
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    return acao


def main():
    texto = json.dumps({"mcpServers": {NOME: ENTRADA}}, indent=2)
    (PASTA.parent / "mcp-config.json").write_text(texto, encoding="utf-8")
    print(texto)
    achados = clientes()
    if not achados:
        print("\nNo LM Studio or Claude Desktop found: paste the entry above into your MCP client.")
        return
    print()
    for nome, arquivo in achados:
        try:
            resposta = input(f"Add the Bridge to {nome} automatically? [Y/n] ").strip().lower()
        except EOFError:
            resposta = "n"
        if resposta not in ("", "y", "yes", "s", "sim"):
            continue
        try:
            acao = registrar(arquivo)
        except (OSError, ValueError) as e:
            print(f"  Could not change {arquivo}: {e}. Paste the entry above by hand.")
            continue
        print(f"  {nome}: {acao} (backup next to {arquivo.name}). Restart {nome} to load it.")


if __name__ == "__main__":
    main()
