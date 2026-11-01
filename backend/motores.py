"""Vigia de instâncias do motor: garante que só exista um ComfyUI de pé.

Dois motores brigam pela GPU e pela porta. O segundo não consegue tomar a
8188, então fica invisível para o app — mas continua ocupando memória, e pode
ter carregado modelos antes de perder a disputa.

ATENÇÃO ao que conta como duplicata. Um ComfyUI saudável aparece como DOIS
processos com a mesma linha de comando: um supervisor de poucos MB e o filho
dele, que é quem carrega os modelos. Contar processos daria falso positivo
sempre, e matar o "extra" derrubaria o supervisor de uma instância sadia.
O que se conta são ÁRVORES: raiz é o processo cujo pai não é outro motor.

A limpeza é conservadora: derruba apenas a árvore que NÃO contém o dono da
porta. Essa árvore não atende ninguém, então não há geração em curso para
perder. Só quando não há dono nenhum é que fecha tudo e reabre — aí não há o
que preservar mesmo.
"""

import config
import asyncio
import json
import pathlib
import subprocess
import threading
import time

import httpx

PORTA = config.COMFY_PORTA
RAIZ = pathlib.Path(__file__).parent.parent
RELANCADOR = RAIZ / "_interno-subir-motor.vbs"
# Vigiar processos, encerrar duplicados e trocar o perfil de memoria so valem
# onde o app SOBE o proprio motor (o lancador existe). No ComfyUI de outra
# pessoa nada disso roda: encerrar o motor dela seria desastroso.
GERENCIADO = RELANCADOR.exists()
PERFIL_ARQUIVO = RAIZ / "logs/perfil-motor.txt"
_mudanca = threading.Lock()

# Um motor que morre na partida faria o vigia relancar sem parar. A espera
# entre tentativas e maior que o tempo de subida (~20 s), entao uma partida
# sadia nunca cai aqui.
ESPERA_ENTRE_RELANCES = 180.0
# None = ainda nao relancou. Era 0.0: no Windows o time.monotonic() conta desde
# que o PC ligou, entao nos 3 primeiros minutos apos ligar o PC a trava achava
# que tinha acabado de relancar e o motor so subia na checagem seguinte (29/10/2026).
_ultimo_relance: float | None = None

# Instalar nos as vezes precisa do ComfyUI desligado: o pip nao troca um arquivo
# que ele carregou (cv2.pyd do OpenCV, "WinError 5 Acesso negado"; PC de teste,
# 29/10/2026). Enquanto a instalacao dura, o vigia nao o religa por conta propria.
_pausa = threading.Event()

# Quantas checagens seguidas com processo de pe mas ninguem atendendo na porta
# antes de considerar o motor quebrado. Subir leva ~20 s, e com a pasta de
# modelos grande pode passar de um minuto; agir antes disso mataria um motor
# sadio no meio do boot — e, como ele seria relancado, em laco.
CHECAGENS_ANTES_DE_DESISTIR = 3
_sem_dono_seguidas = 0

# Uma chamada só do PowerShell: processo e dono da porta juntos. Duas chamadas
# separadas abririam uma janela onde a lista muda entre elas.
_CONSULTA = r"""
$procs = @(Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
  Where-Object { $_.CommandLine -like '*main.py*' -and $_.CommandLine -like '*PORTA*' } |
  ForEach-Object { @{ pid = $_.ProcessId; pai = $_.ParentProcessId } })
$dono = (Get-NetTCPConnection -State Listen -LocalPort PORTA -ErrorAction SilentlyContinue |
  Select-Object -First 1).OwningProcess
@{ processos = $procs; dono = $dono } | ConvertTo-Json -Depth 4 -Compress
"""


def _powershell(script: str) -> str:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.strip()


