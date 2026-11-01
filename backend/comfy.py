"""Cliente da API do ComfyUI: enfileira grafos e acompanha o progresso."""

import config
import asyncio
import contextvars
import json
import os
import pathlib
import time
import uuid

import httpx
import websockets

import chaves

BASE_PRINCIPAL = config.COMFY_URL
# Segundo motor, so para o Flux 3 (ver motor_flux3.py).
BASE_FLUX3 = config.COMFY_URL_FLUX3
WS = config.COMFY_WS

# Qual motor a tarefa corrente usa. Cada tarefa roda numa asyncio.Task
# propria, que copia o contexto: trocar aqui nao afeta as outras.
MOTOR = contextvars.ContextVar("motor", default=BASE_PRINCIPAL)
# Ligado durante o /api/estimar: o grafo e montado so para ler o preco, entao
# enviar_imagem nao grava nada (antes cada mudanca na tela subia arquivos novos).
SO_ESTIMANDO = contextvars.ContextVar("so_estimando", default=False)

# ---- Local ou Comfy Cloud ------------------------------------------------
# A API da nuvem e a do ComfyUI com o prefixo /api e a chave no cabecalho, entao
# o resto do app nao muda: as funcoes abaixo escolhem endereco e cabecalho, e
# enfileirar/historico cuidam do que so a nuvem precisa (nomes de modelo sem a
# nossa subpasta, entradas enviadas por upload, saidas baixadas para o disco).
PNG_ASSINATURA = bytes([0x89]) + b"PNG\r\n\x1a\n"
NUVEM = "https://cloud.comfy.org/api"
NUVEM_WS = "wss://cloud.comfy.org/ws"
PREFERENCIAS = config.RAIZ / "backend" / "preferencias.json"


