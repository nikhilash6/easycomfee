import asyncio

import httpx

import pacotes


def teste_catalogo_tem_campos_para_baixar():
    for p in pacotes.carregar():
        assert p["id"] and p["licenca"]["url"]
        for a in p["arquivos"]:
            assert a["pasta"] and a["arquivo"]
            if a.get("sem_origem"):
                # Sem origem publica so e aceitavel em arquivo listado como manual.
                assert a["repo"] is None and pacotes.url_download(a) is None
            elif a.get("derivado"):
                # Recriado pelo instalador a partir de outro arquivo do mesmo pacote.
                origem = a["derivado"]["de"]
                assert any(f"{b['pasta']}/{b['subpasta']}/{b['arquivo']}" == origem for b in p["arquivos"])
                assert a["derivado"]["prefixos"] and a["tamanho"] > 0
            else:
                # O nome local pode diferir do nome na origem (Flux 3, Kroma).
                assert a["repo"] and a["caminho"] and a["tamanho"] > 0


def teste_situacao_marca_o_que_falta(monkeypatch):
    ltx = pacotes.carregar()[0]
    presente = {a["arquivo"] for a in ltx["arquivos"] if not a["opcional"]}

    def responder(pedido):
        pasta = pedido.url.path.split("/")[-1]
        # O ComfyUI no Windows devolve barra invertida.
        nomes = [pacotes.relativo(a).replace("/", "\\") for a in ltx["arquivos"]
                 if a["pasta"] == pasta and a["arquivo"] in presente]
        # Arquivo certo em outra subpasta (quem ja usava ComfyUI) conta: o grafo
        # passa a pedir o lugar real (pacotes.ajustar_grafo).
        nomes += [a["arquivo"] for a in ltx["arquivos"] if a["pasta"] == pasta and a["opcional"]]
        return httpx.Response(200, json=nomes)

    original = httpx.AsyncClient
    monkeypatch.setattr(pacotes.httpx, "AsyncClient",
                        lambda **kw: original(transport=httpx.MockTransport(responder), **kw))
    s = asyncio.run(pacotes.situacao())
    p = s["pacotes"][0]
    assert s["motor_respondendo"] and p["pronto"]
    assert p["tamanho_faltando"] == 0
    opcionais = [a for a in p["arquivos"] if a["opcional"]]
    assert opcionais and all(a["instalado"] and a["encontrado"] == a["arquivo"] for a in opcionais)


def teste_motor_fora_do_ar_nao_inventa_estado(monkeypatch):
    def falhar(pedido):
        raise httpx.ConnectError("fora")
    original = httpx.AsyncClient
    monkeypatch.setattr(pacotes.httpx, "AsyncClient",
                        lambda **kw: original(transport=httpx.MockTransport(falhar), **kw))
    s = asyncio.run(pacotes.situacao())
    assert not s["motor_respondendo"] and s["pacotes"][0]["pronto"] is None


# Pedidos pelo codigo que NAO entram no catalogo, cada um com o motivo.
FORA_DO_CATALOGO = {
    "nsfw_image_detection_int8.onnx": "classificador do Safe mode; o app baixa sozinho para backend/modelos_seguro",
    "https://huggingface.co/onnx-community/nsfw_image_detection-ONNX/resolve/main/onnx/model_quantized.onnx": "idem (URL)",
    "Krea/kroma-v0.3.1-nicegirls08_fp8_scaled.safetensors": "fusao pessoal do autor; o modo Kroma Foto fica fora da versao publica",
    "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors": "copia antiga sem subpasta; o grafo usa LTX/2.5/",
    "Flux2/flux-2-klein-9b-fp8.safetensors": "variante destilada citada so em comentario de preset",
    "face_detection_yunet_2023mar.onnx": "baixado pelo proprio no do avatar",
    "model_bs_roformer_ep_317_sdr_12.9755.ckpt": "separador de faixas, fora do ComfyUI",
    "video_depth_anything_vits.pth": "baixado pelo proprio no de profundidade",
    "depth_anything_v2_vitl.pth": "baixado pelo comfyui_controlnet_aux",
    "dw-ll_ucoco_384.onnx": "baixado pelo comfyui_controlnet_aux",
    "yolox_l.onnx": "baixado pelo comfyui_controlnet_aux",
    "ltx-2.3-22b-distilled-fp8.safetensors": "so na Comfy Cloud (base dos VFX la)",
    "wan_animate_2_distill_int8_convrot.safetensors": "Wan Animate 2: por ora so na Comfy Cloud",
    "umt5_xxl_fp8_e4m3fn_scaled.safetensors": "Wan Animate 2: por ora so na Comfy Cloud",
    "minimax_h3_ref2va_pruned_int8_convrot.safetensors": "MiniMax H3 Character Swap: so na Comfy Cloud",
    "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors": "MiniMax H3 Character Swap: so na Comfy Cloud",
    "sam3.1_multiplex_fp16.safetensors": "MiniMax H3 Character Swap: so na Comfy Cloud",
    "clip_vision_h.safetensors": "Wan Animate 2: por ora so na Comfy Cloud",
}