def _estado_bruto() -> tuple[dict[int, int], int | None]:
    """Devolve {pid: pid_do_pai} dos motores, e quem escuta na porta."""
    saida = _powershell(_CONSULTA.replace("PORTA", str(PORTA)))
    if not saida:
        return {}, None
    d = json.loads(saida)
    procs = d.get("processos") or []
    # O ConvertTo-Json devolve um objeto só quando há um elemento, não lista.
    if isinstance(procs, dict):
        procs = [procs]
    pais = {int(p["pid"]): int(p.get("pai") or 0) for p in procs if p.get("pid")}
    dono = d.get("dono")
    return pais, int(dono) if dono else None


def _arvores(pais: dict[int, int]) -> dict[int, list[int]]:
    """Agrupa os processos por raiz. Raiz é quem não descende de outro motor."""
    def raiz(pid: int) -> int:
        visto = set()
        while pais.get(pid) in pais and pid not in visto:
            visto.add(pid)
            pid = pais[pid]
        return pid

    grupos: dict[int, list[int]] = {}
    for pid in pais:
        grupos.setdefault(raiz(pid), []).append(pid)
    return grupos


def _encerrar(pids: list[int]) -> None:
    if pids:
        alvos = ",".join(str(p) for p in pids)
        _powershell(f"Stop-Process -Id {alvos} -Force -ErrorAction SilentlyContinue")