def _ler_preferencias() -> dict:
    try:
        return json.loads(PREFERENCIAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_preferencias(**mudancas) -> None:
    PREFERENCIAS.write_text(json.dumps({**_ler_preferencias(), **mudancas}), encoding="utf-8")


_pref = _ler_preferencias()
# "abertos": so modelos de pesos abertos. O padrao vem do config.json; a
# chave na barra do topo grava a escolha aqui.
MODO = {"motor": _pref.get("motor", "local"),
        "abertos": bool(_pref.get("so_abertos", config.SO_MODELOS_ABERTOS)),
        # Safe mode ligado de fabrica; desligar e escolha de quem usa (ver seguro.py).
        "seguro": bool(_pref.get("modo_seguro", True))}


def so_abertos() -> bool:
    return MODO["abertos"]


def escolher_abertos(valor: bool) -> None:
    MODO["abertos"] = bool(valor)
    _gravar_preferencias(so_abertos=bool(valor))


def modo_seguro() -> bool:
    return MODO["seguro"]


def escolher_seguro(valor: bool) -> None:
    MODO["seguro"] = bool(valor)
    _gravar_preferencias(modo_seguro=bool(valor))


def na_nuvem() -> bool:
    return MODO["motor"] == "nuvem"


def escolher_motor(modo: str) -> None:
    if modo not in ("local", "nuvem"):
        raise ValueError(modo)
    MODO["motor"] = modo
    _gravar_preferencias(motor=modo)


def _base() -> str:
    return NUVEM if na_nuvem() else MOTOR.get()


def _cliente(timeout: float) -> httpx.AsyncClient:
    if na_nuvem():
        return httpx.AsyncClient(timeout=timeout, headers={"X-API-Key": chaves.chave() or ""},
                                 verify=config.ssl_sistema(), follow_redirects=True)
    return httpx.AsyncClient(timeout=timeout)


# /object_info: a lista de nos e modelos do motor. Em alguns PCs ela leva quase
# um minuto, e as abas (Music, Voice, Lip Sync) a pediam varias vezes cada.
# Agora e uma busca por motor de cada vez, guardada uns minutos; instalar ou
# remover pacote ou no a esquece (esquecer_info), para o menu ver o novo.
_INFO: dict[str, tuple[float, dict]] = {}
_INFO_TRAVAS: dict[tuple, asyncio.Lock] = {}
INFO_VALIDADE = 300


async def info_nos(base: str | None = None, timeout: float = 120) -> dict:
    base = base or _base()

    def guardado():
        g = _INFO.get(base)
        return g[1] if g and time.monotonic() - g[0] < INFO_VALIDADE else None

    if (info := guardado()) is not None:
        return info
    # Quem chega enquanto a busca anda espera por ela, em vez de pedir de novo.
    trava = _INFO_TRAVAS.setdefault((base, asyncio.get_running_loop()), asyncio.Lock())
    async with trava:
        if (info := guardado()) is not None:
            return info
        cliente = _cliente(timeout) if base == NUVEM else httpx.AsyncClient(timeout=timeout)
        async with cliente as c:
            r = await c.get(f"{base}/object_info")
            r.raise_for_status()
        _INFO[base] = (time.monotonic(), r.json())
        return _INFO[base][1]


def esquecer_info() -> None:
    _INFO.clear()


def motivo_sem_info(erro: Exception) -> str:
    """Por que a lista de nos nao veio: lento nao e o mesmo que fora do ar."""
    if isinstance(erro, httpx.TimeoutException):
        return "ComfyUI is taking long to answer (it may still be loading). Try again in a minute."
    return "ComfyUI is not responding."


_parceiros: dict[str, set[str]] = {}


async def nos_de_parceiro() -> set[str]:
    """Nos que chamam servico fechado: o proprio ComfyUI os marca com
    `api_node` no /object_info. Guardado por motor."""
    base = _base()
    if base not in _parceiros:
        try:
            async with _cliente(120) as c:
                r = await c.get(f"{base}/object_info")
                r.raise_for_status()
            _parceiros[base] = {k for k, v in r.json().items() if v.get("api_node")}
        except Exception:
            return set()  # motor fora: o envio falha adiante com a mensagem do motor
    return _parceiros[base]


# Identifica esta sessao no WebSocket do ComfyUI, para receber so os nossos eventos.
ID_CLIENTE = str(uuid.uuid4())


class ErroComfy(Exception):
    """Falha vinda do motor, com o detalhe util ja extraido."""


async def esta_vivo() -> bool:
    try:
        async with _cliente(3) as c:
            r = await c.get(f"{_base()}/system_stats")
            return r.status_code == 200
    except Exception:
        return False


async def enfileirar(grafo: dict) -> str:
    """Envia o grafo e devolve o prompt_id.

    A chave de API viaja em `extra_data`, FORA do grafo: e de la que o motor a
    entrega aos nos de parceiro, como entrada oculta. Vai em toda requisicao
    porque custa nada quando nao ha nos de nuvem no grafo, e evita um segundo
    caminho de envio so para eles. Sem chave configurada, o campo nem aparece.
    """
    if so_abertos():
        fechados = sorted({n["class_type"] for n in grafo.values()} & await nos_de_parceiro())
        if fechados:
            raise ErroComfy("Este modo usa um serviço fechado (" + ", ".join(fechados) +
                            ") e a versão de modelos abertos não o envia.")
    if not na_nuvem():
        # Modelo que a pessoa ja tinha em outra subpasta: o grafo pede o lugar real.
        import pacotes
        grafo = await pacotes.ajustar_grafo(grafo)
    if na_nuvem():
        import nuvem
        try:
            grafo = await nuvem.preparar(grafo)
        except nuvem.IndisponivelNaNuvem as e:
            raise ErroComfy(str(e))
    envio = {"prompt": grafo, "client_id": ID_CLIENTE}
    extra = chaves.extra_data()
    if extra:
        envio["extra_data"] = extra

    async with _cliente(30) as c:
        r = await c.post(f"{_base()}/prompt", json=envio)
    if na_nuvem() and r.status_code in (401, 402, 429):
        raise ErroComfy({
            401: "Comfy Cloud rejected the API key. Check the key in the settings.",
            402: f"Your Comfy Cloud account is out of credits or has no subscription. Top up at {config.LINK_RECARGA}",
            429: f"Your Comfy Cloud subscription is inactive. Reactivate it at {config.LINK_RECARGA}",
        }[r.status_code])
    if r.status_code != 200:
        # O corpo do 400 traz qual no falhou e por que; sem isso o erro e opaco.
        try:
            corpo = r.json()
            erros = corpo.get("node_errors") or corpo.get("error")
            raise ErroComfy(json.dumps(erros, ensure_ascii=False)[:800])
        except ValueError:
            raise ErroComfy(r.text[:500])
    return r.json()["prompt_id"]


async def historico(prompt_id: str) -> dict | None:
    if na_nuvem():
        async with _cliente(30) as c:
            r = await c.get(f"{_base()}/history_v2/{prompt_id}")
        if r.status_code == 404:
            # Pedido que FALHOU na Comfy Cloud some da fila e do historico; o
            # motivo so aparece em /jobs. Sem isto a tarefa virava "o motor caiu".
            async with _cliente(30) as c:
                j = await c.get(f"{_base()}/jobs/{prompt_id}")
            erro = j.json().get("execution_error") if j.status_code == 200 else None
            if erro:
                no = erro.get("node_type") or "?"
                msg = (erro.get("exception_message") or "unknown error").strip()
                raise ErroComfy(f"Comfy Cloud: {no} failed: {msg}"[:600])
            return None
        h = r.json().get(prompt_id)
        if h and h.get("outputs") and h.get("status", {}).get("status_str") == "success":
            import nuvem
            h = {**h, "outputs": await nuvem.trazer_saidas(prompt_id, h["outputs"])}
        return h
    async with _cliente(30) as c:
        r = await c.get(f"{_base()}/history/{prompt_id}")
    return r.json().get(prompt_id)


async def fila() -> dict:
    async with _cliente(30) as c:
        r = await c.get(f"{_base()}/queue")
        r.raise_for_status()
        return r.json()


async def retomar_cliente(prompt_ids: set[str]):
    """Reassina a sessão que recebe progresso de um pedido já em execução."""
    global ID_CLIENTE
    fila_motor = await fila()
    for item in fila_motor.get("queue_running", []):
        if len(item) > 3 and item[1] in prompt_ids:
            cliente_original = item[3].get("client_id")
            if cliente_original:
                ID_CLIENTE = cliente_original
            return


async def limpar_fila() -> None:
    async with _cliente(10) as c:
        await c.post(f"{_base()}/queue", json={"clear": True})


async def interromper() -> None:
    async with _cliente(10) as c:
        await c.post(f"{_base()}/interrupt")


async def vram_usada_gib() -> float | None:
    """VRAM ocupada na placa, em GiB, ou None se o motor nao responder."""
    try:
        async with _cliente(10) as c:
            r = await c.get(f"{_base()}/system_stats")
            d = r.json()["devices"][0]
        return (d["vram_total"] - d["vram_free"]) / 2**30
    except Exception:
        return None


async def liberar_memoria() -> bool:
    if na_nuvem():
        return True  # a memoria da nuvem nao e nossa
    """Descarrega os modelos e esvazia a memoria da placa.

    Hoje e redundante, e de proposito: o `--cache-none` dos lancadores ja faz
    o motor descarregar os modelos ao fim de cada geracao (medido em 02/10,
    com controle). Isto garante o mesmo resultado se a flag um dia sair dos
    lancadores.

    Nunca levanta: um motor fora do ar nao pode derrubar a fila. Devolve se o
    motor aceitou o pedido.
    """
    try:
        async with _cliente(30) as c:
            r = await c.post(f"{_base()}/free",
                             json={"unload_models": True, "free_memory": True})
            return r.status_code == 200
    except Exception:
        return False


def _local(nome: str, subpasta: str, tipo: str) -> pathlib.Path | None:
    """No modo nuvem, o que ja esta no disco le dali, nao da nuvem: saidas ja
    trazidas e entradas enviadas (que so sobem para a nuvem ao gerar)."""
    if na_nuvem() and tipo in ("output", "input"):
        pasta = config.COMFY_SAIDA if tipo == "output" else config.COMFY_ENTRADA
        caminho = (pasta / subpasta / nome).resolve()
        # ".." ou caminho absoluto no nome nao podem sair da pasta (ex.: chaves.json).
        if not caminho.is_relative_to(pasta.resolve()):
            return None
        if caminho.is_file():
            return caminho
    return None


async def imagem(nome: str, subpasta: str = "", tipo: str = "output") -> bytes:
    if (local := _local(nome, subpasta, tipo)):
        return local.read_bytes()
    async with _cliente(60) as c:
        r = await c.get(f"{_base()}/view",
                        params={"filename": nome, "subfolder": subpasta, "type": tipo})
        r.raise_for_status()
        return r.content


async def unets_disponiveis() -> set[str]:
    """Nomes de modelo que o motor realmente enxerga.

    Perguntar ao motor e melhor que conferir um caminho no disco: e a mesma
    lista que ele usa para validar o grafo, entao nao ha como divergir.
    """
    try:
        async with _cliente(10) as c:
            r = await c.get(f"{_base()}/object_info/UNETLoader")
        req = r.json()["UNETLoader"]["input"]["required"]
        return {n.replace("\\", "/") for n in req["unet_name"][0]}
    except Exception:
        return set()


async def tamanho_imagem(nome: str, subpasta: str = "", tipo: str = "output") -> int:
    """Bytes do arquivo, sem baixar o conteudo. Devolve 0 se nao der."""
    if (local := _local(nome, subpasta, tipo)):
        return local.stat().st_size
    try:
        async with _cliente(10) as c:
            r = await c.head(f"{_base()}/view",
                             params={"filename": nome, "subfolder": subpasta,
                                     "type": tipo})
            return int(r.headers.get("content-length", 0))
    except Exception:
        return 0


async def dimensoes_imagem(nome: str, subpasta: str = "",
                           tipo: str = "output") -> tuple[int, int]:
    """Largura e altura lidas do cabecalho IHDR do PNG.

    O motor aceita requisicoes parciais, entao bastam 32 bytes — nao faz
    sentido baixar megabytes so para saber o tamanho.
    """
    if (local := _local(nome, subpasta, tipo)):
        cab = local.open("rb").read(32)
        if cab[:8] == PNG_ASSINATURA and cab[12:16] == b"IHDR":
            return int.from_bytes(cab[16:20], "big"), int.from_bytes(cab[20:24], "big")
        return 0, 0
    try:
        async with _cliente(10) as c:
            r = await c.get(f"{_base()}/view",
                            params={"filename": nome, "subfolder": subpasta,
                                    "type": tipo},
                            headers={"Range": "bytes=0-31"})
            cab = r.content
        if cab[:8] == b"\x89PNG\r\n\x1a\n" and cab[12:16] == b"IHDR":
            return (int.from_bytes(cab[16:20], "big"),
                    int.from_bytes(cab[20:24], "big"))
    except Exception:
        pass
    return 0, 0


async def enviar_imagem(nome: str, dados: bytes) -> str:
    """Sobe uma imagem para a pasta input do ComfyUI. Devolve o nome gravado.

    No modo Comfy Cloud o arquivo fica na pasta input DESTA maquina: e daqui
    que o app mede, recorta e mostra; a nuvem o recebe na hora de gerar
    (nuvem.preparar sobe cada arquivo de entrada que o grafo usa)."""
    if SO_ESTIMANDO.get():
        return os.path.basename(nome)
    if na_nuvem():
        pasta = config.COMFY_ENTRADA
        pasta.mkdir(parents=True, exist_ok=True)
        base, ext = os.path.splitext(os.path.basename(nome))
        final, n = f"{base}{ext}", 1
        while (pasta / final).exists():
            final, n = f"{base} ({n}){ext}", n + 1
        (pasta / final).write_bytes(dados)
        return final
    async with _cliente(120) as c:
        r = await c.post(f"{_base()}/upload/image",
                         files={"image": (nome, dados)},
                         data={"overwrite": "false"})
        r.raise_for_status()
        return r.json()["name"]


async def acompanhar(ao_evento):
    """Escuta o WebSocket do motor e repassa cada evento para `ao_evento`.

    Reconecta sozinho: o ComfyUI pode ser reiniciado sem derrubar o app.
    """
    while True:
        modo = MODO["motor"]
        url = (f"{NUVEM_WS}?clientId={ID_CLIENTE}&token={chaves.chave() or ''}"
               if modo == "nuvem" else f"{WS}?clientId={ID_CLIENTE}")
        try:
            async with websockets.connect(url, max_size=None,
                                          ssl=config.ssl_sistema() if modo == "nuvem" else None) as sock:
                async for bruto in sock:
                    if MODO["motor"] != modo:
                        break  # trocou de motor: reconecta no outro
                    if isinstance(bruto, bytes):
                        continue  # previews binarios, nao usamos
                    try:
                        await ao_evento(json.loads(bruto))
                    except Exception:
                        pass
        except Exception:
            await asyncio.sleep(2)


async def executar(grafo: dict, timeout: float = 1800) -> dict:
    """Enfileira e espera terminar. Devolve as saidas. Use para tarefas curtas."""
    pid = await enfileirar(grafo)
    espera = 0.0
    while espera < timeout:
        h = await historico(pid)
        if h:
            estado = h["status"].get("status_str")
            if estado == "error":
                raise ErroComfy(json.dumps(h["status"].get("messages"),
                                           ensure_ascii=False)[:1200])
            return h["outputs"]
        await asyncio.sleep(1)
        espera += 1
    raise ErroComfy("tempo esgotado esperando o motor")


async def texto_de(saidas: dict) -> str:
    """Extrai o texto de um grafo de geracao de texto."""
    for saida in saidas.values():
        if "text" in saida:
            valor = saida["text"]
            return valor[0] if isinstance(valor, list) else valor
    return ""


def imagens_salvas(saidas: dict) -> list[dict]:
    """As imagens do no de gravacao, nao tudo que o grafo emitiu.

    Alguns nos devolvem previas proprias junto com o resultado — o
    ExpressionEditor do LivePortrait emite um "fe_edit_preview.png" de nome
    FIXO, que e sobrescrito a cada chamada. Pegar "a primeira imagem das
    saidas" fazia esse arquivo virar o resultado e entrar na galeria.

    Todos os nossos grafos nomeiam o SaveImage de "salva"; quando ele existe,
    e so dele que sai o resultado.
    """
    fonte = {"salva": saidas["salva"]} if "salva" in saidas else saidas
    # Os nos do VHS devolvem sob "gifs", nao "images" — mesmo quando a saida e
    # um mp4. Ler so "images" fazia o video limpo sumir: o arquivo existia no
    # disco e a tarefa terminava sem resultado algum.
    return [{"nome": im["filename"], "subpasta": im.get("subfolder", ""),
             "tipo": im.get("type", "output")}
            for saida in fonte.values()
            for chave in ("images", "gifs", "audio")
            for im in saida.get(chave, [])]