def teste_caminhos_do_codigo_batem_com_o_catalogo():
    """Todo arquivo de modelo que o codigo pede precisa estar no catalogo, na
    MESMA subpasta (e para la que o instalador baixa), ou na lista acima com
    o motivo. Assim um modo novo nao entra sem ser instalavel."""
    import ast
    import presets
    EXT = (".safetensors", ".pth", ".onnx", ".gguf", ".ckpt")
    catalogo = {pacotes.relativo(a) for p in pacotes.carregar() for a in p["arquivos"]}
    nomes = {a["arquivo"] for p in pacotes.carregar() for a in p["arquivos"]}
    pasta_efeitos = presets.VIDEO_TRANSFORMAR["lora_pasta"]
    pedidos = set()
    for f in (pacotes.config.RAIZ / "backend").glob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value.lower().endswith(EXT) and " " not in n.value and n.value[0].isalnum()):
                pedidos.add(n.value.replace("\\", "/"))
    faltam = []
    for nome in pedidos:
        if nome in FORA_DO_CATALOGO or nome.split("/")[-1] in FORA_DO_CATALOGO:
            continue
        if "/" in nome:
            ok = nome in catalogo
        else:  # nome solto: efeito do LTX (pasta fixa) ou arquivo na raiz da pasta
            ok = (pasta_efeitos + nome) in catalogo or nome in catalogo or nome in nomes
        if not ok:
            faltam.append(nome)
    assert not faltam, f"fora do catalogo: {sorted(faltam)}"


def teste_selo_pela_maquina():
    import maquina
    req = {"vram_min": 16, "vram_rec": 24, "ram_min": 32, "nota_limitado": "lento"}
    placa16 = {"vram_gb": 15.9, "ram_gb": 63.8}
    assert maquina.avaliar(req, placa16, 500, 10)["selo"] == "limitado"
    assert maquina.avaliar(req, {"vram_gb": 23.9, "ram_gb": 64}, 500, 10)["selo"] == "bem"
    assert maquina.avaliar(req, {"vram_gb": 11.9, "ram_gb": 64}, 500, 10)["selo"] == "nao_roda"
    assert maquina.avaliar(req, {"vram_gb": 23.9, "ram_gb": 16}, 500, 10)["selo"] == "nao_roda"
    assert maquina.avaliar(req, placa16, 5, 10)["sem_espaco"]
    assert maquina.avaliar(req, None, 500, 10)["selo"] == "sem_perfil"
    assert maquina.avaliar(req, {"so_nuvem": True}, 500, 10)["selo"] == "nuvem"


def teste_todo_pacote_tem_requisitos():
    for p in pacotes.carregar():
        r = p["requisitos"]
        assert 0 < r["vram_min"] <= r["vram_rec"], p["id"]


def test_amd_nao_ganha_runs_well():
    # Pacotes testados so em NVIDIA: numa AMD o selo e "nao_testado", nunca "bem".
    import maquina
    req = {"vram_min": 8, "vram_rec": 12}
    amd = maquina.avaliar(req, {"gpu": "AMD Radeon RX 7900 XTX", "vram_gb": 24, "ram_gb": 64}, None, 0)
    nv = maquina.avaliar(req, {"gpu": "NVIDIA GeForce RTX 4090", "vram_gb": 24, "ram_gb": 64}, None, 0)
    assert amd["selo"] == "nao_testado" and nv["selo"] == "bem"