def _relancar(forcar=False) -> bool:
    """Sobe o motor destacado desta sessão, via WScript.Shell.

    Um processo criado como filho do backend morreria junto com ele; o VBS é
    o que garante independência — é a mesma técnica do iniciar-oculto.vbs.
    """
    global _ultimo_relance
    if not RELANCADOR.exists():
        return False
    if (not forcar and _ultimo_relance is not None
            and time.monotonic() - _ultimo_relance < ESPERA_ENTRE_RELANCES):
        return False
    _ultimo_relance = time.monotonic()
    # ESPERAR o wscript terminar, e nao só disparar. Ele sai em milissegundos
    # (quem fica de pe e o motor, ja destacado pelo sh.Run). Com Popen havia
    # uma corrida: se este processo saisse antes, o wscript morria junto e o
    # motor nunca chegava a nascer — silenciosamente, porque Popen nao falha.
    try:
        r = subprocess.run(["wscript", str(RELANCADOR)],
                           capture_output=True, text=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:
        return False


def inspecionar() -> dict:
    """Fotografia do estado, sem mexer em nada."""
    try:
        pais, dono = _estado_bruto()
    except Exception as e:
        return {"erro": str(e)[:200], "motores": [], "instancias": 0,
                "dono": None, "duplicado": False}
    # Se o dono da porta escapou do filtro, ele ainda assim e um motor: incluir
    # evita o pior erro possivel aqui, que e concluir "nao ha motor" e subir um
    # segundo por cima de um que esta funcionando.
    if dono and dono not in pais:
        pais[dono] = 0

    grupos = _arvores(pais)
    servindo = next((r for r, membros in grupos.items() if dono in membros), None)
    intrusos = [p for r, membros in grupos.items() if r != servindo for p in membros]
    return {"motores": sorted(pais), "instancias": len(grupos), "dono": dono,
            "servindo": servindo, "intrusos": sorted(intrusos),
            "duplicado": len(grupos) > 1}


def _responde() -> bool:
    """O ComfyUI atende na porta? Pergunta a ele, sem depender da tabela do Windows."""
    try:
        with httpx.Client(timeout=5) as c:
            return c.get(f"{config.COMFY_URL}/system_stats").status_code == 200
    except httpx.HTTPError:
        return False


def _limpar() -> dict:
    """Desfaz a duplicação. Devolve o que foi feito, para registrar no log."""
    global _sem_dono_seguidas
    e = inspecionar()
    if e.get("erro"):
        return {**e, "acao": "nada"}

    # Sem motor nenhum: o app esta de pe e inutil. Reerguer e o certo — e nao
    # ha nada rodando para interromper. O caso "duas instancias" e tratado
    # abaixo; este e o oposto dele, e escapava pela guarda antiga.
    if not e["motores"]:
        _sem_dono_seguidas = 0
        return {**e, "acao": "relancou" if _relancar() else "sem_motor",
                "encerrados": []}

    if e["servindo"] is not None:
        _sem_dono_seguidas = 0
        if not e["intrusos"]:
            return {**e, "acao": "nada"}
        # Caminho comum: a instância boa segue servindo, a intrusa sai inteira.
        _encerrar(e["intrusos"])
        return {**e, "acao": "encerrou_intrusos", "encerrados": e["intrusos"]}

    # O Windows as vezes deixa de listar quem escuta na porta (netstat e
    # Get-NetTCPConnection vazios com o ComfyUI atendendo; 29/10/2026). Sem esta
    # pergunta direta, o vigia derrubava um motor sadio a cada 3 minutos.
    if _responde():
        _sem_dono_seguidas = 0
        return {**e, "acao": "nada"}

    # Ha processo, mas ninguem atende ainda: quase sempre e o boot. Esperar.
    _sem_dono_seguidas += 1
    if _sem_dono_seguidas < CHECAGENS_ANTES_DE_DESISTIR:
        return {**e, "acao": "aguardando_subir",
                "checagens": _sem_dono_seguidas}
    _sem_dono_seguidas = 0

    # Ninguém atende na porta: não há geração a preservar. Fecha tudo e reabre.
    _encerrar(e["motores"])
    return {**e, "acao": "reiniciou" if _relancar() else "encerrou_tudo",
            "encerrados": e["motores"]}


def limpar() -> dict:
    if not GERENCIADO:
        return {"acao": "nada", "motores": [], "motivo": "motor nao gerenciado pelo app"}
    if _pausa.is_set():
        return {"acao": "nada", "motores": [], "motivo": "instalando nos"}
    with _mudanca:
        return _limpar()


def perfil_do(modelo: str, modelo_video: str, modelo_avatar: str = "") -> str | None:
    # O LTX 2.3 do avatar foi medido no perfil tradicional (14/10/2026).
    if modelo == "avatar" and modelo_avatar == "ltx23":
        return "tradicional"
    if modelo != "video":
        return None
    if modelo_video in ("ltx", "ltx23"):
        return "tradicional"
    # O perfil "dinamico" so servia ao MiniMax H3 local, removido em
    # 16/10/2026; os lancadores agora sobem sempre no tradicional.
    return None


def _gravar_perfil(perfil):
    PERFIL_ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    temporario = PERFIL_ARQUIVO.with_suffix(".tmp")
    temporario.write_text(perfil, encoding="ascii")
    temporario.replace(PERFIL_ARQUIVO)


def _trocar_perfil(perfil):
    # A fila é conferida novamente imediatamente antes de encerrar a árvore.
    # O mesmo lock impede que o vigia relance um segundo motor nessa janela.
    with _mudanca:
        with httpx.Client(timeout=5) as c:
            fila = c.get(f"{config.COMFY_URL}/queue").raise_for_status().json()
        if fila.get("queue_running") or fila.get("queue_pending"):
            raise RuntimeError("O motor está ocupado; o novo pedido não foi enviado para preservar a geração em execução.")
        estado = inspecionar()
        if estado.get("erro") or estado.get("instancias") != 1 or not estado.get("servindo"):
            raise RuntimeError("Não foi possível identificar uma única instância do motor para trocar o perfil.")
        _gravar_perfil(perfil)
        _encerrar(estado["motores"])
        if not _relancar(forcar=True):
            raise RuntimeError("Não foi possível relançar o motor com o perfil de memória solicitado.")


async def garantir_perfil(perfil):
    if perfil not in ("tradicional", "dinamico"):
        raise ValueError("Perfil de memória desconhecido")
    if not GERENCIADO:
        return False
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{config.COMFY_URL}/system_stats")
        r.raise_for_status()
        argv = r.json().get("system", {}).get("argv")
        if not isinstance(argv, list):
            raise RuntimeError("O motor não informou sua configuração de memória.")
        if _perfil_configurado(argv, perfil):
            await asyncio.to_thread(_gravar_perfil, perfil)
            return False
        await asyncio.to_thread(_trocar_perfil, perfil)
        limite = time.monotonic() + 240
        while time.monotonic() < limite:
            try:
                r = await c.get(f"{config.COMFY_URL}/system_stats")
                r.raise_for_status()
                flags = r.json().get("system", {}).get("argv", [])
                if _perfil_configurado(flags, perfil):
                    return True
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(2)
        raise RuntimeError("O motor não voltou com o perfil de memória esperado; o pedido não foi enviado.")


def _perfil_configurado(argv, perfil):
    if any(flag in argv for flag in ("--cpu", "--gpu-only", "--highvram", "--novram", "--lowvram")):
        return False
    if perfil == "tradicional":
        return "--disable-dynamic-vram" in argv
    try:
        margem = float(argv[argv.index("--vram-headroom") + 1])
    except (ValueError, IndexError, TypeError):
        return False
    return "--disable-dynamic-vram" not in argv and margem == 2.0 and "--disable-comfy-compiler" in argv


def pode_religar() -> bool:
    """O app sabe ligar este ComfyUI de novo: o daqui (lancador) ou o portatil que o
    install.bat baixou ("comfy_iniciar"). O ComfyUI de outra pessoa nunca e desligado."""
    return GERENCIADO or str(config._valor("comfy_iniciar")).lower() in ("true", "1")


# A janela "ComfyUI" do iniciar_comfy.py: se so o python morresse, ela ficaria
# parada no aviso de erro esperando uma tecla.
_JANELA = r"""
Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
  Where-Object { $_.CommandLine -like '*main.py*' -and $_.CommandLine -like '*PORTA*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
"""


def desligar() -> None:
    """Fecha o ComfyUI principal (e a janela dele). Quem chama confere antes que
    pode_religar() e que nada esta gerando."""
    with _mudanca:
        _powershell(_JANELA.replace("PORTA", str(PORTA)))
        _encerrar(inspecionar().get("motores") or [])
    limite = time.monotonic() + 30
    while _responde() and time.monotonic() < limite:
        time.sleep(1)
    time.sleep(2)  # o Windows solta os arquivos um instante depois do fim do processo


def desligar_segundo(porta: int | None) -> None:
    """Fecha o segundo motor (v0.41, LTX e Flux 3), que sobe sob demanda."""
    if porta:
        _powershell(f"""
Get-CimInstance Win32_Process |
  Where-Object {{ $_.CommandLine -like '*main.py*' -and $_.CommandLine -like '*{porta}*' }} |
  ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
""")


def ligar() -> bool:
    if GERENCIADO:
        return _relancar(forcar=True)
    import iniciar_comfy
    iniciar_comfy.main()
    return True


def _frase(r: dict) -> str:
    """O que o vigia fez, em frase legivel na janela do servidor (antes saia
    "sem_motor: []", que parecia erro mesmo quando era so o motor subindo)."""
    pids = ", ".join(str(p) for p in r.get("encerrados") or [])
    return {
        "relancou": "ComfyUI was not running: starting it (it takes a minute or two to load).",
        "sem_motor": "ComfyUI is not running and could not be started now; trying again in a minute.",
        "aguardando_subir": f"ComfyUI is loading; waiting for it to answer (check {r.get('checagens', '?')}).",
        "encerrou_intrusos": f"Closed a duplicate ComfyUI (process {pids}).",
        "reiniciou": f"ComfyUI stopped answering: restarted it (closed {pids}).",
        "encerrou_tudo": f"ComfyUI stopped answering: closed it ({pids}); it will be started again.",
    }.get(r["acao"], f"{r['acao']} {pids}".strip())


async def vigiar(intervalo: float = 60.0) -> None:
    """Repete a checagem em segundo plano enquanto o app estiver de pé."""
    if not GERENCIADO:
        return
    while True:
        try:
            # subprocess bloqueia; numa thread para não travar o servidor.
            r = await asyncio.to_thread(limpar)
            if r.get("acao") not in (None, "nada"):
                print(f"[engine] {_frase(r)}", flush=True)
        except Exception as erro:
            print(f"[motores] falha na checagem: {erro}", flush=True)
        await asyncio.sleep(intervalo)
