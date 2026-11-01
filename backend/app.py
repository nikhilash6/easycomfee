"""Servidor do EasyComfee.

Fala com o ComfyUI rodando em 127.0.0.1:8188 e expoe uma API simples para a
interface: catalogo de modelos, fila de geracao, progresso ao vivo e galeria.
"""

import config
import asyncio
import contextlib
import json
import os
import pathlib
import random
import re
import time
import subprocess
import uuid
from urllib.parse import urlsplit

import httpx
from fastapi import (FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import atualizacao
import biblioteca
import grafos
import andamento
import motores
import chaves
import comfy
import deteccao
import enquadrar
import ideogram
import luz
import miniaturas
import seguro
import previa
import presets
import prompting
import workflows
import voz
import avatar
import precos
import ltx23
import motor_flux3
import videos_leves
import separacao
import troca_voz
import musica
import genjutsu

RAIZ = pathlib.Path(__file__).parent.parent
ESTATICOS = RAIZ / "frontend" / "dist"

app = FastAPI(title="EasyComfee")

# Qual família de modelo está carregada na GPU. Só cabe uma; saber qual é
# permite avisar quando o próximo pedido vai pagar o custo de trocar.
MOTOR_CARREGADO: str | None = None
# A interface usa a mesma origem do backend (o Vite faz proxy em dev). Uma
# pagina qualquer nao deve poder enviar pedidos pagos ao localhost do usuario.
ORIGENS_LOCAIS = {(host, port) for host in ("127.0.0.1", "localhost")
                  for port in (config.APP_PORTA, 5173)}


def _origem_permitida(origem: str | None) -> bool:
    if not origem:
        return True  # scripts locais e verificacoes sem cabecalho Origin
    try:
        url = urlsplit(origem)
        return (url.scheme == "http" and (url.hostname, url.port) in ORIGENS_LOCAIS
                and not url.username and not url.password)
    except ValueError:
        return False


@app.middleware("http")
async def somente_interface_local(request: Request, proximo):
    # Confere Host tambem para bloquear DNS rebinding: o processo so escuta
    # em 127.0.0.1, mas um nome externo pode apontar para esse endereco.
    host = request.headers.get("host", "").split(":", 1)[0].lower()
    # Envio anunciado maior que o limite (com folga para o envelope multipart):
    # recusa antes de receber o corpo, que iria inteiro para um arquivo temporario.
    if request.url.path in ("/api/referencia", "/api/referencia-audio"):
        try:
            tamanho = int(request.headers.get("content-length") or 0)
        except ValueError:
            tamanho = 0
        if tamanho > 40 * 1024 * 1024 + 64 * 1024:
            return JSONResponse({"detail": "file above 40 MB"}, status_code=413)
    # Abrir a PAGINA por um link de outro site (ex.: um link no ChatGPT, 29/10/2026) e so
    # navegar: o outro site nao le nada e nao dispara acao. A API e o WebSocket seguem
    # recusando qualquer pedido vindo de outro site.
    navegacao = (request.method in ("GET", "HEAD")
                 and request.headers.get("sec-fetch-mode") == "navigate"
                 and request.headers.get("sec-fetch-dest") == "document"
                 and not request.url.path.startswith(("/api", "/ws")))
    if (host not in {"127.0.0.1", "localhost"}
            or not _origem_permitida(request.headers.get("origin"))
            or (request.headers.get("sec-fetch-site") == "cross-site" and not navegacao)):
        return JSONResponse({"detail": "acesso local recusado"}, status_code=403)
    return await proximo(request)


class HeadComoGet:
    """HEAD responde como o GET da mesma rota (sem corpo: o uvicorn ve que o
    pedido original era HEAD e nao o envia). As rotas do FastAPI so aceitam
    GET, e HEAD / dava 405, o que derruba verificacoes de "o site esta no ar"."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "HEAD":
            scope = dict(scope, method="GET")
        await self.app(scope, receive, send)


app.add_middleware(HeadComoGet)


class EnvioGrandeDemais(Exception):
    pass


class LimiteDeEnvio:
    """Conta os bytes do corpo dos envios enquanto chegam e corta ao passar de
    40 MB. A conferencia pelo Content-Length (somente_interface_local) nao pega
    um envio em partes (Transfer-Encoding: chunked), que antes ia inteiro para
    um arquivo temporario antes do 413."""

    CAMINHOS = ("/api/referencia", "/api/referencia-audio")
    LIMITE = 40 * 1024 * 1024 + 64 * 1024  # folga para o envelope multipart

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in self.CAMINHOS:
            return await self.app(scope, receive, send)
        recebido, comecou, estourou = 0, False, False
        corpo413 = b'{"detail":"file above 40 MB"}'

        async def receber():
            nonlocal recebido, estourou
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                recebido += len(mensagem.get("body", b""))
                if recebido > self.LIMITE:
                    estourou = True
                    raise EnvioGrandeDemais()
            return mensagem

        async def enviar(mensagem):
            nonlocal comecou
            # O FastAPI pega a interrupcao e responde 400 ("error parsing the
            # body"); com o limite estourado, a resposta vira o 413 certo.
            if estourou:
                if mensagem["type"] == "http.response.start" and not comecou:
                    comecou = True
                    await send({"type": "http.response.start", "status": 413,
                                "headers": [(b"content-type", b"application/json"),
                                            (b"content-length", str(len(corpo413)).encode())]})
                    await send({"type": "http.response.body", "body": corpo413})
                return
            comecou = comecou or mensagem["type"] == "http.response.start"
            await send(mensagem)

        try:
            await self.app(scope, receber, enviar)
        except EnvioGrandeDemais:
            if not comecou:
                await JSONResponse({"detail": "file above 40 MB"}, status_code=413)(scope, receive, send)


app.add_middleware(LimiteDeEnvio)


@app.exception_handler(RequestValidationError)
async def pedido_invalido(request: Request, erro: RequestValidationError):
    # O 422 padrao repete o valor recebido; um NaN ali nao vira JSON e o erro
    # de validacao acabava em 500. So o lugar e o motivo bastam.
    return JSONResponse({"detail": [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")}
                                    for e in erro.errors()]}, status_code=422)


# ---------------------------------------------------------------- modelos de dados

def _tem_surrogate(valor) -> bool:
    if isinstance(valor, str):
        return any(0xD800 <= ord(c) <= 0xDFFF for c in valor)
    if isinstance(valor, (list, tuple)):
        return any(_tem_surrogate(v) for v in valor)
    if isinstance(valor, dict):
        return any(_tem_surrogate(k) or _tem_surrogate(v) for k, v in valor.items())
    return False


class Pedido(BaseModel):
    """Base dos corpos de pedido. O JSON do Python aceita NaN e Infinity; sem
    isto eles passavam pela validacao e estouravam la dentro como erro 500."""
    model_config = ConfigDict(allow_inf_nan=False)

    @model_validator(mode="after")
    def _sem_surrogate(self):
        # Meio emoji sozinho (o escape \ud83d no JSON) passa na leitura, mas nao
        # vira UTF-8: o pedido entrava na fila e quebrava ao gravar no banco (500).
        for nome, valor in self.__dict__.items():
            if _tem_surrogate(valor):
                raise ValueError(f"{nome}: broken character (half of an emoji?)")
        return self


def _referencia_segura(ref: str) -> str:
    """Nome de arquivo vindo do pedido: "nome.png" (pasta input), "subpasta/nome.mp4"
    (galeria) ou "entrada:nome". Recusa o que sairia da pasta: "..", ".", partes
    vazias, barra invertida, caminho absoluto e unidade do Windows ("C:nome",
    "C:/..."). Antes so o modo simples conferia; edicao, controle, rosto e as
    previas repassavam o nome cru ao motor."""
    nome = ref[len("entrada:"):] if ref.startswith("entrada:") else ref
    partes = nome.split("/")
    if (not nome or "\\" in nome or ":" in nome or nome.startswith("/")
            or any(p in ("", ".", "..") for p in partes)):
        raise ValueError("invalid file name")
    return ref


class PedidoGeracao(Pedido):
    @field_validator("referencias", "referencias_video", "referencias_audio", mode="after")
    @classmethod
    def _refs(cls, v: list[str]) -> list[str]:
        return [_referencia_segura(r) for r in v]

    @field_validator("fundo_referencia", "referencia_voz", "referencia_musica", "referencia_avatar", mode="after")
    @classmethod
    def _ref(cls, v: str | None) -> str | None:
        return _referencia_segura(v) if v else v

    encerramento_musica: str = Field("original", pattern="^(original|natural|fade)$")
    margem_musica: float = Field(10.0, ge=0, le=10)
    modelo_musica: str = Field("minimax-music3", pattern="^(minimax-music3|stable-audio3|ace-step15|yue2|yue2-cover)$")
    # So o YuE2 (Plenio): um dos estilos prontos do pedido, ou "none".
    estilo_musica: str = Field("none", max_length=120)
    # Revisao antes de gerar (YuE2): "direto" gera sem parar; "letra" e
    # "partitura" param e devolvem os rascunhos; "gerar" usa os aprovados.
    etapa_musica: str = Field("direto", pattern="^(direto|letra|partitura|gerar)$")
    # Cover (YuE2 Cover): a voz (letra original, nova ou instrumental), a
    # harmonia (manter os acordes ou refazer) e o tema da letra nova.
    voz_cover: str = Field("original", pattern="^(original|nova|instrumental)$")
    harmonia_cover: str = Field("nova", pattern="^(manter|nova)$")
    tema_cover: str = Field("", max_length=300)
    docs_musica: dict[str, str] = {}
    letra_musica: str = Field("", max_length=12000)
    vocal_musica: bool = False
    duracao_musica: float = Field(30.0, ge=10, le=600)
    referencia_musica: str = ""
    projeto_musica: str = Field("", max_length=120)
    titulo_musica: str = Field("", max_length=120)
    transformacao_musica: float = Field(0.75, ge=0.3, le=1.0)
    bpm_musica: int = Field(120, ge=10, le=300)
    tonalidade_musica: str = "C major"
    genero_vocal_musica: str = Field("livre", pattern="^(livre|feminino|masculino)$")
    idioma_musica: str = Field("pt", pattern="^(pt|en|es|de|it|fr|ja|zh|ko)$")
    idioma_voz: str = Field("Portuguese", pattern="^(Portuguese|English|Spanish|German|Italian|French|Japanese|Chinese|Korean)$")
    idioma_referencia_voz: str = Field("Portuguese", pattern="^(Portuguese|English|Spanish|German|Italian|French|Japanese|Chinese|Korean)$")
    modo_voz: str = Field("narrar", pattern="^(narrar|criar|clonar)$")
    referencia_voz: str = ""
    nome_voz: str = Field("", max_length=120)
    titulo_audio_voz: str = Field("", max_length=120)
    # Avatar: a fala vem da pasta input do motor (refaudio_...); a foto, de
    # referencias[0]. A duracao e medida no servidor, nunca aceita do cliente.
    referencia_avatar: str = ""
    duracao_avatar: float = 0.0
    # Dois motores na aba Avatar, para comparar (14/10/2026).
    modelo_avatar: str = Field("longcat", pattern="^(longcat|ltx23|kling|heygen|sync|veed)$")
    vertical_avatar: bool = False
    # Separar faixas: a musica vem da galeria (id) ou de um envio (refaudio_).
    separar_item: int = 0
    referencia_separar: str = ""
    modo_separar: str = Field("4", pattern="^(4|6|voz)$")
    formato_separar: str = Field("flac", pattern="^(flac|mp3)$")
    # Trocar voz (Applio/RVC): a musica vem como na separacao (separar_item
    # ou referencia_separar), a voz e um modelo treinado, o tom em semitons.
    voz_troca: str = Field("", max_length=80)
    tom_troca: int = Field(0, ge=-12, le=12)
    # Treinar voz: gravacoes enviadas (refaudio_), nome e epocas.
    nome_voz: str = Field("", max_length=40)
    arquivos_voz: list[str] = Field(default_factory=list, max_length=40)
    epocas_voz: int = Field(300, ge=20, le=1000)
    separar_treino_voz: bool = False
    transcricao_voz: str = ""
    instrucao_voz: str = ""
    falante_voz: str = Field("Ryan", max_length=20)  # so na nuvem (Qwen3-TTS)
    # Genjutsu: referencias[0] e o video ("entrada:..."), o resto sao imagens.
    modelo_genjutsu: str = Field("wan_animate2", pattern="^(wan_animate2|wan22_replace|h3_swap|higgsfield|kling_omni|aleph2)$")
    # So o MiniMax H3 Character Swap: quem sai do video (texto para o SAM 3),
    # se o Gemini escreve o prompt (pago, centavos) e o atalho Turbo.
    alvo_genjutsu: str = Field("person", max_length=120)
    gemini_genjutsu: bool = True
    turbo_genjutsu: bool = False
    velocidade_voz: float = Field(1.0, ge=0.5, le=2.0)
    passos_voz: int = Field(32, ge=16, le=64)
    modelo: str = "krea"
    # Antes sem limite: 30.000 caracteres passavam e ganhavam preco, e um modelo de API
    # recusaria so depois do envio (varredura de 29/10/2026). 12.000 e o da narracao.
    prompt: str = Field(..., max_length=12000)
    negativo: str = ""
    proporcao: str = "1:1"
    escala: float = Field(1.0, ge=0.5, le=2.0)
    # So nos modelos que declaram `nativo_4k` (hoje, o Flux 3): ignora a escala.
    nativo_4k: bool = False
    # So o "transformar_video": qual IC-LoRA do Creative Lab aplicar.
    efeito_video: str = "noite"
    # So o efeito "trocar": de onde sai o movimento do video original.
    controle_troca: str = Field("pose", pattern="^(pose|profundidade|contornos)$")
    # So o "Seguir mapa de profundidade": o video ja e o mapa (passe Z do Blender).
    mapa_pronto: bool = False
    # Mapa de profundidade: "gray" (perto claro) ou "inferno" (colorido); EXR opcional.
    mapa_cor: str = Field("gray", pattern="^(gray|inferno)$")
    exr: bool = False
    # So o "Expandir enquadramento": o formato do video final.
    formato_saida: str = Field("16:9", pattern="^(16:9|9:16|1:1)$")
    # Maquete: quadros-chave em qualquer quantidade, cada um com o NUMERO DO
    # QUADRO (contado de 1, a 24 fps, como no Blender).
    chaves_video: list[dict] = Field(default_factory=list)
    # Lado menor da saida do 3D render -> Video (576, 720 ou 1088). 0 = o maximo que a
    # placa aguenta (presets.limite_maquete); o servidor nunca passa desse teto.
    lado_maquete: int = Field(0, ge=0, le=1088)
    # 3D render -> Video: onde comeca o trecho usado do render (quadro, contado de 0).
    # Renders mais longos que o teto (14,7 s) usam so esse trecho.
    inicio_maquete: int = Field(0, ge=0, le=100000)
    # Duracao escolhida do trecho, em quadros (0 = o maximo que cabe).
    quadros_maquete: int = Field(0, ge=0, le=100000)
    # Extracao de quadros da maquete: numeros de quadro; vazio = inicio, meio e fim.
    quadros_extrair: list[int] = Field(default_factory=list)
    # So o LTX 2.5, modos texto e imagem: < 1 liga o LoRA de camera lenta.
    velocidade_video: float = Field(1.0, ge=0.1, le=1.0)
    lote: int = Field(1, ge=1, le=8)
    # Chamadas de diagnostico podem ficar registradas sem poluir a galeria
    # normal. O rotulo identifica a rodada/caso para auditoria posterior.
    teste: bool = False
    rotulo_teste: str | None = None
    # Variacoes de uma EDICAO. O lote nao serve aqui: o latente vem da
    # imagem de entrada, nao de um EmptyLatent com batch_size. Medido na
    # migracao de luz: com tudo igual e so a seed mudando, a transferencia
    # foi de +3,0 a -18,3 numa escala cujo alvo era -24. A seed domina, e
    # o remedio e oferecer escolha, nao caçar parametro.
    variacoes: int = Field(1, ge=1, le=4)
    # Limites: valores absurdos (steps 99999999, cfg -1e9) seguiam ate o ComfyUI.
    seed: int | None = Field(None, ge=0, le=2**64 - 1)
    steps: int | None = Field(None, ge=1, le=150)
    cfg: float | None = Field(None, ge=0, le=30)
    # Especifico dos modelos por nuvem: 1K, 2K ou 4K. Nao usa `escala`, que
    # vale para os modelos locais e vira pixels em presets.dimensoes.
    resolucao_nuvem: str = "1K"
    # Especificos dos modelos da OpenAI: o preco depende dos dois.
    qualidade_nuvem: str = "medium"
    fundo_nuvem: str = "auto"
    # Video (LTX 2.5). `modo_video` diz de onde vem o movimento:
    # "texto" (sem imagem), "imagem" (uma) ou "primeiro_ultimo" (duas).
    modo_video: str = "texto"
    # Modo "chaves": o numero do quadro (de 1, a 24 fps) de cada referencia,
    # na mesma ordem, e quanto cada imagem prende o seu quadro.
    quadros_referencias: list[int] = []
    forca_chaves: float = Field(0.7, ge=0.3, le=1.0)
    duracao_video: int = Field(5, ge=1, le=30)
    com_audio: bool = True
    prompt_automatico: bool = False
    tamanho_video: str = "1280x720"
    # "ltx" ou "minimax". Sao os dois geradores locais de video.
    modelo_video: str = "ltx"
    # So o gerador "planos": um texto por plano, na ordem. O primeiro plano
    # pode partir de uma imagem (referencias[0]); os demais partem sempre do
    # ultimo quadro do anterior, e por isso nao recebem imagem propria.
    planos: list[str] = []
    # Chave da LoRA turbo do MiniMax: LoRA + 6 passos, em vez de 20.
    turbo: bool = True
    # So o gerador de nuvem usa estes: la o tamanho e proporcao +
    # resolucao, nao pixels.
    proporcao_video: str = "16:9"
    resolucao_video: str = "480p"
    # So o Wan 3.0: variante do modelo e se o servico enriquece o prompt.
    variante_video: str = "wan3.0-video"
    melhorar_prompt: bool = True
    # Altura alvo da limpeza de video. O no ajusta a largura pela proporcao.
    resolucao_limpeza: int = Field(1088, ge=256, le=2160)
    # "seedvr" amplia em pixels; "ltx" amplia no latente. Ver o preset.
    metodo_video: str = "ltx"
    # Especificos do metodo Magnific dentro do Reluz.
    estilo_luz: str = "standard"
    forca_luz: int = Field(100, ge=0, le=100)
    mudar_fundo_luz: bool = False
    # Especificos do Ideogram 4.
    qualidade: str = "padrao"
    caption: dict | None = None          # JSON pronto, vindo do editor de caixas
    # Cor da tipografia quando ela e composta sobre uma foto enviada. A
    # peca sai branca sobre preto e so vira esta cor na composicao.
    tinta: str | None = None
    # Camada de linguagem.
    expandir_prompt: bool = False
    # "fiel" preserva o que o usuario ja decidiu; "livre" deixa o modelo
    # escolher angulo e enquadramento. Ver prompting.EXPANSOES.
    modo_expansao: str = "fiel"
    # Estilo da geração: o positivo vale para todos os modelos, o negativo só
    # onde o CFG é maior que 1 (ver presets.honra_negativo).
    estilo: str = presets.ESTILO_PADRAO
    estilo_manual: str = ""
    # Edicao: nomes de arquivos ja enviados para a pasta input do motor.
    # A primeira e a imagem base; as demais sao referencias.
    referencias: list[str] = Field(default_factory=list)
    forca_referencia: float = Field(1.0, ge=0.5, le=4.0)
    # SD 1.5, SDXL e SD 3.5 com uma imagem: quanto a imagem muda (img2img).
    forca_imagem: float = Field(0.6, ge=0.15, le=1.0)
    # Cena com 2-3 personagens (Krea/Kroma): onde cada referencia fica, na
    # ordem das referencias; "" deixa o modelo decidir.
    posicoes_referencia: list[str] = Field(default_factory=list, max_length=3)
    # Referencias por VIDEO vem da GALERIA, nao de upload: o VHS_LoadVideoPath
    # le do disco por caminho absoluto. Por isso campo proprio — misturar com
    # `referencias`, que sao envios para a pasta de entrada, confundiria duas
    # coisas que chegam por caminhos diferentes.
    referencias_video: list[str] = Field(default_factory=list)
    # Audios avulsos de referencia ficam na pasta input do motor, como as
    # imagens. Campo proprio porque nao sao imagens e porque o ref2va tem um
    # autogrow diferente (`ref_audios.ref_audio_N`).
    referencias_audio: list[str] = Field(default_factory=list)
    # LTXVReferenceAudio: intensidade da identidade vocal. Zero ainda injeta
    # os tokens da amostra, mas evita a passada adicional de guiagem.
    forca_audio_referencia: float = Field(3.0, ge=0.0, le=10.0)
    # MiniMax ref2va: `match` reduz cada imagem para a area da geracao; `max`
    # usa borda curta de 2048 para priorizar identidade, com custo bem maior.
    tamanho_referencia: str = "match"
    # O quinto slot do MSR: uma imagem so, e SO o cenario. Chega como
    # envio, igual as outras referencias — o que torna o campo proprio
    # necessario, porque pelo caminho nao da para distinguir.
    fundo_referencia: str | None = None
    forca_estilo: float = Field(1.0, ge=0.1, le=1.5)
    # Ampliação.
    metodo_ampliar: str = "seedvr"
    escala_ampliar: float = Field(2.0, ge=1.1, le=16.0)
    magnific_criatividade: int = Field(0, ge=-10, le=10)
    magnific_hdr: int = Field(0, ge=-10, le=10)
    magnific_semelhanca: int = Field(0, ge=-10, le=10)
    magnific_fractalidade: int = Field(0, ge=-10, le=10)

    otimizacao: str = "geral"
    criatividade: float = Field(0.33, ge=0.0, le=0.8)
    semelhanca: float = Field(0.0, ge=0.0, le=1.0)
    microcontraste: float = Field(0.0, ge=0.0, le=1.0)
    granulacao: float = Field(0.0, ge=0.0, le=1.0)
    detalhe: float = Field(0.0, ge=0.0, le=1.0)
    # Troca de personagem em três imagens.
    blocos: dict[str, bool] = Field(default_factory=dict)
    # Padrao "rapido" desde 22/09/2026: ver presets.PERSONAGEM["prioridades"].
    # Cai em "fiel" sozinho quando o destilado nao esta no disco.
    prioridade: str = "rapido"  # "rapido" (destilado) ou "fiel" (Klein base)
    # Edição por instrução no Qwen: "baixa" 1 MP, "media" 1,5 MP, "alta" 2 MP.
    resolucao_edicao: str = "media"

    # Girar a camera (Anygles). As faixas repetem as do no, e nao por
    # descuido: aqui elas RECUSAM o pedido com mensagem clara, antes de
    # carregar 13 GB de modelo para falhar la dentro.
    yaw: float = Field(50.0, ge=-180.0, le=180.0)
    # Orbit: so a previa do angulo (malha do corpo vista da camera nova), sem gerar.
    previa_angulo: bool = False
    # Orbit 3D (modelo "orbita3d"): giro da camera e altura em graus.
    giro_3d: float = Field(0.0, ge=-180.0, le=180.0)
    altura_3d: float = Field(0.0, ge=-60.0, le=60.0)
    # Estreitadas junto com o preset, e pela mesma medicao: -60 perde a leitura
    # de "em pe" e 0,6 corta a cabeca. Duplicar a faixa em dois lugares diverge
    # — ja aconteceu aqui com o alinhamento do LTX —, entao se uma mudar, a
    # outra muda no mesmo commit.
    elevation: float = Field(0.0, ge=-45.0, le=60.0)
    distance: float = Field(1.0, ge=0.8, le=1.8)
    # Ângulo e reiluminação: qual das duas operações. Ver presets.ANGULO e
    # presets.RELUZ — não são dois níveis de qualidade, são coisas diferentes.
    metodo_angulo: str = "camera"
    metodo_luz: str = "direcional"
    # Ajuste fino de rosto: id do controle -> valor. Ver presets.ROSTO.
    rosto: dict[str, float] = Field(default_factory=dict)
    # Ângulo e reiluminação.
    vista: str = "tres_quartos_esq"
    # Orbit com o Qwen (metodo_angulo "camera96"): uma das 96 poses da LoRA.
    camera_direcao: str = "front-right quarter view"
    camera_altura: str = "eye-level shot"
    camera_distancia: str = "medium shot"
    azimute: float = Field(-45.0, ge=-180.0, le=180.0)
    elevacao: float = Field(25.0, ge=-90.0, le=90.0)
    intensidade: float = Field(1.0, ge=0.1, le=1.5)
    temperatura: str = "neutra"
    usar_mapa_luz: bool = True
    # Controle de estrutura.
    tipo_controle: str = "contorno"
    forca_controle: float = Field(1.0, ge=0.1, le=2.0)
    # Freio do artefato nas edições: o tipo escolhe QUAIS defeitos combater,
    # o nível escolhe com que força.
    tipo_imagem: str = presets.TIPO_IMAGEM_PADRAO
    nivel_pele: str = presets.NIVEL_PELE_PADRAO
    # Máscara opcional: com um alvo descrito em texto, só a região achada pelo
    # SAM 3 recebe o resultado; o resto é copiado do original.
    mascara_alvo: str = ""
    mascara_limiar: float = Field(0.5, ge=0.05, le=0.95)
    mascara_expandir: int = Field(12, ge=-64, le=128)
    mascara_suavizar: int = Field(12, ge=0, le=128)


class PedidoTexto(Pedido):
    ideia: str
    proporcao: str = "1:1"
    # Foto de fundo, quando houver. Sem ela a sugestao de layout e cega —
    # e foi assim que o texto foi parar em cima do letreiro da mercearia.
    fundo: str | None = None


# ---------------------------------------------------------------- estado da fila

class Tarefa:
    def __init__(self, pedido: PedidoGeracao):
        self.id = str(uuid.uuid4())
        self.pedido = pedido
        self.prompt_id: str | None = None
        self.estado = "na_fila"      # na_fila | preparando | executando | pronto | erro
        self.progresso = 0.0
        self.detalhe = ""
        self.etapa_no = ""
        self.etapa_iniciada_em = 0.0
        self.ultimo_avanco_em = 0.0
        self.passo_atual = 0
        self.passos_total = 0
        self.imagens: list[str] = []
        self.erro = ""
        self.criada_em = time.time()
        self.iniciada_em = 0.0      # quando saiu da fila e o trabalho comecou
        self.duracao = 0.0          # segundos do inicio do trabalho ate a imagem
        self.largura = 0
        self.altura = 0
        self.resultado_texto = ""
        self.prompt_final = ""
        self.caption: dict | None = None
        # Aviso nao bloqueante: a peca sai, mas algo merece
        # atencao — hoje, contraste baixo do texto sobre a foto.
        self.aviso = ""
        # Dolares medidos pela diferenca de saldo. So nos modelos de nuvem.
        self.custo_usd = 0.0
        # Medidos do arquivo quando a saida e video; zero nas imagens.
        self.duracao_video = 0.0
        self.fps = 0.0
        self.saldo_antes = None
        self.imagens_cobranca: list[str] = []
        self.variacoes_concluidas = 0
        self._ultima_gravacao = 0.0
        self._assinatura_gravada = None

    def como_dict(self):
        return {"id": self.id, "estado": self.estado, "progresso": self.progresso,
                "custo_usd": self.custo_usd,
                "duracao_video": self.duracao_video,
                "detalhe": self.detalhe, "imagens": self.imagens, "erro": self.erro,
                "modelo": self.pedido.modelo, "prompt": self.pedido.prompt,
                "teste": self.pedido.teste, "rotulo_teste": self.pedido.rotulo_teste,
                "prompt_final": self.prompt_final, "criada_em": self.criada_em,
                "duracao": self.duracao,
                "iniciada_em": self.iniciada_em,
                "modelo_video": self.pedido.modelo_video if self.pedido.modelo == "video" else None,
                "etapa_no": self.etapa_no, "etapa_iniciada_em": self.etapa_iniciada_em,
                "ultimo_avanco_em": self.ultimo_avanco_em,
                "passo_atual": self.passo_atual, "passos_total": self.passos_total,
                "largura": self.largura, "altura": self.altura,
                "aviso": self.aviso, "resultado_texto": self.resultado_texto,
                # O mapa de profundidade pode ter gerado quadros EXR para baixar.
                "exr": self.pedido.modelo == "profundidade_video" and self.pedido.exr}

    def registro(self):
        dados = {k: v for k, v in vars(self).items() if not k.startswith("_")}
        dados["pedido"] = self.pedido.model_dump()
        return dados

    @classmethod
    def de_registro(cls, dados: dict):
        tarefa = cls(PedidoGeracao.model_validate(dados["pedido"]))
        for chave, valor in dados.items():
            if chave != "pedido" and hasattr(tarefa, chave):
                setattr(tarefa, chave, valor)
        return tarefa


TAREFAS: dict[str, Tarefa] = {}
POR_PROMPT_ID: dict[str, Tarefa] = {}
FILA: asyncio.Queue[Tarefa] = asyncio.Queue()
OUVINTES: set[WebSocket] = set()
COBRANCA_PENDENTE: asyncio.Task | None = None


async def transmitir(evento: dict):
    mortos = []
    for ws in list(OUVINTES):
        try:
            await ws.send_json(evento)
        except Exception:
            mortos.append(ws)
    for ws in mortos:
        OUVINTES.discard(ws)


async def anunciar(tarefa: Tarefa):
    assinatura = (tarefa.estado, tarefa.prompt_id, tarefa.custo_usd,
                  len(tarefa.imagens), len(tarefa.imagens_cobranca))
    agora = time.monotonic()
    if (assinatura != tarefa._assinatura_gravada
            or agora - tarefa._ultima_gravacao >= 2):
        biblioteca.salvar_tarefa(tarefa.registro())
        tarefa._ultima_gravacao = agora
        tarefa._assinatura_gravada = assinatura
    await transmitir({"tipo": "tarefa", "dados": tarefa.como_dict()})


# ---------------------------------------------------------------- montagem do grafo

def freio_pele(pedido: PedidoGeracao) -> str:
    """Negativo que segura o artefato. Ver presets.TIPOS_IMAGEM."""
    negativo = pedido.negativo
    if comfy.modo_seguro():
        negativo = f"{negativo}, {seguro.NEGATIVO}" if negativo.strip() else seguro.NEGATIVO
    return presets.negativo_do_tipo(pedido.tipo_imagem, pedido.nivel_pele, negativo)


async def escolher_modelo_personagem(prioridade: str = "rapido") -> tuple[str, int, float]:
    """Qual dos dois Klein usar, segundo a chave Rápido/Fiel.

    "Rápido" só existe se o destilado estiver no disco — ele mora num
    repositório restrito da Black Forest Labs (exige aceitar a licença e
    autenticar), então não dá para assumir que existe. Sem ele, o pedido cai
    em "fiel" em vez de falhar: é lento, mas é o que dá o resultado certo.
    """
    e = presets.PERSONAGEM
    fiel = e["prioridades"]["fiel"]
    modo = e["prioridades"].get(prioridade, fiel)
    if modo["destilado"] and e["unet"] in await comfy.unets_disponiveis():
        return e["unet"], modo["steps"], modo["cfg"]
    return e["unet_alternativo"], fiel["steps"], fiel["cfg"]


# Pasta onde o motor grava. Barras normais de proposito: o Windows as aceita e
# elas evitam que uma letra maiuscula depois da barra invertida vire escape de
# unicode no codigo-fonte.
SAIDA_DO_MOTOR = config.COMFY_SAIDA
ENTRADA_DO_MOTOR = config.COMFY_ENTRADA


def _caminho_de_saida(referencia: str) -> str:
    """Caminho absoluto de um arquivo da galeria, ou "" se ele nao existir.

    Recebe "subpasta/arquivo" ou so "arquivo". Confere a existencia ANTES de
    montar o grafo: o no de video falharia com uma mensagem do ffmpeg, que nao
    diz nada a quem esta usando o site.
    """
    alvo = (SAIDA_DO_MOTOR / referencia).resolve()
    # Nao deixa escapar da pasta de saida, mesmo com ".." na referencia.
    try:
        alvo.relative_to(SAIDA_DO_MOTOR.resolve())
    except ValueError:
        return ""
    return str(alvo) if alvo.exists() else ""


def _caminho_de_entrada(referencia: str) -> str:
    """Caminho absoluto de um upload na pasta input, ou "" se for invalido.

    O LoadImage aceita nome relativo, mas o VHS_LoadAudio valida um VHS_PATH e
    recusou o mesmo nome que o endpoint de upload acabara de gravar. Resolver
    aqui tambem impede que um nome vindo do pedido escape da pasta de entrada.
    """
    alvo = (ENTRADA_DO_MOTOR / referencia).resolve()
    try:
        alvo.relative_to(ENTRADA_DO_MOTOR.resolve())
    except ValueError:
        return ""
    return str(alvo) if alvo.exists() else ""


async def montar(tarefa: Tarefa):
    """Traduz o pedido num grafo do ComfyUI, chamando o LLM quando preciso."""
    global MOTOR_CARREGADO
    p = tarefa.pedido
    metodo = (p.metodo_angulo if p.modelo == "angulo"
              else p.metodo_luz if p.modelo == "reluz"
              else p.metodo_ampliar if p.modelo == "ampliar"
              else p.prioridade if p.modelo == "personagem" else "")
    # Modelo de nuvem nao ocupa a placa: quem estava carregado continua
    # carregado. Sobrescrever aqui faria a interface anunciar como motor
    # ativo um modelo que nunca esteve na VRAM.
    # "nuvem" vale tanto para os modelos de nuvem quanto para metodos de
    # nuvem dentro de um modo local, como o Magnific dentro do Reluz.
    if (p.modelo not in presets.NUVEM and p.modelo != "recorte"
            and presets.motor_do(p.modelo, metodo) != "nuvem"):
        MOTOR_CARREGADO = presets.motor_do(p.modelo, metodo)
    largura, altura = presets.dimensoes(p.proporcao, p.escala)
    if p.nativo_4k and presets.SIMPLE.get(p.modelo, {}).get("nativo_4k"):
        largura, altura = presets.dimensoes_4k(p.proporcao)
        p.lote = 1  # duas de uma vez nao cabem na placa
    tarefa.largura, tarefa.altura = largura, altura
    seed = p.seed if p.seed is not None else random.randint(0, 2**52)
    tarefa.pedido.seed = seed
    prefixo = f"editor/{p.modelo}"

    if p.modelo == "musica":
        tarefa.largura = tarefa.altura = 0
        tarefa.prompt_final = musica.configuracao_geracao(p)[0]
        cfg = next(c for c in await musica.catalogo() if c["id"] == p.modelo_musica)
        if not cfg["disponivel"]: raise comfy.ErroComfy(cfg["motivo"])
        if cfg.get("plenio"):
            return musica.grafo_yue2(p, seed, p.estilo_musica, p.etapa_musica, p.docs_musica)
        return musica.grafo(p, seed, cfg["pesos"])

    if p.modelo == "transcricao_voz":
        tarefa.largura = tarefa.altura = 0
        return voz.grafo_transcricao(p.referencia_voz, p.idioma_referencia_voz)

    if p.modelo == "avatar":
        tarefa.prompt_final = p.prompt
        if p.modelo_avatar in avatar.API:
            return avatar.grafo_api(p, seed, prefixo)
        if p.modelo_avatar == "ltx23":
            tarefa.largura, tarefa.altura = ((704, 1280) if p.vertical_avatar
                                             else (avatar.LTX23["largura"], avatar.LTX23["altura"]))
            return avatar.grafo_ltx23(p, seed, p.duracao_avatar, prefixo, p.vertical_avatar)
        tarefa.largura, tarefa.altura = avatar.LARGURA, avatar.ALTURA
        return avatar.grafo(p, seed, p.duracao_avatar, prefixo)

    if p.modelo == "genjutsu":
        caminho = _video_de_referencia(p.referencias[0]) if p.referencias else None
        if not caminho:
            raise ValueError("não encontrei esse vídeo")
        refs = [r for r in p.referencias[1:] if r]
        tarefa.prompt_final = p.prompt
        sufixo = pathlib.Path(caminho).suffix
        if p.modelo_genjutsu == "wan_animate2":
            if not refs:
                raise ValueError("envie a foto do personagem")
            dados = await asyncio.to_thread(genjutsu.video_wan, caminho)
            d = await asyncio.to_thread(miniaturas.dados_do_video, dados)
            # O Wan Animate 2 anima o personagem DENTRO da foto (o fundo vem
            # dela), entao o enquadramento e o da foto; o video so da o
            # movimento. Com o tamanho do video, um retrato em pe recortado
            # para 16:9 perdia a cabeca (teste de 23/10/2026).
            from PIL import Image
            with Image.open(_caminho_de_entrada(refs[0])) as im:
                larg, alt = genjutsu.tamanho_wan(*im.size)
            tarefa.largura, tarefa.altura = larg, alt
            entrada = await comfy.enviar_imagem(f"genjutsu_{uuid.uuid4().hex[:12]}.mp4", dados)
            return genjutsu.grafo_wan_animate2(entrada, refs[0], p.prompt, genjutsu.quadros_wan(dados),
                                               larg, alt, seed, prefixo)
        if p.modelo_genjutsu == "wan22_replace":
            if not refs:
                raise ValueError("envie a foto do personagem")
            dados = await asyncio.to_thread(genjutsu.video_wan, caminho)
            d = await asyncio.to_thread(miniaturas.dados_do_video, dados)
            # Aqui o personagem entra NO video: o enquadramento e o do video.
            larg, alt = genjutsu.tamanho_wan(d["largura"] or 16, d["altura"] or 9)
            tarefa.largura, tarefa.altura = larg, alt
            entrada = await comfy.enviar_imagem(f"genjutsu_{uuid.uuid4().hex[:12]}.mp4", dados)
            g = genjutsu.grafo_wan22_replace(entrada, refs[0], p.prompt, genjutsu.quadros_wan(dados),
                                             larg, alt, seed, prefixo, alvo=p.alvo_genjutsu)
            if not comfy.na_nuvem():  # o instalador grava o SAM numa subpasta
                g["sam"]["inputs"]["ckpt_name"] = "SAM3\\sam3.1_multiplex_fp16.safetensors"
            return g
        if p.modelo_genjutsu == "h3_swap":
            if not refs:
                raise ValueError("envie a foto do personagem")
            dados, quadros = await asyncio.to_thread(genjutsu.video_h3, caminho)
            d = await asyncio.to_thread(miniaturas.dados_do_video, dados)
            larg, alt = genjutsu.tamanho_h3(d["largura"] or 16, d["altura"] or 9)
            tarefa.largura, tarefa.altura = larg, alt
            com_som = bool(await asyncio.to_thread(miniaturas.tem_audio, caminho))
            entrada = await comfy.enviar_imagem(f"genjutsu_{uuid.uuid4().hex[:12]}.mp4", dados)
            return genjutsu.grafo_h3_swap(entrada, refs[0], quadros, larg, alt, seed, prefixo,
                                          alvo=p.alvo_genjutsu, pedido=p.prompt, gemini=p.gemini_genjutsu,
                                          turbo=p.turbo_genjutsu, com_som=com_som, local=not comfy.na_nuvem())
        dados = await asyncio.to_thread(pathlib.Path(caminho).read_bytes)
        d = await asyncio.to_thread(miniaturas.dados_do_video, dados)
        if p.modelo_genjutsu == "kling_omni":
            maior = await asyncio.to_thread(genjutsu.video_minimo, caminho, d["largura"] or 0, d["altura"] or 0)
            if maior:
                dados, sufixo = maior, ".mp4"
                d = await asyncio.to_thread(miniaturas.dados_do_video, dados)
        entrada = await comfy.enviar_imagem(f"genjutsu_{uuid.uuid4().hex[:12]}{sufixo}", dados)
        larg, alt = d["largura"] or 16, d["altura"] or 9
        proporcao = "16:9" if larg / alt > 1.2 else "9:16" if larg / alt < 0.83 else "1:1"
        return genjutsu.grafo_api(p.modelo_genjutsu, entrada, refs, p.prompt, seed,
                                  d["duracao"] or 5, proporcao, prefixo)

    if p.modelo == "voz":
        tarefa.largura = tarefa.altura = 0
        tarefa.prompt_final = p.prompt
        return voz.grafo_nuvem(p, seed) if comfy.na_nuvem() else voz.grafo(p, seed)

    if p.modelo in presets.NUVEM:
        # Nao passa por presets.dimensoes: quem decide o tamanho e o provedor,
        # a partir da proporcao e da resolucao. As dimensoes reais so se sabem
        # quando a imagem volta, e esperar_fim as mede do arquivo.
        cfg = presets.NUVEM[p.modelo]

        if cfg["familia"] == "generico":
            tarefa.prompt_final = p.prompt
            return workflows.gerar_api_generico(cfg, p.prompt, seed, p.proporcao, p.resolucao_nuvem,
                                                p.referencias, prefixo)

        if cfg["familia"] == "openai":
            # A tela mostra apenas 1K/2K/4K. A proporcao decide qual tamanho
            # horizontal, vertical ou quadrado o no realmente recebe.
            tamanho = presets.tamanho_gpt(p.resolucao_nuvem, p.proporcao)
            qualidade = (p.qualidade_nuvem if p.qualidade_nuvem in cfg["qualidades"]
                         else "medium")
            fundos = [i for i, _ in cfg["fundos"]]
            tarefa.prompt_final = p.prompt
            return workflows.gerar_openai(
                cfg["modelo"], p.prompt, seed, tamanho, qualidade,
                p.fundo_nuvem if p.fundo_nuvem in fundos else "auto",
                p.referencias, prefixo)

        proporcao = p.proporcao if p.proporcao in presets.PROPORCOES_NUVEM else None
        if proporcao is None:
            # 3:1 e o unico da nossa lista que o no nao conhece. Recusar seria
            # pior que aproximar, mas o usuario precisa saber que aproximamos.
            proporcao = "21:9"
            tarefa.aviso = (f"A proporção {p.proporcao} não existe neste modelo; "
                            f"foi usada a mais próxima, 21:9.")
        resolucao = (p.resolucao_nuvem if p.resolucao_nuvem in cfg["resolucoes"]
                     else cfg["resolucoes"][0])
        tarefa.prompt_final = p.prompt
        return workflows.gerar_nuvem(p.modelo, p.prompt, seed, proporcao,
                                     resolucao, p.referencias, prefixo)

    if p.modelo == "personagem":
        e = presets.PERSONAGEM
        if len(p.referencias) < e["min_referencias"]:
            raise ValueError("envie ao menos a cena e a pessoa que entra")
        refs = p.referencias[:e["max_referencias"]]
        # Sem a 3ª imagem, a 2ª também é a referência de rosto — a instrução
        # fala em "Figure 3", então ela precisa existir no grafo.
        if len(refs) == 2:
            refs = refs + [refs[1]]
        unet, steps, cfg = await escolher_modelo_personagem(p.prioridade)
        instrucao = workflows.instrucao_de_personagem(p.blocos, p.prompt)
        tarefa.prompt_final = instrucao
        return workflows.trocar_personagem(
            instrucao, refs, seed, unet,
            p.steps or steps, p.cfg if p.cfg is not None else cfg,
            prefixo=prefixo, negativo=freio_pele(p))

    if p.modelo == "rosto":
        if not p.referencias:
            raise ValueError("envie uma imagem")
        tarefa.prompt_final = ", ".join(f"{k} {v:g}" for k, v in sorted(p.rosto.items())
                                        if v) or "sem ajuste"
        return workflows.ajustar_rosto(p.referencias[0], p.rosto, prefixo=prefixo)

    if p.modelo in ("angulo", "reluz"):
        if not p.referencias:
            raise ValueError("envie uma imagem")
        refs = [p.referencias[0]]
        cfg_modo = presets.ANGULO if p.modelo == "angulo" else presets.RELUZ
        escolhido = (p.metodo_angulo if p.modelo == "angulo" else p.metodo_luz)
        metodo = cfg_modo["metodos"].get(escolhido) or             cfg_modo["metodos"][cfg_modo["metodo_padrao"]]

        if p.modelo == "angulo":
            if p.vista not in presets.ANGULO["vistas"]:
                raise ValueError(f"vista desconhecida: {p.vista}")
            instrucao = (workflows.instrucao_de_camera96(
                p.camera_direcao, p.camera_altura, p.camera_distancia, p.prompt)
                if escolhido == "camera96" else workflows.instrucao_de_angulo(
                p.vista, p.prompt, metodo=escolhido if metodo["motor"] == "qwen"
                else "personagem"))
        elif escolhido == "nuvem":
            # O Magnific nao usa a esfera nem a frase construida: ou recebe
            # uma referencia de luz, ou a descricao escrita pelo usuario. A
            # segunda referencia, quando existe, e a imagem de onde copiar.
            luz_ref = p.referencias[1] if len(p.referencias) > 1 else None
            descricao = p.prompt.strip()
            if not descricao and not luz_ref:
                raise ValueError(
                    "descreva a luz que você quer, ou envie uma imagem de "
                    "referência para copiar a luz dela")
            tarefa.prompt_final = descricao or "luz copiada da referência"
            return workflows.reluz_magnific(
                p.referencias[0], descricao, estilo=p.estilo_luz,
                forca=p.forca_luz, referencia=luz_ref,
                mudar_fundo=p.mudar_fundo_luz, prefixo=prefixo)
        else:
            frase = luz.em_palavras(p.azimute, p.elevacao, p.intensidade,
                                    p.temperatura)
            usa_mapa = p.usar_mapa_luz and metodo["motor"] != "qwen"
            instrucao = workflows.instrucao_de_luz(
                frase, p.prompt, com_mapa=usa_mapa,
                gatilho=metodo.get("gatilho", ""))
            # O mapa so serve ao caminho do Klein. No caminho direcional a
            # LoRA segue a direcao escrita, e mandar a esfera junto faz ela ser
            # DESENHADA dentro da cena — aconteceu no teste, apesar da frase
            # que manda nao desenhar.
            if usa_mapa:
                # O mapa entra como segunda referência. Vai para a pasta de
                # entrada do motor com um nome estável por parâmetro, então
                # repetir a mesma luz não reenvia o arquivo.
                caminho = luz.arquivo(p.azimute, p.elevacao, p.intensidade,
                                      p.temperatura)
                enviado = await comfy.enviar_imagem(caminho.name,
                                                    await asyncio.to_thread(caminho.read_bytes))
                refs.append(enviado)
        tarefa.prompt_final = instrucao
        if metodo["motor"] == "qwen":
            return workflows.editar_qwen(instrucao, refs, seed, megapixels=1.5,
                                         prefixo=prefixo, lora=metodo["lora"],
                                         forca_lora=metodo.get("forca", 1.0))
        e = presets.EDICAO["trocar"]
        return workflows.editar_klein(instrucao, refs, seed,
                                      steps=p.steps or e["steps"],
                                      cfg=p.cfg if p.cfg is not None else e["cfg"],
                                      prefixo=prefixo, negativo=freio_pele(p))

    if p.modelo == "video" and p.modelo_video in presets.VIDEO_API:
        cfg = presets.VIDEO_API[p.modelo_video]
        if p.modo_video not in cfg["modos"]:
            raise ValueError(f'{cfg["rotulo"]} não faz este modo')
        refs = p.referencias or []
        tarefa.prompt_final = p.prompt
        if cfg.get("familia") == "generico":
            return workflows.gerar_video_generico(
                cfg, p.modo_video, p.prompt, seed,
                p.proporcao_video if p.proporcao_video in cfg["proporcoes"] else cfg["proporcoes"][0],
                p.resolucao_video if p.resolucao_video in cfg["resolucoes"] else cfg["resolucoes"][0],
                max(cfg["duracao_min"], min(cfg["duracao_max"], p.duracao_video)),
                imagem=refs[0] if refs else None, imagem_final=refs[1] if len(refs) > 1 else None,
                com_audio=p.com_audio and not cfg.get("sem_audio"), prefixo=prefixo)
        return workflows.gerar_video_api(
            p.modelo_video, p.prompt, seed, p.modo_video,
            p.proporcao_video if p.proporcao_video in cfg["proporcoes"] else cfg["proporcoes"][0],
            p.resolucao_video if p.resolucao_video in cfg["resolucoes"] else cfg["resolucoes"][0],
            max(cfg["duracao_min"], min(cfg["duracao_max"], p.duracao_video)),
            imagem=refs[0] if refs else None, imagem_final=refs[1] if len(refs) > 1 else None,
            com_audio=p.com_audio and not cfg.get("sem_audio"), prefixo=prefixo,
            referencias=refs if p.modo_video == "referencia" else ())

    if p.modelo == "video" and p.modelo_video == "wan3":
        cfg = presets.VIDEO_WAN3
        if p.modo_video not in cfg["modos"]:
            raise ValueError(
                f'o Wan 3.0 não faz "{p.modo_video}" — ele precisa de pelo '
                f"menos uma imagem")
        refs = p.referencias or []
        tarefa.prompt_final = p.prompt
        return workflows.gerar_video_wan3(
            p.prompt, seed, modo=p.modo_video, variante=p.variante_video,
            resolucao=(p.resolucao_video if p.resolucao_video in cfg["resolucoes"]
                       else cfg["resolucao_padrao"]),
            proporcao=(p.proporcao_video if p.proporcao_video in cfg["proporcoes"]
                       else cfg["proporcao_padrao"]),
            duracao=p.duracao_video,
            imagem=refs[0] if refs else None,
            imagem_final=refs[1] if len(refs) > 1 else None,
            referencias=refs, com_audio=p.com_audio,
            melhorar_prompt=p.melhorar_prompt, prefixo=prefixo)

    if p.modelo == "video" and p.modelo_video == "minimax-ref-nuvem":
        cfg = presets.VIDEO_MINIMAX_REF_NUVEM
        refs = p.referencias or []
        if not refs:
            raise ValueError("envie ao menos uma imagem de referência")
        tarefa.prompt_final = p.prompt
        # As dimensoes reais so se sabem quando o video volta, como no outro
        # gerador por nuvem: quem mede e o `esperar_fim`, no arquivo.
        return workflows.gerar_video_minimax_ref_nuvem(
            p.prompt, seed, refs,
            variante=p.variante_video or cfg["variante_padrao"],
            resolucao=p.resolucao_video, proporcao=p.proporcao_video,
            duracao=p.duracao_video, prefixo=prefixo)

    if p.modelo == "video" and p.modelo_video == "minimax-nuvem":
        cfg = presets.VIDEO_MINIMAX_NUVEM
        refs = p.referencias or []
        tarefa.prompt_final = p.prompt
        # As dimensoes reais so se sabem quando o video volta; esperar_fim as
        # mede do arquivo. Aqui nao ha pixels a declarar.
        return workflows.gerar_video_minimax_nuvem(
            p.prompt, seed, modo=p.modo_video,
            proporcao=(p.proporcao_video if p.proporcao_video in cfg["proporcoes"]
                       else cfg["proporcao_padrao"]),
            resolucao=(p.resolucao_video if p.resolucao_video in cfg["resolucoes"]
                       else cfg["resolucao_padrao"]),
            # O no recusa fora de 5..15; prender aqui evita uma ida ao
            # motor so para ouvir "nao".
            duracao=max(cfg["duracao_minima"],
                        min(cfg["duracao_maxima"], p.duracao_video)),
            imagem=refs[0] if refs else None,
            imagem_final=refs[1] if len(refs) > 1 else None,
            prefixo=prefixo)

    if p.modelo == "video" and p.modelo_video == "planos":
        raise ValueError("este gerador foi removido; use o MiniMax H3 ou o LTX")

    if p.modelo == "video" and p.modelo_video == "fasth3":
        cfg = presets.VIDEO_FASTH3
        larg, alt = presets.tamanho_de_video(p.resolucao_video, p.proporcao_video,
                                             cfg["alinhamento"])
        refs = p.referencias or []
        if p.modo_video not in ("texto", "imagem", "primeiro_ultimo"):
            raise ValueError("o FastH3 não faz esse modo; para referências use o MiniMax H3")
        if p.modo_video in ("imagem", "primeiro_ultimo") and not refs:
            raise ValueError("envie a imagem do primeiro quadro")
        if p.modo_video == "primeiro_ultimo" and len(refs) < 2:
            raise ValueError("envie DUAS imagens: o primeiro e o último quadro")
        tarefa.largura, tarefa.altura = larg, alt
        tarefa.prompt_final = p.prompt
        return workflows.gerar_video_fasth3(
            p.prompt, seed, larg, alt,
            max(cfg["duracao_min"], min(cfg["duracao_max"], p.duracao_video)),
            imagem=refs[0] if p.modo_video != "texto" and refs else None,
            imagem_final=refs[1] if p.modo_video == "primeiro_ultimo" else None,
            com_audio=p.com_audio, prefixo=prefixo)

    if p.modelo == "video" and p.modelo_video == "minimax":
        # Pesos abertos: local em placas grandes, ou na Comfy Cloud com os
        # mesmos nomes de arquivo (ver presets.VIDEO_MINIMAX).
        cfg = presets.VIDEO_MINIMAX
        larg, alt = presets.tamanho_de_video(p.resolucao_video, p.proporcao_video,
                                             cfg["alinhamento"])
        refs = p.referencias or []
        if p.modo_video in ("imagem", "primeiro_ultimo") and not refs:
            raise ValueError("envie a imagem do primeiro quadro")
        if p.modo_video == "primeiro_ultimo" and len(refs) < 2:
            raise ValueError("envie DUAS imagens: o primeiro e o último quadro")
        tarefa.largura, tarefa.altura = larg, alt
        tarefa.prompt_final = p.prompt
        return workflows.gerar_video_minimax(
            p.prompt, seed, larg, alt,
            max(cfg["duracao_min"], min(cfg["duracao_max"], p.duracao_video)),
            imagem=refs[0] if p.modo_video != "texto" and refs else None,
            imagem_final=refs[1] if p.modo_video == "primeiro_ultimo" else None,
            turbo=p.turbo, com_audio=p.com_audio, prefixo=prefixo)

    if p.modelo == "video" and p.modelo_video == "ltx23":
        cfg = presets.VIDEO_LTX23
        larg, alt = presets.tamanho_de_video(p.resolucao_video, p.proporcao_video,
                                             cfg["alinhamento"])
        if larg * alt > cfg["max_pixels"]:
            raise ValueError(f"{larg}x{alt} é grande demais para o LTX 2.3 — use 720p ou menos")
        if not p.referencias:
            raise ValueError("envie a imagem do primeiro quadro")
        final = None
        if p.modo_video == "primeiro_ultimo":
            if len(p.referencias) < 2:
                raise ValueError("envie DUAS imagens: o primeiro e o último quadro")
            final = p.referencias[1]
        duracao = min(float(p.duracao_video), cfg["duracao_max"])
        trilha = p.referencias_audio[0] if p.referencias_audio else None
        if trilha:
            # O audio e cortado na duracao do video; se for mais curto, o
            # video encolhe para ele, em vez de ficar com o fim sem som.
            duracao = min(duracao, await avatar.duracao_audio(trilha))
        tarefa.largura, tarefa.altura = larg, alt
        tarefa.prompt_final = p.prompt
        return ltx23.grafo(p.prompt, seed, larg, alt, duracao, p.referencias[0],
                           ultimo=final, audio=trilha, prefixo=prefixo)

    if p.modelo == "video" and p.modelo_video in videos_leves.VIDEO_LEVES:
        cfg = videos_leves.VIDEO_LEVES[p.modelo_video]
        if p.modo_video not in cfg["modos"]:
            raise ValueError(f"o {cfg['rotulo']} não tem esse modo")
        if p.modo_video in ("imagem", "primeiro_ultimo") and not p.referencias:
            raise ValueError("envie a imagem de partida")
        if p.modo_video == "primeiro_ultimo" and len(p.referencias) < 2:
            raise ValueError("envie DUAS imagens: o primeiro e o último quadro")
        resolucao = p.resolucao_video if p.resolucao_video in cfg["resolucoes"] else cfg["resolucoes"][0]
        larg, alt = presets.tamanho_de_video(resolucao, p.proporcao_video, cfg["alinhamento"])
        tarefa.largura, tarefa.altura = larg, alt
        tarefa.prompt_final = p.prompt
        return videos_leves.grafo(p.modelo_video, p.prompt, seed, larg, alt, p.duracao_video,
                                  imagem=p.referencias[0] if p.modo_video in ("imagem", "primeiro_ultimo") else None,
                                  imagem_final=p.referencias[1] if p.modo_video == "primeiro_ultimo" else None,
                                  prefixo=prefixo)

    if p.modelo == "video":
        cfg = presets.VIDEO_LTX
        larg, alt = presets.tamanho_de_video(p.resolucao_video, p.proporcao_video,
                                             cfg["alinhamento"])
        max_pixels = cfg.get("max_pixels", presets.MAX_PIXELS_VIDEO_LOCAL)
        if larg * alt > max_pixels:
            raise ValueError(
                f"{larg}x{alt} é grande demais para a placa neste modelo — "
                f"o limite é de {max_pixels:,} "
                f"pixels por quadro")
        tarefa.largura, tarefa.altura = larg, alt
        tarefa.prompt_final = p.prompt
        audio_referencia = None
        if p.referencias_audio:
            if not p.com_audio:
                raise ValueError("ative 'Gerar com som' para usar a voz de referência")
            audio_referencia = _caminho_de_entrada(p.referencias_audio[0])
            if not audio_referencia:
                raise ValueError("não encontrei o áudio de identidade")

        if p.modo_video == "primeiro_ultimo":
            if len(p.referencias) < 2:
                raise ValueError("envie DUAS imagens: o primeiro e o último quadro")
            return workflows.gerar_video_ltx_flf(
                p.prompt, seed, p.referencias[0], p.referencias[1],
                largura=larg, altura=alt, duracao=p.duracao_video,
                com_audio=p.com_audio, prompt_automatico=p.prompt_automatico,
                audio_referencia=audio_referencia,
                forca_audio_referencia=p.forca_audio_referencia,
                prefixo=prefixo)

        if p.modo_video == "referencia":
            if not p.referencias:
                raise ValueError("envie ao menos uma imagem de referência")
            return workflows.gerar_video_ltx_msr(
                p.prompt, seed, p.referencias, fundo=p.fundo_referencia,
                largura=larg, altura=alt, duracao=p.duracao_video,
                com_audio=p.com_audio, audio_referencia=audio_referencia,
                forca_audio_referencia=p.forca_audio_referencia,
                prefixo=prefixo)

        if p.modo_video == "chaves":
            if len(p.referencias) < 2:
                raise ValueError("escolha ao menos duas imagens")
            a, b = (float(x) for x in p.proporcao_video.split(":"))
            larg_c, alt_c = presets.tamanho_chaves(round(a * 1000), round(b * 1000))
            pedidos = int(p.duracao_video * 24) + 1
            quadros = min(361, ((max(pedidos, 9) - 1) // 8) * 8 + 1)
            if quadros < pedidos:
                tarefa.aviso = (f"Quadros-chave vão até {quadros / 24:.1f} s (testado); "
                                f"o vídeo saiu com essa duração.")
            # Cada imagem no seu quadro, levado a multiplo de 8; duas no mesmo
            # lugar, fica a ultima. Sem numero, espalha por igual.
            n = len(p.referencias)
            numeros = [p.quadros_referencias[i] if i < len(p.quadros_referencias)
                       else 1 + round(i * (quadros - 1) / max(1, n - 1)) for i in range(n)]
            posicoes = {_posicao_do_quadro(int(q), quadros): nome
                        for nome, q in zip(p.referencias, numeros)}
            chaves = [(nome, q) for q, nome in sorted(posicoes.items())]
            tarefa.largura, tarefa.altura = larg_c, alt_c
            tarefa.prompt_final = p.prompt
            return workflows.chaves_ltx(p.prompt, chaves, quadros, larg_c, alt_c,
                                        forca=p.forca_chaves, seed=seed,
                                        com_audio=p.com_audio, prefixo=prefixo)

        if p.modo_video == "ingredientes":
            if not p.referencias:
                raise ValueError("escolha ao menos uma imagem para a folha")
            refs = p.referencias[:presets.INGREDIENTES["max_imagens"]]
            # Mesmo tamanho dos efeitos: lado menor em 544, na proporcao pedida.
            a, b = (float(x) for x in p.proporcao_video.split(":"))
            larg_f, alt_f = presets.tamanho_transformar(round(a * 1000), round(b * 1000))
            dados = [await comfy.imagem(r, "", "input") for r in refs]
            png = await asyncio.to_thread(workflows.montar_folha, dados, larg_f, alt_f)
            folha = await comfy.enviar_imagem(f"folha_{uuid.uuid4().hex[:12]}.png", png)
            quadros = min(presets.VIDEO_TRANSFORMAR["max_quadros"],
                          ((max(int(p.duracao_video * 24), 9) - 1) // 8) * 8 + 1)
            tarefa.largura, tarefa.altura = larg_f, alt_f
            tarefa.prompt_final = p.prompt
            return workflows.ingredientes_ltx(folha, p.prompt, quadros, larg_f, alt_f,
                                              seed=seed, prefixo=prefixo)

        # "texto" e "imagem" sao o MESMO grafo; o que muda e haver ou nao
        # imagem de partida.
        imagem = p.referencias[0] if p.referencias else None
        if p.modo_video == "imagem" and not imagem:
            raise ValueError("envie a imagem de partida")
        g = workflows.gerar_video_ltx(
            p.prompt, seed, largura=larg, altura=alt, duracao=p.duracao_video,
            imagem=imagem, com_audio=p.com_audio,
            prompt_automatico=p.prompt_automatico,
            audio_referencia=audio_referencia,
            forca_audio_referencia=p.forca_audio_referencia, prefixo=prefixo)
        if p.velocidade_video < 1:
            g = workflows.aplicar_camera_lenta(g, p.velocidade_video)
        return g

    if p.modelo == "transformar_video":
        cfg = presets.VIDEO_TRANSFORMAR
        efeito = cfg["efeitos"].get(p.efeito_video)
        if not efeito:
            raise ValueError("efeito desconhecido")
        if not p.referencias:
            raise ValueError("escolha um vídeo da galeria")
        # "entrada:<nome>" e um video enviado do computador; o resto vem da galeria.
        caminho = _video_de_referencia(p.referencias[0])
        if not caminho:
            raise ValueError("não encontrei esse vídeo")
        estilo, chaves = None, []
        if efeito.get("imagem_estilo"):
            if len(p.referencias) >= 2 and p.referencias[1]:
                estilo = p.referencias[1]
            elif not efeito.get("imagem_opcional"):
                raise ValueError("este efeito precisa também da imagem de estilo")
        origem = await asyncio.to_thread(_video_a_24fps, caminho)
        d = await asyncio.to_thread(miniaturas.dados_do_video, origem)
        if not d["largura"]:
            raise ValueError("não consegui medir o vídeo")
        total = int(round((d["duracao"] or 0) * (d["fps"] or 24)))
        quadros, meio, fim = _quadros_e_posicoes(d, efeito.get("max_quadros"))
        inicio = 0
        if efeito.get("quadros_chave"):
            inicio, quadros = _trecho_maquete(total, p.inicio_maquete, efeito["max_quadros"], p.quadros_maquete)
            # Cada quadro-chave no seu momento (numero no render inteiro, contado de 1),
            # levado a posicao aceita pelo modelo dentro do trecho (multiplo de 8
            # quadros); dois no mesmo lugar, fica o ultimo.
            posicoes = {}
            for c in p.chaves_video:
                if c.get("imagem"):
                    posicoes[_posicao_do_quadro(int(c.get("quadro", 1)) - inicio, quadros)] = c["imagem"]
            chaves = [(nome, q) for q, nome in sorted(posicoes.items())]
        lado = 576
        if efeito.get("quadros_chave"):
            import maquina
            teto = presets.limite_maquete((await maquina.detectar()).get("vram_gb"))
            if teto is None:
                raise ValueError("3D render → Video needs a graphics card with at least 16 GB of VRAM.")
            lado = max(576, min(p.lado_maquete or teto, teto))
        if efeito.get("formatos"):
            larg, alt = efeito["formatos"][p.formato_saida]
        else:
            larg, alt = (presets.tamanho_troca if efeito.get("controles")
                         else (lambda l, a: presets.tamanho_maquete(l, a, lado)) if efeito.get("quadros_chave")
                         else presets.tamanho_transformar)(d["largura"], d["altura"])
        com_audio = bool(await asyncio.to_thread(miniaturas.tem_audio, caminho))
        # O LoadVideo do v0.41 so le da pasta de entrada.
        entrada = await comfy.enviar_imagem(
            f"transf_{uuid.uuid4().hex[:12]}{pathlib.Path(caminho).suffix}", origem)
        texto = " ".join(t for t in (p.prompt.strip(), efeito["texto"]) if t)
        tarefa.prompt_final = texto
        tarefa.largura, tarefa.altura = larg, alt
        if inicio or p.quadros_maquete:
            tarefa.aviso = (f"The render is {total / 24:.1f} s; used {quadros / 24:.1f} s "
                            f"from {inicio / 24:.1f} s.")
        elif quadros < total:
            tarefa.aviso = (f"The video is {total / 24:.1f} s; the first "
                            f"{quadros / 24:.1f} s were used.")
        if efeito.get("formatos"):
            return workflows.expandir_enquadramento(
                entrada, efeito["lora_completo"], texto, quadros,
                (d["largura"], d["altura"]), (larg, alt), seed=seed, com_audio=com_audio,
                prefixo=f"editor/video_{p.efeito_video}")
        if efeito.get("controles"):
            return workflows.trocar_personagem_video(
                entrada, efeito["lora_completo"], texto, quadros, larg, alt, estilo,
                controle=("pronto" if efeito.get("mapa_pronto") and p.mapa_pronto
                          else "profundidade" if p.efeito_video == "profundidade"
                          else p.controle_troca),
                seed=seed, com_audio=com_audio,
                prefixo=f"editor/video_{p.efeito_video}")
        if efeito.get("imagem_estilo"):
            return workflows.maquete_ltx(
                entrada, cfg["lora_pasta"] + efeito["lora"], texto, quadros, larg, alt,
                estilo, chaves, seed=seed, com_audio=com_audio,
                prefixo=f"editor/video_{p.efeito_video}", inicio=inicio)
        g = workflows.transformar_video(
            entrada, cfg["lora_pasta"] + efeito["lora"], texto, quadros, larg, alt,
            seed=seed, com_audio=com_audio, prefixo=f"editor/video_{p.efeito_video}")
        return workflows.em_base_ltx23(g) if comfy.na_nuvem() else g

    if p.modelo == "profundidade_video":
        if comfy.na_nuvem():
            raise ValueError("o mapa de profundidade roda só na sua placa: escolha Local")
        if not p.referencias:
            raise ValueError("envie um vídeo")
        caminho = _video_de_referencia(p.referencias[0])
        if not caminho:
            raise ValueError("não encontrei esse vídeo")
        origem = await asyncio.to_thread(pathlib.Path(caminho).read_bytes)
        d = await asyncio.to_thread(miniaturas.dados_do_video, origem)
        fps = d["fps"] or 24
        total = int(round((d["duracao"] or 0) * fps)) or 1
        quadros = min(total, int(MAX_SEGUNDOS_PROFUNDIDADE * fps))
        if quadros < total:
            tarefa.aviso = (f"O vídeo tem {total / fps:.1f} s; o mapa cobre os "
                            f"primeiros {MAX_SEGUNDOS_PROFUNDIDADE} s.")
        entrada = await comfy.enviar_imagem(
            f"prof_{uuid.uuid4().hex[:12]}{pathlib.Path(caminho).suffix}", origem)
        tarefa.largura, tarefa.altura = d["largura"], d["altura"]
        tarefa.prompt_final = ""
        return workflows.mapa_profundidade(
            entrada, quadros, colormap=p.mapa_cor,
            exr_pasta=f"editor/profundidade_exr_{tarefa.id[:8]}" if p.exr else None,
            prefixo="editor/video_profundidade")

    if p.modelo == "limpar_video":
        if not p.referencias:
            raise ValueError("escolha um vídeo da galeria")
        # O VHS_LoadVideoPath le do DISCO, por caminho absoluto, e nao
        # aceita upload. Por isso o que chega aqui e "subpasta/arquivo"
        # da galeria, nao um nome enviado para a pasta de entrada.
        # Da galeria ("subpasta/arquivo") ou enviado do computador ("entrada:").
        caminho = _video_de_referencia(p.referencias[0])
        if not caminho:
            raise ValueError("não encontrei esse vídeo")
        # A cadencia sai do ARQUIVO de origem, nao de um padrao: gravar um
        # clipe de 24 fps a 30 o deixaria mais curto e acelerado.
        origem = await asyncio.to_thread(pathlib.Path(caminho).read_bytes)
        d = await asyncio.to_thread(miniaturas.dados_do_video, origem)
        fps = d["fps"] or presets.VIDEO_LTX["fps"]
        # O VHS_LoadVideoPath EXPLODE ao tentar extrair audio de um video que
        # nao tem: "VHS failed to extract audio from ...". Como a ampliacao
        # pede essa saida para carregar a trilha original intacta, ela quebrava
        # todo video gerado com o som desligado — que e uma opcao da propria
        # tela. Por isso se pergunta antes.
        com_audio = await asyncio.to_thread(miniaturas.tem_audio, caminho)
        if com_audio is None:
            # Sem ffprobe nao da para saber. Seguir SEM audio e o lado seguro:
            # perde-se a trilha, mas amplia; pedir audio inexistente nao
            # amplia nada.
            com_audio = False
            tarefa.aviso = ("Não consegui verificar se o vídeo tem som "
                            "(ffprobe não encontrado); a ampliação seguiu "
                            "sem a trilha original.")
        tarefa.prompt_final = ""

        if p.metodo_video in presets.METODOS_RTX:
            # O LoadVideo do v0.41 so le da pasta de entrada: o video da
            # galeria vai para la com nome proprio.
            entrada = await comfy.enviar_imagem(
                f"rtx_{uuid.uuid4().hex[:12]}{pathlib.Path(caminho).suffix}", origem)
            if p.metodo_video == "rtx":
                if not d["largura"]:
                    raise ValueError("não consegui medir o vídeo")
                larg, alt = presets.alvo_de_ampliacao(d["largura"], d["altura"])
                if (larg, alt) == (d["largura"], d["altura"]):
                    raise ValueError(f"este vídeo já tem {larg}x{alt}, no limite "
                                     f"do que a placa aguenta")
                tarefa.largura, tarefa.altura = larg, alt
                return workflows.video_rtx(entrada, "rtx", larg, alt,
                                           prefixo="editor/video_ampliado_rtx")
            tarefa.largura, tarefa.altura = d["largura"], d["altura"]
            return workflows.video_rtx(entrada, "rtx48", prefixo="editor/video_48fps")

        if p.metodo_video == "ltx":
            # O alvo sai das dimensoes REAIS do arquivo — um video em pe e um
            # deitado precisam de alvos diferentes — e passa pelo TETO, senao
            # ampliar um video ja ampliado pediria 3200x4704 e estouraria.
            if not d["largura"]:
                raise ValueError("não consegui medir o vídeo")
            larg, alt = presets.alvo_de_ampliacao(d["largura"], d["altura"])
            if (larg, alt) == (d["largura"], d["altura"]):
                raise ValueError(
                    f'este video ja tem {larg}x{alt}, no limite do que a placa '
                    f'aguenta — ampliar nao traria ganho')
            tarefa.largura, tarefa.altura = larg, alt
            return workflows.ampliar_video_ltx(
                caminho, seed, larg, alt, descricao=p.prompt, fps=fps,
                com_audio=com_audio, origem=(d["largura"], d["altura"]),
                prefixo="editor/video_ampliado")

        return workflows.limpar_video(caminho, seed, p.resolucao_limpeza,
                                      fps=fps, com_audio=com_audio,
                                      prefixo="editor/video_limpo")

    if p.modelo == "recorte":
        if not p.referencias:
            raise ValueError("envie uma imagem")
        tarefa.prompt_final = ""
        return workflows.recortar_fundo(p.referencias[0], prefixo=prefixo)

    if p.modelo == "orbita3d":
        if not p.referencias:
            raise ValueError("envie uma imagem")
        tarefa.prompt_final = "" if p.previa_angulo else presets.TRELLIS["instrucao"]
        return workflows.orbita_3d(p.referencias[0], p.giro_3d, p.altura_3d, largura, altura, seed,
                                   previa=p.previa_angulo, extra=p.prompt, prefixo=prefixo)

    if p.modelo == "ampliar":
        if not p.referencias:
            raise ValueError("envie uma imagem")
        if p.metodo_ampliar not in presets.AMPLIAR["metodos"]:
            raise ValueError(f"método desconhecido: {p.metodo_ampliar}")
        if p.otimizacao not in presets.AMPLIAR["otimizacoes"]:
            raise ValueError(f"otimização desconhecida: {p.otimizacao}")
        if p.metodo_ampliar == "magnific":
            larg, alt = await comfy.dimensoes_imagem(p.referencias[0], "", "input")
            workflows.validar_magnific(larg, alt, p.escala_ampliar)
            tarefa.prompt_final = p.prompt
            return workflows.ampliar_magnific(p.referencias[0], p.escala_ampliar,
                p.prompt, p.magnific_criatividade, p.magnific_hdr,
                p.magnific_semelhanca, p.magnific_fractalidade, prefixo)
        if p.escala_ampliar > 4:
            raise ValueError("Este método aceita até 4×")
        if p.metodo_ampliar == "topaz":
            # O no recebe o tamanho FINAL em pixels, nao um fator. As
            # dimensoes vem do arquivo enviado, medidas no motor: usar as do
            # pedido daria errado, porque a imagem a ampliar costuma ser uma
            # saida de outra ferramenta, com tamanho proprio.
            larg, alt = await comfy.dimensoes_imagem(p.referencias[0], "", "input")
            if not larg:
                raise ValueError("não consegui medir a imagem enviada")
            cfg_t = presets.AMPLIAR["metodos"]["topaz"]
            tarefa.prompt_final = ""
            return workflows.ampliar_topaz(
                p.referencias[0], p.escala_ampliar,
                modelo=cfg_t["modelo_topaz"], largura=larg, altura=alt,
                prefixo=prefixo)

        ajustes = {"otimizacao": p.otimizacao, "criatividade": p.criatividade,
                   "semelhanca": p.semelhanca, "microcontraste": p.microcontraste,
                   "granulacao": p.granulacao, "detalhe": p.detalhe}
        tarefa.prompt_final = (presets.AMPLIAR["otimizacoes"][p.otimizacao]["prompt"]
                               if p.metodo_ampliar == "criativo" else "")
        return workflows.ampliar(p.referencias[0], p.metodo_ampliar,
                                 p.escala_ampliar, seed, prefixo, ajustes)

    if p.modelo == "controle":
        if not p.referencias:
            raise ValueError("envie uma imagem de referência")
        if p.tipo_controle not in presets.CONTROLE["tipos"]:
            raise ValueError(f"tipo de controle desconhecido: {p.tipo_controle}")
        tarefa.prompt_final = p.prompt
        return workflows.gerar_com_controle(p.prompt, p.referencias[0],
                                            p.tipo_controle, seed,
                                            forca=p.forca_controle,
                                            steps=p.steps, prefixo=prefixo)

    if p.modelo in presets.EDICAO:
        e = presets.EDICAO[p.modelo]
        # @imagem1, @imagem2... viram o rotulo que ESTE modelo usa.
        p.prompt = presets.traduzir_referencias(p.prompt, p.modelo)
        if len(p.referencias) < e["min_referencias"]:
            raise ValueError(f"{e['rotulo']} precisa de ao menos "
                             f"{e['min_referencias']} imagem")
        refs = p.referencias[:e["max_referencias"]]
        tarefa.prompt_final = p.prompt
        mascara = None
        if p.mascara_alvo.strip():
            mascara = {"alvo": p.mascara_alvo.strip(), "limiar": p.mascara_limiar,
                       "expandir": p.mascara_expandir, "suavizar": p.mascara_suavizar}
        if p.modelo == "anygles":
            # Esta ferramenta nao usa prompt livre nem mascara: a instrucao de
            # camera e MONTADA pelo no, na frase em que o LoRA foi treinado.
            # O texto do usuario entra como complemento, nunca no lugar dela.
            tarefa.prompt_final = "girar %+.0f graus, altura %+.0f, distancia %.1fx" % (
                p.yaw, p.elevation, p.distance)
            return workflows.girar_camera(
                refs[0], p.yaw, p.elevation, p.distance,
                extra=p.prompt.strip(), seed=seed, prefixo=prefixo,
                previa=p.previa_angulo)

        if p.modelo == "flux3ref":
            return workflows.editar_flux3(p.prompt, refs, seed,
                                          largura=largura, altura=altura,
                                          steps=p.steps or e["steps"],
                                          cfg=p.cfg if p.cfg is not None else e["cfg"],
                                          prefixo=prefixo)
        if p.modelo == "trocar":
            return workflows.editar_klein(p.prompt, refs, seed,
                                          steps=p.steps or e["steps"],
                                          cfg=p.cfg if p.cfg is not None else e["cfg"],
                                          prefixo=prefixo, mascara=mascara,
                                          negativo=freio_pele(p))
        if p.modelo == "luzref":
            # O gatilho substitui o prompt: a LoRA responde a essa frase, e um
            # texto livre por cima so atrapalha. O que o usuário escrever entra
            # depois, como complemento.
            instrucao = e["gatilho"]
            if p.prompt.strip():
                instrucao += " " + p.prompt.strip()
            tarefa.prompt_final = instrucao
            return workflows.editar_qwen(instrucao, refs, seed,
                                         megapixels=e["megapixels"],
                                         prefixo=prefixo, lora=e["lora"],
                                         mascara=mascara)
        if p.modelo == "folha":
            # Mesmo arranjo do luzref: o gatilho e a frase em que o LoRA foi
            # treinado, e o texto do usuario entra DEPOIS, como complemento.
            # Trocar o gatilho pelo texto livre afastaria o pedido da
            # distribuicao de treino e a folha perde as quatro vistas.
            instrucao = e["gatilho"]
            if p.prompt.strip():
                instrucao += " " + p.prompt.strip()
            tarefa.prompt_final = instrucao
            # As dimensoes NAO vem do pedido: a folha tem uma tela propria, em
            # presets. A proporcao escolhida na tela vale para os modos que
            # geram livremente, nao para este.
            return workflows.gerar_folha_personagem(
                refs[0], instrucao, seed,
                steps=p.steps or e["steps"],
                cfg=p.cfg if p.cfg is not None else e["cfg"],
                prefixo=prefixo)
        if p.modelo == "cabeca":
            # O LoRA foi treinado com este gatilho. As referencias mantem a
            # ordem cena -> cabeca em todo o grafo.
            instrucao = e["gatilho"]
            if p.prompt.strip():
                instrucao += " " + p.prompt.strip()
            tarefa.prompt_final = instrucao
            return workflows.trocar_cabeca(
                refs, instrucao, seed, steps=p.steps or e["steps"],
                prefixo=prefixo)
        if p.modelo == "qwen21edit":
            # Proporcao diferente da foto 1: sai na escolhida. Igual (ou com mascara,
            # que recorta a propria foto): edita a foto no tamanho dela.
            outra = False
            if not mascara:
                try:
                    w, h = await comfy.dimensoes_imagem(refs[0], "", "input")
                    outra = abs((w / h) / (largura / altura) - 1) > 0.05
                except Exception:  # sem medida: edita no tamanho da foto, como antes
                    pass
            return workflows.editar_qwen21(
                p.prompt, refs, seed, steps=p.steps, cfg=p.cfg,
                prefixo=prefixo, mascara=mascara,
                largura=largura if outra else 0, altura=altura if outra else 0)

        if p.modelo == "qwen":
            mp = {r["id"]: r["megapixels"] for r in e["resolucoes"]}
            return workflows.editar_qwen(
                p.prompt, refs, seed,
                megapixels=mp.get(p.resolucao_edicao,
                                  mp[e["resolucao_padrao"]]),
                steps=p.steps, cfg=p.cfg, prefixo=prefixo, mascara=mascara)
        if p.modelo == "instrucao":
            return workflows.editar_mage(p.prompt, refs, seed,
                                         steps=p.steps or e["steps"],
                                         cfg=p.cfg if p.cfg is not None else e["cfg"],
                                         prefixo=prefixo, mascara=mascara)
        # "estilo" gera uma imagem nova, entao as dimensoes vem do pedido.
        return workflows.gerar_com_estilo(p.prompt, refs, seed, largura, altura,
                                          steps=p.steps or e["steps"],
                                          forca=p.forca_estilo, prefixo=prefixo)

    if p.modelo == "ideogram":
        caption = p.caption
        # Caption vinda do editor de caixas: o usuario posicionou olhando a
        # foto e as zonas marcadas. Ali a decisao e dele.
        do_usuario = caption is not None
        if caption is None:
            tarefa.detalhe = "escrevendo o layout"
            await anunciar(tarefa)
            caption = await ideogram.caption_ideogram(p.prompt, p.proporcao)
        # Com uma foto de fundo a peca precisa sair branco sobre preto: a
        # mascara do recorte vem da luminancia dela.
        fundo = p.referencias[0] if p.referencias else None
        # Definida FORA do `if`: ela e usada na montagem do grafo, que roda
        # com ou sem foto. Ficando so dentro, a peca sem fundo morria com
        # "cannot access local variable 'tintas_extra'" — e esse e o caminho
        # mais comum do Ideogram, o de sempre.
        tintas_extra = []
        if fundo:
            caption = ideogram.preparar_para_recorte(caption)
            # O LLM escreveu as caixas sem nunca ver a foto. Aqui elas saem
            # de cima de um rosto, se houver um — ver enquadrar.encaixar.
            #
            # No layout manual isso NAO se aplica: medi, e o encaixe movia as
            # caixas de 120/340/860 para 584/788/902, atropelando quem tinha
            # acabado de posiciona-las olhando a imagem. Proteger de um erro
            # que o usuario nao cometeu e so tirar dele o controle.
            try:
                foto = await comfy.imagem(fundo, tipo="input")
                if not do_usuario:
                    caption = enquadrar.encaixar(caption, foto)
                tinta = p.tinta or presets.IDEOGRAM["fundo"]["tinta_padrao"]
                paleta = presets.IDEOGRAM["fundo"]["paleta"]
                # Onde ha solucao, o sistema resolve: o bloco que sumiria
                # ganha a cor da paleta que o torna legivel. O aviso fica so
                # para o que nao tem conserto por cor.
                tintas_extra = enquadrar.tintas_por_bloco(
                    caption, foto, tinta, paleta)
                trocados = {t["texto"] for t in tintas_extra}
                sem_saida = [t for t, r in enquadrar.contraste_por_bloco(
                    caption, foto, tinta)
                    if r < enquadrar.CONTRASTE_MINIMO and t not in trocados]
                partes = []
                if tintas_extra:
                    partes.append(
                        "Para nao sumir sobre a foto, mudei a cor de: "
                        + ", ".join(f'"{t["texto"]}"' for t in tintas_extra)
                        + ".")
                # O contraste nao pega texto sobre texto: na fachada da
                # mercearia a linha caiu sobre o letreiro pintado com
                # contraste otimo e mesmo assim nada se lia.
                sobrepostos = enquadrar.texto_sobre_texto(caption, foto)
                if sobrepostos:
                    partes.append(
                        "A foto ja tem letreiro grande onde caiu: "
                        + ", ".join(f'"{t}"' for t in sobrepostos)
                        + ". Os dois textos vao competir — vale reposicionar "
                          "ou escolher outra foto.")
                if sem_saida:
                    partes.append(
                        "Segue com contraste baixo, e nenhuma cor da paleta "
                        "resolve: " + ", ".join(f'"{t}"' for t in sem_saida)
                        + ".")
                tarefa.aviso = " ".join(partes)
            except Exception as e:
                # Fundo ilegivel ou detector indisponivel: a peca sai com o
                # layout do LLM, que e o comportamento de antes. O log importa:
                # um `except` mudo aqui escondeu por uma rodada inteira que o
                # encaixe estava desistindo por falta de espaco.
                print(f"encaixe no fundo falhou, seguindo sem ele: {e!r}",
                      flush=True)
        tarefa.caption = caption
        tarefa.prompt_final = ideogram.minificar(caption)
        return workflows.gerar_ideogram(tarefa.prompt_final, seed, largura, altura,
                                        p.qualidade, prefixo, p.lote,
                                        fundo=fundo, tinta=p.tinta,
                                        tintas_extra=tintas_extra)

    est = presets.ESTILOS.get(p.estilo, presets.ESTILOS[presets.ESTILO_PADRAO])
    acrescimo = (p.estilo_manual.strip() if p.estilo == "manual"
                 else est["positivo"])

    texto = p.prompt
    if p.expandir_prompt:
        tarefa.detalhe = "enriquecendo o prompt"
        await anunciar(tarefa)
        texto = await prompting.expandir(p.prompt, seed, est["llm"],
                                         p.modo_expansao)
        # A orientação do estilo já mandou o LLM nomear a lente, e ele nomeia.
        # Repetir a lente do preset punha duas no mesmo prompt — "35mm prime
        # lens" do texto brigando com "50mm lens" do acréscimo.
        acrescimo = presets.sem_lente(acrescimo)
    if acrescimo:
        # Sem o strip o texto expandido termina em ponto e a emenda saía com
        # dois: "...calm resolve.. photorealistic photograph".
        base = texto.strip().rstrip(".,;")
        texto = f"{base}. {acrescimo}" if base else acrescimo

    # O negativo do estilo só entra onde o modelo o honra; nos de CFG 1 ele
    # seria ignorado e daria a falsa impressão de estar agindo.
    negativo = p.negativo
    if not negativo and presets.honra_negativo(p.modelo):
        negativo = est["negativo"]

    tarefa.prompt_final = texto
    return workflows.gerar_simples(p.modelo, texto, negativo, seed, largura,
                                   altura, p.steps, p.cfg, prefixo, p.lote,
                                   referencias=p.referencias,
                                   forca_referencia=p.forca_referencia,
                                   posicoes=p.posicoes_referencia, forca_imagem=p.forca_imagem)


# ---------------------------------------------------------------- operario da fila

def _custa_credito(p) -> bool:
    """True quando o pedido vai para a nuvem e sera cobrado.

    Cobre os dois casos: um MODELO de nuvem (Nano Banana) e um METODO de
    nuvem dentro de um modo local (Magnific dentro do Reluz). Sem o segundo,
    o custo do Magnific nunca seria medido.
    """
    if p.modelo in presets.NUVEM:
        return True
    if p.modelo == "recorte":
        return True
    # Video por nuvem: cobrado por tempo de GPU, nao por peca, mas cobrado.
    if p.modelo == "video" and p.modelo_video in presets.GERADORES_VIDEO_PAGOS:
        return True
    metodo = (p.metodo_angulo if p.modelo == "angulo"
              else p.metodo_luz if p.modelo == "reluz"
              else p.metodo_ampliar if p.modelo == "ampliar"
              else p.prioridade if p.modelo == "personagem" else "")
    return presets.motor_do(p.modelo, metodo) == "nuvem"


# Descarregar os modelos ao fim de cada geracao. Ver o `finally` do operario
# para o custo medido.
LIBERAR_APOS_GERAR = True


# Teto do mapa de profundidade: todos os quadros vao para a RAM juntos.
MAX_SEGUNDOS_PROFUNDIDADE = 20


def _video_de_referencia(ref: str) -> str:
    """Caminho de um video: "entrada:<nome>" (enviado) ou "subpasta/arquivo"."""
    return (_caminho_de_entrada(ref.split(":", 1)[1]) if ref.startswith("entrada:")
            else _caminho_de_saida(ref))


def _video_a_24fps(caminho: str) -> bytes:
    """O video em 24 fps, a cadencia que o grafo assume ao contar os quadros.
    Acima de 24 (30 fps do Blender) o video rendia menos tempo que o prometido;
    ABAIXO de 24 (um meme a 15 fps, 18/10/2026) cada quadro valia 1/24 s, e o
    resultado saia acelerado e curto (15 s viravam 9,4 s). Converte nos dois
    sentidos; so passa direto o que ja esta a 24."""
    dados = pathlib.Path(caminho).read_bytes()
    fps = miniaturas.dados_do_video(dados)["fps"] or 24
    if abs(fps - 24) <= 0.5:
        return dados
    import tempfile
    with tempfile.TemporaryDirectory() as pasta:
        saida = pathlib.Path(pasta) / "24fps.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", caminho, "-vf", "fps=24",
                        "-c:v", "libx264", "-crf", "14", "-c:a", "aac", str(saida)],
                       check=True, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return saida.read_bytes()


def _posicao_do_quadro(numero: int, quadros: int) -> int:
    """Quadro numero N (contado de 1) na posicao aceita pelo modelo: multiplo
    de 8, a partir de 0. N=1 -> 0, 48 -> 48, 80 -> 80; o ultimo vale para o fim."""
    q = round(max(0, numero - 1) / 8) * 8
    return quadros - 1 if q >= quadros - 1 else q


def _trecho_maquete(total: int, inicio: int, teto: int, duracao: int = 0) -> tuple[int, int]:
    """(inicio, quadros) do trecho usado de um render com `total` quadros: o inicio
    nunca deixa menos de 9 quadros e o trecho tem 8k+1 quadros, no maximo o teto
    e a duracao pedida (0 = o maximo)."""
    inicio = max(0, min(inicio, total - 9))
    limite = min(teto, duracao) if duracao else teto
    return inicio, min(((max(limite, 9) - 1) // 8) * 8 + 1, ((max(total - inicio, 9) - 1) // 8) * 8 + 1)


def _quadros_e_posicoes(d: dict, teto: int | None = None) -> tuple[int, int, int]:
    """Quadros usados (8k+1, no maximo o teto) e as posicoes do meio e do fim."""
    total = int(round((d["duracao"] or 0) * (d["fps"] or 24)))
    teto = teto or presets.VIDEO_TRANSFORMAR["max_quadros"]
    quadros = min(teto, ((max(total, 9) - 1) // 8) * 8 + 1)
    return quadros, ((quadros - 1) // 2) // 8 * 8, quadros - 1


async def extrair_quadros_maquete(tarefa: Tarefa):
    """Salva na galeria os quadros do inicio, meio e fim da maquete, nas mesmas
    posicoes e no mesmo tamanho em que os quadros-chave vao entrar. Sem motor."""
    p = tarefa.pedido
    tarefa.iniciada_em = time.time()
    tarefa.estado, tarefa.detalhe = "executando", "extraindo os quadros"
    await anunciar(tarefa)
    caminho = _video_de_referencia(p.referencias[0]) if p.referencias else ""
    if not caminho:
        raise RuntimeError("não encontrei esse vídeo")
    dados = await asyncio.to_thread(_video_a_24fps, caminho)
    d = await asyncio.to_thread(miniaturas.dados_do_video, dados)
    quadros, meio, fim = _quadros_e_posicoes(
        d, presets.VIDEO_TRANSFORMAR["efeitos"]["maquete"]["max_quadros"])
    total = int(round((d["duracao"] or 0) * (d["fps"] or 24)))
    inicio, quadros = _trecho_maquete(total, p.inicio_maquete,
                                      presets.VIDEO_TRANSFORMAR["efeitos"]["maquete"]["max_quadros"],
                                      p.quadros_maquete)
    larg, alt = presets.tamanho_maquete(d["largura"], d["altura"])
    import tempfile
    base = f"maquete_{uuid.uuid4().hex[:8]}"
    nomes = []
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(dados)
    try:
        # Numeros do render inteiro; a posicao cai no trecho usado (multiplo de 8 a partir do inicio).
        momentos = ([(f"quadro{inicio + _posicao_do_quadro(n - inicio, quadros) + 1}",
                      inicio + _posicao_do_quadro(n - inicio, quadros))
                     for n in p.quadros_extrair] if p.quadros_extrair
                    else [("inicio", 0), ("meio", meio), ("fim", fim)])
        for rotulo, q in momentos:
            nome = f"{base}_{rotulo}.png"
            await asyncio.to_thread(subprocess.run, [
                "ffmpeg", "-v", "error", "-y", "-i", f.name, "-vf",
                f"select=eq(n\\,{q}),scale={larg}:{alt}:force_original_aspect_ratio=increase,crop={larg}:{alt}",
                "-frames:v", "1", str(SAIDA_DO_MOTOR / "editor" / nome)],
                check=True, capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            nomes.append(nome)
    finally:
        pathlib.Path(f.name).unlink(missing_ok=True)
    tarefa.imagens = [json.dumps({"nome": n, "subpasta": "editor", "tipo": "output"}) for n in nomes]
    tarefa.largura, tarefa.altura = larg, alt
    tarefa.duracao = time.time() - tarefa.iniciada_em
    tamanhos = {n: (SAIDA_DO_MOTOR / "editor" / n).stat().st_size for n in nomes}
    biblioteca.registrar(tarefa, tamanhos, rotulo="Quadros da maquete")
    tarefa.estado, tarefa.detalhe, tarefa.progresso = "pronto", "", 1.0
    await anunciar(tarefa)


def _musica_de_entrada(p):
    """A musica de um pedido de separar ou trocar voz: da galeria ou enviada.
    Devolve (caminho, nome base, prompt)."""
    if p.separar_item:
        item = biblioteca.obter(p.separar_item)
        if item is None:
            raise RuntimeError("A música saiu da galeria antes de começar.")
        entrada = (musica.FINALIZACOES / item["arquivo"]
                   if item["subpasta"] == "finalizacoes_musica"
                   else SAIDA_DO_MOTOR / item["subpasta"] / item["arquivo"])
        # "Projeto – Nome · Original" vira "Projeto – Nome"; a faixa e somada depois.
        base = re.sub(r"\s·\s(Original|Finalizada)$", "", item.get("rotulo") or "")
        base = base or re.sub(r"_\d+$", "", pathlib.Path(item["arquivo"]).stem)
        return entrada, base, item.get("prompt") or ""
    return ENTRADA_DO_MOTOR / p.referencia_separar, "Áudio enviado", ""


def _registrar_audios(tarefa, subpasta, feitos, rotulo, prompt):
    """Poe arquivos de audio na galeria como musica (cartao, player, filtro)."""
    tarefa.imagens = [json.dumps({"nome": nome, "subpasta": subpasta, "tipo": "output",
                                  "musica": {"versao": versao}}, ensure_ascii=False)
                      for nome, versao in feitos]
    tamanhos = {nome: (SAIDA_DO_MOTOR / subpasta / nome).stat().st_size for nome, _ in feitos}
    tarefa.duracao = time.time() - tarefa.iniciada_em
    original = tarefa.pedido
    tarefa.pedido = original.model_copy(update={"modelo": "musica", "prompt": prompt})
    try:
        biblioteca.registrar(tarefa, tamanhos, rotulo=rotulo)
    finally:
        tarefa.pedido = original


async def trocar_voz(tarefa: Tarefa):
    """Troca a voz da musica pelo timbre de um modelo treinado (troca_voz.py).
    Fora do ComfyUI, mas dentro da fila, para nao disputar a placa."""
    p = tarefa.pedido
    tarefa.iniciada_em = time.time()
    tarefa.estado, tarefa.detalhe = "executando", "separando a voz da música"
    tarefa.largura = tarefa.altura = 0
    await anunciar(tarefa)
    await comfy.liberar_memoria()
    entrada, base, prompt = _musica_de_entrada(p)
    if not entrada.exists():
        raise RuntimeError("O arquivo da música não foi encontrado no disco.")

    async def etapa(texto):
        tarefa.detalhe = texto
        await anunciar(tarefa)
    feitos = await troca_voz.trocar(entrada, p.voz_troca, p.tom_troca, SAIDA_DO_MOTOR / "faixas",
                                    base, formato=p.formato_separar, ao_etapa=etapa)
    _registrar_audios(tarefa, "faixas", feitos, base, prompt)
    tarefa.estado, tarefa.detalhe, tarefa.progresso = "pronto", "", 1.0
    await anunciar(tarefa)


async def treinar_voz(tarefa: Tarefa):
    """Treina um modelo de voz com as gravacoes enviadas. Nao gera arquivo
    na galeria: a voz pronta aparece na lista da aba Trocar voz."""
    p = tarefa.pedido
    tarefa.iniciada_em = time.time()
    tarefa.estado, tarefa.detalhe = "executando", "preparando as gravações"
    tarefa.largura = tarefa.altura = 0
    await anunciar(tarefa)
    await comfy.liberar_memoria()

    async def etapa(texto):
        tarefa.detalhe = texto
        await anunciar(tarefa)

    async def progresso(x):
        tarefa.progresso = x
    pronta = await troca_voz.treinar([ENTRADA_DO_MOTOR / a for a in p.arquivos_voz], p.nome_voz,
                                     p.epocas_voz, p.separar_treino_voz,
                                     ao_etapa=etapa, ao_progresso=progresso)
    tarefa.duracao = time.time() - tarefa.iniciada_em
    tarefa.resultado_texto = json.dumps(pronta, ensure_ascii=False)
    tarefa.estado, tarefa.detalhe, tarefa.progresso = "pronto", "", 1.0
    await anunciar(tarefa)


async def separar_faixas(tarefa: Tarefa):
    """Separa uma musica em faixas e poe cada faixa na galeria.

    Nao passa pelo ComfyUI: roda no ambiente do separador (separacao.py),
    mas DENTRO da fila, para nao disputar a placa com uma geracao.
    """
    p = tarefa.pedido
    tarefa.iniciada_em = time.time()
    tarefa.estado, tarefa.detalhe = "executando", "separando as faixas"
    tarefa.largura = tarefa.altura = 0
    await anunciar(tarefa)

    prompt = ""
    if p.separar_item:
        item = biblioteca.obter(p.separar_item)
        if item is None:
            raise RuntimeError("A música saiu da galeria antes da separação.")
        entrada = (musica.FINALIZACOES / item["arquivo"]
                   if item["subpasta"] == "finalizacoes_musica"
                   else SAIDA_DO_MOTOR / item["subpasta"] / item["arquivo"])
        # "Projeto – Nome · Original" vira "Projeto – Nome"; a faixa e somada depois.
        base = re.sub(r"\s·\s(Original|Finalizada)$", "", item.get("rotulo") or "")
        base = base or re.sub(r"_\d+$", "", pathlib.Path(item["arquivo"]).stem)
        prompt = item.get("prompt") or ""
    else:
        entrada = ENTRADA_DO_MOTOR / p.referencia_separar
        base = "Áudio enviado"
    if not entrada.exists():
        raise RuntimeError("O arquivo da música não foi encontrado no disco.")

    feitos = await separacao.separar(entrada, p.modo_separar, SAIDA_DO_MOTOR / "faixas", base,
                                     formato=p.formato_separar)
    if not feitos:
        raise RuntimeError("O separador não devolveu nenhuma faixa.")

    # As faixas entram na galeria como musica: o cartao, o player e o filtro
    # de audio ja sabem trata-las. O nome da faixa vai no rotulo.
    tarefa.imagens = [json.dumps({"nome": nome, "subpasta": "faixas", "tipo": "output",
                                  "musica": {"versao": faixa}}, ensure_ascii=False)
                      for nome, faixa in feitos]
    tamanhos = {nome: (SAIDA_DO_MOTOR / "faixas" / nome).stat().st_size for nome, _ in feitos}
    tarefa.duracao = time.time() - tarefa.iniciada_em
    original = tarefa.pedido
    tarefa.pedido = original.model_copy(update={"modelo": "musica", "prompt": prompt})
    try:
        biblioteca.registrar(tarefa, tamanhos, rotulo=base)
    finally:
        tarefa.pedido = original
    tarefa.estado, tarefa.detalhe, tarefa.progresso = "pronto", "", 1.0
    await anunciar(tarefa)


# A tarefa em execucao, como asyncio.Task: o botao Interromper a cancela.
# Sem isto, um motor que morre no meio da carga deixava a tarefa presa em
# "executando" para sempre, e interromper o motor nao adiantava nada.
ATUAL: asyncio.Task | None = None


async def _executar(tarefa):
    if presets.usa_motor_flux3(tarefa.pedido) and not comfy.na_nuvem():
        # Esta tarefa inteira (envio, historico, leitura do resultado) fala
        # com o segundo motor. O contexto e desta Task; as outras nao mudam.
        tarefa.detalhe = "preparando o motor do Flux 3"
        await anunciar(tarefa)
        await motor_flux3.garantir()
        comfy.MOTOR.set(comfy.BASE_FLUX3)
    if tarefa.pedido.modelo == "separar":
        await separar_faixas(tarefa)
        return
    if tarefa.pedido.modelo == "trocar_voz":
        await trocar_voz(tarefa)
        return
    if tarefa.pedido.modelo == "treinar_voz":
        await treinar_voz(tarefa)
        return
    if tarefa.pedido.modelo == "quadros_maquete":
        await extrair_quadros_maquete(tarefa)
        return
    if tarefa.variacoes_concluidas == 0:
        tarefa.iniciada_em = time.time()
        tarefa.estado = "preparando"
        await anunciar(tarefa)
        grafo = await montar(tarefa)

        await submeter(tarefa, grafo)
        await esperar_fim(tarefa)

    # O Ideogram às vezes devolve a tela "Image blocked by safety
    # filter". Não é filtro: medimos que tirar conteúdo não resolve e
    # que a mesma descrição com outra seed gera normalmente. É um modo
    # degenerado do modelo, e a saída é a mesma que o usuário tomaria —
    # gerar de novo. Uma vez só, para não entrar em laço.
    if tarefa.pedido.modelo == "ideogram" and await saida_bloqueada(tarefa):
        print("[ideogram] tela de bloqueio; refazendo com outra seed",
              flush=True)
        tarefa.detalhe = "o modelo devolveu a tela de bloqueio; refazendo"
        tarefa.estado = "preparando"
        await anunciar(tarefa)
        tarefa.pedido.seed = random.randint(0, 2**52)
        tarefa.variacoes_concluidas = 0
        grafo = await montar(tarefa)
        await submeter(tarefa, grafo)
        await esperar_fim(tarefa)

    # Variacoes: mesma entrada, seed nova. Cada uma e uma execucao
    # completa, entao cada uma entra na galeria por si — o que muda e
    # que a tarefa junta todas para aparecerem lado a lado.
    for n in range(max(2, tarefa.variacoes_concluidas + 1),
                   _quantas_variacoes(tarefa.pedido) + 1):
        tarefa.pedido.seed = random.randint(0, 2**52)
        tarefa.estado = "preparando"
        tarefa.detalhe = f"variação {n}"
        await anunciar(tarefa)
        grafo = await montar(tarefa)
        await submeter(tarefa, grafo)
        await esperar_fim(tarefa, acumular=True)



async def operario():
    """Executa uma tarefa por vez: a GPU nao ganha nada com paralelismo."""
    global ATUAL
    while True:
        tarefa = await FILA.get()
        try:
            ATUAL = asyncio.create_task(_executar(tarefa))
            await ATUAL
        except asyncio.CancelledError:
            tarefa.estado = "erro"
            tarefa.erro = "interrompida pelo usuário"
            await anunciar(tarefa)
        except Exception as e:
            tarefa.estado = "erro"
            # Algumas excecoes de transporte (notadamente ReadTimeout) tem
            # str(e) vazio. A interface precisa de algo diagnosticavel.
            tarefa.erro = str(e).strip() or repr(e)
            await anunciar(tarefa)
        finally:
            ATUAL = None
            for pid, item in list(POR_PROMPT_ID.items()):
                if item is tarefa:
                    POR_PROMPT_ID.pop(pid, None)
            concluidas = sorted((t for t in TAREFAS.values()
                                 if t.estado in ("pronto", "erro")),
                                key=lambda t: t.criada_em, reverse=True)
            for antiga in concluidas[100:]:
                TAREFAS.pop(antiga.id, None)
            biblioteca.podar_tarefas()
            # Esvazia a placa ao fim de CADA geracao, com sucesso ou erro, a
            # pedido do usuario. E uma REDE DE SEGURANCA, nao a causa do
            # esvaziamento: medido em 02/10, com controle, o motor ja
            # descarrega sozinho por causa do `--cache-none` dos lancadores —
            # gerando direto no motor, sem esta chamada, a VRAM voltou a
            # 1,36 GiB e o processo a 5,6 GiB depois de um Krea de 13 GB, igual
            # a quando ela roda. Ela existe para o comportamento nao depender
            # dessa flag, e nao custa recarga nenhuma: quando roda, ja nao ha
            # modelo para descarregar. Para desligar, LIBERAR_APOS_GERAR.
            if LIBERAR_APOS_GERAR:
                await comfy.liberar_memoria()
            FILA.task_done()


async def submeter(tarefa: Tarefa, grafo: dict):
    """Registra a fronteira do envio para recuperar sem pagar duas vezes."""
    global COBRANCA_PENDENTE
    perfil = motores.perfil_do(tarefa.pedido.modelo, tarefa.pedido.modelo_video,
                                   tarefa.pedido.modelo_avatar)
    if perfil and not comfy.na_nuvem():
        tarefa.detalhe = "preparando o motor para o vídeo"
        await anunciar(tarefa)
        await motores.garantir_perfil(perfil)
    if _custa_credito(tarefa.pedido):
        # O debito do envio anterior pode aparecer depois da imagem. Medir o
        # saldo seguinte antes de apura-lo atribuiria a cobranca ao pedido novo.
        if COBRANCA_PENDENTE is not None:
            await COBRANCA_PENDENTE
        antes = await chaves.saldo(forcar=True)
        tarefa.saldo_antes = antes["usd"] if antes.get("ok") else None
    else:
        tarefa.saldo_antes = None
    tarefa.estado = "submetendo"
    await anunciar(tarefa)
    # Copia do grafo para o botao "Node recipe" (grafos.py); salva quando a saida existir.
    tarefa._grafo = json.loads(json.dumps(grafo))
    tarefa.prompt_id = await comfy.enfileirar(grafo)
    POR_PROMPT_ID[tarefa.prompt_id] = tarefa
    tarefa.estado = "executando"
    tarefa.detalhe = ""
    await anunciar(tarefa)


def _quantas_variacoes(p: PedidoGeracao) -> int:
    """Variacao so faz sentido onde a seed muda o resultado e o lote nao vale.

    Na geracao simples e no Ideogram existe `lote`, que sai numa passada so e
    e mais barato. Aqui cada variacao e uma execucao inteira.
    """
    if p.modelo in presets.SIMPLE or p.modelo == "ideogram":
        return 1
    return max(1, min(p.variacoes, 4))


async def saida_bloqueada(tarefa: Tarefa) -> bool:
    """A imagem que saiu é a tela de bloqueio do Ideogram? Ver deteccao.py."""
    for bruto in tarefa.imagens:
        im = json.loads(bruto)
        try:
            dados = await comfy.imagem(im["nome"], im.get("subpasta", ""),
                                       im.get("tipo", "output"))
        except Exception:
            return False
        if deteccao.e_tela_de_bloqueio(dados):
            return True
    return False


async def apurar_custo(tarefa: Tarefa, saldo_antes: float, imagens: list[str]):
    """Descobre o que a imagem custou de verdade e anota na galeria.

    MEDIDO: o debito nao esta no saldo no instante em que a imagem fica
    pronta. A primeira versao lia de imediato e registrava sempre zero, com o
    saldo caindo logo em seguida — por isso insiste ate ver a mudanca.
    """
    # MEDIDO: 8 tentativas de 1,5 s (12 s no total) bastavam para os nos de
    # IMAGEM, mas nao para o video por nuvem — o Wan 3.0 levou mais que isso
    # e o custo foi gravado como zero, com o saldo caindo logo depois. Roda em
    # segundo plano, entao esperar mais nao atrasa nada para quem usa.
    try:
        for _ in range(40):
            await asyncio.sleep(3)
            depois = await chaves.saldo(forcar=True)
            if not depois.get("ok"):
                continue
            gasto = round(saldo_antes - depois["usd"], 4)
            if gasto > 0:
                biblioteca.anotar_custo(imagens, gasto)
                tarefa.custo_usd = round(tarefa.custo_usd + gasto, 4)
                await anunciar(tarefa)
                return
        tarefa.aviso = (tarefa.aviso + " Não foi possível confirmar o custo "
                        "desta geração; confira o extrato da nuvem.").strip()
    finally:
        tarefa.imagens_cobranca = []
        await anunciar(tarefa)


async def esperar_fim(tarefa: Tarefa, timeout: float = 3600,
                     acumular: bool = False, recuperada: bool = False):
    """O WebSocket move o progresso; o historico e a fonte da verdade do fim."""
    inicio = time.time()
    ultima_falha_de_consulta = ""
    ausencias_na_retomada = 0
    while time.time() - inicio < timeout:
        try:
            h = await comfy.historico(tarefa.prompt_id)
            ultima_falha_de_consulta = ""
        except (httpx.RequestError, json.JSONDecodeError, OSError) as e:
            # Durante os modelos de video mais pesados o ComfyUI pode deixar
            # de responder ao /history por mais de 30 s, embora a GPU continue
            # trabalhando e o arquivo seja salvo no fim. Uma falha isolada de
            # polling nao pode transformar uma geracao valida em erro nem
            # liberar a proxima tarefa para disputar a GPU.
            ultima_falha_de_consulta = str(e).strip() or repr(e)
            ausencias_na_retomada = 0
            await asyncio.sleep(2)
            continue
        if h:
            recuperada = False
            estado = h["status"].get("status_str")
            if estado == "error":
                mensagens = h["status"].get("messages") or []
                if any(isinstance(m, (list, tuple)) and m and m[0] == "execution_interrupted" for m in mensagens):
                    raise comfy.ErroComfy("Geração interrompida.")
                bruto = json.dumps(h["status"].get("messages"), ensure_ascii=False)
                # Falha de nuvem vira explicacao; o resto sobe cru, com o
                # traceback do motor, que e o que ajuda a depurar.
                raise comfy.ErroComfy(chaves.traduzir_erro(bruto) or bruto[:1000])
            if tarefa.pedido.modelo == "musica" and tarefa.pedido.etapa_musica in ("letra", "partitura"):
                # Rodada de revisao: nada foi gerado, so os rascunhos voltam.
                tarefa.resultado_texto = json.dumps(
                    musica.revisao_do_historico(h["outputs"], tarefa.pedido.etapa_musica,
                                                tarefa.pedido.modelo_musica),
                    ensure_ascii=False)
                tarefa.duracao = time.time() - (tarefa.iniciada_em or inicio)
                tarefa.estado, tarefa.progresso = "pronto", 1.0
                tarefa.variacoes_concluidas = 1
                await anunciar(tarefa)
                return
            if tarefa.pedido.modelo == "transcricao_voz":
                tarefa.resultado_texto = voz.texto_transcrito(h["outputs"])
                tarefa.duracao = time.time() - (tarefa.iniciada_em or inicio)
                tarefa.estado, tarefa.progresso = "pronto", 1.0
                tarefa.variacoes_concluidas = 1
                await anunciar(tarefa)
                return
            if tarefa.pedido.modelo == "voz":
                voz.conferir_resultado(h["outputs"])
            saidas = comfy.imagens_salvas(h["outputs"])
            if tarefa.pedido.modelo == "musica" and saidas:
                # YuE2: o Plenio tambem exporta em output/plenio; a galeria
                # fica com a copia do SaveAudio (editor/), como no modo direto.
                saidas = sorted(saidas, key=lambda s: s.get("subpasta") == "plenio")[:1]
                tarefa.detalhe = "analisando o encerramento da música"
                await anunciar(tarefa)
                try:
                    saidas, rel = await musica.finalizar_saida(tarefa.pedido, saidas[0])
                    tarefa.aviso = rel["motivo"]
                except Exception as e:
                    # Um erro de pós-processamento não invalida a geração original.
                    tarefa.aviso = f"Original preservado: não foi possível finalizar o áudio ({type(e).__name__})."
            nomes = [json.dumps(im, ensure_ascii=False) for im in saidas]
            try:
                grafos.salvar(getattr(tarefa, "_grafo", None), saidas)
            except OSError:
                pass  # a receita e um extra: nunca derruba a geracao
            if tarefa.pedido.modelo in ("voz", "musica") and not nomes:
                raise comfy.ErroComfy("O motor terminou sem salvar áudio.")
            tarefa.imagens = tarefa.imagens + nomes if acumular else nomes
            tarefa.duracao = time.time() - (tarefa.iniciada_em or inicio)
            # Tamanho e dimensoes vem do proprio arquivo, sem baixa-lo: nos
            # modos de edicao e de controle a saida nao acompanha o pedido.
            # Isto roda ANTES de marcar "pronto": quem consulta a tarefa no
            # instante em que ela fica pronta precisa ver os valores medidos,
            # nao os do pedido.
            tamanhos = {}
            for bruto in nomes:
                im = json.loads(bruto)
                tamanhos[im["nome"]] = ((musica.FINALIZACOES / im["nome"]).stat().st_size
                    if im.get("subpasta") == "finalizacoes_musica" else await comfy.tamanho_imagem(
                    im["nome"], im["subpasta"], im["tipo"]))
            primeira = json.loads(nomes[0]) if nomes else None
            if primeira and miniaturas.e_video(primeira["nome"]):
                # Video: duracao, fps e dimensoes saem do arquivo. O pedido diz
                # o que se queria; so o arquivo diz o que saiu — e ja vimos o
                # modelo devolver 704 onde pedimos 720.
                bruto = await comfy.imagem(primeira["nome"], primeira["subpasta"],
                                           primeira["tipo"])
                d = await asyncio.to_thread(miniaturas.dados_do_video, bruto)
                tarefa.duracao_video, tarefa.fps = d["duracao"], d["fps"]
                if d["largura"]:
                    tarefa.largura, tarefa.altura = d["largura"], d["altura"]
            elif primeira:
                largura, altura = await comfy.dimensoes_imagem(
                    primeira["nome"], primeira["subpasta"], primeira["tipo"])
                if largura:
                    tarefa.largura, tarefa.altura = largura, altura
            # Custo REAL: a diferenca de saldo. O cabecalho
            # X-Comfy-Credits-Used existe, mas o motor so o transforma em
            # mensagem no ticker de polling, e os nos do Gemini sao sincronos
            # — nada e emitido. O extrato e a fonte que sempre responde.
            tarefa.variacoes_concluidas += 1
            total = _quantas_variacoes(tarefa.pedido)
            tarefa.estado = "pronto" if tarefa.variacoes_concluidas >= total else "preparando"
            tarefa.progresso = tarefa.variacoes_concluidas / total
            if tarefa.saldo_antes is not None:
                tarefa.imagens_cobranca = list(nomes)
            biblioteca.registrar(
                tarefa,
                tamanhos,
                teste=tarefa.pedido.teste,
                rotulo=tarefa.pedido.rotulo_teste,
            )
            await anunciar(tarefa)
            # A apuracao do custo vem DEPOIS de a imagem aparecer. O debito
            # leva alguns segundos para entrar no saldo, e fazer o usuario
            # esperar por ele seria trocar a coisa que importa pela que nao.
            if tarefa.saldo_antes is not None:
                global COBRANCA_PENDENTE
                COBRANCA_PENDENTE = asyncio.create_task(
                    apurar_custo(tarefa, tarefa.saldo_antes, list(nomes)))
            return
        # Vale SEMPRE, nao so na retomada: o historico e a fila do ComfyUI
        # ficam na memoria, e um motor que CAI no meio da geracao (o vigia o
        # religa sozinho) perde o pedido. Sem isto a tarefa ficava
        # "executando" para sempre e travava a fila (17/10/2026, LTX 2.3).
        if True:
            # O historico e a fila do ComfyUI ficam na memoria. Se o motor
            # reiniciou, um prompt antigo pode ter desaparecido dos dois:
            # esperar uma hora por ele bloqueava todas as tarefas seguintes.
            # Confirmar a ausencia repetidamente evita a corrida entre a
            # retirada da fila e a publicacao do resultado no historico.
            try:
                fila_motor = await comfy.fila()
            except (httpx.RequestError, httpx.HTTPStatusError,
                    json.JSONDecodeError, OSError):
                ausencias_na_retomada = 0
                await asyncio.sleep(2)
                continue
            presente = any(
                len(item) > 1 and item[1] == tarefa.prompt_id
                for chave in ("queue_running", "queue_pending")
                for item in fila_motor.get(chave, []))
            if presente:
                ausencias_na_retomada = 0
            else:
                ausencias_na_retomada += 1
                # Na Comfy Cloud o pedido demora a aparecer na fila (e some dela
                # antes de ir ao historico): 3 ausencias (~6 s) davam "o motor caiu"
                # em pedidos que ainda iam rodar. La, so desiste depois de ~1 min.
                if ausencias_na_retomada >= (30 if comfy.na_nuvem() else 3):
                    raise comfy.ErroComfy(
                        "O pedido anterior não está mais na fila nem no histórico "
                        "do motor. Confira os arquivos de saída antes de gerar novamente."
                        if recuperada else
                        "O motor caiu durante a geração e perdeu o pedido; ele já "
                        "foi religado. Gere de novo.")
            await asyncio.sleep(2)
            continue
        await asyncio.sleep(1)
    detalhe = (f"; última falha ao consultar o motor: {ultima_falha_de_consulta}"
               if ultima_falha_de_consulta else "")
    raise comfy.ErroComfy(f"tempo esgotado{detalhe}")


# O motor informa o progresso pelo identificador do no, que e interno. Isto
# traduz os que valem a pena mostrar; os demais viram texto vazio, porque um
# "sam_cresce" na barra de status nao diz nada a quem esta usando.
ETAPAS = {
    "clip": "carregando o interpretador de texto",
    "unet": "carregando o modelo", "unet_cond": "carregando o modelo",
    "unet_uncond": "carregando o modelo auxiliar",
    "lora": "aplicando o estilo", "patch": "carregando o controle",
    "pos": "lendo o prompt", "neg": "lendo o prompt",
    "cond": "lendo o prompt", "sam_txt": "lendo o alvo da máscara",
    "amostra": "gerando", "run": "gerando", "ks": "gerando",
    "decodifica": "revelando a imagem",
    "pre": "analisando a referência", "mapa": "analisando a referência",
    "sam_det": "encontrando a região", "sam_cresce": "ajustando a máscara",
    "sam_suave": "ajustando a máscara", "composto": "compondo o resultado",
    "prep": "preparando a ampliação", "latente": "preparando",
    "motor_asr": "carregando o modelo de transcrição", "transcreve": "transcrevendo o áudio",
    "checkpoint_musica": "carregando o modelo de música", "cond_musica": "preparando a composição",
    "amostra_musica": "gerando a música", "audio_musica": "decodificando o áudio",
    "motor_voz": "carregando o modelo de voz", "fala": "gerando a fala",
    "personagem_voz": "preparando a voz de referência",
    "amplia": "ampliando", "salva": "salvando",
    "passo": "gerando o vídeo", "passo1": "gerando a base do vídeo",
    "passo2": "refinando o vídeo", "som": "decodificando o áudio",
    "monta": "montando o vídeo", "upsampler": "carregando o ampliador de vídeo",
    "vae_v": "carregando o decodificador de vídeo", "vae_a": "carregando o decodificador de áudio",
}


async def do_motor(evento: dict):
    """Traduz os eventos do ComfyUI em progresso das nossas tarefas."""
    tipo = evento.get("type")
    dados = evento.get("data", {})
    tarefa = POR_PROMPT_ID.get(dados.get("prompt_id", ""))
    # O replay de executing ao reconectar não contém prompt_id.
    if not tarefa and tipo == "executing" and not dados.get("prompt_id"):
        ativas = [t for t in POR_PROMPT_ID.values() if t.estado == "executando"]
        tarefa = ativas[0] if len(ativas) == 1 else None
    if not tarefa:
        return
    if tipo == "progress":
        maximo = dados.get("max") or 1
        tarefa.passo_atual = max(0, int(dados.get("value", 0)))
        tarefa.passos_total = int(maximo)
        tarefa.ultimo_avanco_em = time.time()
        tarefa.progresso = min(dados.get("value", 0) / maximo, 0.99)
        await anunciar(tarefa)
    elif tipo == "executing" and dados.get("node"):
        no = str(dados["node"])
        rotulo = ETAPAS.get(no, "preparando a geração")
        if tarefa.pedido.modelo == "video":
            if no == "prep":
                rotulo = "preparando o vídeo e a referência"
            elif no == "decodifica":
                rotulo = "decodificando o vídeo"
        if no != tarefa.etapa_no:
            tarefa.etapa_no = no
            tarefa.passo_atual = 0
            tarefa.passos_total = 0
            tarefa.progresso = 0.0
            if dados.get("prompt_id"):
                tarefa.etapa_iniciada_em = tarefa.ultimo_avanco_em = time.time()
            tarefa.detalhe = rotulo
            await anunciar(tarefa)


async def atualizar_fila_monitor(fila: dict):
    for item in fila.get("queue_running", []):
        if len(item) < 3:
            continue
        tarefa = POR_PROMPT_ID.get(item[1])
        if not tarefa or tarefa.passos_total:
            continue
        grafo = item[2]
        no = grafo.get(tarefa.etapa_no, {})
        if no.get("class_type") != "SamplerCustomAdvanced":
            continue
        sigmas = no.get("inputs", {}).get("sigmas")
        if isinstance(sigmas, list) and sigmas:
            entradas = grafo.get(sigmas[0], {}).get("inputs", {})
            if "steps" in entradas:
                tarefa.passos_total = int(entradas["steps"])
            elif isinstance(entradas.get("sigmas"), str):
                tarefa.passos_total = max(0, len(entradas["sigmas"].split(",")) - 1)


# ---------------------------------------------------------------- ciclo de vida

async def recuperar_pendentes():
    """Retoma a fila e acompanha envios confirmados, sem repetir envio incerto."""
    for tarefa in sorted(TAREFAS.values(), key=lambda t: t.criada_em):
        if tarefa.imagens_cobranca and tarefa.saldo_antes is not None:
            await apurar_custo(tarefa, tarefa.saldo_antes,
                               list(tarefa.imagens_cobranca))
        if tarefa.estado in ("na_fila", "preparando"):
            tarefa.estado = "na_fila"
            tarefa.detalhe = "retomada após reinício"
            await anunciar(tarefa)
            await FILA.put(tarefa)
        elif tarefa.estado == "submetendo":
            # Caiu entre POST /prompt e a resposta. Não sabemos se o ComfyUI
            # aceitou o pedido; reenviar poderia gastar crédito duas vezes.
            tarefa.estado = "erro"
            tarefa.erro = ("O site reiniciou durante o envio. Confira o histórico "
                           "do ComfyUI antes de gerar novamente.")
            await anunciar(tarefa)
        elif tarefa.estado == "executando" and tarefa.prompt_id:
            POR_PROMPT_ID[tarefa.prompt_id] = tarefa
            while not await comfy.esta_vivo():
                await asyncio.sleep(2)
            try:
                await esperar_fim(tarefa, acumular=bool(tarefa.variacoes_concluidas),
                                  recuperada=True)
                if tarefa.variacoes_concluidas < _quantas_variacoes(tarefa.pedido):
                    tarefa.estado = "na_fila"
                    tarefa.detalhe = "retomando variações após reinício"
                    await anunciar(tarefa)
                    await FILA.put(tarefa)
            except Exception as e:
                tarefa.estado = "erro"
                tarefa.erro = str(e).strip() or repr(e)
                await anunciar(tarefa)
            finally:
                POR_PROMPT_ID.pop(tarefa.prompt_id, None)


async def operar_apos_recuperar():
    await recuperar_pendentes()
    await operario()

@app.on_event("startup")
async def iniciar():
    biblioteca.criar_tabelas()
    biblioteca.podar_tarefas()
    for dados in biblioteca.carregar_tarefas():
        tarefa = Tarefa.de_registro(dados)
        TAREFAS[tarefa.id] = tarefa
    # Assinar novamente a sessão original mantém os eventos de um pedido
    # em execução quando só o servidor do Editor é atualizado/reiniciado.
    try:
        await comfy.retomar_cliente({t.prompt_id for t in TAREFAS.values() if t.prompt_id})
    except (httpx.HTTPError, ValueError, OSError):
        pass
    app.state.tarefas_fundo = [
        asyncio.create_task(operar_apos_recuperar()),
        asyncio.create_task(comfy.acompanhar(do_motor)),
        # Vigia de instâncias: dois motores brigariam pela GPU.
        asyncio.create_task(motores.vigiar()),
        asyncio.create_task(andamento.vigiar(atualizar_fila_monitor)),
    ]


@app.on_event("shutdown")
async def parar():
    for t in app.state.tarefas_fundo:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t


# ---------------------------------------------------------------- rotas

@app.get("/api/motores")
async def estado_motores():
    """Consulta sem efeitos colaterais; limpeza exige POST."""
    return await asyncio.to_thread(motores.inspecionar)


@app.post("/api/motores/limpar")
async def limpar_motores():
    return await asyncio.to_thread(motores.limpar)


def _geracao_em_andamento() -> bool:
    return FILA.qsize() > 0 or any(
        t.estado in ("na_fila", "preparando", "submetendo", "executando")
        for t in TAREFAS.values())


@app.post("/api/desligar")
async def desligar():
    """O botao Power: fecha os motores que o app sabe religar e depois o proprio app.

    Recusa com algo gerando aqui ou na fila de um motor (os motores podem
    atender outro app ou um script de teste). O ComfyUI de outra pessoa, que o
    app nao sabe ligar de novo, fica de pe."""
    if _geracao_em_andamento():
        raise HTTPException(409, "A generation is running. Wait for it to finish or stop it first.")
    async with httpx.AsyncClient(timeout=5) as c:
        for base in {comfy.BASE_PRINCIPAL, comfy.BASE_FLUX3}:
            try:
                q = (await c.get(f"{base}/queue")).json()
            except (httpx.HTTPError, ValueError):
                continue  # motor fora do ar: nada a perder
            if q.get("queue_running") or q.get("queue_pending"):
                raise HTTPException(409, "ComfyUI is still working on something. Wait for it to finish first.")
    fechou = False
    if motores.pode_religar():
        await asyncio.to_thread(motores.desligar)
        if not motor_flux3.UNICO:
            await asyncio.to_thread(motores.desligar_segundo, urlsplit(comfy.BASE_FLUX3).port)
        fechou = True
    # Responde antes de sair: a tela precisa receber a confirmacao.
    asyncio.get_running_loop().call_later(1.0, os._exit, 0)
    return {"ok": True, "motores_fechados": fechou}


@app.post("/api/liberar-memoria")
async def liberar_memoria():
    """Descarrega os modelos e esvazia a placa, a pedido do usuario.

    RECUSA durante uma geracao: o motor descarregaria o modelo em uso e a
    derrubaria. Confere as duas filas — a do aplicativo e a do proprio motor,
    que recebe pedidos de scripts de teste que nunca passam pelo app.
    """
    global MOTOR_CARREGADO
    if _geracao_em_andamento():
        raise HTTPException(409, "Há uma geração em andamento — esvaziar agora "
                                 "a derrubaria. Espere ela terminar.")
    try:
        f = await comfy.fila()
    except Exception:
        raise HTTPException(503, "O motor não respondeu.")
    if f.get("queue_running") or f.get("queue_pending"):
        raise HTTPException(409, "O motor está processando um pedido. "
                                 "Espere ele terminar.")
    antes = await comfy.vram_usada_gib()
    if not await comfy.liberar_memoria():
        raise HTTPException(503, "O motor não aceitou o pedido.")
    # O descarregamento nao e instantaneo; sem esta pausa o "depois" lido
    # logo em seguida ainda mostra os pesos na placa.
    await asyncio.sleep(2)
    depois = await comfy.vram_usada_gib()
    MOTOR_CARREGADO = None
    liberado = (antes - depois) if antes is not None and depois is not None else None
    return {"antes_gib": antes, "depois_gib": depois, "liberado_gib": liberado}


@app.get("/api/saude")
async def saude():
    return {"motor": await comfy.esta_vivo(), "na_fila": FILA.qsize(),
            "motor_carregado": MOTOR_CARREGADO}


@app.get("/api/andamento")
async def estado_andamento():
    return andamento.ESTADO


def _metodos(cfg: dict) -> list[dict]:
    """Os métodos como a interface precisa: sem caminho de modelo nem gatilho."""
    return [{"id": k, "rotulo": v["rotulo"], "nota": v["nota"],
             "segundos": v["segundos"],
             # So os metodos de nuvem tem custo e estilos; a interface usa a
             # presenca do custo para saber que precisa avisar antes do clique.
             **({"custo_usd": v["custo_usd"]} if "custo_usd" in v else {}),
             **({"max_referencias": v["max_referencias"]}
                if "max_referencias" in v else {}),
             **({"estilos": [{"id": i, "rotulo": r} for i, r in v["estilos"]]}
                if "estilos" in v else {})}
            for k, v in cfg["metodos"].items()]


class PedidoMotor(Pedido):
    modo: str


def _eh_api(p: PedidoGeracao) -> bool:
    return p.modelo in presets.NUVEM or p.modelo == "recorte" or (
        p.modelo == "reluz" and p.metodo_luz == "nuvem") or (p.modelo == "avatar" and p.modelo_avatar in avatar.API) or (
        p.modelo == "genjutsu" and not genjutsu.MODELOS[p.modelo_genjutsu]["aberto"]) or (
        p.modelo == "video" and (p.modelo_video in presets.VIDEO_API
                                 or p.modelo_video in ("wan3", "minimax-nuvem", "minimax-ref-nuvem")))


def _modelos_conhecidos() -> set[str]:
    """Os modelos que /api/gerar aceita; o /api/estimar usa a mesma lista
    (antes um modelo inventado dava 200 "gratis" no preco e 400 so ao gerar)."""
    return (set(presets.SIMPLE) | set(presets.EDICAO) | set(presets.NUVEM)
            | {"ideogram", "controle", "ampliar", "angulo", "reluz",
               "personagem", "rosto", "recorte", "orbita3d", "video",
               "limpar_video", "transformar_video", "quadros_maquete", "voz",
               "profundidade_video",
               "transcricao_voz", "musica", "genjutsu",
               "avatar", "separar", "trocar_voz", "treinar_voz"})


@app.post("/api/estimar")
async def estimar(p: PedidoGeracao):
    """Custo estimado do pedido, sem enviar nada.

    API: monta o grafo (os ramos de API nao tem efeito colateral) e avalia o
    price_badge de cada no, a mesma conta que a Comfy mostra. Modelo aberto na
    nuvem: tempo previsto x tarifa de GPU. Local: gratis."""
    if p.modelo not in _modelos_conhecidos():
        raise HTTPException(400, f"Unknown model: {p.modelo}")
    global MOTOR_CARREGADO
    if _eh_api(p):
        antes = MOTOR_CARREGADO
        so_estimando = comfy.SO_ESTIMANDO.set(True)
        try:
            grafo = await montar(Tarefa(p.model_copy(deep=True)))
            faixa = await precos.de_api(grafo)
        except Exception as e:
            return {"tipo": "desconhecido", "motivo": str(e)[:200]}
        finally:
            MOTOR_CARREGADO = antes
            comfy.SO_ESTIMANDO.reset(so_estimando)
        if faixa is not None and p.modelo == "genjutsu" and p.modelo_genjutsu != "kling_omni":
            # Higgsfield e Aleph2 cobram por segundo do video de origem.
            try:
                caminho = _video_de_referencia(p.referencias[0])
                # Fora do laco de eventos: ler e analisar um video grande travaria o servidor.
                dur = (await asyncio.to_thread(
                    lambda: miniaturas.dados_do_video(pathlib.Path(caminho).read_bytes())))["duracao"] or 5
            except Exception:
                dur = 5.0
            dur = min(dur, genjutsu.MODELOS[p.modelo_genjutsu]["max_segundos"])
            faixa = (faixa[0] * dur, faixa[1] * dur)
        if faixa is not None and p.modelo == "avatar":
            # Os nos de lip sync cobram por segundo de fala.
            try:
                fala = await avatar.duracao_audio(p.referencia_avatar)
            except Exception:
                fala = 10.0
            faixa = (faixa[0] * fala, faixa[1] * fala)
        if faixa is None:
            if p.modelo_video == "minimax-nuvem":
                seg = presets.VIDEO_MINIMAX_NUVEM["segundos_estimados"] * max(1.0, p.duracao_video / 5)
                return {"tipo": "gpu", "usd": round(precos.de_gpu(seg), 4)}
            return {"tipo": "desconhecido", "motivo": "sem tabela de preco"}
        mult = max(1, p.lote) if p.modelo in presets.NUVEM else 1
        return {"tipo": "api", "min": round(faixa[0] * mult, 4), "max": round(faixa[1] * mult, 4)}
    if not comfy.na_nuvem():
        return {"tipo": "gratis"}
    # Modelo aberto na Comfy Cloud: cobra o tempo de GPU. Os tempos sao os
    # medidos nesta maquina (16 GB); na nuvem a placa e maior, entao e teto.
    if p.modelo == "avatar":
        try:
            fala = await avatar.duracao_audio(p.referencia_avatar)
        except Exception:
            fala = 10.0
        seg = avatar.MODELOS["ltx23"]["segundos_por_segundo"] * max(fala, 3.0)
    elif p.modelo == "genjutsu":
        seg = genjutsu.MODELOS.get(p.modelo_genjutsu, {}).get("segundos_gpu") or genjutsu.MODELOS["wan_animate2"]["segundos_gpu"]
    elif p.modelo == "voz":
        seg = 20 + len(p.prompt) / 15  # ~15 caracteres por segundo de fala, gerados em tempo real
    elif p.modelo == "musica":
        seg = musica.MODELOS.get(p.modelo_musica, {}).get("gpu_por_segundo", 0.5) * p.duracao_musica + 15
    elif p.modelo == "transformar_video":
        # Tempo medido por segundo de video, ate o maximo do efeito.
        cfg = presets.VIDEO_TRANSFORMAR
        efeito = cfg["efeitos"].get(p.efeito_video, {})
        caminho = _video_de_referencia(p.referencias[0]) if p.referencias else None
        dur = 5.0
        try:
            d = await asyncio.to_thread(lambda: miniaturas.dados_do_video(pathlib.Path(caminho).read_bytes()))
            dur = d["duracao"] or dur
        except Exception:
            pass
        seg = cfg["segundos_por_segundo"] * min(dur, efeito.get("max_quadros", cfg["max_quadros"]) / 24)
    elif p.modelo == "video":
        base = (presets.VIDEO_LTX23 if p.modelo_video == "ltx23" else
                videos_leves.VIDEO_LEVES.get(p.modelo_video, presets.VIDEO_LTX))["segundos_estimados"]
        seg = base * max(0.6, p.duracao_video / 5)
        if p.modelo_video == "minimax" and not p.turbo:
            seg *= 5
    else:
        seg = presets.SIMPLE.get(p.modelo, {}).get("segundos_estimados", 30) * max(1, p.lote)
    return {"tipo": "gpu", "usd": round(precos.de_gpu(seg), 4)}


@app.get("/api/atualizacao")
async def ver_atualizacao(forcar: bool = False):
    """Se a instalacao (git clone do GitHub) tem versao nova. Ver atualizacao.py."""
    return await asyncio.to_thread(atualizacao.estado, forcar)


@app.post("/api/atualizacao")
async def aplicar_atualizacao():
    """Abre atualizar.bat e encerra o servidor. Nunca no meio de uma geracao."""
    if any(t.estado in ("na_fila", "preparando", "submetendo", "executando") for t in TAREFAS.values()):
        raise HTTPException(409, "Wait for the current generation to finish, then update.")
    try:
        await asyncio.to_thread(atualizacao.aplicar)
    except atualizacao.SemInternet as e:
        raise HTTPException(503, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    atualizacao.encerrar_em(1.5)
    return {"ok": True}


@app.get("/api/motor")
async def motor_atual():
    return {"modo": comfy.MODO["motor"], "chave_nuvem": chaves.chave() is not None,
            "link_recarga": config.LINK_RECARGA, "so_abertos": comfy.so_abertos(),
            "modo_seguro": comfy.modo_seguro()}


@app.get("/api/profundidade/exr/{tarefa_id}")
async def baixar_exr(tarefa_id: str):
    """Os quadros EXR de um mapa de profundidade, num .zip."""
    if not re.fullmatch(r"[0-9a-f-]{8,36}", tarefa_id):
        raise HTTPException(400, "id inválido")
    pasta = config.COMFY_SAIDA / "editor" / f"profundidade_exr_{tarefa_id[:8]}"
    quadros = sorted(pasta.glob("frame_*.exr")) if pasta.is_dir() else []
    if not quadros:
        raise HTTPException(404, "esta tarefa não gerou EXR")

    def zipar() -> bytes:
        import io, zipfile
        buf = io.BytesIO()
        # EXR ja e comprimido por dentro; guardar sem recomprimir e mais rapido.
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            for q in quadros:
                z.write(q, q.name)
        return buf.getvalue()

    dados = await asyncio.to_thread(zipar)
    return Response(dados, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="depth_exr_{tarefa_id[:8]}.zip"'})


@app.get("/api/nos/editor")
async def editor_de_nos():
    """Enderecos dos ComfyUI locais para a aba Advanced (editor de nodes).
    Sempre os locais, mesmo com a nuvem escolhida nos menus."""
    async def de_pe(url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                return (await c.get(f"{url}/system_stats")).status_code == 200
        except Exception:
            return False
    async def estrito(url: str) -> bool:
        # ComfyUI sem --enable-cors-header recusa (403) pagina que o navegador
        # chama de "cross-site", e o quadro da aba fica em branco sem aviso.
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                return (await c.get(f"{url}/", headers={"Sec-Fetch-Site": "cross-site"})).status_code == 403
        except Exception:
            return False

    async def motor(ident, rotulo, url):
        vivo = await de_pe(url)
        return {"id": ident, "rotulo": rotulo, "url": url, "vivo": vivo,
                "estrito": vivo and await estrito(url)}

    motores_nos = [await motor("principal", "Main engine", config.COMFY_URL)]
    if not motor_flux3.UNICO and motor_flux3.instalado():
        motores_nos.append(await motor("video", "Video engine (LTX, YuE2)", config.COMFY_URL_FLUX3))
    return {"motores": motores_nos}


class PedidoAbertos(Pedido):
    valor: bool


@app.post("/api/abertos")
async def trocar_abertos(pedido: PedidoAbertos):
    """Liga/desliga o filtro de pesos abertos (modelos de API pela Comfy)."""
    comfy.escolher_abertos(pedido.valor)
    return await motor_atual()


@app.post("/api/seguro")
async def trocar_seguro(pedido: PedidoAbertos):
    """Liga/desliga o Safe mode (filtro de prompt + imagens NSFW borradas)."""
    comfy.escolher_seguro(pedido.valor)
    return await motor_atual()


@app.post("/api/motor")
async def trocar_motor(pedido: PedidoMotor):
    if pedido.modo == "nuvem" and not chaves.chave():
        raise HTTPException(400, "Add your Comfy Cloud API key to run models on the cloud.")
    # A tarefa nao guarda o motor: roda no que estiver escolhido quando chega a
    # vez. Trocar com pedido na fila mandaria um pedido "gratis" para a nuvem
    # (gastando creditos) ou um da nuvem para a placa local.
    if _geracao_em_andamento():
        raise HTTPException(409, "Wait for the queued generations to finish before switching between your GPU and Comfy Cloud.")
    try:
        comfy.escolher_motor(pedido.modo)
    except ValueError:
        raise HTTPException(400, "Motor desconhecido.")
    return await motor_atual()


class PedidoInicializacao(Pedido):
    ativo: bool


@app.get("/api/inicializacao")
async def estado_inicializacao():
    """Se o ComfyUI liga junto com o Windows (botao em Config Models)."""
    import inicializacao
    return await asyncio.to_thread(inicializacao.estado)


@app.post("/api/inicializacao")
async def mudar_inicializacao(pedido: PedidoInicializacao):
    import inicializacao
    try:
        return await asyncio.to_thread(inicializacao.mudar, pedido.ativo)
    except (RuntimeError, OSError) as e:
        raise HTTPException(409, str(e))


@app.get("/api/maquina")
async def ver_maquina():
    import maquina
    return {"detectado": await maquina.detectar(), "salvo": maquina.salvo()}


class PerfilMaquina(Pedido):
    gpu: str = Field("", max_length=80)
    vram_gb: float = Field(0, ge=0, le=1024)
    ram_gb: float = Field(0, ge=0, le=8192)
    so_nuvem: bool = False


@app.post("/api/maquina")
async def salvar_maquina(perfil: PerfilMaquina):
    # Modelo tipado: {"vram_gb": "abc"} da 422 (era ValueError -> 500).
    import maquina
    return maquina.salvar(perfil.model_dump())


@app.get("/api/pacotes")
async def listar_pacotes():
    import pacotes
    return await pacotes.situacao()


class PedidoInstalar(Pedido):
    opcionais: bool = False


@app.post("/api/pacotes/{id_pacote}/instalar")
async def instalar_pacote(id_pacote: str, pedido: PedidoInstalar):
    import instalador
    try:
        return await instalador.iniciar(id_pacote, pedido.opcionais)
    except KeyError:
        raise HTTPException(404, "Pacote desconhecido.")
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.get("/api/pacotes/{id_pacote}/remover")
async def plano_remocao(id_pacote: str):
    """O que o botao Remove tiraria do disco (sem mexer em nada). Ver remocao.py."""
    import remocao
    try:
        return await asyncio.to_thread(remocao.plano, id_pacote)
    except KeyError:
        raise HTTPException(404, "Pacote desconhecido.")


@app.post("/api/pacotes/{id_pacote}/remover")
async def remover_pacote(id_pacote: str):
    """Manda para a Lixeira os arquivos que so este pacote usa. Nunca durante uma geracao."""
    import remocao
    if any(t.estado in ("na_fila", "preparando", "submetendo", "executando") for t in TAREFAS.values()):
        raise HTTPException(409, "Wait for the current generation to finish.")
    try:
        comfy.esquecer_info()
        return await asyncio.to_thread(remocao.remover, id_pacote)
    except KeyError:
        raise HTTPException(404, "Pacote desconhecido.")
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.get("/api/pacotes/progresso")
async def progresso_instalacao():
    import instalador
    return instalador.ESTADO


class PedidoTokenHF(Pedido):
    token: str = ""


@app.get("/api/pacotes/token")
async def token_hf():
    return chaves.situacao_hf()


@app.post("/api/pacotes/token")
async def salvar_token_hf(pedido: PedidoTokenHF):
    chaves.salvar_hf_token(pedido.token)
    return chaves.situacao_hf()


class PedidoNos(Pedido):
    pacote: str | None = None


@app.get("/api/nos")
async def nos_extras():
    import instalador_nos
    return {"nos": instalador_nos.situacao(), "progresso": instalador_nos.ESTADO,
            "comfy_dir": str(config.COMFY_DIR) if config.COMFY_DIR else None}


@app.post("/api/nos/instalar")
async def instalar_nos(pedido: PedidoNos):
    import instalador_nos
    try:
        # Com geracao em andamento o instalador nao desliga o ComfyUI (nem para religar).
        return instalador_nos.iniciar(pedido.pacote, ocupado=lambda: any(
            t.estado in ("na_fila", "preparando", "submetendo", "executando") for t in TAREFAS.values()))
    except KeyError:
        raise HTTPException(404, "Unknown package.")
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.post("/api/pacotes/cancelar")
async def cancelar_instalacao():
    import instalador
    instalador.cancelar()
    return {"ok": True}


@app.get("/api/modelos")
async def modelos():
    """Catalogo da tela. No modo nuvem, cada modelo e efeito leva `nuvem`:
    se roda na Comfy Cloud (a tela marca "so local" e bloqueia os outros)."""
    dados = _filtrar_publico(await _modelos_base())
    # Com chave, a compatibilidade vem sempre (nao so no modo nuvem): os menus
    # de modelo mostram "Your GPU" e "Comfy Cloud" lado a lado.
    if not chaves.chave():
        return dados
    import nuvem
    try:
        compat = await nuvem.compatibilidade()
    except Exception:
        return dados
    for m in dados.get("modelos", []):
        if m["id"] in compat["imagem"]:
            m["nuvem"] = compat["imagem"][m["id"]]
    for f in (dados.get("transformar_video") or {}).get("efeitos", []):
        f["nuvem"] = compat["efeitos_video"].get(f["id"], False)
    dados["nuvem_compat"] = compat
    return dados


def _de_parceiro(item: dict) -> bool:
    """Metodo, modo ou gerador que roda num servico fechado (no de parceiro)."""
    return bool(item.get("custo_usd") or item.get("nuvem") is True or item.get("id") == "nuvem"
                or "(nuvem)" in str(item.get("rotulo", "")))


def _filtrar_publico(dados: dict) -> dict:
    """Tira do catalogo o que nao vai para a versao publica: modos pessoais e,
    com SO_MODELOS_ABERTOS, tudo que depende de servico fechado."""
    dados["modelos"] = [m for m in dados["modelos"] if m["id"] not in config.MODELOS_OCULTOS]
    if not comfy.so_abertos():
        return dados
    dados["nuvem"], dados["nuvem_pronta"] = [], False
    dados["edicao"] = [e for e in dados["edicao"] if not e.get("custo_usd")]
    for e in dados["edicao"]:
        if "metodos" in e:
            e["metodos"] = [m for m in e["metodos"] if not _de_parceiro(m)]
    dados["video"]["geradores"] = [g for g in dados["video"]["geradores"] if not _de_parceiro(g)]
    dados["video_api"] = []
    dados["lipsync_api"] = []
    dados["so_modelos_abertos"] = True
    return dados


async def _modelos_base():
    simples = [{"id": k, **{c: v[c] for c in ("rotulo", "descricao", "steps", "cfg",
                                              "segundos_estimados")},
                "honra_negativo": presets.honra_negativo(k),
                "referencia_personagem": k in ("krea", "kroma", "kroma_foto"),
                **({"nativo_4k": v["nativo_4k"]} if "nativo_4k" in v else {})}
               for k, v in presets.SIMPLE.items()]
    ideogram = {"id": "ideogram",
                "rotulo": presets.IDEOGRAM["rotulo"],
                "descricao": presets.IDEOGRAM["descricao"],
                "segundos_estimados": presets.IDEOGRAM["segundos_estimados"],
                "qualidades": list(presets.IDEOGRAM["qualidades"]),
                "honra_negativo": False}
    edicao = [{"id": k, **{c: v[c] for c in ("rotulo", "descricao", "dica",
                                             "min_referencias", "max_referencias",
                                             "segundos_estimados")},
               "grupo": v["grupo"],
               **({"papeis": v["papeis"]} if "papeis" in v else {}),
               # Só o Qwen tem resolução escolhível; nos outros o tamanho vem
               # da imagem enviada.
               **({"resolucoes": v["resolucoes"],
                   "resolucao_padrao": v["resolucao_padrao"]}
                  if "resolucoes" in v else {}),
               # Controles proprios da ferramenta (hoje so o "Girar a camera").
               # Sem repassar aqui, o campo novo do preset NAO chega na tela —
               # foi assim que a `nota` do ampliar ficou vazia na primeira vez.
               **({"camera": v["camera"]} if "camera" in v else {})}
              for k, v in presets.EDICAO.items()]
    controle = {"id": "controle",
                  "grupo": presets.CONTROLE["grupo"],
                **{c: presets.CONTROLE[c] for c in
                   ("rotulo", "descricao", "dica", "min_referencias",
                    "max_referencias", "segundos_estimados")},
                "tipos": [{"id": k, "rotulo": v["rotulo"]}
                          for k, v in presets.CONTROLE["tipos"].items()]}
    ampliar = {"id": "ampliar",
                  "grupo": presets.AMPLIAR["grupo"],
               **{c: presets.AMPLIAR[c] for c in
                  ("rotulo", "descricao", "dica", "min_referencias",
                   "max_referencias", "segundos_estimados")},
               # A `nota` diz o que a bateria de 18/09 mediu em cada um — o
               # clássico deixa trama na pele, o criativo desloca o
               # enquadramento. Sem repassá-la, o texto morria no preset.
               # O custo entra aqui tambem. Este serializador e proprio do
               # ampliar e nao passa pelo _metodos — foi assim que a `nota`
               # ficou vazia na primeira vez. Um campo novo no preset NAO
               # aparece sozinho na interface.
               "metodos": [{"id": k, "rotulo": v["rotulo"],
                            "nota": v.get("nota", ""),
                            **({"custo_usd": v["custo_usd"]}
                               if "custo_usd" in v else {})}
                           for k, v in presets.AMPLIAR["metodos"].items()],
               "escalas": presets.AMPLIAR["escalas"],
               # Só o criativo tem preset. O SeedVR2 roda cru por escolha
               # medida; ver presets.AMPLIAR["otimizacoes"].
               "otimizacoes": [{"id": k, "rotulo": v["rotulo"],
                                "padroes": v["padroes"]}
                               for k, v in presets.AMPLIAR["otimizacoes"].items()]}
    angulo = {"id": "angulo",
                  "grupo": presets.ANGULO["grupo"],
              **{c: presets.ANGULO[c] for c in
                 ("rotulo", "descricao", "dica", "min_referencias",
                  "max_referencias", "segundos_estimados")},
              "vistas": [{"id": k, "rotulo": v["rotulo"],
                          # Onde a LoRA sai do repertório que a ficha dela
                          # documenta, a interface avisa em vez de fingir.
                          "camera_documentada": v.get("camera_documentada", True)}
                         for k, v in presets.ANGULO["vistas"].items()],
              "metodos": _metodos(presets.ANGULO),
              "metodo_padrao": presets.ANGULO["metodo_padrao"]}
    reluz = {"id": "reluz",
                  "grupo": presets.RELUZ["grupo"],
             **{c: presets.RELUZ[c] for c in
                ("rotulo", "descricao", "dica", "min_referencias",
                 "max_referencias", "segundos_estimados")},
             "temperaturas": [{"id": k, "rotulo": v}
                              for k, v in presets.RELUZ["temperaturas"].items()],
             "metodos": _metodos(presets.RELUZ),
             "metodo_padrao": presets.RELUZ["metodo_padrao"]}
    estilos = [{"id": k, "rotulo": v["rotulo"], "nota": v["nota"]}
               for k, v in presets.ESTILOS.items()]

    # Uma consulta so ao motor, reusada por quem precisa saber o que esta no
    # disco: o "Rapido" do Personagem.
    unets = await comfy.unets_disponiveis()

    # "Rápido" só aparece se o Klein destilado estiver no disco; sem ele a
    # chave não teria o que fazer, e uma opção que não muda nada engana.
    pe = presets.PERSONAGEM
    tem_destilado = pe["unet"] in unets
    prioridades = [{"id": k, "rotulo": v["rotulo"], "nota": v["nota"],
                    "segundos": v["segundos"]}
                   for k, v in pe["prioridades"].items()
                   if tem_destilado or not v["destilado"]]
    personagem = {"id": "personagem",
                  "grupo": pe["grupo"],
                  **{c: pe[c] for c in ("rotulo", "descricao", "dica",
                                        "min_referencias", "max_referencias")},
                  "papeis": pe["papeis"],
                  "tem_destilado": tem_destilado,
                  "prioridades": prioridades,
                  # O padrao e a primeira prioridade que sobreviveu ao filtro
                  # acima, entao a estimativa tem de sair dela, e nao de uma
                  # chave fixa que o painel talvez nem abra.
                  "segundos_estimados": prioridades[0]["segundos"],
                  "blocos": [{"id": k, "rotulo": v["rotulo"], "padrao": v["padrao"]}
                             for k, v in pe["blocos"].items()]}

    rosto = {"id": "rosto",
                  "grupo": presets.ROSTO["grupo"],
             **{c: presets.ROSTO[c] for c in
                ("rotulo", "descricao", "dica", "min_referencias",
                 "max_referencias", "segundos_estimados")},
             "grupos": presets.ROSTO["grupos"]}

    recorte = {"id": "recorte",
               **{c: presets.RECORTE[c] for c in
                  ("grupo", "rotulo", "descricao", "dica", "min_referencias",
                   "max_referencias", "segundos_estimados", "custo_usd")}}

    # Os tres modos que todo gerador local faz. O de referencia NAO entra
    # aqui: ele depende de outro checkpoint (MiniMax) ou de outra LoRA (LTX),
    # e por isso cada gerador diz se tem.
    MODOS_CLASSICOS = ["texto", "imagem", "primeiro_ultimo"]

    def _um_gerador(vid, ident):
        # Local tambem passa a falar em RESOLUCAO + PROPORCAO. O tamanho em
        # pixels e calculado dos dois, com alinhamento de 32 — e a tela mostra
        # o resultado real, em vez de prometer 720 e entregar 704.
        # `max_referencias` no preset e o sinal de que este gerador tem o
        # modo: o MiniMax tem (ref2va), e o LTX tem (MSR).
        modos = list(MODOS_CLASSICOS)
        if vid.get("max_referencias"):
            modos.append("referencia")
        return {"id": ident, "modos": modos,
                "max_referencias": vid.get("max_referencias"),
                # So o ref2va aceita VIDEO como referencia. O teto vem do
                # preset para a tela nao precisar saber quem faz o que.
                "max_videos_referencia": vid.get("max_videos_referencia"),
                # O mesmo ref2va aceita arquivos de audio avulsos. Declarado
                # como capacidade para a tela nao conhecer o MiniMax pelo id.
                "max_audios_referencia": vid.get("max_audios_referencia"),
                # O LTX aceita uma voz de identidade em qualquer modo; nao e
                # um substituto para as imagens obrigatorias do MSR.
                "max_audios_identidade": vid.get("max_audios_identidade"),
                "forca_audio_referencia_padrao": vid.get("forca_audio_referencia"),
                **({"tamanhos_referencia": vid["tamanhos_referencia"],
                    "tamanho_referencia_padrao": vid["tamanho_referencia"]}
                   if "tamanhos_referencia" in vid else {}),
                # So o MSR tem um slot separado para o CENARIO.
                "tem_fundo_referencia": bool(vid.get("tem_fundo_referencia")),
                "tipo_tamanho": "proporcao",
                "resolucoes": [r for r, _ in presets.RESOLUCOES_VIDEO],
                "resolucao_padrao": "720p",
                "proporcoes": presets.PROPORCOES_VIDEO,
                "proporcao_padrao": "16:9",
                "max_pixels": vid.get("max_pixels", presets.MAX_PIXELS_VIDEO_LOCAL),
                "alinhamento": vid["alinhamento"],
                **{c: vid[c] for c in ("rotulo", "descricao", "fps", "duracao_min", "duracao_max",
                                       "duracao_padrao", "segundos_estimados")},
                # O tempo NAO cresce linear com a duracao, e cada modelo cresce
                # de um jeito. Ausente = linear, que e o que a tela fazia para
                # todos: so vai onde a curva foi medida, para nao "melhorar" a
                # estimativa dos outros com um numero tirado de outro modelo.
                **({"expoente_duracao": vid["expoente_duracao"]}
                   if "expoente_duracao" in vid else {}),
                # O que cada gerador REALMENTE aceita. Sem isto a tela mostrava
                # os tres controles em todos e dois nao chegavam ao grafo.
                # `_um_gerador` serve LTX e MiniMax, e so o LTX sugere prompt.
                "sugere_prompt": vid.get("sugere_prompt", False),
                "tem_audio": True, "enriquece_prompt": False,
                # So o MiniMax tem a chave turbo.
                **({"turbo": {"passos": vid["passos_turbo"],
                              "passos_normal": vid["passos_normal"]}}
                   if "passos_turbo" in vid else {})}

    def _um_ltx23():
        # Sem modo texto: o grafo parte sempre de uma imagem.
        base = _um_gerador(presets.VIDEO_LTX23, "ltx23")
        base.update({"modos": ["imagem", "primeiro_ultimo"],
                     "resolucoes": ["480p", "720p"],
                     "max_audios_trilha": presets.VIDEO_LTX23["max_audios_trilha"],
                     "max_audios_identidade": None})
        return base

    def _um_gerador_nuvem(vid, ident):
        """Forma PROPRIA: aqui o tamanho e proporcao + resolucao, e o custo e
        por tempo de GPU — nao da para mostrar um preco fechado antes do
        clique, so a tarifa."""
        return {"id": ident, "nuvem": True, "modos": MODOS_CLASSICOS,
                **{c: vid[c] for c in ("rotulo", "descricao", "fps", "duracao_min", "duracao_max",
                                       "duracao_padrao", "segundos_estimados",
                                       "proporcoes", "proporcao_padrao",
                                       "resolucoes", "resolucao_padrao",
                                       "usd_por_segundo_gpu")},
                "sugere_prompt": False, "tem_audio": False,
                "enriquece_prompt": False,
                "tipo_tamanho": vid["tipo_tamanho"]}

    def _um_ref_nuvem(vid, ident):
        """Hailuo 03: SO faz referencia, e as resolucoes mudam com a variante.

        E o unico gerador do projeto com um modo so. Declarar os tres classicos
        aqui faria a tela oferecer o que o no nao tem."""
        return {"id": ident, "nuvem": True, "modos": ["referencia"],
                "tipo_tamanho": "proporcao",
                "sugere_prompt": False, "tem_audio": False,
                "enriquece_prompt": False,
                **{c: vid[c] for c in ("rotulo", "descricao", "fps",
                                       "duracao_min", "duracao_max",
                                       "duracao_padrao", "segundos_estimados",
                                       "proporcoes", "proporcao_padrao",
                                       "resolucao_padrao", "max_referencias")},
                "preco_multiref": vid["preco_multiref"],
                # A lista de resolucoes NAO e fixa: depende da variante.
                "resolucoes": vid["resolucoes_por_variante"][vid["variante_padrao"]],
                "resolucoes_por_variante": vid["resolucoes_por_variante"],
                "variantes": [{"id": i, "rotulo": r} for i, r in vid["variantes"]],
                "variante_padrao": vid["variante_padrao"]}

    def _um_wan(vid, ident):
        """O Wan tem forma propria: variantes, preco por SEGUNDO de video, e
        uma lista de modos que NAO inclui texto puro."""
        return {"id": ident, "nuvem": True,
                **{c: vid[c] for c in ("rotulo", "descricao", "fps", "duracao_min", "duracao_max",
                                       "duracao_padrao", "segundos_estimados",
                                       "proporcoes", "proporcao_padrao",
                                       "resolucoes", "resolucao_padrao",
                                       "modos", "max_referencias")},
                "sugere_prompt": False, "tem_audio": True,
                "enriquece_prompt": True,
                "tipo_tamanho": vid["tipo_tamanho"],
                "variantes": [{"id": i, "rotulo": r} for i, r in vid["variantes"]],
                "variante_padrao": vid["variante_padrao"],
                "preco_por_segundo": vid["preco_por_segundo"]}

    v = presets.VIDEO_LTX
    video = {"id": "video",
             **{c: v[c] for c in ("rotulo", "descricao", "fps", "duracao_min", "duracao_max",
                                  "duracao_padrao", "tamanho_padrao",
                                  "segundos_estimados")},
             # Em (rotulo, largura, altura); a interface so precisa do rotulo,
             # mas manda as tres para poder avisar sobre proporcao.
             "tamanhos": [{"id": r, "largura": l, "altura": a}
                          for r, l, a in v["tamanhos"]],
             "modos": [
                 {"id": "texto", "rotulo": "A partir de um texto",
                  "imagens": 0,
                  "nota": "Descreva a cena e o movimento. Não usa imagem."},
                 {"id": "imagem", "rotulo": "Animar uma imagem",
                  "imagens": 1,
                  "nota": "A imagem vira o primeiro quadro e ganha movimento."},
                 {"id": "primeiro_ultimo", "rotulo": "Primeiro e ultimo quadro",
                  "imagens": 2,
                  "nota": "Duas imagens; o modelo inventa o caminho entre elas. "
                          "Elas precisam ter a MESMA proporção do vídeo, senão "
                          "o corte central remove conteúdo sem avisar."},
                 # `imagens` e o MINIMO e `imagens_max` o teto. Nos outros
                 # modos os dois coincidem; aqui nao: uma referencia basta, e
                 # o teto varia por gerador (4 no LTX, 9 no MiniMax, 10 no
                 # Wan). Antes so havia `imagens`, tratado como obrigatorio —
                 # o botao Gerar ficava travado ate subir as dez.
                 {"id": "referencia", "rotulo": "Por referências",
                  "imagens": 1, "imagens_max": 10,
                  "nota": "Imagens de referência de personagem, objeto ou "
                          "cenário. O texto pode citá-las por ordem."},
                 {"id": "ingredientes", "rotulo": "Ingredientes (folha)",
                  "imagens": 1, "imagens_max": 4,
                  "nota": "De 1 a 4 imagens viram uma folha de referência: lado "
                          "a lado no vídeo deitado, empilhadas no em pé. Cite cada "
                          "uma pela POSIÇÃO NA FOLHA, em inglês: \"the woman from "
                          "the left of the reference sheet ... the street shown on "
                          "the right of the sheet\". Escrever \"image 1, image 2\" "
                          "faz o modelo animar a folha em vez de combinar (medido). "
                          "Sai com o lado menor em 544 px e até 8 s."},
                 {"id": "chaves", "rotulo": "Quadros-chave",
                  "imagens": 2, "imagens_max": 8,
                  "nota": "De 2 a 8 imagens, cada uma presa ao número de quadro "
                          "que você marcar; o texto descreve o movimento entre "
                          "elas. Imagens vizinhas precisam ter ponto de vista "
                          "parecido: se mudarem muito, o modelo funde uma na "
                          "outra. Até 15 s; saída 1280×720 em 16:9, com upscale e refinamento."},
             ],
             # Os dois geradores LOCAIS. Os modos acima valem para ambos: o
             # MiniMax faz os tres num no so, o LTX em duas funcoes.
             "geradores": [{**(lambda g: {**g, "modos": g["modos"] + (
                                ["ingredientes", "chaves"] if motor_flux3.instalado() else [])})(
                                _um_gerador(presets.VIDEO_LTX, "ltx")),
                            "camera_lenta": presets.CAMERA_LENTA["velocidades"],
                            "modos_camera_lenta": presets.CAMERA_LENTA["modos"]},
                           _um_ltx23(),
                           _um_gerador_nuvem(presets.VIDEO_MINIMAX_NUVEM,
                                             "minimax-nuvem"),
                           _um_ref_nuvem(presets.VIDEO_MINIMAX_REF_NUVEM,
                                         "minimax-ref-nuvem"),
                           _um_wan(presets.VIDEO_WAN3, "wan3")]}

    # Video por API para a interface nova (a antiga nao le esta lista).
    video_api = [{"id": k, "rotulo": v["rotulo"], "nuvem": True, "modos": v["modos"],
                  "proporcoes": v["proporcoes"], "resolucoes": v["resolucoes"],
                  "duracao_min": v["duracao_min"], "duracao_max": v["duracao_max"],
                  "sem_audio": bool(v.get("sem_audio")),
                  "max_referencias": v.get("max_referencias")}
                 for k, v in presets.VIDEO_API.items()]

    limpar = {"id": "limpar_video",
              "grupo": "acabamento",
              "rotulo": "Ampliar o vídeo",
              "descricao": "Dobra a resolução de um vídeo da galeria.",
              "min_referencias": 1, "max_referencias": 1,
              "segundos_estimados": presets.VIDEO_AMPLIAR_LTX["segundos_estimados"],
              # A interface calcula o mesmo alvo para mostrar antes do clique.
              "maior_lado": presets.VIDEO_AMPLIAR_LTX["maior_lado"],
              # A CONSTANTE vai para a tela, nao o numero escrito a mao la:
              # regra duplicada em dois lugares diverge, e isso ja aconteceu
              # neste projeto com a lista de geradores pagos.
              "alinhamento_temporal": presets.ALINHAMENTO_TEMPORAL_LTX,
              "alinhamento_espacial": presets.ALINHAMENTO_ESPACIAL_LTX,
              # O SeedVR2 vem PRIMEIRO, e e o padrao. O metodo no latente
              # derrete rostos: medido em duas cenas, em duas resolucoes e em
              # tres niveis de ruido (0,30 / 0,15 / 0,08), sempre igual. Ele
              # fica porque entende movimento e serve a quem quer reinterpretar
              # a cena — mas nao como primeira escolha de quem so quer ampliar.
              "metodo_padrao": "seedvr",
              "metodos": [
                  {"id": "seedvr", "rotulo": "Em pixels (SeedVR2)",
                   "segundos": presets.VIDEO_LIMPAR["segundos_estimados"],
                   "nota": presets.VIDEO_LIMPAR["descricao"]},
                  *({"id": m, "rotulo": presets.VIDEO_RTX[m]["rotulo"],
                     "segundos": presets.VIDEO_RTX[m]["segundos_estimados"],
                     "nota": presets.VIDEO_RTX[m]["descricao"]}
                    for m in ("rtx", "rtx48") if motor_flux3.instalado()),
                  {"id": "ltx", "rotulo": "No latente (LTX)",
                   "segundos": presets.VIDEO_AMPLIAR_LTX["segundos_estimados"],
                   "nota": presets.VIDEO_AMPLIAR_LTX["descricao"]},
              ]}

    medidos = biblioteca.tempos_medidos()
    for m in simples + [ideogram] + edicao + [personagem, controle, ampliar,
                                              angulo, reluz, rosto, recorte]:
        m["motor"] = presets.motor_do(m["id"])
        if m["id"] in medidos:
            m["medido"] = medidos[m["id"]]
        if m["id"] in presets.MOTOR_POR_METODO:
            m["motor_por_metodo"] = presets.MOTOR_POR_METODO[m["id"]]

    modos_expansao = [
        {"id": "fiel", "rotulo": "Fiel",
         "nota": "Enriquece material, luz e clima. Não mexe no enquadramento, "
                 "no ângulo nem em quem está na cena."},
        {"id": "livre", "rotulo": "Livre",
         "nota": "Deixa o modelo escolher ângulo e enquadramento e acrescentar "
                 "detalhe do gênero. Muda mais, arrisca mais."},
    ]

    # Modelos por nuvem. Vao numa lista PROPRIA, e nao junto de "modelos":
    # eles custam dinheiro por imagem e mandam o pedido para fora da maquina.
    # Misturar com os locais convidaria a clicar num deles sem perceber.
    # As duas familias tem controles diferentes, entao os campos proprios de
    # cada uma so vao quando existem. A interface decide pelo campo "familia".
    def _um_nuvem(k, v):
        d = {"id": k, "familia": v["familia"],
             **{c: v[c] for c in ("rotulo", "descricao", "preco_usd",
                                  "max_referencias", "segundos_estimados")}}
        for extra in ("resolucoes", "tamanhos", "niveis",
                      "tamanhos_por_nivel", "qualidades"):
            if extra in v:
                d[extra] = v[extra]
        if "fundos" in v:
            d["fundos"] = [{"id": i, "rotulo": r} for i, r in v["fundos"]]
        return d

    nuvem = [_um_nuvem(k, v) for k, v in presets.NUVEM.items() if not v.get("fora_do_menu")]

    return {"video_api": video_api,
            "lipsync_api": [{"id": k, "rotulo": v["rotulo"], "limite": v["limite"]} for k, v in avatar.API.items()],
            "modos_expansao": modos_expansao,
            "grupos_edicao": [{"id": i, "rotulo": r}
                              for i, r in presets.GRUPOS_EDICAO],
            "estilos": estilos,
            "niveis_pele": [{"id": k, "rotulo": r} for k, r in
                            (("nenhum", "Nenhum"), ("moderado", "Moderado"),
                             ("forte", "Forte"))],
            "tipos_imagem": [{"id": k, "rotulo": v["rotulo"], "nota": v["nota"]}
                             for k, v in presets.TIPOS_IMAGEM.items()]
                            + [{"id": presets.TIPO_MANUAL, "rotulo": "Manual",
                                "nota": "Escreva o negativo você mesmo; nada é "
                                        "acrescentado por cima."}],
            "modelos": simples + [ideogram],
            "nuvem": nuvem,
            # Sem chave a interface mostra o caminho em vez do botao. O
            # diagnostico nunca inclui a chave; ver chaves.situacao.
            "nuvem_pronta": chaves.situacao()["tem_chave"],
            "proporcoes_nuvem": presets.PROPORCOES_NUVEM,
            "edicao": edicao + [personagem, controle, ampliar, angulo, reluz,
                                rosto, recorte],
            "proporcoes": list(presets.PROPORCOES),
            "video": video,
            "ampliar_video": limpar,
            # Some da tela se o segundo motor nao estiver instalado.
            "transformar_video": ({
                "id": "transformar_video",
                "segundos_por_segundo": presets.VIDEO_TRANSFORMAR["segundos_por_segundo"],
                "max_segundos": round(presets.VIDEO_TRANSFORMAR["max_quadros"] / 24, 1),
                "efeitos": [{"id": k, "rotulo": v["rotulo"], "nota": v["nota"],
                             "imagem_estilo": bool(v.get("imagem_estilo")),
                             "quadros_chave": bool(v.get("quadros_chave")),
                             "rotulo_imagem": v.get("rotulo_imagem"),
                             "imagem_opcional": bool(v.get("imagem_opcional")),
                             "mapa_pronto": bool(v.get("mapa_pronto")),
                             "formatos": list(v.get("formatos", {})),
                             "controles": [{"id": c, "rotulo": r} for c, r in v.get("controles", {}).items()],
                             "max_segundos": round(v.get("max_quadros", presets.VIDEO_TRANSFORMAR["max_quadros"]) / 24, 1)}
                            for k, v in presets.VIDEO_TRANSFORMAR["efeitos"].items()],
            } if motor_flux3.instalado() else None)}


class PedidoChave(Pedido):
    chave: str = Field("", max_length=400)


@app.post("/api/nuvem/chave")
async def nuvem_chave(pedido: PedidoChave):
    """A chave que o usuario digitou. A resposta nunca a devolve, nem o
    final dela: so se ha chave (chaves.situacao)."""
    chaves.salvar_chave(pedido.chave)
    if not chaves.chave() and comfy.na_nuvem():
        comfy.escolher_motor("local")
    s = await chaves.saldo(forcar=True)
    return {"situacao": chaves.situacao(), "saldo": s}


@app.get("/api/nuvem/saldo")
async def nuvem_saldo(forcar: bool = False):
    """Creditos restantes no ComfyUI. Chamada propria, e nao dentro de
    /api/modelos: o saldo muda a cada geracao e a lista de modelos, nunca."""
    s = await chaves.saldo(forcar)
    # O gasto acumulado vem do banco, entao sobrevive a reinicio e conta as
    # sessoes anteriores. Util para saber quanto a frente inteira ja custou.
    return {**s, "gasto": biblioteca.gasto_total()}


LIMITE_ENVIO = 40 * 1024 * 1024


async def _ler_ate_o_limite(arquivo: UploadFile, aviso: str) -> bytes:
    """Le o envio em pedacos e para assim que passa do limite: antes o arquivo
    inteiro ia para a memoria e so depois o tamanho era conferido."""
    if arquivo.size is not None and arquivo.size > LIMITE_ENVIO:
        raise HTTPException(413, aviso)
    partes, total = [], 0
    while pedaco := await arquivo.read(1024 * 1024):
        total += len(pedaco)
        if total > LIMITE_ENVIO:
            raise HTTPException(413, aviso)
        partes.append(pedaco)
    return b"".join(partes)


@app.post("/api/referencia")
async def referencia(arquivo: UploadFile = File(...)):
    """Sobe uma imagem de referencia para a pasta input do motor."""
    dados = await _ler_ate_o_limite(arquivo, "imagem acima de 40 MB")
    # Prefixo proprio para nao colidir com o que ja existe na pasta do motor.
    nome = f"ref_{uuid.uuid4().hex[:12]}_{pathlib.Path(arquivo.filename or 'ref.png').name}"
    try:
        gravado = await comfy.enviar_imagem(nome, dados)
    except Exception as e:
        raise HTTPException(502, f"o motor recusou a imagem: {e}")
    return {"nome": gravado}


@app.post("/api/referencia-audio")
async def referencia_audio(arquivo: UploadFile = File(...)):
    """Sobe um audio avulso para o MiniMax ref2va.

    O ComfyUI usa o mesmo endpoint de upload para arquivos da pasta input;
    quem interpreta o arquivo depois e o VHS_LoadAudio, nao um no de imagem.
    """
    nome_original = pathlib.Path(arquivo.filename or "referencia.wav").name
    extensao = pathlib.Path(nome_original).suffix.lower()
    permitidas = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}
    if extensao not in permitidas:
        raise HTTPException(415, "use WAV, MP3, FLAC, M4A ou OGG")
    dados = await _ler_ate_o_limite(arquivo, "áudio acima de 40 MB")
    # O /view do ComfyUI bloqueia ".." inclusive em nomes comuns.
    # Um identificador sem o nome original evita essa rejeição e caracteres especiais.
    nome = f"refaudio_{uuid.uuid4().hex[:12]}{extensao}"
    try:
        gravado = await comfy.enviar_imagem(nome, dados)
    except Exception as e:
        raise HTTPException(502, f"o motor recusou o áudio: {e}")
    return {"nome": gravado}


class PedidoQuadro(Pedido):
    video: str


@app.post("/api/genjutsu/quadro")
async def genjutsu_quadro(p: PedidoQuadro):
    """Primeiro quadro do video (para o Recast redesenhar), ja na pasta de entrada."""
    caminho = _video_de_referencia(p.video)
    if not caminho:
        raise HTTPException(404, "não encontrei esse vídeo")
    nome = await asyncio.to_thread(genjutsu.primeiro_quadro, caminho, f"quadro_{uuid.uuid4().hex[:12]}.png")
    return {"nome": nome}


# Modelos de checkpoint unico que aceitam uma imagem de partida (img2img).
IMG2IMG = {"sd15", "sdxl", "sd35m", "sd35l"}


@app.post("/api/gerar")
async def gerar(pedido: PedidoGeracao):
    if comfy.modo_seguro():
        termo = seguro.checar_prompt(pedido.prompt)
        if termo:
            raise HTTPException(400, f'Safe mode is on: "{termo}" is not allowed. You can turn Safe mode off in Config Models.')
    if pedido.modelo not in _modelos_conhecidos():
        raise HTTPException(400, f"Unknown model: {pedido.modelo}")
    if pedido.modelo in presets.SIMPLE and pedido.referencias:
        img2img = pedido.modelo in IMG2IMG
        if pedido.modelo not in ("krea", "kroma", "kroma_foto") and not img2img:
            raise HTTPException(400, "Este gerador não aceita referência de personagem.")
        if img2img and len(pedido.referencias) != 1:
            raise HTTPException(400, "Envie uma imagem de partida.")
        if not 1 <= len(pedido.referencias) <= 3:
            raise HTTPException(400, "Envie de uma a três referências de personagem.")
        if not all(_caminho_de_entrada(r) for r in pedido.referencias):
            raise HTTPException(400, "Uma referência não existe. Envie a imagem novamente.")
        if any(x not in ("", "esquerda", "centro", "direita") for x in pedido.posicoes_referencia):
            raise HTTPException(400, "Posição inválida para o personagem.")
        if pedido.lote != 1 or pedido.escala != 1 or pedido.nativo_4k:
            raise HTTPException(400, "Com referência, use uma imagem por vez e resolução padrão.")
    precisa_imagem = (pedido.modelo in presets.EDICAO
                      or pedido.modelo in ("controle", "ampliar", "angulo",
                                          "reluz", "personagem", "rosto",
                                          "recorte", "limpar_video", "transformar_video"))
    if precisa_imagem and not pedido.referencias:
        raise HTTPException(400, "envie ao menos uma imagem de referência")
    # Ângulo e reiluminação montam a instrução sozinhos; o texto é opcional.
    # Estes montam a instrução sozinhos; o texto do usuário é complemento.
    # O "anygles" entra aqui pelo mesmo motivo do "angulo" e do "reluz": a
    # instrucao e montada pelo no, na frase em que o LoRA foi treinado, e o
    # texto do usuario e so complemento. Eu tinha liberado o campo na TELA e
    # esquecido desta lista — a tela deixava enviar e o backend devolvia
    # "prompt vazio", que nao diz nada a quem so mexeu nos deslizantes.
    sem_prompt = ("ampliar", "angulo", "reluz", "personagem", "rosto", "luzref",
                  "recorte", "limpar_video", "transformar_video", "quadros_maquete",
                  "profundidade_video", "anygles", "cabeca", "folha", "orbita3d", "avatar",
                  "separar", "trocar_voz", "treinar_voz")
    # O video de TEXTO exige prompt. Os outros dois aceitam so as imagens,
    # porque o gerador automatico escreve a descricao a partir delas.
    if (pedido.modelo == "video" and pedido.modo_video != "texto"
            and (pedido.referencias or pedido.referencias_video
                 or pedido.referencias_audio)):
        sem_prompt = sem_prompt + ("video",)
    if (pedido.modelo not in sem_prompt and not pedido.prompt.strip()
            and not pedido.caption):
        raise HTTPException(400, "prompt vazio")
    if pedido.modelo == "transcricao_voz":
        ref = pedido.referencia_voz
        if not ref or pathlib.PurePosixPath(ref).name != ref or chr(92) in ref or pathlib.Path(ref).suffix.lower() not in {".wav", ".flac", ".mp3", ".m4a", ".ogg"}:
            raise HTTPException(400, "Envie um áudio de referência válido.")
        caps = await voz.capacidades()
        if not caps.get("transcricao"):
            raise HTTPException(503, "A transcrição local não está disponível no ComfyUI.")
        pedido.lote = pedido.variacoes = 1
    if pedido.modelo == "musica":
        if pedido.tonalidade_musica not in musica.TONALIDADES:
            raise HTTPException(400, "Tonalidade musical inválida.")
        cfg = next(c for c in await musica.catalogo() if c["id"] == pedido.modelo_musica)
        if not cfg["disponivel"]: raise HTTPException(400, cfg["motivo"])
        if not pedido.prompt.strip(): raise HTTPException(400, "Descreva a música que deseja gerar.")
        if pedido.referencia_musica:
            if pedido.modelo_musica not in ("ace-step15", "yue2-cover"): raise HTTPException(400, "A guia musical está disponível no ACE-Step 1.5.")
            ref=pedido.referencia_musica
            if pathlib.PurePosixPath(ref).name != ref or chr(92) in ref or not ref.startswith('refaudio_'):
                raise HTTPException(400, "Referência musical inválida.")
            try:
                pedido.duracao_musica = await musica.duracao_referencia(ref)
            except Exception: raise HTTPException(400, "Não foi possível ler a guia. Envie WAV, FLAC ou MP3 válido de 10 a 600 segundos.")
            if not 10 <= pedido.duracao_musica <= 600: raise HTTPException(400, "Use uma guia de 10 a 600 segundos.")
            pedido.encerramento_musica = "original"
        if cfg.get("cover") and not pedido.referencia_musica: raise HTTPException(400, "Envie a gravação que vai virar cover.")
        if pedido.duracao_musica > cfg["maximo"]: raise HTTPException(400, f"Duração máxima: {cfg['maximo']} segundos.")
        if pedido.vocal_musica and not cfg["letra"] and not cfg.get("plenio"): raise HTTPException(400, "Este modelo gera instrumentais e sons, sem letra controlada.")
        if pedido.vocal_musica and not cfg.get("plenio") and not pedido.letra_musica.strip(): raise HTTPException(400, "Digite a letra ou escolha instrumental.")
        pedido.lote = pedido.variacoes = 1

    if pedido.modelo == "separar":
        caps = separacao.disponivel()
        if not caps["disponivel"]:
            raise HTTPException(503, caps["motivo"])
        if pedido.separar_item:
            if not biblioteca.obter(pedido.separar_item):
                raise HTTPException(404, "Música não encontrada na galeria.")
        else:
            ref = pedido.referencia_separar
            if (not ref or pathlib.PurePosixPath(ref).name != ref or chr(92) in ref
                    or not ref.startswith("refaudio_")):
                raise HTTPException(400, "Escolha uma música da galeria ou envie um arquivo.")
        pedido.lote = pedido.variacoes = 1

    if pedido.modelo in ("trocar_voz", "treinar_voz"):
        caps = troca_voz.disponivel()
        if not caps["disponivel"]:
            raise HTTPException(503, caps["motivo"])

        def _enviado(ref):
            return (ref and pathlib.PurePosixPath(ref).name == ref and chr(92) not in ref
                    and ref.startswith("refaudio_") and (ENTRADA_DO_MOTOR / ref).exists())
        if pedido.modelo == "trocar_voz":
            if not any(v["id"] == pedido.voz_troca for v in caps["vozes"]):
                raise HTTPException(400, "Escolha uma voz treinada.")
            if pedido.separar_item:
                if not biblioteca.obter(pedido.separar_item):
                    raise HTTPException(404, "Música não encontrada na galeria.")
            elif not _enviado(pedido.referencia_separar):
                raise HTTPException(400, "Escolha uma música da galeria ou envie um arquivo.")
        else:
            if not re.fullmatch(r"[\w-]{2,40}", pedido.nome_voz):
                raise HTTPException(400, "Dê um nome à voz: letras, números, - ou _.")
            if (troca_voz.MODELOS / pedido.nome_voz).exists():
                raise HTTPException(409, "Já existe uma voz com esse nome.")
            if not pedido.arquivos_voz or not all(_enviado(a) for a in pedido.arquivos_voz):
                raise HTTPException(400, "Envie as gravações da voz.")
        pedido.lote = pedido.variacoes = 1

    if pedido.modelo == "avatar":
        if not pedido.referencias:
            raise HTTPException(400, "Envie a foto da pessoa.")
        ref = pedido.referencia_avatar
        if (not ref or pathlib.PurePosixPath(ref).name != ref or chr(92) in ref
                or not ref.startswith("refaudio_")):
            raise HTTPException(400, "Envie a fala em áudio.")
        try:
            pedido.duracao_avatar = await avatar.duracao_audio(ref)
        except Exception:
            raise HTTPException(400, "Não foi possível ler a fala. Envie WAV, FLAC, MP3 ou OGG.")
        teto = avatar.limite(pedido.modelo_avatar)
        if pedido.duracao_avatar > teto + 0.05:
            raise HTTPException(400, f"A fala tem {pedido.duracao_avatar:.1f} s; o limite "
                                     f"deste modelo é {teto:.0f} s.")
        if pedido.modelo_avatar in avatar.API:
            if comfy.so_abertos():
                raise HTTPException(400, "Este modelo é pago por API. Desligue \"Open weights only\" para usá-lo.")
            if not chaves.chave():
                raise HTTPException(400, "Configure a chave da Comfy Cloud para usar modelos de API.")
        elif comfy.na_nuvem():
            # Na Comfy Cloud nao ha instalacao a conferir: o que falta la sai
            # do proprio grafo, na preparacao (nuvem.preparar).
            if pedido.modelo_avatar != "ltx23":
                raise HTTPException(400, "Na Comfy Cloud o Lip Sync usa o LTX 2.3.")
        else:
            caps = await avatar.capacidades()
            escolhido = next((m for m in caps.get("modelos", []) if m["id"] == pedido.modelo_avatar), None)
            if not escolhido or not escolhido["disponivel"]:
                raise HTTPException(503, (escolhido or caps)["motivo"] or "Modelo indisponível.")
        pedido.lote = pedido.variacoes = 1

    if pedido.modelo == "genjutsu":
        cfg = genjutsu.MODELOS[pedido.modelo_genjutsu]
        if not pedido.referencias or not _video_de_referencia(pedido.referencias[0]):
            raise HTTPException(400, "Envie o vídeo.")
        if not cfg["aberto"]:
            if comfy.so_abertos():
                raise HTTPException(400, "Este modelo é pago por API. Desligue \"Open weights only\" para usá-lo.")
            if not chaves.chave():
                raise HTTPException(400, "Configure a chave da Comfy Cloud para usar modelos de API.")
        if len(pedido.referencias) - 1 > cfg["max_refs"]:
            raise HTTPException(400, f"{cfg['rotulo']} aceita até {cfg['max_refs']} imagens.")
        if cfg.get("pacote") and not comfy.na_nuvem():
            import pacotes
            sit = await pacotes.situacao()
            if not any(x["id"] == cfg["pacote"] and x["pronto"] for x in sit["pacotes"]):
                raise HTTPException(400, f"Para rodar {cfg['rotulo']} na sua GPU, instale o pacote em "
                                         "Config Models > Local models, ou escolha-o no grupo Comfy Cloud.")
        if pedido.modelo_genjutsu == "h3_swap":
            if not genjutsu.h3_disponivel():
                raise HTTPException(400, "Falta o workflow gratuito do MDMZ: baixe H3_Character_Swap_MDMZ_v1.json em "
                                         "https://www.patreon.com/MDMZ/posts/h3-character-172119619 e coloque em backend/terceiros.")
            if len(pedido.referencias) < 2:
                raise HTTPException(400, "Envie a foto do personagem.")
        if not pedido.prompt.strip() and pedido.modelo_genjutsu not in ("wan_animate2", "wan22_replace", "h3_swap"):
            raise HTTPException(400, "Descreva o que muda no vídeo.")
        pedido.lote = pedido.variacoes = 1

    if pedido.modelo == "voz":
        if len(pedido.prompt) > 12000:
            raise HTTPException(400, "Use up to 12,000 characters per narration.")
        if pedido.modo_voz == "clonar" and (not pedido.referencia_voz
                                            or (not pedido.transcricao_voz.strip() and not comfy.na_nuvem())):
            raise HTTPException(400, "Envie a referência de voz e sua transcrição.")
        if pedido.modo_voz == "criar" and not pedido.instrucao_voz.strip():
            raise HTTPException(400, "Escolha as características da voz.")
        if pedido.referencia_voz and (pathlib.PurePosixPath(pedido.referencia_voz).name != pedido.referencia_voz or chr(92) in pedido.referencia_voz):
            raise HTTPException(400, "Referência de voz inválida.")
        caps = await voz.capacidades()
        if not caps["disponivel"] or (pedido.modo_voz == "criar" and not caps["design"]):
            raise HTTPException(503, caps["motivo"] or "Criação de voz indisponível.")
        pedido.lote = pedido.variacoes = 1
    tarefa = Tarefa(pedido)
    TAREFAS[tarefa.id] = tarefa
    await FILA.put(tarefa)
    await anunciar(tarefa)
    return tarefa.como_dict()


class PedidoTranscricao(Pedido):
    referencia: str
    idioma: str = Field("Portuguese", pattern="^(Portuguese|English|Spanish|German|French|Japanese)$")


@app.post("/api/voz/transcrever")
async def transcrever_voz(pedido: PedidoTranscricao):
    try:
        interno = PedidoGeracao(modelo="transcricao_voz", prompt="Transcrição do áudio de referência",
                                referencia_voz=pedido.referencia, idioma_referencia_voz=pedido.idioma)
    except ValueError:  # nome de arquivo recusado por _referencia_segura
        raise HTTPException(400, "Invalid voice sample name.")
    return await gerar(interno)


@app.get("/api/voz/transcricao/{tarefa_id}")
async def consultar_transcricao(tarefa_id: str):
    tarefa = TAREFAS.get(tarefa_id)
    if not tarefa or tarefa.pedido.modelo != "transcricao_voz":
        raise HTTPException(404, "Transcrição não encontrada.")
    return tarefa.como_dict()


@app.get("/api/musica")
async def modelos_musica():
    lista = await musica.catalogo()
    # Na nuvem o catalogo nao traz os do Plenio; o menu mostra todos, cada um no seu grupo.
    vistos = {m["id"] for m in lista}
    lista += [{"id": k, "rotulo": v["rotulo"], "letra": v["letra"], "maximo": v["maximo"], "disponivel": False,
               "plenio": bool(v.get("plenio")), "cover": bool(v.get("cover")), "estilos": [], "pesos": {}}
              for k, v in musica.MODELOS.items() if k not in vistos]
    lados = await musica.onde_roda()
    return [m | lados.get(m["id"], {}) for m in lista]


# Ponte para as rotas do Plenio (segundo motor): o editor da Song Sheet,
# embutido na aba Musica, valida a partitura, importa/exporta MIDI etc.
# chamando /plenio/... — aqui, /api/plenio/... repassado ao v0.41.
@app.api_route("/api/plenio/{caminho:path}", methods=["GET", "POST"])
async def ponte_plenio(caminho: str, request: Request):
    # So rotas do proprio Plenio: ".." (mesmo vindo como %2F..) sairia do
    # prefixo e alcancaria qualquer rota do motor (/system_stats, /free...).
    partes = caminho.split("/")
    if (not caminho or "\\" in caminho or any(p in ("", ".", "..") for p in partes)
            or not all(re.fullmatch(r"[\w.\-]+", p) for p in partes)):
        raise HTTPException(404, "rota do Plenio desconhecida")
    if not await motor_flux3.vivo():
        # Subir o segundo motor descarrega o principal: no meio de uma geracao
        # isso a derrubaria (a fila do app sobe o motor sozinha quando e a vez).
        if _geracao_em_andamento():
            raise HTTPException(409, "Wait for the current generation to finish "
                                     "to open the score editor.")
        await motor_flux3.garantir()
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.request(request.method, f"{comfy.BASE_FLUX3}/plenio/{caminho}",
                            params=dict(request.query_params), content=await request.body(),
                            headers={"Content-Type": request.headers.get("content-type", "application/json")})
    return Response(r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type", "application/json"))


@app.get("/api/view")
async def audio_referencia_plenio(request: Request):
    """Entrega ao editor do Plenio o áudio temporário do segundo motor."""
    nome = request.query_params.get("filename", "")
    subpasta = request.query_params.get("subfolder", "")
    tipo = request.query_params.get("type", "")
    if (not re.fullmatch(r"plenio_reference_\d+\.(?:opus|wav|flac|mp3|ogg|m4a)", nome)
            or subpasta or tipo != "temp"):
        raise HTTPException(400, "referência de áudio inválida")
    if not await motor_flux3.vivo():
        raise HTTPException(503, "o segundo motor não está respondendo")
    async with httpx.AsyncClient(timeout=30) as cliente:
        resposta = await cliente.get(f"{comfy.BASE_FLUX3}/view",
                                     params={"filename": nome, "subfolder": "", "type": "temp"})
    return Response(resposta.content, status_code=resposta.status_code,
                    media_type=resposta.headers.get("content-type", "application/octet-stream"))


@app.get("/api/voz")
async def estado_voz():
    return await voz.capacidades()


@app.get("/api/separar")
async def estado_separar():
    return separacao.disponivel()


@app.get("/api/trocar-voz")
async def estado_trocar_voz():
    return troca_voz.disponivel()


@app.delete("/api/trocar-voz/{nome}")
async def remover_voz(nome: str):
    """Tira a voz da lista (vai para a quarentena do Applio, nao e apagada)."""
    if any(t.estado in ("na_fila", "preparando", "executando")
           and t.pedido.modelo in ("trocar_voz", "treinar_voz") for t in TAREFAS.values()):
        raise HTTPException(409, "Há uma troca ou treino de voz em andamento.")
    try:
        alvo = troca_voz.apagar(nome)
    except RuntimeError as e:
        raise HTTPException(404, str(e))
    except OSError:
        raise HTTPException(409, "Could not move the voice (a file in it may be open). Try again.")
    return {"movida_para": str(alvo)}


@app.get("/api/avatar")
async def estado_avatar():
    return await avatar.capacidades()


class PedidoRecorteAvatar(Pedido):
    foto: str
    vertical: bool = False


@app.post("/api/avatar/recorte")
async def recorte_avatar(pedido: PedidoRecorteAvatar):
    """Recorta a foto em volta do rosto ANTES de gerar, para a tela mostrar."""
    foto = pedido.foto
    try:
        if "/" in _referencia_segura(foto):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "Invalid photo name.")
    try:
        nome, achou = await avatar.recortar_no_rosto(foto, pedido.vertical)
    except Exception:
        # O detalhe (com o endereco interno do ComfyUI) fica fora da resposta.
        raise HTTPException(400, "Could not read the photo. Upload it again.")
    return {"nome": nome, "rosto": achou}


@app.get("/api/tarefas")
async def tarefas():
    recentes = sorted(TAREFAS.values(), key=lambda t: t.criada_em, reverse=True)[:50]
    return [t.como_dict() for t in recentes]


class PedidoPrevia(Pedido):
    referencia: str


@app.post("/api/video/previa-latente")
async def previa_latente(pedido: PedidoPrevia):
    """Mostra o que o espaco latente do LTX perde NESTE video.

    Nao e estimativa: roda o `encode -> decode` de verdade, que e a etapa
    exata onde o metodo de ampliar no latente destroi o que for pequeno no
    quadro. Sai em poucos segundos porque carrega uma JANELA de quadros, nao o
    clipe inteiro.

    Fica fora da fila de tarefas de proposito: e uma conferencia antes de
    decidir, nao uma geracao, e nao deve entrar na galeria nem no historico.
    """
    caminho = _video_de_referencia(pedido.referencia)
    if not caminho:
        raise HTTPException(404, "não encontrei esse vídeo na pasta de saída")

    # Ler o video inteiro (centenas de MB) no laco de eventos parava o servidor.
    origem = await asyncio.to_thread(pathlib.Path(caminho).read_bytes)
    d = await asyncio.to_thread(miniaturas.dados_do_video, origem)
    fps = d["fps"] or presets.VIDEO_LTX["fps"]
    # `dados_do_video` devolve duracao e fps, nao contagem de quadros. Usar
    # `d.get("quadros")` daria None, a janela ficaria no inicio do clipe, e o
    # inicio e o pior lugar para julgar: costuma ser o quadro-guia, mais limpo
    # que o resto.
    total = int((d.get("duracao") or 0) * fps)

    # Uma janela no MEIO do clipe: o comeco costuma ser o quadro-guia, que e
    # mais limpo que o resto e daria uma impressao boa demais.
    janela = 25
    pular = max(0, (total - janela) // 2) if total > janela else 0

    grafo = workflows.previa_latente(caminho, fps=fps, pular=pular,
                                     quadros=janela)
    try:
        saidas = await comfy.executar(grafo, timeout=600)
    except Exception as e:
        raise HTTPException(502, chaves.traduzir_erro(str(e)) or f"a prévia falhou: {e}")

    arquivos = comfy.imagens_salvas(saidas)
    if not arquivos:
        raise HTTPException(502, "a prévia não devolveu vídeo")
    info = json.loads(arquivos[0]) if isinstance(arquivos[0], str) else arquivos[0]
    resultado = SAIDA_DO_MOTOR / info.get("subpasta", "") / info["nome"]

    # O quadro 0 do resultado corresponde ao `pular` do original: comparar
    # indices iguais mostraria movimento, e movimento engana o olho.
    try:
        return await asyncio.to_thread(
            previa.comparar, caminho, str(resultado), pular, 0)
    except ValueError as e:
        raise HTTPException(502, str(e))


@app.post("/api/cancelar")
async def cancelar():
    """Para TUDO: fila do app, fila do motor, o que roda no motor e a tarefa
    que o app esta acompanhando (mesmo que o motor ja tenha morrido)."""
    canceladas = 0
    while not FILA.empty():
        t = FILA.get_nowait()
        FILA.task_done()
        t.estado, t.erro = "erro", "cancelada pelo usuário"
        await anunciar(t)
        canceladas += 1
    for base in (comfy.BASE_PRINCIPAL, comfy.BASE_FLUX3):
        token = comfy.MOTOR.set(base)
        try:
            await comfy.limpar_fila()
            await comfy.interromper()
        except Exception:
            pass  # motor fora do ar: ainda assim a tarefa do app e abandonada
        finally:
            comfy.MOTOR.reset(token)
    if ATUAL and not ATUAL.done():
        ATUAL.cancel()
        canceladas += 1
    return {"ok": True, "canceladas": canceladas}


@app.post("/api/prompt/expandir")
async def expandir(pedido: PedidoTexto):
    return {"prompt": await prompting.expandir(pedido.ideia)}


class PedidoDiretor(Pedido):
    cena: str = Field(..., min_length=1, max_length=2000)
    enquadramento: str = Field("", max_length=300)
    visual: str = Field("", max_length=2000)
    seed: int = 0


@app.post("/api/cinema/diretor")
async def cinema_diretor(pedido: PedidoDiretor):
    """Reescreve a cena como um diretor de fotografia (ver prompting.DIRETOR)."""
    # Logo depois de ligar o PC o motor local ainda esta subindo (30-60 s; o
    # vigia de motores.py o levanta). Esperar e melhor que cair no prompt simples.
    limite = time.monotonic() + 150
    while True:
        try:
            texto = await prompting.diretor(pedido.cena, pedido.enquadramento,
                                            pedido.visual, pedido.seed)
            break
        except httpx.ConnectError as e:
            if time.monotonic() > limite:
                raise HTTPException(502, f"o motor não subiu a tempo: {e}")
            await asyncio.sleep(3)
        except Exception as e:
            raise HTTPException(502, f"o modelo de texto não respondeu: {e}")
    if not texto:
        raise HTTPException(502, "o modelo de texto voltou vazio")
    return {"prompt": texto}


class PedidoEscreverMaquete(Pedido):
    ideia: str = Field(..., min_length=1, max_length=500)
    campo: str = Field(..., pattern="^(nome|cena)$")
    objeto: str = Field("", max_length=200)
    seed: int = 0


@app.post("/api/maquete/escrever")
async def maquete_escrever(pedido: PedidoEscreverMaquete):
    """3D render -> Video, "Write it for me": o nome do elemento ou a cena, pelo modelo de texto local."""
    try:
        texto = await prompting.maquete(pedido.ideia, pedido.campo, pedido.objeto, pedido.seed)
    except Exception as e:
        raise HTTPException(502, f"The text model did not answer: {e}")
    if not texto:
        raise HTTPException(502, "The text model returned nothing. Try again.")
    return {"texto": texto}


@app.post("/api/ideogram/caption")
async def caption(pedido: PedidoTexto):
    """Converte uma ideia livre no JSON de layout, para o editor de caixas abrir.

    Com uma foto de fundo, a sugestao ja sai desviando do rosto, e as zonas
    ocupadas voltam junto para o editor poder marca-las na tela: o usuario ve
    onde nao pode pousar texto em vez de descobrir depois de gerar.
    """
    cap = await ideogram.caption_ideogram(pedido.ideia, pedido.proporcao)
    zonas = {"rostos": [], "letreiros": []}
    if pedido.fundo:
        try:
            foto = await comfy.imagem(pedido.fundo, tipo="input")
            cap = enquadrar.encaixar(cap, foto)
            zonas = {"rostos": enquadrar.faixas_de_rosto(foto),
                     "letreiros": enquadrar.faixas_de_texto(foto)}
        except Exception as e:
            print(f"sugestao sem a foto: {e!r}", flush=True)
    return {"caption": cap, "zonas": zonas}


class PedidoRotacao(BaseModel):
    referencia: str


@app.post("/api/orbita/rotacao")
async def rotacao_do_corpo(pedido: PedidoRotacao):
    """Orbit: quantos graus a pessoa ja esta virada na foto (0 = de frente).
    Roda so a deteccao do corpo (segundos), sem gerar imagem."""
    if comfy.na_nuvem():
        raise HTTPException(400, "so no motor local")
    try:
        nome = _referencia_segura(pedido.referencia)
    except ValueError as e:
        raise HTTPException(400, str(e))
    saidas = await comfy.executar(workflows.medir_rotacao_corpo(nome), timeout=300)
    texto = await comfy.texto_de(saidas)
    try:
        return {"graus": round(float(texto), 1)}
    except ValueError:
        raise HTTPException(500, "nao consegui medir o corpo nesta foto")


@app.post("/api/rosto/previa")
async def previa_rosto(pedido: PedidoGeracao):
    """Aplica o ajuste na hora, fora da fila.

    São ~1,1 s, então esperar atrás de uma geração de 110 s mataria a ideia de
    arrastar um controle e ver o efeito. Por isso vai direto ao motor, como já
    faz a prévia do ControlNet.
    """
    if not pedido.referencias:
        raise HTTPException(400, "envie uma imagem")
    grafo = workflows.ajustar_rosto(pedido.referencias[0], pedido.rosto,
                                    prefixo="previa/rosto")
    try:
        saidas = await comfy.executar(grafo, timeout=300)
    except Exception as e:
        # Na primeira execução os pesos do LivePortrait são baixados sob
        # demanda e a chamada falha. Uma segunda tentativa costuma passar; se
        # não passar, a mensagem explica em vez de dizer só "erro".
        try:
            saidas = await comfy.executar(grafo, timeout=600)
        except Exception:
            raise HTTPException(502, "o ajuste de rosto falhou. Na primeira vez "
                                     "o motor baixa os modelos do LivePortrait "
                                     "(~200 MB); tente de novo em um minuto. "
                                     f"Detalhe: {str(e)[:300]}")
    for im in comfy.imagens_salvas(saidas):
        return {"nome": im["nome"], "subpasta": im["subpasta"]}
    raise HTTPException(502, "nenhum rosto encontrado na imagem")


@app.post("/api/controle/previa")
async def previa_controle(pedido: PedidoGeracao):
    """Roda só o pré-processador e devolve o mapa de controle, para conferência."""
    if not pedido.referencias:
        raise HTTPException(400, "envie uma imagem de referência")
    if pedido.tipo_controle not in presets.CONTROLE["tipos"]:
        raise HTTPException(400, "tipo de controle desconhecido")
    grafo = workflows.previa_de_controle(pedido.referencias[0], pedido.tipo_controle,
                                         "previa/controle")
    try:
        saidas = await comfy.executar(grafo, timeout=600)
    except Exception as e:
        raise HTTPException(502, str(e)[:500])
    for im in comfy.imagens_salvas(saidas):
        return {"nome": im["nome"], "subpasta": im["subpasta"]}
    raise HTTPException(502, "o pré-processador não devolveu imagem")


# Temperatura desconhecida virava "neutra" calada (luz.py); agora e 422.
TEMPERATURAS_LUZ = "^(" + "|".join(luz.TEMPERATURAS) + ")$"


@app.get("/api/luz/mapa")
async def mapa_de_luz(azimute: float = Query(-45, ge=-720, le=720, allow_inf_nan=False),
                      elevacao: float = Query(25, ge=-180, le=180, allow_inf_nan=False),
                      intensidade: float = Query(1.0, ge=0, le=10, allow_inf_nan=False),
                      temperatura: str = Query("neutra", pattern=TEMPERATURAS_LUZ)):
    """A esfera iluminada que o widget mostra — e a mesma imagem que vai ao modelo."""
    # Desenhar a esfera e trabalho de CPU, pedido a cada arrasto: fora do laco de eventos.
    dados = await asyncio.to_thread(luz.desenhar, azimute, elevacao, intensidade, temperatura)
    return Response(dados, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/luz/frase")
async def frase_de_luz(azimute: float = Query(-45, ge=-720, le=720, allow_inf_nan=False),
                       elevacao: float = Query(25, ge=-180, le=180, allow_inf_nan=False),
                       intensidade: float = Query(1.0, ge=0, le=10, allow_inf_nan=False),
                       temperatura: str = Query("neutra", pattern=TEMPERATURAS_LUZ)):
    """Mostra ao usuário exatamente o que será pedido ao modelo."""
    return {"frase": luz.em_palavras(azimute, elevacao, intensidade, temperatura)}


_MIME = {".flac": "audio/flac", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska",
         ".mov": "video/quicktime", ".webp": "image/webp", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".gif": "image/gif"}


def _tipo_mime(nome: str) -> str:
    """Tipo do arquivo pela extensao. PNG e o padrao, que e o caso comum."""
    return _MIME.get(pathlib.Path(nome).suffix.lower(), "image/png")


def _falha_ao_ler(erro: Exception) -> HTTPException:
    """Arquivo que nao existe e 404; motor fora do ar ou lento e 503. Antes tudo
    virava "imagem nao encontrada" e a galeria parecia ter perdido os arquivos."""
    if isinstance(erro, (httpx.ConnectError, httpx.TimeoutException)):
        return HTTPException(503, "ComfyUI is not responding; the file could not be read.")
    if isinstance(erro, FileNotFoundError) or (
            isinstance(erro, httpx.HTTPStatusError) and erro.response.status_code < 500):
        return HTTPException(404, "imagem não encontrada")
    return HTTPException(502, "ComfyUI could not deliver the file.")


async def _versao_segura(dados: bytes, nome: str, subpasta: str, mime: str) -> tuple[bytes, str]:
    """Safe mode: o arquivo que o classificador marcou sai borrado (o do disco fica igual)."""
    chave = f"{subpasta}/{nome}"
    if not await asyncio.to_thread(seguro.oculto, dados, nome, chave):
        return dados, mime
    if mime.startswith("video/"):
        cache = seguro.PASTA / "borrados" / (chave.replace("/", "__") + ".mp4")
        if not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(await asyncio.to_thread(seguro.borrar_video, dados, nome))
        return cache.read_bytes(), "video/mp4"
    if mime.startswith("image/"):
        return await asyncio.to_thread(seguro.borrar_imagem, dados), "image/png"
    return dados, mime


@app.get("/api/imagem")
async def imagem(nome: str, subpasta: str = "", tipo: str = "output"):
    if subpasta == "finalizacoes_musica":
        if pathlib.Path(nome).name != nome or "/" in nome or "\\" in nome or not nome.startswith("musica_final_") or not nome.endswith(".flac"):
            raise HTTPException(404, "áudio não encontrado")
        arquivo = musica.FINALIZACOES / nome
        if not arquivo.is_file(): raise HTTPException(404, "áudio não encontrado")
        return FileResponse(arquivo, media_type="audio/flac")
    try:
        dados = await comfy.imagem(nome, subpasta, tipo)
    except Exception as e:
        raise _falha_ao_ler(e)
    mime = _tipo_mime(nome)
    if tipo == "output" and comfy.modo_seguro():
        dados, mime = await _versao_segura(dados, nome, subpasta, mime)
    # O tipo tem que casar com o arquivo. Servindo um mp4 como image/png o
    # navegador se recusa a toca-lo, e o <video> fica preto sem dizer por que.
    return Response(dados, media_type=mime,
                    headers={"Accept-Ranges": "bytes",
                             "Cache-Control": "public, max-age=604800"})


@app.get("/api/miniatura")
async def miniatura(nome: str, subpasta: str = "", tipo: str = "output"):
    try:
        dados = await miniaturas.obter(nome, subpasta, tipo)
        if tipo == "output" and comfy.modo_seguro():
            original = await comfy.imagem(nome, subpasta, tipo)
            if await asyncio.to_thread(seguro.oculto, original, nome, f"{subpasta}/{nome}"):
                dados = await asyncio.to_thread(seguro.borrar_imagem, dados)
    except Exception as e:
        raise _falha_ao_ler(e)
    # O arquivo de saida nunca muda de conteudo, entao pode ficar no cache.
    return Response(dados, media_type="image/webp",
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/galeria")
async def galeria(limite: int = Query(60, ge=1, le=5000),
                  antes: float | None = Query(None, allow_inf_nan=False),
                  com_testes: bool = False):
    """As imagens de teste ficam guardadas, mas fora da vista por padrão."""
    return biblioteca.listar(limite, antes, com_testes)


@app.get("/api/galeria/arquivo")
async def galeria_arquivo(subpasta: str, nome: str):
    """Informacoes de um arquivo gerado, para o visualizador do estudio novo."""
    item = biblioteca.por_arquivo(subpasta, nome)
    if item is None:
        raise HTTPException(404, "arquivo sem registro na galeria")
    return item


@app.get("/api/galeria/receita")
async def receita_de_nodes(subpasta: str, nome: str):
    """O grafo do ComfyUI que gerou este arquivo, para baixar e arrastar no ComfyUI."""
    g = grafos.ler(subpasta, nome)
    if g is None:
        raise HTTPException(404, "this file has no saved node recipe (made before this feature)")
    base = pathlib.Path(nome).stem
    return Response(json.dumps(g, ensure_ascii=False, indent=1), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{base}_recipe.json"'})


@app.get("/api/galeria/testes")
async def contar_testes():
    """Quantas imagens estão escondidas, para o botão dizer o número."""
    todas = biblioteca.listar(limite=100000, com_testes=True)
    return {"testes": sum(1 for i in todas if i.get("teste")),
            "total": len(todas)}


class PedidoArquivo(Pedido):
    subpasta: str
    nome: str


@app.post("/api/arquivo/remover")
async def remover_arquivo(p: PedidoArquivo):
    """Tira um arquivo das galerias (a da aba e Assets). O arquivo continua na
    pasta de saida do ComfyUI: some da tela, nao do disco."""
    item = biblioteca.por_arquivo(p.subpasta, p.nome)
    if item:
        biblioteca.apagar(item["id"])
    for t in list(TAREFAS.values()):
        if t.estado not in ("pronto", "erro"):
            continue
        restam = [s for s in t.imagens
                  if not ((d := json.loads(s)).get("nome") == p.nome and d.get("subpasta", "") == p.subpasta)]
        if len(restam) == len(t.imagens):
            continue
        if restam:
            t.imagens = restam
            biblioteca.salvar_tarefa(t.registro())
        else:
            TAREFAS.pop(t.id, None)
            biblioteca.apagar_tarefa(t.id)
    return {"ok": True}


@app.post("/api/tarefa/{tarefa_id}/dispensar")
async def dispensar_tarefa(tarefa_id: str):
    """Tira da tela um cartao de ERRO (nao ha arquivo; so o registro da tarefa)."""
    t = TAREFAS.get(tarefa_id)
    if t is None or t.estado != "erro":
        raise HTTPException(400, "só cartões de erro podem ser dispensados")
    TAREFAS.pop(tarefa_id, None)
    biblioteca.apagar_tarefa(tarefa_id)
    return {"ok": True}


@app.delete("/api/galeria/{item_id}")
async def apagar(item_id: int):
    biblioteca.apagar(item_id)
    return {"ok": True}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    host = sock.headers.get("host", "").split(":", 1)[0].lower()
    if (host not in {"127.0.0.1", "localhost"}
            or not _origem_permitida(sock.headers.get("origin"))):
        await sock.close(code=1008)
        return
    await sock.accept()
    OUVINTES.add(sock)
    try:
        while True:
            await sock.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        OUVINTES.discard(sock)


# A interface compilada e servida pelo proprio backend, para rodar em um endereco so.
if ESTATICOS.exists():
    app.mount("/assets", StaticFiles(directory=ESTATICOS / "assets"), name="assets")

    @app.get("/{caminho:path}")
    async def spa(caminho: str):
        # Rota da API que nao existe e erro, nao a pagina: com 200 + index.html
        # um nome errado no frontend ou num script parecia funcionar.
        if caminho.lower() == "api" or caminho.lower().startswith("api/"):
            raise HTTPException(404, "Not found")
        # So arquivos de dentro da pasta da interface: "../" (ou %2e%2e, barra
        # invertida) nao pode sair dela e entregar, por exemplo, chaves.json.
        alvo = (ESTATICOS / caminho).resolve()
        if caminho and alvo.is_relative_to(ESTATICOS.resolve()) and alvo.is_file():
            return FileResponse(alvo)
        return FileResponse(ESTATICOS / "index.html")
