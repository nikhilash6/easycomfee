"""Montagem dos grafos em formato API do ComfyUI.

Cada funcao devolve um dicionario {id_do_no: {class_type, inputs}} pronto para
POST em /prompt. A fiacao reproduz os templates oficiais do ComfyUI.
"""

from presets import (AMPLIAR, ANGULO, CONTROLE, EDICAO, IDEOGRAM, LLM, MASCARA, TRELLIS,
                     NUVEM, PERSONAGEM, RELUZ, ROSTO, SIMPLE,
                     VIDEO_AMPLIAR_LTX, VIDEO_LIMPAR, VIDEO_LTX,
                     VIDEO_FASTH3, VIDEO_MINIMAX_NUVEM,
                     VIDEO_MINIMAX_REF_NUVEM, VIDEO_WAN3,
                     controles_do_rosto, quadros_minimax, win)


def _texto(grafo, nid, clip_id, texto):
    # clip_id: o id do no (saida 0) ou ja a ligacao [no, saida].
    clip = clip_id if isinstance(clip_id, list) else [clip_id, 0]
    grafo[nid] = {"class_type": "CLIPTextEncode",
                  "inputs": {"clip": clip, "text": texto}}


def gerar_simples(modelo, prompt, negativo, seed, largura, altura,
                  steps=None, cfg=None, prefixo="saida", lote=1,
                  referencias=None, forca_referencia=1.0, posicoes=None):
    """Pipeline padrao: Krea 2, Flux 2 Klein, Z-Image ou Mage."""
    p = SIMPLE[modelo]
    if "escala" in p:
        largura, altura = (max(256, round(v * p["escala"] / 8) * 8) for v in (largura, altura))
    if "checkpoint" in p:
        # Checkpoint unico (SDXL, SD 1.5, FLUX.1 schnell, SD 3.5): o mesmo no
        # entrega modelo (0), texto (1) e VAE (2).
        g = {"unet": {"class_type": "CheckpointLoaderSimple",
                      "inputs": {"ckpt_name": win(p["checkpoint"])}},
             "latente": {"class_type": p["latent"],
                         "inputs": {"width": largura, "height": altura, "batch_size": lote}}}
        _texto(g, "pos", ["unet", 1], prompt)
        if p["zero_negative"] and not negativo:
            g["neg"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["pos", 0]}}
        else:
            _texto(g, "neg", ["unet", 1], negativo or "")
        g["amostra"] = {"class_type": "KSampler",
                        "inputs": {"model": ["unet", 0], "positive": ["pos", 0],
                                   "negative": ["neg", 0], "latent_image": ["latente", 0],
                                   "seed": seed, "steps": steps or p["steps"],
                                   "cfg": cfg if cfg is not None else p["cfg"],
                                   "sampler_name": p["sampler"],
                                   "scheduler": p["scheduler"], "denoise": 1.0}}
        g["decodifica"] = {"class_type": "VAEDecode",
                           "inputs": {"samples": ["amostra", 0], "vae": ["unet", 2]}}
        g["salva"] = {"class_type": "SaveImage",
                      "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}}
        if referencias:
            raise ValueError("Este gerador não aceita referência de personagem.")
        return g
    if p.get("familia") == "flux2":
        return _gerar_flux2(p, prompt, seed, largura, altura, steps, prefixo, lote)
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        "latente": {"class_type": p["latent"],
                    "inputs": {"width": largura, "height": altura, "batch_size": lote}},
    }
    if "clips" in p:
        # 2, 3 ou 4 codificadores de texto (FLUX.1, Kandinsky, HiDream).
        cl = p["clips"]
        no = {2: "DualCLIPLoader", 3: "TripleCLIPLoader", 4: "QuadrupleCLIPLoader"}[len(cl)]
        entradas = {f"clip_name{i + 1}": win(c) for i, c in enumerate(cl)}
        if len(cl) == 2:
            entradas.update(type=p["clip_type"], device="default")
        g["clip"] = {"class_type": no, "inputs": entradas}
    else:
        g["clip"] = {"class_type": "CLIPLoader",
                     "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                                "device": "default"}}
    if p.get("t5_opcoes"):
        # Chroma: o template zera o preenchimento do T5.
        g["clip_t5"] = {"class_type": "T5TokenizerOptions", "inputs": {"clip": ["clip", 0], "min_padding": 0, "min_length": 0}}
    if "shift" in p or "shift_aura" in p:
        no = "ModelSamplingSD3" if "shift" in p else "ModelSamplingAuraFlow"
        g["unet_base"] = g.pop("unet")
        g["unet"] = {"class_type": no, "inputs": {"model": ["unet_base", 0], "shift": p.get("shift", p.get("shift_aura"))}}
    if not negativo and p.get("negativo_padrao"):
        negativo = p["negativo_padrao"]
    if p.get("encoder") == "qwen21":
        # O Qwen 2.1 nao passa por CLIPTextEncode: um no proprio devolve o
        # positivo E o negativo de uma vez. Ele tambem devolve um LATENTE, que
        # aqui NAO e usado — e o da referencia, para edicao. Na geracao o
        # latente vem do EmptyLatentImage, como no template oficial.
        g["cond"] = {"class_type": "TextEncodeQwenImage21",
                     "inputs": {"clip": ["clip", 0], "vae": ["vae", 0],
                                "prompt": prompt,
                                "negative_prompt": negativo or "",
                                "resolution": max(largura, altura)}}
        pos, neg = ["cond", 0], ["cond", 1]
    else:
        fonte = "clip_t5" if "clip_t5" in g else "clip"
        _texto(g, "pos", fonte, prompt)

        # Nos modelos turbo (CFG 1.0) o negativo oficial e um ConditioningZeroOut
        # sobre o positivo, nao um texto vazio codificado.
        if p["zero_negative"] and not negativo:
            g["neg"] = {"class_type": "ConditioningZeroOut",
                        "inputs": {"conditioning": ["pos", 0]}}
        else:
            _texto(g, "neg", fonte, negativo or "")
        pos, neg = ["pos", 0], ["neg", 0]

    g["amostra"] = {"class_type": "KSampler",
                    "inputs": {"model": ["unet", 0], "positive": pos,
                               "negative": neg, "latent_image": ["latente", 0],
                               "seed": seed,
                               "steps": steps or p["steps"],
                               "cfg": cfg if cfg is not None else p["cfg"],
                               "sampler_name": p["sampler"],
                               "scheduler": p["scheduler"], "denoise": 1.0}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["amostra", 0], "vae": ["vae", 0]}}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}}
    if referencias:
        if modelo not in ("krea", "kroma", "kroma_foto"):
            raise ValueError("Este gerador não aceita referência de personagem.")
        if not 1 <= len(referencias) <= 3:
            raise ValueError("Envie de uma a três referências de personagem.")
        _referencias_personagem(g, prompt, negativo, referencias, posicoes or [],
                                forca_referencia, seed, prefixo)
    return g


def _gerar_flux2(p, prompt, seed, largura, altura, steps, prefixo, lote):
    """FLUX.2 dev (template image_flux2_fp8, sem as referencias): guia 4,
    BasicGuider e o Flux2Scheduler, que calcula os sigmas pelo tamanho."""
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"], "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        "latente": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": largura, "height": altura, "batch_size": lote}},
    }
    _texto(g, "pos", "clip", prompt)
    g["guia_flux"] = {"class_type": "FluxGuidance", "inputs": {"conditioning": ["pos", 0], "guidance": p["guidance"]}}
    g["guia"] = {"class_type": "BasicGuider", "inputs": {"model": ["unet", 0], "conditioning": ["guia_flux", 0]}}
    g["sigmas"] = {"class_type": "Flux2Scheduler", "inputs": {"steps": steps or p["steps"], "width": largura, "height": altura}}
    g["amostrador"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": p["sampler"]}}
    g["ruido"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["amostra"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["ruido", 0], "guider": ["guia", 0],
        "sampler": ["amostrador", 0], "sigmas": ["sigmas", 0], "latent_image": ["latente", 0]}}
    g["decodifica"] = {"class_type": "VAEDecode", "inputs": {"samples": ["amostra", 0], "vae": ["vae", 0]}}
    g["salva"] = {"class_type": "SaveImage", "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}}
    return g


# Posicoes na cena, em ingles (o idioma em que o LoRA foi treinado).
POSICOES = {"esquerda": "on the left side", "centro": "in the center",
            "direita": "on the right side"}


def _referencias_personagem(g, prompt, negativo, referencias, posicoes, forca, seed, prefixo):
    """Identity Edit v1.2: imagem no encoder E nos tokens do modelo. A tela
    nasce vazia para poder mudar pose e cenario; nao e img2img.

    Com 2-3 personagens, ENCADEIA passadas no mesmo grafo: o no aceita so
    cena + 1 pessoa por vez (scene -> source_latent/image, pessoa -> *_b, a
    ordem do treino), e o autor recomenda encadear para rostos diferentes.
    Teste de 22/10/2026 (scripts/testes_kroma/multi_personagem.py): tres
    personagens ficticios numa livraria, cada um fiel a referencia e os
    anteriores preservados; ~1,5 min no Kroma. A etapa 1 e identica ao fluxo
    de uma referencia, que segue igual quando so ha uma."""
    g["clip"]["inputs"]["clip_name"] = win("Qwen/qwen3vl_4b_bf16.safetensors")
    g["ref_lora"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["unet", 0],
        "lora_name": win("Krea/krea2_identity_edit_v1_2_r64.safetensors"),
        "strength_model": 1.0}}
    onde = lambda i: POSICOES.get(posicoes[i] if i < len(posicoes) else "", "")
    cena = None
    for i, ref in enumerate(referencias):
        k = "" if i == 0 else f"_{i + 1}"
        g["referencia" + k] = {"class_type": "LoadImage", "inputs": {"image": ref}}
        g["ref_escala" + k] = {"class_type": "ImageScaleToTotalPixels", "inputs": {
            "image": ["referencia" + k, 0], "upscale_method": "lanczos",
            "megapixels": 1.0, "resolution_steps": 1}}
        g["ref_latente" + k] = {"class_type": "VAEEncode", "inputs": {
            "pixels": ["ref_escala" + k, 0], "vae": ["vae", 0]}}
        if cena is None:
            patch = {"source_latent": ["ref_latente", 0], "source_image": ["ref_escala", 0]}
            imagens = {"image": ["ref_escala", 0]}
            instrucao = ("Create a new scene with the same character as the reference image. "
                         "Preserve the character's identity, face, hair, distinctive markings "
                         "and outfit unless explicitly requested otherwise. Change the pose, "
                         "action and background to match this scene: " + prompt)
            if onde(0):
                instrucao += f" The character stands {onde(0)}."
            if len(referencias) > 1:
                # O prompt descreve a cena INTEIRA ("os tres amigos"), mas nesta
                # passada so ha uma pessoa: sem isto o modelo inventava os
                # outros, e as passadas seguintes somavam mais gente (22/10).
                instrucao += (" For now, show only this one character and no other people; "
                              "leave room for the others.")
        else:
            g["cena_latente" + k] = {"class_type": "VAEEncode", "inputs": {
                "pixels": [cena, 0], "vae": ["vae", 0]}}
            patch = {"source_latent": ["cena_latente" + k, 0], "source_image": [cena, 0],
                     "source_latent_b": ["ref_latente" + k, 0]}
            imagens = {"image": [cena, 0], "image_b": ["ref_escala" + k, 0]}
            instrucao = ("Add the person from the second image to this scene"
                         + (f", {onde(i)}" if onde(i) else "")
                         + ", preserving their identity, face, hair and outfit. Keep the "
                         "people already in the scene and the rest of the scene unchanged.")
        g["ref_modelo" + k] = {"class_type": "Krea2EditModelPatch", "inputs": {
            "model": ["ref_lora", 0], "vae": ["vae", 0], **patch,
            "fit_mode": "fit", "ref_boost": forca, "ref_boost_a": 1.0}}
        for nid, texto in (("pos" + k, instrucao), ("neg" + k, negativo or "")):
            g[nid] = {"class_type": "Krea2EditGroundedEncode", "inputs": {
                "clip": ["clip", 0], **imagens,
                "prompt": texto, "grounding_px": 768, "system_prompt": ""}}
        amostra = "amostra" + k
        if i:
            g[amostra] = {**g["amostra"], "inputs": dict(g["amostra"]["inputs"])}
            g[amostra]["inputs"]["seed"] = seed + i
            g["decodifica" + k] = {"class_type": "VAEDecode", "inputs": {
                "samples": [amostra, 0], "vae": ["vae", 0]}}
        g[amostra]["inputs"].update(model=["ref_modelo" + k, 0],
                                    positive=["pos" + k, 0], negative=["neg" + k, 0])
        cena = "decodifica" + k
    # So a imagem final vai para a galeria; as etapas saem como previa.
    if len(referencias) > 1:
        g["salva"]["inputs"]["images"] = [cena, 0]
        for i in range(len(referencias) - 1):
            k = "" if i == 0 else f"_{i + 1}"
            g["etapa" + (k or "_1")] = {"class_type": "PreviewImage",
                                        "inputs": {"images": ["decodifica" + k, 0]}}


def gerar_ideogram(caption_json, seed, largura, altura, qualidade="padrao",
                   prefixo="saida", lote=1, fundo=None, tinta=None,
                   tintas_extra=None):
    """Pipeline do Ideogram 4.

    Dois UNETs combinados por DualModelGuider, agendador proprio e prompt em
    JSON. `caption_json` deve ser o objeto JSON minificado, ja pronto.

    Com `fundo` (nome de uma imagem enviada), a peca e escrita sobre preto
    chapado e COMPOSTA sobre a foto: ver `_compor_sobre_fundo`.
    """
    p = IDEOGRAM
    steps, mu, std = p["qualidades"][qualidade]
    g = {
        "unet_cond": {"class_type": "UNETLoader",
                      "inputs": {"unet_name": win(p["unet_cond"]),
                                 "weight_dtype": "default"}},
        "unet_uncond": {"class_type": "UNETLoader",
                        "inputs": {"unet_name": win(p["unet_uncond"]),
                                   "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        # O CFG so entra nos ultimos 30% dos passos.
        "cfg_override": {"class_type": "CFGOverride",
                         "inputs": {"model": ["unet_cond", 0], "cfg": p["override_cfg"],
                                    "start_percent": p["override_start"],
                                    "end_percent": p["override_end"]}},
        "latente": {"class_type": "EmptyFlux2LatentImage",
                    "inputs": {"width": largura, "height": altura, "batch_size": lote}},
        "ruido": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "sigmas": {"class_type": "Ideogram4Scheduler",
                   "inputs": {"steps": steps, "width": largura, "height": altura,
                              "mu": mu, "std": std}},
    }
    _texto(g, "pos", "clip", caption_json)
    g["neg"] = {"class_type": "ConditioningZeroOut",
                "inputs": {"conditioning": ["pos", 0]}}
    g["guia"] = {"class_type": "DualModelGuider",
                 "inputs": {"model": ["cfg_override", 0], "positive": ["pos", 0],
                            "model_negative": ["unet_uncond", 0],
                            "negative": ["neg", 0], "cfg": p["guider_cfg"]}}
    g["amostra"] = {"class_type": "SamplerCustomAdvanced",
                    "inputs": {"noise": ["ruido", 0], "guider": ["guia", 0],
                               "sampler": ["sampler", 0], "sigmas": ["sigmas", 0],
                               "latent_image": ["latente", 0]}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["amostra", 0], "vae": ["vae", 0]}}
    saida = "decodifica"
    if fundo:
        saida = _compor_sobre_fundo(g, fundo, tinta, largura, altura,
                                    tintas_extra)
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": [saida, 0], "filename_prefix": prefixo}}
    return g


def _compor_sobre_fundo(g, fundo, tinta, largura, altura,
                        tintas_extra=None):
    """Recorta as letras da peca e as aplica sobre a foto enviada.

    A foto NAO passa pelo modelo: entra so aqui, na composicao. Fora das
    letras ela fica identica — medimos 0.00/255 de diferenca media.

    O corte de preto age apenas no ramo da mascara. A fonte da composicao e
    uma chapa de tinta, nao a peca crua, porque os pixels de borda da peca ja
    vem misturados com o preto do fundo e levariam uma franja escura junto.
    """
    p = IDEOGRAM["fundo"]
    g["foto"] = {"class_type": "LoadImage", "inputs": {"image": fundo}}
    g["foto_esc"] = {"class_type": "ImageScale",
                     "inputs": {"image": ["foto", 0], "width": largura,
                                "height": altura, "upscale_method": "lanczos",
                                "crop": "center"}}
    g["niveis"] = {"class_type": "JWImageLevels",
                   "inputs": {"image": ["decodifica", 0],
                              "min": p["corte_preto"], "max": p["branco"]}}
    g["mascara"] = {"class_type": "ImageToMask",
                    "inputs": {"image": ["niveis", 0], "channel": "red"}}
    g["tinta"] = {"class_type": "LayerUtility: ColorImage",
                  "inputs": {"width": largura, "height": altura,
                             "color": tinta or p["tinta_padrao"]}}
    g["composto"] = {"class_type": "ImageCompositeMasked",
                     "inputs": {"destination": ["foto_esc", 0],
                                "source": ["tinta", 0], "x": 0, "y": 0,
                                "resize_source": False,
                                "mask": ["mascara", 0]}}
    return _tintas_de_bloco(g, "composto", tintas_extra or [], largura, altura)


def _tintas_de_bloco(g, base, tintas, largura, altura):
    """Repinta blocos de texto que sumiriam na cor da peca.

    Uma cor so nao serve a toda foto: no ensaio de costas o titulo cai sobre
    cabelo escuro, a chamada sobre camiseta branca e o rodape sobre calca
    escura. Aqui cada bloco que precisa e recomposto com a sua propria cor, por
    cima da composicao ja pronta — o que fica fora dos blocos mantem a cor
    escolhida pelo usuario.
    """
    anterior = base
    for i, t in enumerate(tintas):
        y1, x1, y2, x2 = t["bbox"]
        x = max(0, round(x1 / 1000 * largura))
        y = max(0, round(y1 / 1000 * altura))
        larg = max(1, min(largura - x, round((x2 - x1) / 1000 * largura)))
        alt = max(1, min(altura - y, round((y2 - y1) / 1000 * altura)))
        # O recorte sai da imagem JA nivelada: a mascara do bloco tem de ter o
        # mesmo corte de preto do resto, senao a borda da letra muda de peso
        # so nesse bloco.
        g[f"rec{i}"] = {"class_type": "ImageCrop",
                        "inputs": {"image": ["niveis", 0], "width": larg,
                                   "height": alt, "x": x, "y": y}}
        g[f"msk{i}"] = {"class_type": "ImageToMask",
                        "inputs": {"image": [f"rec{i}", 0], "channel": "red"}}
        g[f"cor{i}"] = {"class_type": "LayerUtility: ColorImage",
                        "inputs": {"width": larg, "height": alt,
                                   "color": t["cor"]}}
        g[f"blo{i}"] = {"class_type": "ImageCompositeMasked",
                        "inputs": {"destination": [anterior, 0],
                                   "source": [f"cor{i}", 0], "x": x, "y": y,
                                   "resize_source": False,
                                   "mask": [f"msk{i}", 0]}}
        anterior = f"blo{i}"
    return anterior


def _aplicar_mascara(g, chave_base, chave_editada, mascara, prefixo):
    """Faz o resultado editado valer so dentro da regiao marcada.

    O SAM 3 acha a regiao a partir de uma descricao em texto ("o homem de
    jaqueta", "o ceu"). O que fica fora da mascara e copiado do original sem
    passar pelo modelo, entao nao muda nem um pixel.

    `mascara` traz: alvo (texto), limiar, expandir e suavizar em pixels.
    """
    p = MASCARA
    g["sam"] = {"class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": win(p["checkpoint"])}}
    g["sam_txt"] = {"class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["sam", 1], "text": mascara["alvo"]}}
    g["sam_det"] = {"class_type": "SAM3_Detect",
                    "inputs": {"model": ["sam", 0], "image": [chave_base, 0],
                               "conditioning": ["sam_txt", 0],
                               "threshold": mascara.get("limiar", 0.5),
                               "refine_iterations": 2, "individual_masks": False}}
    # Expandir evita halo na borda do objeto; suavizar evita emenda dura.
    g["sam_cresce"] = {"class_type": "GrowMask",
                       "inputs": {"mask": ["sam_det", 0],
                                  "expand": mascara.get("expandir", 12),
                                  "tapered_corners": True}}
    suave = mascara.get("suavizar", 12)
    g["sam_suave"] = {"class_type": "FeatherMask",
                      "inputs": {"mask": ["sam_cresce", 0], "left": suave,
                                 "top": suave, "right": suave, "bottom": suave}}
    g["composto"] = {"class_type": "ImageCompositeMasked",
                     "inputs": {"destination": [chave_base, 0],
                                "source": [chave_editada, 0],
                                "x": 0, "y": 0, "resize_source": True,
                                "mask": ["sam_suave", 0]}}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["composto", 0], "filename_prefix": prefixo}}
    return g


def editar_klein(instrucao, referencias, seed, megapixels=1.0, steps=20, cfg=5.0,
                 prefixo="edicao", mascara=None, negativo=""):
    """Edicao por referencia com o Flux 2 Klein 9B.

    A primeira imagem e a base: e dela que saem as dimensoes da saida. As
    demais entram como referencias adicionais. Cada referencia vira um
    ReferenceLatent encadeado no condicionamento, positivo e negativo.

    E o modo bom para trocar quem esta na cena mantendo o resto.
    """
    p = EDICAO["trocar"]
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
    }
    for i, nome in enumerate(referencias):
        g[f"img{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        g[f"esc{i}"] = {"class_type": "ImageScaleToTotalPixels",
                        "inputs": {"image": [f"img{i}", 0], "upscale_method": "lanczos",
                                   "megapixels": megapixels, "resolution_steps": 1}}
        g[f"enc{i}"] = {"class_type": "VAEEncode",
                        "inputs": {"pixels": [f"esc{i}", 0], "vae": ["vae", 0]}}

    g["tam"] = {"class_type": "GetImageSize", "inputs": {"image": ["esc0", 0]}}
    _texto(g, "pos", "clip", instrucao)
    # O negativo e o freio do artefato; montado em presets.negativo_do_tipo.
    _texto(g, "neg", "clip", negativo or "")

    # Encadeia uma referencia por vez sobre os dois condicionamentos.
    atual_pos, atual_neg = "pos", "neg"
    for i in range(len(referencias)):
        g[f"refp{i}"] = {"class_type": "ReferenceLatent",
                         "inputs": {"conditioning": [atual_pos, 0],
                                    "latent": [f"enc{i}", 0]}}
        g[f"refn{i}"] = {"class_type": "ReferenceLatent",
                         "inputs": {"conditioning": [atual_neg, 0],
                                    "latent": [f"enc{i}", 0]}}
        atual_pos, atual_neg = f"refp{i}", f"refn{i}"

    g.update({
        "guia": {"class_type": "CFGGuider",
                 "inputs": {"model": ["unet", 0], "positive": [atual_pos, 0],
                            "negative": [atual_neg, 0], "cfg": cfg}},
        "sig": {"class_type": "Flux2Scheduler",
                "inputs": {"steps": steps, "width": ["tam", 0], "height": ["tam", 1]}},
        "lat": {"class_type": "EmptyFlux2LatentImage",
                "inputs": {"width": ["tam", 0], "height": ["tam", 1], "batch_size": 1}},
        "ruido": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "samp": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "run": {"class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["ruido", 0], "guider": ["guia", 0],
                           "sampler": ["samp", 0], "sigmas": ["sig", 0],
                           "latent_image": ["lat", 0]}},
        "decodifica": {"class_type": "VAEDecode",
                       "inputs": {"samples": ["run", 0], "vae": ["vae", 0]}},
        "salva": {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}},
    })
    if mascara and mascara.get("alvo"):
        _aplicar_mascara(g, "esc0", "decodifica", mascara, prefixo)
    return g


def editar_mage(instrucao, referencias, seed, megapixels=1.0, steps=30, cfg=5.0,
                prefixo="edicao", mascara=None):
    """Edicao por instrucao com o Mage Flow Edit.

    Um unico no recebe ate tres imagens. As entradas dele crescem sob demanda,
    entao as chaves vao prefixadas: "images.image_1" e nao "image_1".

    E o modo bom para mudar um atributo sem mexer no resto.
    """
    p = EDICAO["instrucao"]
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        "img0": {"class_type": "LoadImage", "inputs": {"image": referencias[0]}},
        "esc0": {"class_type": "ImageScaleToTotalPixels",
                 "inputs": {"image": ["img0", 0], "upscale_method": "lanczos",
                            "megapixels": megapixels, "resolution_steps": 16}},
    }
    g["tam"] = {"class_type": "GetImageSize", "inputs": {"image": ["esc0", 0]}}

    imagens = {"images.image_1": ["esc0", 0]}
    for i, nome in enumerate(referencias[1:p["max_referencias"]], start=2):
        g[f"img{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        imagens[f"images.image_{i}"] = [f"img{i}", 0]

    g["cond"] = {"class_type": "TextEncodeMageFlowEdit",
                 "inputs": {"clip": ["clip", 0], "vae": ["vae", 0],
                            "prompt": instrucao, "negative_prompt": "",
                            "width": ["tam", 0], "height": ["tam", 1],
                            "batch_size": 1, **imagens}}
    g["run"] = {"class_type": "KSampler",
                "inputs": {"model": ["unet", 0], "positive": ["cond", 0],
                           "negative": ["cond", 1], "latent_image": ["cond", 2],
                           "seed": seed, "steps": steps, "cfg": cfg,
                           "sampler_name": "euler", "scheduler": "simple",
                           "denoise": 1.0}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["run", 0], "vae": ["vae", 0]}}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}}
    if mascara and mascara.get("alvo"):
        _aplicar_mascara(g, "esc0", "decodifica", mascara, prefixo)
    return g


def _trellis_render(g, foto, giro, altura_cam, largura, altura):
    """Acrescenta ao grafo a malha 3D da foto (TRELLIS 2) girada e renderizada.

    Os nos da malha nao dependem do angulo: entre uma previa e outra o ComfyUI
    reaproveita do cache e so o giro e o render rodam de novo (segundos).
    O giro e o da camera em volta da pessoa: positivo = camera para a direita,
    entao a malha gira para o outro lado (angle_y = -giro). Devolve a chave do render.
    """
    p = TRELLIS
    g |= {
        "t_img": {"class_type": "LoadImage", "inputs": {"image": foto}},
        "t_bgm": {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": p["recorte"]}},
        "t_mask": {"class_type": "RemoveBackground", "inputs": {"bg_removal_model": ["t_bgm", 0], "image": ["t_img", 0]}},
        "t_crop": {"class_type": "ImageCropToMask", "inputs": {"images": ["t_img", 0], "masks": ["t_mask", 0],
                   "width": 1024, "height": 1024, "pad_factor": 1.1, "grow_mask": 0, "background": "#000000"}},
        "t_dino": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": p["dino"]}},
        "t_cond": {"class_type": "Trellis2Conditioning", "inputs": {"clip_vision_model": ["t_dino", 0], "image": ["t_crop", 0]}},
        "t_unet": {"class_type": "UNETLoader", "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "t_ms": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["t_unet", 0], "shift": 5.0}},
        "t_vaes": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_forma"])}},
        "t_vaet": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_textura"])}},
        "t_lat": {"class_type": "EmptyTrellis2LatentStructure", "inputs": {"batch_size": 1}},
        "t_ks1": {"class_type": "KSampler", "inputs": {"model": ["t_ms", 0], "positive": ["t_cond", 0], "negative": ["t_cond", 1],
                  "latent_image": ["t_lat", 0], "seed": 42, "steps": 12, "cfg": 7.5, "sampler_name": "euler",
                  "scheduler": "simple", "denoise": 1.0}},
        "t_vox": {"class_type": "VaeDecodeStructureTrellis2", "inputs": {"samples": ["t_ks1", 0], "vae": ["t_vaes", 0], "resolution": "32"}},
        "t_shp": {"class_type": "Trellis2ShapeStage", "inputs": {"positive": ["t_cond", 0], "negative": ["t_cond", 1], "voxel": ["t_vox", 0]}},
        "t_rs2": {"class_type": "RescaleCFG", "inputs": {"model": ["t_ms", 0], "multiplier": 0.7}},
        "t_ks2": {"class_type": "KSampler", "inputs": {"model": ["t_rs2", 0], "positive": ["t_shp", 0], "negative": ["t_shp", 1],
                  "latent_image": ["t_shp", 2], "seed": 56, "steps": 12, "cfg": 7.5, "sampler_name": "euler",
                  "scheduler": "normal", "denoise": 1.0}},
        "t_dec": {"class_type": "VaeDecodeShapeTrellis", "inputs": {"samples": ["t_ks2", 0], "vae": ["t_vaes", 0]}},
        "t_tex": {"class_type": "Trellis2TextureStage", "inputs": {"positive": ["t_cond", 0], "negative": ["t_cond", 1], "shape_latent": ["t_ks2", 0]}},
        "t_rs3": {"class_type": "RescaleCFG", "inputs": {"model": ["t_ms", 0], "multiplier": 0.5}},
        "t_ks3": {"class_type": "KSampler", "inputs": {"model": ["t_rs3", 0], "positive": ["t_tex", 0], "negative": ["t_tex", 1],
                  "latent_image": ["t_tex", 2], "seed": 42, "steps": 20, "cfg": 7.5, "sampler_name": "euler",
                  "scheduler": "normal", "denoise": 1.0}},
        "t_vt": {"class_type": "VaeDecodeTextureTrellis", "inputs": {"samples": ["t_ks3", 0], "vae": ["t_vaet", 0], "shape_subdivides": ["t_dec", 1]}},
        "t_paint": {"class_type": "PaintMesh", "inputs": {"mesh": ["t_dec", 0], "voxel_colors": ["t_vt", 0]}},
        # Primeiro o giro (em torno do eixo vertical), depois a altura da camera em
        # torno do eixo horizontal da TELA: num no so (euler x,y,z) a inclinacao vinha
        # antes do giro e o corpo "deitava" de lado em vez de ser visto de cima.
        "t_giro": {"class_type": "RotateMesh", "inputs": {"mesh": ["t_paint", 0], "mode": "euler_xyz",
                   "mode.angle_x": 0.0, "mode.angle_y": float(-giro), "mode.angle_z": 0.0}},
        "t_rot": {"class_type": "RotateMesh", "inputs": {"mesh": ["t_giro", 0], "mode": "euler_xyz",
                  "mode.angle_x": float(altura_cam), "mode.angle_y": 0.0, "mode.angle_z": 0.0}},
        "t_ren": {"class_type": "RenderMesh", "inputs": {"mesh": ["t_rot", 0], "mode": "auto", "width": largura,
                  "height": altura, "background": "#000000"}},
    }
    return "t_ren"


def frase_direcao_3d(giro, altura_cam=0.0):
    """A pose do render em palavras. Giro positivo = camera a direita = pessoa
    olhando para a esquerda da imagem (conferido no render do TRELLIS)."""
    g = abs(giro)
    lado = "left" if giro > 0 else "right"
    if g < 10:
        pose = "The person faces the camera as in @image2."
    elif g < 35:
        pose = f"The person is turned slightly, facing a little toward the {lado} side of the picture, exactly like the 3D figure in @image1."
    elif g < 70:
        pose = f"The person is turned three-quarters, facing toward the {lado} side of the picture, exactly like the 3D figure in @image1."
    elif g < 115:
        pose = f"The person is seen from the side, in profile, facing toward the {lado} side of the picture, exactly like the 3D figure in @image1. Do not turn them toward the camera."
    elif g < 160:
        pose = f"The person is seen from behind and to the side, mostly their back, facing away toward the {lado} side of the picture, exactly like the 3D figure in @image1."
    else:
        pose = "The person is seen from behind: we see their back, not their face, exactly like the 3D figure in @image1."
    if altura_cam >= 20:
        pose += " The camera is high, looking down at them."
    elif altura_cam <= -20:
        pose += " The camera is low, looking up at them."
    return pose


def orbita_3d(foto, giro, altura_cam, largura, altura, seed, previa=False, extra="", prefixo="editor/orbita3d"):
    """Orbit 3D. previa: so o render da malha no angulo (o que a tela mostra).
    Final: o Qwen Image Edit refaz o render (@image1) como foto, com a original
    (@image2) dando rosto, roupa, lugar e luz."""
    if previa:
        g = {}
        chave = _trellis_render(g, foto, giro, altura_cam, largura, altura)
        g["salva"] = {"class_type": "SaveImage", "inputs": {"images": [chave, 0], "filename_prefix": prefixo + "_previa"}}
        return g
    # A direcao do corpo vai escrita tambem: so com a imagem, num quadro largo o
    # Qwen tendia a virar a pessoa de volta para a camera (teste de 31/10/2026).
    # Giro negativo: o Qwen tende a virar a pessoa para DENTRO do quadro e ignorava
    # "facing right" com ela na borda direita (teste de 31/10/2026). Faz-se no espelho
    # (foto espelhada, giro positivo) e o resultado volta espelhado: mesmo cenario.
    espelho = giro < 0
    giro_ef = abs(giro) if espelho else giro
    instrucao = " ".join(x for x in (TRELLIS["instrucao"], frase_direcao_3d(giro_ef, altura_cam), extra.strip()) if x)
    g = editar_qwen(instrucao, ["__render__", foto], seed, prefixo=prefixo)
    chave = _trellis_render(g, foto, giro_ef, altura_cam, largura, altura)
    del g["img0"]
    g["esc0"]["inputs"]["image"] = [chave, 0]
    if espelho:
        g["t_esp"] = {"class_type": "ImageFlip", "inputs": {"image": ["t_img", 0], "flip_method": "y-axis: horizontally"}}
        for no in ("t_mask", "t_crop"):  # a malha sai da foto espelhada
            for k, v in g[no]["inputs"].items():
                if v == ["t_img", 0]:
                    g[no]["inputs"][k] = ["t_esp", 0]
        g["esc1"]["inputs"]["image"] = ["t_esp", 0]   # a referencia de rosto e lugar tambem
        g["volta"] = {"class_type": "ImageFlip", "inputs": {"image": ["decodifica", 0], "flip_method": "y-axis: horizontally"}}
        g["salva"]["inputs"]["images"] = ["volta", 0]
    return g


def editar_qwen(instrucao, referencias, seed, megapixels=1.5, steps=None,
                cfg=None, prefixo="qwen", mascara=None, lora=None, forca_lora=1.0):
    """Edicao por instrucao com o Qwen Image Edit 2511.

    Diferente dos outros modos, as imagens NAO entram por ReferenceLatent: o
    no TextEncodeQwenImageEditPlus recebe as tres direto e ja devolve o
    condicionamento. O negativo e o mesmo no com o texto vazio — e o que o
    template oficial faz, e trocar por um CLIPTextEncode nao funciona, porque
    o condicionamento precisa carregar as imagens tambem.

    O latente vem da primeira imagem, entao a saida herda o enquadramento
    dela. `megapixels` controla o tamanho: mais pixels, mais tempo, quase em
    linha reta.
    """
    p = EDICAO["qwen"]
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
    }
    imagens = {}
    for i, nome in enumerate(referencias[:p["max_referencias"]]):
        g[f"img{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        g[f"esc{i}"] = {"class_type": "ImageScaleToTotalPixels",
                        "inputs": {"image": [f"img{i}", 0],
                                   "upscale_method": "lanczos",
                                   "megapixels": megapixels, "resolution_steps": 1}}
        imagens[f"image{i + 1}"] = [f"esc{i}", 0]

    g["lat"] = {"class_type": "VAEEncode",
                "inputs": {"pixels": ["esc0", 0], "vae": ["vae", 0]}}
    for chave, texto in (("pos", instrucao), ("neg", "")):
        g[chave] = {"class_type": "TextEncodeQwenImageEditPlus",
                    "inputs": {"clip": ["clip", 0], "prompt": texto,
                               "vae": ["vae", 0], **imagens}}
    # A LoRA entra entre o UNET e o resto da cadeia. As LoRAs de angulo e de
    # relight sao treinadas na 2509 e carregam sem erro na 2511 — testado.
    base = "unet"
    if lora:
        g["lora"] = {"class_type": "LoraLoaderModelOnly",
                     "inputs": {"model": ["unet", 0], "lora_name": win(lora),
                                "strength_model": forca_lora}}
        base = "lora"
    # O shift reposiciona a curva de ruido; 3.0 e o valor do template oficial.
    g["shift"] = {"class_type": "ModelSamplingAuraFlow",
                  "inputs": {"model": [base, 0], "shift": p["shift"]}}
    g["norm"] = {"class_type": "CFGNorm",
                 "inputs": {"model": ["shift", 0], "strength": 1.0}}
    g["run"] = {"class_type": "KSampler",
                "inputs": {"model": ["norm", 0], "positive": ["pos", 0],
                           "negative": ["neg", 0], "latent_image": ["lat", 0],
                           "seed": seed, "steps": steps or p["steps"],
                           "cfg": cfg if cfg is not None else p["cfg"],
                           "sampler_name": "euler", "scheduler": "simple",
                           "denoise": 1.0}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["run", 0], "vae": ["vae", 0]}}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}}
    if mascara and mascara.get("alvo"):
        _aplicar_mascara(g, "esc0", "decodifica", mascara, prefixo)
    return g


def gerar_folha_personagem(referencia, instrucao, seed, steps=None, cfg=None,
                           prefixo="folha"):
    """Folha de personagem em quatro vistas (Krea 2 + LoRA QuadView).

    Nao e geracao nem edicao no lugar: a foto vira o LATENTE DE ORIGEM de um
    remendo no modelo (Krea2EditModelPatch), e a amostragem acontece numa tela
    vazia deitada. Por isso ha duas resolucoes em jogo — a da foto ajustada
    (em pe) e a da folha (deitada) — e trocar uma pela outra nao da erro, da
    uma folha com o enquadramento errado.

    O negativo e um segundo Krea2EditGroundedEncode, como no template, e nao um
    ConditioningZeroOut. Em CFG 1.0 ele e ignorado e os dois dariam no mesmo,
    mas `cfg` e regulavel aqui: acima de 1 o negativo volta a pesar, e um
    zero-out silenciosamente nao seria a mesma coisa. Custa uma passada a mais
    no CLIP; colapsar isso quando cfg==1 e otimizacao possivel, nao feita.
    """
    p = EDICAO["folha"]
    larg_entrada, alt_entrada = p["entrada"]
    larg_saida, alt_saida = p["saida"]
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "lora": {"class_type": "LoraLoaderModelOnly",
                 "inputs": {"model": ["unet", 0], "lora_name": win(p["lora"]),
                            "strength_model": 1.0}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        "img": {"class_type": "LoadImage", "inputs": {"image": referencia}},
        # keep_proportion="resize" cabe a foto dentro da tela sem deformar; o
        # divisible_by=2 e o que o template usa. No "cpu" de proposito: a placa
        # ja esta com o modelo, e um lanczos de 1,5 MP nao justifica disputar.
        "ajusta": {"class_type": "ImageResizeKJv2",
                   "inputs": {"image": ["img", 0],
                              "width": larg_entrada, "height": alt_entrada,
                              "upscale_method": "lanczos",
                              "keep_proportion": "resize",
                              "pad_color": "0, 0, 0",
                              "crop_position": "center",
                              "divisible_by": 2, "device": "cpu"}},
        "lat_origem": {"class_type": "VAEEncode",
                       "inputs": {"pixels": ["ajusta", 0], "vae": ["vae", 0]}},
        # grounding_px=0 no positivo e 768 no negativo: e o que o template faz.
        "pos": {"class_type": "Krea2EditGroundedEncode",
                "inputs": {"clip": ["clip", 0], "prompt": instrucao,
                           "image": ["ajusta", 0], "grounding_px": 0,
                           "system_prompt": ""}},
        "neg": {"class_type": "Krea2EditGroundedEncode",
                "inputs": {"clip": ["clip", 0], "prompt": "",
                           "image": ["ajusta", 0], "grounding_px": 768,
                           "system_prompt": ""}},
        "remenda": {"class_type": "Krea2EditModelPatch",
                    "inputs": {"model": ["lora", 0],
                               "source_latent": ["lat_origem", 0],
                               "vae": ["vae", 0],
                               "source_image": ["ajusta", 0],
                               "ref_boost": 1.0, "ref_boost_a": 1.0,
                               "fit_mode": "fit"}},
        # A folha nasce VAZIA e deitada. O latente da foto nao entra aqui — ele
        # entrou pelo remendo acima.
        "latente": {"class_type": "EmptySD3LatentImage",
                    "inputs": {"width": larg_saida, "height": alt_saida,
                               "batch_size": 1}},
    }
    g["amostra"] = {"class_type": "KSampler",
                    "inputs": {"model": ["remenda", 0], "positive": ["pos", 0],
                               "negative": ["neg", 0],
                               "latent_image": ["latente", 0],
                               "seed": seed, "steps": steps or p["steps"],
                               "cfg": cfg if cfg is not None else p["cfg"],
                               "sampler_name": "euler", "scheduler": "simple",
                               "denoise": 1.0}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["amostra", 0], "vae": ["vae", 0]}}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}}
    return g


def trocar_cabeca(referencias, instrucao, seed, steps=None, prefixo="cabeca"):
    """BFS Head Swap V1.1: cena primeiro, cabeca de referencia depois.

    Reproduz o workflow simples do autor para Krea 2. As duas imagens entram
    tanto no condicionamento quanto no remendo do modelo; a tela de saida
    segue o tamanho da cena ajustada, nunca o da segunda referencia.
    """
    p = EDICAO["cabeca"]
    largura, altura = p["entrada"]
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "lora": {"class_type": "LoraLoaderModelOnly",
                 "inputs": {"model": ["unet", 0], "lora_name": win(p["lora"]),
                            "strength_model": 1.0}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
    }
    for i, nome in enumerate(referencias[:2]):
        g[f"img{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        g[f"ajusta{i}"] = {
            "class_type": "ImageResizeKJv2",
            "inputs": {"image": [f"img{i}", 0], "width": largura,
                       "height": altura, "upscale_method": "lanczos",
                       "keep_proportion": "resize", "pad_color": "0, 0, 0",
                       "crop_position": "center", "divisible_by": 2,
                       "device": "cpu"},
        }
        g[f"lat{i}"] = {"class_type": "VAEEncode",
                       "inputs": {"pixels": [f"ajusta{i}", 0],
                                  "vae": ["vae", 0]}}
    for nid, prompt, grounding in (("pos", instrucao, 512), ("neg", "", 768)):
        g[nid] = {"class_type": "Krea2EditGroundedEncode",
                  "inputs": {"clip": ["clip", 0], "prompt": prompt,
                             "image": ["ajusta0", 0],
                             "image_b": ["ajusta1", 0],
                             "grounding_px": grounding, "system_prompt": ""}}
    g["remenda"] = {"class_type": "Krea2EditModelPatch",
                    "inputs": {"model": ["lora", 0],
                               "source_latent": ["lat0", 0],
                               "source_latent_b": ["lat1", 0],
                               "vae": ["vae", 0],
                               "source_image": ["ajusta0", 0],
                               "source_image_b": ["ajusta1", 0],
                               "ref_boost": 1.0, "ref_boost_a": 1.0,
                               "fit_mode": "fit"}}
    g["tam"] = {"class_type": "GetImageSize",
                "inputs": {"image": ["ajusta0", 0]}}
    g["latente"] = {"class_type": "EmptySD3LatentImage",
                    "inputs": {"width": ["tam", 0], "height": ["tam", 1],
                               "batch_size": 1}}
    g["amostra"] = {"class_type": "KSampler",
                    "inputs": {"model": ["remenda", 0], "positive": ["pos", 0],
                               "negative": ["neg", 0],
                               "latent_image": ["latente", 0],
                               "seed": seed, "steps": steps or p["steps"],
                               "cfg": p["cfg"], "sampler_name": "euler",
                               "scheduler": "simple", "denoise": 1.0}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["amostra", 0],
                                  "vae": ["vae", 0]}}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0],
                             "filename_prefix": prefixo}}
    return g


def gerar_com_estilo(prompt, referencias, seed, largura, altura, steps=8,
                     forca=1.0, prefixo="estilo"):
    """Gera uma imagem nova imitando a estetica das referencias (Krea 2).

    Nao edita nada: as referencias entram so como estilo. Aceita ate tres.
    """
    p = EDICAO["estilo"]
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "lora": {"class_type": "LoraLoaderModelOnly",
                 "inputs": {"model": ["unet", 0], "lora_name": win(p["lora"]),
                            "strength_model": forca}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        "ms": {"class_type": "ModelSamplingFlux",
               "inputs": {"model": ["lora", 0], "max_shift": 1.15, "base_shift": 0.5,
                          "width": largura, "height": altura}},
        "lat": {"class_type": "EmptyLatentImage",
                "inputs": {"width": largura, "height": altura, "batch_size": 1}},
        "ruido": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "samp": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
    }
    entradas = {"clip": ["clip", 0], "prompt": prompt, "vae": ["vae", 0]}
    for i, nome in enumerate(referencias[:p["max_referencias"]], start=1):
        g[f"img{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        entradas[f"image{i}"] = [f"img{i}", 0]

    g.update({
        "cond": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": entradas},
        "multi": {"class_type": "FluxKontextMultiReferenceLatentMethod",
                  "inputs": {"conditioning": ["cond", 0],
                             "reference_latents_method": "index_timestep_zero"}},
        "zero": {"class_type": "ConditioningZeroOut",
                 "inputs": {"conditioning": ["multi", 0]}},
        "guia": {"class_type": "CFGGuider",
                 "inputs": {"model": ["ms", 0], "positive": ["multi", 0],
                            "negative": ["zero", 0], "cfg": 1.0}},
        "sig": {"class_type": "BasicScheduler",
                "inputs": {"model": ["ms", 0], "scheduler": "simple",
                           "steps": steps, "denoise": 1.0}},
        "run": {"class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["ruido", 0], "guider": ["guia", 0],
                           "sampler": ["samp", 0], "sigmas": ["sig", 0],
                           "latent_image": ["lat", 0]}},
        "decodifica": {"class_type": "VAEDecode",
                       "inputs": {"samples": ["run", 0], "vae": ["vae", 0]}},
        "salva": {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}},
    })
    return g


def instrucao_de_personagem(blocos_ligados, extra=""):
    """Monta a instrucao da troca de personagem a partir dos blocos ligados.

    A ordem importa: pose e cabeca primeiro (o que NAO pode mudar), identidade
    depois (o que deve vir da referencia), e por fim a integracao. Foi assim
    que o workflow original separou as coisas, e e o que evita a referencia
    trazer junto a pose e a roupa.
    """
    p = PERSONAGEM
    partes = ["Replace the person in Figure 1 with the person from Figure 2, "
              "naturally and seamlessly."]
    for chave, bloco in p["blocos"].items():
        if blocos_ligados.get(chave, bloco["padrao"]):
            partes.append(bloco["texto"])
    if extra.strip():
        partes.append(extra.strip())
    return " ".join(partes)


def trocar_personagem(instrucao, referencias, seed, unet, steps, cfg,
                      megapixels=1.0, prefixo="personagem", negativo=""):
    """Troca de personagem em tres imagens (protocolo do Flux 2 Banana).

    Mesma espinha do editar_klein — uma cadeia de ReferenceLatent — mas com o
    modelo, os passos e o CFG vindos de fora, porque este modo roda tanto no
    Klein destilado (4 passos, CFG 1) quanto no base (20 passos, CFG 5).
    """
    p = PERSONAGEM
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(unet), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
    }
    for i, nome in enumerate(referencias):
        g[f"img{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        g[f"esc{i}"] = {"class_type": "ImageScaleToTotalPixels",
                        "inputs": {"image": [f"img{i}", 0], "upscale_method": "lanczos",
                                   "megapixels": megapixels, "resolution_steps": 1}}
        g[f"enc{i}"] = {"class_type": "VAEEncode",
                        "inputs": {"pixels": [f"esc{i}", 0], "vae": ["vae", 0]}}

    # A saida acompanha a Figura 1: e a cena que deve permanecer.
    g["tam"] = {"class_type": "GetImageSize", "inputs": {"image": ["esc0", 0]}}
    _texto(g, "pos", "clip", instrucao)
    _texto(g, "neg", "clip", negativo or "")

    atual_pos, atual_neg = "pos", "neg"
    for i in range(len(referencias)):
        g[f"refp{i}"] = {"class_type": "ReferenceLatent",
                         "inputs": {"conditioning": [atual_pos, 0],
                                    "latent": [f"enc{i}", 0]}}
        g[f"refn{i}"] = {"class_type": "ReferenceLatent",
                         "inputs": {"conditioning": [atual_neg, 0],
                                    "latent": [f"enc{i}", 0]}}
        atual_pos, atual_neg = f"refp{i}", f"refn{i}"

    g.update({
        "guia": {"class_type": "CFGGuider",
                 "inputs": {"model": ["unet", 0], "positive": [atual_pos, 0],
                            "negative": [atual_neg, 0], "cfg": cfg}},
        "sig": {"class_type": "Flux2Scheduler",
                "inputs": {"steps": steps, "width": ["tam", 0], "height": ["tam", 1]}},
        "lat": {"class_type": "EmptyFlux2LatentImage",
                "inputs": {"width": ["tam", 0], "height": ["tam", 1], "batch_size": 1}},
        "ruido": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "samp": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": p["sampler"]}},
        "run": {"class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["ruido", 0], "guider": ["guia", 0],
                           "sampler": ["samp", 0], "sigmas": ["sig", 0],
                           "latent_image": ["lat", 0]}},
        "decodifica": {"class_type": "VAEDecode",
                       "inputs": {"samples": ["run", 0], "vae": ["vae", 0]}},
        "salva": {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}},
    })
    return g


def instrucao_de_camera96(direcao, altura, distancia, extra=""):
    """Frase da LoRA de 96 poses do Qwen Image Edit 2511, exatamente no formato do
    treino: "<sks> front-right quarter view eye-level shot medium shot". O texto do
    usuario entra depois, como complemento (igual ao "camera")."""
    a = ANGULO
    if direcao not in a["direcoes_96"] or altura not in a["alturas_96"] or distancia not in a["distancias_96"]:
        raise ValueError("posicao de camera desconhecida")
    frase = f"<sks> {direcao} {altura} {distancia}"
    return f"{frase} {extra.strip()}" if extra.strip() else frase


def instrucao_de_angulo(vista, extra="", metodo="personagem"):
    """Monta a instrucao de mudanca de ponto de vista.

    Sao duas operacoes diferentes, nao duas redacoes da mesma. "personagem"
    gira o CORPO e mantem o enquadramento; "camera" move o ponto de vista, e
    usa o vocabulario em que a LoRA foi treinada — ela so responde bem a ele.
    """
    v = ANGULO["vistas"][vista]
    if metodo == "camera":
        # A frase vai PURA. Medido: acrescentar a nossa clausula de preservacao
        # estrangula a LoRA — com ela o "aproximar" mal se mexe; sem ela sai um
        # close de verdade. Ela foi treinada nessas frases sozinhas, e pedir
        # "mantenha o mesmo enquadramento" briga com mover a camera.
        partes = [v["frase_camera"]]
        if extra.strip():
            partes.append(extra.strip())
        return " ".join(partes)

    partes = [v["frase"] + "."]
    if extra.strip():
        partes.append(extra.strip())
    partes.append(ANGULO["preservar"])
    return " ".join(partes)


def instrucao_de_luz(frase_da_luz, extra="", com_mapa=False, gatilho=""):
    """Monta a instrucao de reiluminacao a partir da posicao da luz.

    Quando o mapa vai junto, a instrucao PRECISA dizer o que ele e e que ele
    nao deve aparecer. Sem isso o Klein trata a segunda imagem como conteudo a
    compor e desenha a esfera dentro da cena — foi o que aconteceu no teste.
    """
    # O gatilho da LoRA vem ANTES de tudo e em chines — e assim que ela foi
    # treinada, e sem ele o efeito direcional nao aparece.
    if gatilho:
        partes = [gatilho + frase_da_luz]
    else:
        partes = ["Relight this image. " + frase_da_luz]
    if com_mapa:
        partes.append(
            "The second image is a lighting reference only: a plain grey sphere "
            "lit from the intended direction. Use it to understand where the "
            "light comes from. Do NOT draw the sphere, any circle, any glow or "
            "any part of that reference into the result."
        )
    if extra.strip():
        partes.append(extra.strip())
    partes.append(RELUZ["preservar"])
    return " ".join(partes)


def _mapa_de_controle(g, referencia, tipo):
    """Nos que transformam a imagem de referencia no mapa que guia a geracao.

    Devolve a chave do no que produz o mapa.
    """
    p = CONTROLE
    t = p["tipos"][tipo]
    g["img0"] = {"class_type": "LoadImage", "inputs": {"image": referencia}}
    g["esc0"] = {"class_type": "ImageScaleToMaxDimension",
                 "inputs": {"image": ["img0", 0], "upscale_method": "lanczos",
                            "largest_size": p["lado_maximo"]}}
    g["pre"] = {"class_type": t["no"],
                "inputs": {"image": ["esc0", 0], **t["inputs"]}}
    # Os pre-processadores do controlnet_aux reescalam pela MENOR dimensao, o
    # que devolve um mapa maior que a entrada e faz cada tipo gerar num tamanho
    # diferente. Normalizar aqui mantem a saida previsivel.
    g["mapa"] = {"class_type": "ImageScaleToMaxDimension",
                 "inputs": {"image": ["pre", 0], "upscale_method": "lanczos",
                            "largest_size": p["lado_maximo"]}}
    return "mapa"


def previa_de_controle(referencia, tipo, prefixo="controle"):
    """So o mapa, sem gerar imagem. Serve para o usuario ver o que o modelo ve."""
    g = {}
    mapa = _mapa_de_controle(g, referencia, tipo)
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": [mapa, 0], "filename_prefix": prefixo}}
    return g


def gerar_com_controle(prompt, referencia, tipo, seed, forca=1.0, steps=None,
                       prefixo="controle"):
    """Gera uma imagem nova seguindo a estrutura da referencia (Z-Image).

    O ControlNet do Z-Image nao e um ControlNet classico: ele entra como um
    model patch aplicado ao modelo, via QwenImageDiffsynthControlnet.
    """
    p = CONTROLE
    g = {}
    mapa = _mapa_de_controle(g, referencia, tipo)
    g.update({
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "patch": {"class_type": "ModelPatchLoader",
                  "inputs": {"name": win(p["patch"])}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        "controle": {"class_type": "QwenImageDiffsynthControlnet",
                     "inputs": {"model": ["unet", 0], "model_patch": ["patch", 0],
                                "vae": ["vae", 0], "image": [mapa, 0],
                                "strength": forca}},
        "ms": {"class_type": "ModelSamplingAuraFlow",
               "inputs": {"model": ["controle", 0], "shift": p["shift"]}},
        "tam": {"class_type": "GetImageSize", "inputs": {"image": [mapa, 0]}},
        "latente": {"class_type": "EmptySD3LatentImage",
                    "inputs": {"width": ["tam", 0], "height": ["tam", 1],
                               "batch_size": 1}},
    })
    _texto(g, "pos", "clip", prompt)
    g["neg"] = {"class_type": "ConditioningZeroOut",
                "inputs": {"conditioning": ["pos", 0]}}
    g["amostra"] = {"class_type": "KSampler",
                    "inputs": {"model": ["ms", 0], "positive": ["pos", 0],
                               "negative": ["neg", 0], "latent_image": ["latente", 0],
                               "seed": seed, "steps": steps or p["steps"],
                               "cfg": p["cfg"], "sampler_name": p["sampler"],
                               "scheduler": p["scheduler"], "denoise": 1.0}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["amostra", 0], "vae": ["vae", 0]}}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}}
    return g


def _alinhar(g, ancora, alvo, sufixo):
    """Poe a ancora EXATAMENTE no tamanho da imagem difundida.

    Sem isto o grafo estoura com imagens cujo tamanho final nao e multiplo de
    16: o VAE arredonda a saida da difusao para baixo (1665x2961 vira
    1664x2960), a ancora mantem o tamanho fracionario, e o no de detalhe tenta
    somar matrizes de formatos diferentes:

        operands could not be broadcast together with shapes
          (1664,2960,3) (1665,2961,3)

    Passou despercebido em todos os testes porque usamos 1024, 1760 e 1920 —
    todos ja multiplos de 16.
    """
    g[f"tam{sufixo}"] = {"class_type": "GetImageSize",
                         "inputs": {"image": [alvo, 0]}}
    nome = f"anc{sufixo}"
    g[nome] = {"class_type": "ImageScale",
               "inputs": {"image": [ancora, 0], "upscale_method": "lanczos",
                          "width": [f"tam{sufixo}", 0],
                          "height": [f"tam{sufixo}", 1], "crop": "disabled"}}
    return nome


def _acabamento(g, chave, ancora, ajustes):
    """Detalhe, microcontraste e granulacao, nesta ordem.

    Sao aplicados depois da difusao. `ancora` e a versao so-ESRGAN, usada como
    fonte da alta frequencia que a difusao suavizou. Cada etapa so entra no
    grafo se o valor dela for maior que zero — nao adianta pendurar nos inertes.
    """
    a = AMPLIAR["acabamento"]

    detalhe = ajustes.get("detalhe", 0.0)
    if detalhe > 0:
        # A ancora so entra depois de alinhada ao tamanho real da saida.
        if ancora != chave:
            ancora = _alinhar(g, ancora, chave, "_det")
        # 0..1 vira o quanto de alta frequencia da ancora volta.
        maximo = a["detalhe"]["keep_high_freq_max"]
        g["fim_detalhe"] = {"class_type": a["detalhe"]["no"],
                            "inputs": {"image": [chave, 0],
                                       "detail_image": [ancora, 0],
                                       "keep_high_freq": int(round(detalhe * maximo)),
                                       "erase_low_freq": a["detalhe"]["erase_low_freq"],
                                       "mask_blur": a["detalhe"]["mask_blur"]}}
        # A restauracao traz junto a cor da ancora e esquenta a imagem. Este no
        # devolve o tom da entrada mantendo o detalhe recuperado — e o mesmo
        # que o SeedVR2 usa internamente para nao desviar de cor.
        g["fim_cor"] = {"class_type": a["detalhe"]["recor_no"],
                        "inputs": {"images": ["fim_detalhe", 0],
                                   "original_resized_images": [chave, 0],
                                   "color_correction_method": a["detalhe"]["recor_metodo"]}}
        chave = "fim_cor"

    micro = ajustes.get("microcontraste", 0.0)
    if micro > 0:
        g["fim_micro"] = {"class_type": a["microcontraste"]["no"],
                          "inputs": {"image": [chave, 0], "amount": micro}}
        chave = "fim_micro"

    grao = ajustes.get("granulacao", 0.0)
    if grao > 0:
        g["fim_grao"] = {"class_type": a["granulacao"]["no"],
                         "inputs": {"image": [chave, 0], "grain_power": grao,
                                    "grain_scale": a["granulacao"]["escala"],
                                    "grain_sat": a["granulacao"]["saturacao"]}}
        chave = "fim_grao"
    return chave


def _ampliar_criativo(referencia, escala, seed, ajustes, prefixo):
    """Amplia com ESRGAN e re-difunde por cima, guiado por um prompt."""
    p = AMPLIAR["metodos"]["criativo"]
    otimizacao = AMPLIAR["otimizacoes"].get(ajustes.get("otimizacao", "geral"),
                                            AMPLIAR["otimizacoes"]["geral"])
    g = {
        "img": {"class_type": "LoadImage", "inputs": {"image": referencia}},
        # Normaliza a entrada: o custo da difusao depende do tamanho, entao
        # imagens muito grandes precisam descer antes de subir.
        "base": {"class_type": "ImageScaleToTotalPixels",
                 "inputs": {"image": ["img", 0], "upscale_method": "lanczos",
                            "megapixels": p["megapixels_entrada"],
                            "resolution_steps": 16}},
        "modelo": {"class_type": "UpscaleModelLoader",
                   "inputs": {"model_name": p["ampliador"]}},
        "esr4x": {"class_type": "ImageUpscaleWithModel",
                  "inputs": {"upscale_model": ["modelo", 0], "image": ["base", 0]}},
        # O tamanho pedido, medido a partir da imagem ORIGINAL. Antes a escala
        # saia do encadeamento — a entrada era normalizada para 1 MP e tudo
        # depois se referia a ela, entao "2x" de uma imagem de 0,85 MP virava
        # 2,22x, e de uma de 2,2 MP virava 0,58x. Este ImageScaleBy e so uma
        # reescala barata, sem modelo: serve de regua.
        "alvo": {"class_type": "ImageScaleBy",
                 "inputs": {"image": ["img", 0], "upscale_method": "lanczos",
                            "scale_by": escala}},
        "tam_final": {"class_type": "GetImageSize", "inputs": {"image": ["alvo", 0]}},
        # A versao so-ESRGAN no tamanho final: ancora de semelhanca e de detalhe.
        "ancora": {"class_type": "ImageScale",
                   "inputs": {"image": ["esr4x", 0], "upscale_method": "lanczos",
                              "width": ["tam_final", 0],
                              "height": ["tam_final", 1], "crop": "disabled"}},
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        "ms": {"class_type": "ModelSamplingAuraFlow",
               "inputs": {"model": ["unet", 0], "shift": p["shift"]}},
        # A difusao roda numa versao LIMITADA da ancora. Em 4x a ancora tem
        # 16 MP, e o VAEEncode disso nao cabe na placa — travava sem terminar
        # e sem poder ser interrompido. Aqui ela desce ao teto; o tamanho
        # final e recuperado depois, por reescala.
        "difusa_entrada": {"class_type": "ImageScaleToTotalPixels",
                           "inputs": {"image": ["ancora", 0],
                                      "upscale_method": "lanczos",
                                      "megapixels": p["megapixels_difusao"],
                                      "resolution_steps": 16}},
        "latente": {"class_type": "VAEEncode",
                    "inputs": {"pixels": ["difusa_entrada", 0], "vae": ["vae", 0]}},
    }
    _texto(g, "pos", "clip", otimizacao["prompt"])
    _texto(g, "neg", "clip", "blurry, soft, low quality, oversharpened halo")
    g["amostra"] = {"class_type": "KSampler",
                    "inputs": {"model": ["ms", 0], "positive": ["pos", 0],
                               "negative": ["neg", 0], "latent_image": ["latente", 0],
                               "seed": seed, "steps": p["steps"], "cfg": p["cfg"],
                               "sampler_name": p["sampler"], "scheduler": p["scheduler"],
                               # Aqui mora a criatividade: quanto o modelo pode
                               # se afastar do que ja estava na imagem.
                               "denoise": ajustes.get("criatividade", 0.33)}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["amostra", 0], "vae": ["vae", 0]}}

    # De volta ao tamanho pedido. Quando a difusao ja rodou no tamanho final
    # isto e uma reescala de 1:1, entao nao custa nada; quando nao, e o que
    # entrega a escala que o usuario escolheu.
    g["ao_tamanho"] = {"class_type": "ImageScale",
                       "inputs": {"image": ["decodifica", 0],
                                  "upscale_method": "lanczos",
                                  "width": ["tam_final", 0],
                                  "height": ["tam_final", 1], "crop": "disabled"}}

    chave = "ao_tamanho"
    semelhanca = ajustes.get("semelhanca", 0.0)
    if semelhanca > 0:
        # Puxa o resultado de volta para a versao so-ESRGAN.
        g["mistura"] = {"class_type": "ImageBlend",
                        # `decodifica` ainda esta no teto intermediario da
                        # difusao (2,25 MP); a ancora ja esta no tamanho final.
                        # Misturar os dois diretamente quebra quando a escala
                        # pedida ultrapassa esse teto. `ao_tamanho` e a versao
                        # alinhada que deve entrar aqui.
                        "inputs": {"image1": ["ao_tamanho", 0], "image2": ["ancora", 0],
                                   "blend_factor": semelhanca, "blend_mode": "normal"}}
        chave = "mistura"

    chave = _acabamento(g, chave, "ancora", ajustes)
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": [chave, 0], "filename_prefix": prefixo}}
    return g


def ampliar(referencia, metodo, escala, seed=0, prefixo="ampliado", ajustes=None):
    """Aumenta a resolucao da imagem. Nao usa prompt.

    "seedvr" refaz o detalhe com difusao em um unico passo, com VAE em
    ladrilhos para caber na VRAM. "classico" passa por um ESRGAN, que e
    instantaneo mas so interpola. "criativo" amplia e re-difunde por cima,
    guiado por um prompt, e aceita os ajustes finos.
    """
    ajustes = ajustes or {}
    if metodo == "criativo":
        return _ampliar_criativo(referencia, escala, seed, ajustes, prefixo)

    p = AMPLIAR["metodos"][metodo]
    g = {"img": {"class_type": "LoadImage", "inputs": {"image": referencia}}}

    if metodo == "classico":
        g["modelo"] = {"class_type": "UpscaleModelLoader",
                       "inputs": {"model_name": p["modelo"]}}
        g["amplia"] = {"class_type": "ImageUpscaleWithModel",
                       "inputs": {"upscale_model": ["modelo", 0], "image": ["img", 0]}}
        saida = "amplia"
        # O ESRGAN so sabe 4x; para escalas menores reduzimos o resultado.
        if abs(escala - p["fator_nativo"]) > 0.01:
            g["ajusta"] = {"class_type": "ResizeImageMaskNode",
                           "inputs": {"input": ["amplia", 0],
                                      "resize_type": "scale by multiplier",
                                      "resize_type.multiplier": escala / p["fator_nativo"],
                                      "scale_method": "lanczos"}}
            saida = "ajusta"
        saida = _acabamento(g, saida, saida, ajustes)
        g["salva"] = {"class_type": "SaveImage",
                      "inputs": {"images": [saida, 0], "filename_prefix": prefixo}}
        return g

    ladrilho, sobre = p["ladrilho"], p["sobreposicao"]
    g.update({
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        # O template oficial junta a imagem ao proprio canal alfa antes de escalar.
        "rgba": {"class_type": "JoinImageWithAlpha",
                 "inputs": {"image": ["img", 0], "alpha": ["img", 1]}},
        "escala": {"class_type": "ResizeImageMaskNode",
                   "inputs": {"input": ["rgba", 0],
                              "resize_type": "scale by multiplier",
                              "resize_type.multiplier": escala,
                              "scale_method": "lanczos"}},
        "prep": {"class_type": "SeedVR2Preprocess",
                 "inputs": {"resized_images": ["escala", 0]}},
        "latente": {"class_type": "VAEEncodeTiled",
                    "inputs": {"pixels": ["prep", 0], "vae": ["vae", 0],
                               "tile_size": ladrilho, "overlap": sobre,
                               "temporal_size": 4096, "temporal_overlap": 8}},
        "cond": {"class_type": "SeedVR2Conditioning",
                 "inputs": {"model": ["unet", 0], "vae_conditioning": ["latente", 0]}},
        "amostra": {"class_type": "KSampler",
                    "inputs": {"model": ["unet", 0], "positive": ["cond", 0],
                               "negative": ["cond", 1], "latent_image": ["latente", 0],
                               "seed": seed, "steps": p["steps"], "cfg": p["cfg"],
                               "sampler_name": "euler", "scheduler": "simple",
                               "denoise": 1.0}},
        "decodifica": {"class_type": "VAEDecodeTiled",
                       "inputs": {"samples": ["amostra", 0], "vae": ["vae", 0],
                                  "tile_size": ladrilho, "overlap": sobre,
                                  "temporal_size": 4096, "temporal_overlap": 8}},
        # Reancora a cor no original: a difusao tende a desviar o tom.
        "pos": {"class_type": "SeedVR2PostProcessing",
                "inputs": {"images": ["decodifica", 0],
                           "original_resized_images": ["escala", 0],
                           "color_correction_method": p["correcao_cor"]}},
    })
    chave = _acabamento(g, "pos", "escala", ajustes)
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": [chave, 0], "filename_prefix": prefixo}}
    return g


def escrever_texto(instrucao, max_length=1024, criativo=False, seed=0):
    """Grafo minimo que usa um Qwen3-VL local como gerador de texto.

    Serve para escrever o JSON de layout do Ideogram e para expandir prompts.
    `criativo=False` usa decodificacao gulosa, que e o que se quer para JSON.

    O sampling_mode e um COMFY_DYNAMICCOMBO_V3. Os parametros da opcao vao em
    chaves prefixadas -- "sampling_mode.temperature" e nao "temperature".
    Passa-los soltos falha na validacao; passa-los como dicionario aninhado
    passa na validacao mas quebra na execucao.
    """
    amostragem = {"sampling_mode": "off"}
    if criativo:
        opcao = {"temperature": 0.7, "top_k": 64, "top_p": 0.95, "min_p": 0.05,
                 "repetition_penalty": 1.05, "seed": seed}
        amostragem = {"sampling_mode": "on",
                      **{f"sampling_mode.{k}": v for k, v in opcao.items()}}
    return {
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(LLM["clip"]), "type": LLM["clip_type"],
                            "device": "default"}},
        "gera": {"class_type": "TextGenerate",
                 "inputs": {"clip": ["clip", 0], "prompt": instrucao,
                            "max_length": max_length, "thinking": False,
                            "use_default_template": True, **amostragem}},
        "saida": {"class_type": "PreviewAny", "inputs": {"source": ["gera", 0]}},
    }


def ajustar_rosto(imagem, valores, prefixo="rosto"):
    """Ajuste fino do rosto pelo ExpressionEditor (LivePortrait).

    Tres nos so. Nao ha VAE, sampler nem seed: o no recebe a imagem e os 15
    numeros e devolve o rosto deformado. Valores fora da faixa sao cortados
    em vez de recusados — arrastar um controle nao deve virar erro 400.
    """
    defs = controles_do_rosto()
    entradas = dict(ROSTO["fixos"])
    for chave, d in defs.items():
        v = valores.get(chave, d["padrao"])
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = d["padrao"]
        entradas[chave] = min(d["max"], max(d["min"], v))

    return {
        "img": {"class_type": "LoadImage", "inputs": {"image": imagem}},
        "exp": {"class_type": "ExpressionEditor",
                "inputs": {"src_image": ["img", 0], **entradas}},
        "salva": {"class_type": "SaveImage",
                  "inputs": {"images": ["exp", 0], "filename_prefix": prefixo}},
    }


def gerar_nuvem(modelo, prompt, seed, proporcao="auto", resolucao="1K",
                referencias=None, prefixo="nuvem", sistema=None):
    """Geracao ou edicao pelo no de parceiro do Google (Nano Banana Pro / 2).

    Nao ha UNETLoader, VAE, sampler nem latente: o no e uma chamada de API que
    devolve IMAGE pronta. A placa nao e usada — o que significa que isto roda
    mesmo com outro programa ocupando a VRAM.

    A chave NAO entra aqui. Ela e entrada oculta do no e viaja em extra_data,
    montada em chaves.py. Se ela faltar, o motor devolve um erro do proprio no,
    e nao um grafo invalido.

    As referencias vao todas para uma entrada SO ("images"), que espera um
    lote. Por isso elas sao encadeadas em ImageBatch duas a duas, que e o mesmo
    que o no "Batch Images" faz na tela. O limite e do proprio no: 14.
    """
    p = NUVEM[modelo]
    referencias = referencias or []
    if len(referencias) > p["max_referencias"]:
        raise ValueError(
            f'{p["rotulo"]} aceita no maximo {p["max_referencias"]} referencias; '
            f"foram {len(referencias)}")

    g = {}
    for i, nome in enumerate(referencias):
        g[f"img{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}

    # Encadeamento: lote0 = img0+img1, lote1 = lote0+img2, e assim por diante.
    # Com uma referencia so nao existe lote nenhum — a propria LoadImage serve.
    entrada = None
    if referencias:
        entrada = ["img0", 0]
        for i in range(1, len(referencias)):
            g[f"lote{i}"] = {"class_type": "ImageBatch",
                             "inputs": {"image1": entrada, "image2": [f"img{i}", 0]}}
            entrada = [f"lote{i}", 0]

    g["nuvem"] = {
        "class_type": p["no"],
        "inputs": {
            "prompt": prompt,
            "model": p["modelo"],
            "seed": seed,
            "aspect_ratio": proporcao,
            "resolution": resolucao,
            # Pedir so IMAGE evita gastar token gerando um texto que jogariamos
            # fora — a segunda saida do no nao e usada por nos.
            "response_modalities": "IMAGE",
        },
    }
    if entrada is not None:
        g["nuvem"]["inputs"]["images"] = entrada
    if sistema:
        g["nuvem"]["inputs"]["system_prompt"] = sistema

    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["nuvem", 0], "filename_prefix": prefixo}}
    return g


def _razao(texto):
    """'16:9' -> 1.777; '(2K) 2848x1600 (16:9)' / '1920:1080' / '1024x1024' -> largura/altura."""
    import re
    m = re.search(r"(\d+)x(\d+)", texto) or re.search(r"^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$", texto.strip())
    return float(m.group(1)) / float(m.group(2)) if m else None


def _mais_proxima(opcoes, proporcao, nivel=None):
    """A opcao cuja proporcao fica mais perto da pedida (em escala log), e no nivel pedido quando ha."""
    import math
    alvo = _razao(proporcao) or 1.0
    candidatas = [o for o in opcoes if nivel and o.startswith(f"({nivel})")] or list(opcoes)
    if nivel and not any(o.startswith("(") for o in opcoes):
        # Listas de pixels ("1024x1024"): o nivel escolhe pelo tamanho do lado maior.
        lado = {"1K": 1536, "2K": 2600, "4K": 4000}.get(nivel, 1536)
        def tamanho(o):
            import re
            m = re.search(r"(\d+)[x:](\d+)", o)
            return max(int(m.group(1)), int(m.group(2))) if m else 0
        no_nivel = [o for o in candidatas if tamanho(o) <= lado]
        if no_nivel:
            maior = max(tamanho(o) for o in no_nivel)
            candidatas = [o for o in no_nivel if tamanho(o) == maior] + [o for o in no_nivel if tamanho(o) != maior]
    return min(candidatas, key=lambda o: abs(math.log((_razao(o) or 1.0) / alvo)))


def gerar_api_generico(ficha, prompt, seed, proporcao, nivel, referencias=None, prefixo="nuvem"):
    """Grafo de UM no de parceiro de imagem, a partir da ficha em presets.NUVEM
    (familia "generico"). A chave viaja em extra_data, fora do grafo."""
    referencias = list(referencias or [])
    refs = ficha.get("refs")
    if len(referencias) > ficha["max_referencias"]:
        raise ValueError(f'{ficha["rotulo"]} aceita no maximo {ficha["max_referencias"]} imagens; '
                         f"foram {len(referencias)}")
    g = {f"img{i}": {"class_type": "LoadImage", "inputs": {"image": n}} for i, n in enumerate(referencias)}
    ent = dict(ficha["campos"])
    ent[ficha["prompt"]] = prompt
    if ficha.get("seed"):
        ent[ficha["seed"]] = seed % 2147483647
    # Um nivel que o modelo nao tem (2K no Wan 2.5, que vai ate 1440 px) cai no primeiro que ele tem.
    if ficha.get("resolucoes") and nivel not in ficha["resolucoes"]:
        nivel = ficha["resolucoes"][0]
    tipo, *args = ficha["formato"]
    if tipo == "ar":
        ent[args[0]] = _mais_proxima(args[1], proporcao)
    elif tipo == "px":
        ent[args[0]] = _mais_proxima(args[1], proporcao, nivel)
    else:  # "wh": o lado maior vem do nivel, multiplo de 16
        r = _razao(proporcao) or 1.0
        lado = {"2K": 2048, "4K": 2048}.get(nivel, 1024)
        w, h = (lado, lado / r) if r >= 1 else (lado * r, lado)
        # Limites do no (o Wan 2.5 pede cada lado entre 768 e 1440): sobe o lado menor e corta o maior.
        if ficha.get("lados"):
            minimo, maximo = ficha["lados"]
            f = max(1.0, minimo / min(w, h))
            w, h = w * f, h * f
            f = min(1.0, maximo / max(w, h))
            w, h = max(minimo, w * f), max(minimo, h * f)
        ent[args[0]], ent[args[1]] = int(round(w / 16) * 16), int(round(h / 16) * 16)
    campo_nivel = ficha.get("nivel", ("", []))[0]
    if campo_nivel:
        ent[campo_nivel] = nivel if nivel in ficha["resolucoes"] else ficha["resolucoes"][0]
    if referencias and refs:
        if refs[0] == "autogrow":
            for i in range(len(referencias)):
                ent[f"{refs[1]}.image_{i + 1}"] = [f"img{i}", 0]
        elif refs[0] == "lote":
            atual = ["img0", 0]
            for i in range(1, len(referencias)):
                g[f"lote{i}"] = {"class_type": "ImageBatch", "inputs": {"image1": atual, "image2": [f"img{i}", 0]}}
                atual = [f"lote{i}", 0]
            ent[refs[1]] = atual
        else:
            ent[refs[1]] = ["img0", 0]
    g["nuvem"] = {"class_type": ficha["no"], "inputs": ent}
    g["salva"] = {"class_type": "SaveImage", "inputs": {"images": ["nuvem", 0], "filename_prefix": prefixo}}
    return g


def gerar_video_generico(cfg, modo, prompt, seed, proporcao, resolucao, duracao,
                         imagem=None, imagem_final=None, com_audio=True, prefixo="video"):
    """Grafo de UM no de parceiro de video, a partir da ficha do modo em
    presets.VIDEO_API (familia "generico")."""
    f = cfg["nos"].get(modo)
    if not f:
        raise ValueError(f'{cfg["rotulo"]} não faz este modo')
    g, ent = {}, dict(f["campos"])
    ent[f["prompt"]] = prompt
    if f.get("seed"):
        ent[f["seed"]] = seed % 2147483646
    if f.get("ar"):
        ent[f["ar"][0]] = _mais_proxima(f["ar"][1], proporcao)
    if f.get("res"):
        chave, opcoes = f["res"]
        ent[chave] = next((o for o in opcoes if o.lower() == resolucao.lower()), opcoes[0])
    if f.get("px"):
        # Resolucao em pixels: a orientacao da proporcao e a altura da resolucao pedida.
        altura = int("".join(c for c in resolucao if c.isdigit()) or 720)
        r = _razao(proporcao) or 1.0
        cand = [o for o in f["px"][1] if (int(o.split("x")[0]) >= int(o.split("x")[1])) == (r >= 1)]
        ent[f["px"][0]] = min(cand, key=lambda o: abs(min(map(int, o.split("x"))) - altura))
    if f.get("dur"):
        chave, tipo, dmin, dmax = f["dur"]
        d = max(dmin, min(dmax, int(round(duracao))))
        ent[chave] = d if tipo == "int" else str(d)
    if f.get("audio"):
        ent[f["audio"]] = bool(com_audio)
    for papel, nome in (("img", imagem), ("fim", imagem_final)):
        if not f.get(papel):
            continue
        if not nome:
            raise ValueError("este modo precisa da imagem" + (" final" if papel == "fim" else ""))
        g[papel] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        alvo = f[papel]
        if alvo.startswith("autogrow:"):
            ent[f"{alvo.split(':', 1)[1]}.image_1"] = [papel, 0]
        else:
            ent[alvo] = [papel, 0]
    g["gera"] = {"class_type": f["no"], "inputs": ent}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {"video": ["gera", 0], "filename_prefix": prefixo,
                                                        "format": "auto", "codec": "auto"}}
    return g


def reluz_magnific(imagem, descricao, estilo="standard", forca=100,
                   referencia=None, mudar_fundo=False, preservar_detalhe=True,
                   prefixo="reluz"):
    """Reiluminacao pelo Magnific, por nuvem.

    Faz numa chamada o que aqui sao DOIS caminhos separados: reiluminar por
    descricao (o nosso "clima", no Klein) e transferir a luz de outra imagem
    (o nosso "luzref"). Se houver referencia, ela manda; senao vale o texto.

    Nao tem seed. Os nossos dois caminhos locais dependem dela — medimos que a
    transferencia de luz varia de +3,0 a -18,3 so trocando a seed — entao aqui
    nao ha o que sortear, e repetir devolve o mesmo.

    `mudar_fundo` vem FALSO por padrao, ao contrario do no, que traz True.
    Reiluminar e mudar a luz; trocar o fundo e outro pedido, e quem quiser que
    peca. O padrao do no surpreenderia quem so queria a luz.
    """
    g = {"base": {"class_type": "LoadImage", "inputs": {"image": imagem}}}
    entradas = {
        "image": ["base", 0],
        "prompt": descricao or "",
        "light_transfer_strength": int(max(0, min(100, forca))),
        "style": estilo,
        "interpolate_from_original": False,
        "change_background": bool(mudar_fundo),
        "preserve_details": bool(preservar_detalhe),
        "advanced_settings": "disabled",
    }
    if referencia:
        g["luz"] = {"class_type": "LoadImage", "inputs": {"image": referencia}}
        entradas["reference_image"] = ["luz", 0]

    g["nuvem"] = {"class_type": "MagnificImageRelightNode", "inputs": entradas}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["nuvem", 0], "filename_prefix": prefixo}}
    return g


def ampliar_topaz(imagem, escala, modelo="Wonder 3.5", largura=None, altura=None,
                  prefixo="ampliado"):
    """Ampliacao pelo Topaz, por nuvem.

    O no nao recebe um FATOR, e sim o tamanho final em pixels. Como quem
    escolhe na interface e a escala, o tamanho de saida e calculado aqui, a
    partir das dimensoes reais do arquivo — que o chamador mede.

    `model` e um DynamicCombo: manda-se a chave, e as opcoes especificas
    daquele ramo ficam de fora quando nao se quer mexer nelas. Foi assim que
    o Magnific aceitou "advanced_settings": "disabled".
    """
    g = {"base": {"class_type": "LoadImage", "inputs": {"image": imagem}}}
    entradas = {
        "image": ["base", 0],
        "model": modelo,
        # ATENCAO ao prefixo. O ramo "Wonder 3.5" tem seis campos
        # OBRIGATORIOS, e eles vao com o nome do combo na frente:
        # "model.enhancement_strength", nao "enhancement_strength". O proprio
        # erro do motor diz isso ("input_name": "model.grain_strength"), mas
        # so depois de duas tentativas eu fui ler o campo certo da mensagem.
        #
        # Foi diferente do Magnific, cujo ramo "disabled" nao tem sub-campo
        # algum e por isso aceitou a chave sozinha — nao da para generalizar
        # o formato de um no para outro.
        "model.enhancement_strength": "high",
        # Granulacao desligada: a ampliacao existe para ganhar textura real,
        # e grao sintetico por cima disfarcaria justamente o que se quer ver.
        # Os tres valores abaixo so sao lidos quando `grain` e verdadeiro,
        # mas precisam estar presentes de qualquer forma.
        "model.grain": False,
        "model.grain_model": "silver",
        "model.grain_strength": 0.5,
        "model.grain_size": 1.0,
        "model.grain_density": 0.5,
    }
    if largura and altura:
        entradas["output_width"] = int(largura * escala)
        entradas["output_height"] = int(altura * escala)
    g["nuvem"] = {"class_type": "TopazImageEnhanceV2", "inputs": entradas}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["nuvem", 0], "filename_prefix": prefixo}}
    return g


def recortar_fundo(imagem, prefixo="recorte"):
    """Remove o fundo pelo Recraft, por nuvem.

    Escolhido em vez do Bria por dois motivos medidos na tabela de precos e
    nas saidas do no: custa US$ 0,010 contra 0,018, e devolve IMAGE **e
    MASK**, enquanto o Bria devolve so a imagem. A mascara e o que permite,
    depois, compor texto ATRAS do sujeito.

    A saida vai como PNG com transparencia — por isso o SaveImage recebe a
    imagem ja com o alfa aplicado pelo proprio no.
    """
    g = {
        "base": {"class_type": "LoadImage", "inputs": {"image": imagem}},
        "nuvem": {"class_type": "RecraftRemoveBackgroundNode",
                  "inputs": {"image": ["base", 0]}},
        "salva": {"class_type": "SaveImage",
                  "inputs": {"images": ["nuvem", 0], "filename_prefix": prefixo}},
    }
    return g


def gerar_openai(modelo_api, prompt, seed, tamanho="1024x1024", qualidade="medium",
                 fundo="auto", referencias=None, prefixo="nuvem"):
    """Geracao ou edicao pelo no de parceiro da OpenAI (GPT Image 2.5).

    O `model` e um DynamicCombo, entao os campos do ramo escolhido vao com o
    prefixo — "model.size", nao "size". Mesma armadilha do Topaz.

    As referencias NAO sao um lote: este no tem uma entrada por imagem
    ("image_1" ate "image_16"), geradas por um Autogrow dentro do ramo. Por
    isso nao ha ImageBatch aqui, ao contrario do Nano Banana.

    `fundo="transparent"` e capacidade propria deste modelo: ele devolve PNG
    recortado sem precisar de uma segunda ferramenta.
    """
    referencias = referencias or []
    if len(referencias) > 16:
        raise ValueError(f"o GPT Image aceita até 16 referências; foram {len(referencias)}")

    # O campo do OpenAIGPTImageNodeV2 e um INT assinado de 32 bits. A seed
    # geral do aplicativo tem 52 bits porque os samplers locais aceitam essa
    # faixa; mandar o mesmo valor cru fazia parte das geracoes de nuvem ser
    # recusada antes mesmo de chamar o provedor. O modulo mantem seeds que ja
    # cabem intactas e reduz somente as maiores para 0..2147483647.
    seed_openai = int(seed) % (2**31)

    g = {}
    entradas = {
        "prompt": prompt,
        "model": modelo_api,
        # Uma imagem por chamada: as variacoes do painel repetem a chamada
        # com outra seed, como nos demais modelos.
        "n": 1,
        "seed": seed_openai,
        "model.size": tamanho,
        "model.quality": qualidade,
        "model.background": fundo,
        # Lidos so quando size == "Custom", mas o motor exige presenca.
        "model.custom_width": 1024,
        "model.custom_height": 1024,
    }
    for i, nome in enumerate(referencias, start=1):
        g[f"img{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        entradas[f"model.images.image_{i}"] = [f"img{i}", 0]

    g["nuvem"] = {"class_type": "OpenAIGPTImageNodeV2", "inputs": entradas}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["nuvem", 0], "filename_prefix": prefixo}}
    return g


def _modelo_ltx_com_memoria(g, modelo, p, largura, altura):
    """Divide o feed-forward em resolucao alta sem recortar a linha do tempo.

    Janelas temporais retiram as referencias dos trechos intermediarios e
    limitam a continuidade mesmo no texto puro. Todos os modos de geracao
    mantem o contexto completo; em 720p o modelo nao recebe este patch.
    """
    if int(largura) * int(altura) <= p["otimiza_memoria_acima"]:
        return modelo
    g["mem_ff"] = {
        "class_type": "LTXVChunkFeedForward",
        "inputs": {"model": modelo,
                   "chunks": p["chunks_feed_forward"],
                   "dim_threshold": 0},
    }
    return ["mem_ff", 0]


def _referencia_audio_ltx(g, modelo, positivo, negativo, p, caminho, forca):
    """Acrescenta identidade vocal ao modelo e aos dois condicionamentos."""
    if not caminho:
        return modelo, positivo, negativo
    # VHS_LoadAudio exige caminho absoluto; o backend ja o resolveu dentro da
    # pasta input antes de montar o grafo.
    g["carrega_audio_identidade"] = {
        "class_type": "VHS_LoadAudio",
        "inputs": {"audio_file": caminho, "seek_seconds": 0,
                   "duration": 5.0},
    }
    g["audio_identidade"] = {
        "class_type": "LTXVReferenceAudio",
        "inputs": {"model": modelo, "positive": positivo,
                   "negative": negativo,
                   "reference_audio": ["carrega_audio_identidade", 0],
                   "audio_vae": ["vae_a", 0],
                   "identity_guidance_scale": float(forca),
                   "start_percent": 0.0, "end_percent": 1.0},
    }
    return (["audio_identidade", 0], ["audio_identidade", 1],
            ["audio_identidade", 2])


def gerar_video_ltx(prompt, seed, largura=1280, altura=720, duracao=5,
                    imagem=None, com_audio=True, prompt_automatico=False,
                    negativo=None, audio_referencia=None,
                    forca_audio_referencia=3.0, prefixo="video"):
    """Video pelo LTX 2.5, local. Cobre text2video e img2video.

    TRADUZIDO do workflow do usuario (video_ltx2_5_i2v.json), que ja dava bom
    resultado nesta placa — nao foi derivado por mim. A estrutura que importa:

      1. Gera na METADE da resolucao pedida (640x360 para um 1280x720).
      2. Sobe o latente com o upsampler x2.
      3. Refina num segundo estagio de quatro passos.

    Gerar direto no tamanho final custaria muito mais; e assim que 16 GB dao
    conta de um modelo de 21 GB.

    Os nos Primitive/Math/Switch do workflow original NAO aparecem aqui: eles
    existem para a tela, e no formato API as contas sao feitas em Python.

    `com_audio` liga ou desliga um RAMO INTEIRO — sem ele nao ha latente de
    audio, nem concatenacao, nem decodificacao de som.
    """
    p = VIDEO_LTX
    fps = p["fps"]
    # Quadros = duracao * fps + 1. O +1 e do modelo: ele conta o quadro
    # inicial fora do intervalo.
    quadros = int(duracao) * fps + 1
    # Meia resolucao no primeiro estagio; o upsampler devolve o tamanho cheio.
    baixa_l, baixa_a = int(largura) // 2, int(altura) // 2

    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae_v": {"class_type": "VAELoader",
                  "inputs": {"vae_name": win(p["vae_video"])}},
        "upsampler": {"class_type": "LatentUpscaleModelLoader",
                      "inputs": {"model_name": win(p["upsampler"])}},
    }
    modelo = _modelo_ltx_com_memoria(g, ["unet", 0], p, largura, altura)

    # ---- entrada de imagem, quando houver --------------------------------
    # Sem imagem o modo e text2video: nao ha o que preprocessar, e o latente
    # inicial fica vazio.
    entrada_img = None
    if imagem:
        g["img"] = {"class_type": "LoadImage", "inputs": {"image": imagem}}
        # `resize_type` e DynamicCombo: o sub-campo vai com o prefixo do
        # combo, como no Topaz. Sem o prefixo o motor reclama que
        # "resize_type.longer_size" esta faltando.
        g["redim"] = {"class_type": "ResizeImageMaskNode",
                      "inputs": {"input": ["img", 0],
                                 "resize_type": "scale longer dimension",
                                 "resize_type.longer_size": p["entrada_maior_lado"],
                                 "scale_method": "lanczos"}}
        g["pre"] = {"class_type": "LTXVPreprocess",
                    "inputs": {"image": ["redim", 0],
                               "img_compression": p["preprocess"]}}
        entrada_img = ["pre", 0]

    # ---- texto -----------------------------------------------------------
    if prompt_automatico and entrada_img is not None:
        # O gerador automatico le a IMAGEM e escreve o prompt de movimento.
        # So faz sentido com imagem; sem ela nao teria o que descrever.
        g["clip_p"] = {"class_type": "CLIPLoader",
                       "inputs": {"clip_name": win(p["clip_prompt"]),
                                  "type": p["clip_type"], "device": "default"}}
        g["auto"] = {"class_type": "TextGenerateLTX2Prompt",
                     "inputs": {"clip": ["clip_p", 0], "image": entrada_img,
                                "prompt": prompt,
                                "max_length": p["auto_max_tokens"],
                                "sampling_mode": "on",
                                "sampling_mode.temperature": 0.7,
                                "sampling_mode.top_k": 64,
                                "sampling_mode.top_p": 0.95,
                                "sampling_mode.min_p": 0.05,
                                "sampling_mode.repetition_penalty": 1.15,
                                "sampling_mode.seed": seed}}
        g["pos"] = {"class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["clip", 0], "text": ["auto", 0]}}
    else:
        g["pos"] = {"class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["clip", 0], "text": prompt}}

    g["neg"] = {"class_type": "CLIPTextEncode",
                "inputs": {"clip": ["clip", 0],
                           "text": negativo if negativo is not None else p["negativo"]}}
    g["cond"] = {"class_type": "LTXVConditioning",
                 "inputs": {"positive": ["pos", 0], "negative": ["neg", 0],
                            "frame_rate": fps}}

    if com_audio:
        g["vae_a"] = {"class_type": "VAELoader",
                      "inputs": {"vae_name": win(p["vae_audio"])}}
    modelo, positivo, negativo_cond = _referencia_audio_ltx(
        g, modelo, ["cond", 0], ["cond", 1], p,
        audio_referencia if com_audio else None, forca_audio_referencia)

    # ---- estagio 1, em meia resolucao -------------------------------------
    g["vazio"] = {"class_type": "EmptyLTXVLatentVideo",
                  "inputs": {"width": baixa_l, "height": baixa_a,
                             "length": quadros, "batch_size": 1}}
    if entrada_img is not None:
        g["enc1"] = {"class_type": "LTXVImgToVideoInplace",
                     "inputs": {"vae": ["vae_v", 0], "image": entrada_img,
                                "latent": ["vazio", 0],
                                "strength": p["forca_imagem_1"], "bypass": False}}
        video_lat = ["enc1", 0]
    else:
        video_lat = ["vazio", 0]

    g["ruido1"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["amostrador"] = {"class_type": "KSamplerSelect",
                       "inputs": {"sampler_name": p["sampler"]}}
    g["sig1"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": p["sigmas_1"]}}
    g["sig2"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": p["sigmas_2"]}}
    g["guia"] = {"class_type": "LTXVDualCFGGuider",
                 "inputs": {"model": modelo, "positive": positivo,
                            "negative": negativo_cond,
                            "video_cfg": p["cfg_video"],
                            "audio_cfg": p["cfg_audio"]}}

    if com_audio:
        g["audio_vazio"] = {"class_type": "LTXVEmptyLatentAudio",
                            "inputs": {"audio_vae": ["vae_a", 0],
                                       "frames_number": quadros,
                                       "frame_rate": fps, "batch_size": 1}}
        g["junta1"] = {"class_type": "LTXVConcatAVLatent",
                       "inputs": {"video_latent": video_lat,
                                  "audio_latent": ["audio_vazio", 0]}}
        latente_1 = ["junta1", 0]
    else:
        latente_1 = video_lat

    g["passo1"] = {"class_type": "SamplerCustomAdvanced",
                   "inputs": {"noise": ["ruido1", 0], "guider": ["guia", 0],
                              "sampler": ["amostrador", 0], "sigmas": ["sig1", 0],
                              "latent_image": latente_1}}

    # ---- upsampling e estagio 2 -------------------------------------------
    if com_audio:
        g["separa1"] = {"class_type": "LTXVSeparateAVLatent",
                        "inputs": {"av_latent": ["passo1", 0]}}
        video_do_1, audio_do_1 = ["separa1", 0], ["separa1", 1]
    else:
        video_do_1, audio_do_1 = ["passo1", 0], None

    g["sobe"] = {"class_type": "LTXVLatentUpsampler",
                 "inputs": {"samples": video_do_1,
                            "upscale_model": ["upsampler", 0],
                            "vae": ["vae_v", 0]}}

    if entrada_img is not None:
        g["enc2"] = {"class_type": "LTXVImgToVideoInplace",
                     "inputs": {"vae": ["vae_v", 0], "image": entrada_img,
                                "latent": ["sobe", 0],
                                "strength": p["forca_imagem_2"], "bypass": False}}
        video_lat2 = ["enc2", 0]
    else:
        video_lat2 = ["sobe", 0]

    if com_audio:
        g["junta2"] = {"class_type": "LTXVConcatAVLatent",
                       "inputs": {"video_latent": video_lat2,
                                  "audio_latent": audio_do_1}}
        latente_2 = ["junta2", 0]
    else:
        latente_2 = video_lat2

    # Seed FIXA no refino, como no workflow original: o segundo estagio nao
    # deve reinventar o que o primeiro decidiu.
    g["ruido2"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}}
    g["passo2"] = {"class_type": "SamplerCustomAdvanced",
                   "inputs": {"noise": ["ruido2", 0], "guider": ["guia", 0],
                              "sampler": ["amostrador", 0], "sigmas": ["sig2", 0],
                              "latent_image": latente_2}}

    # ---- decodificacao -----------------------------------------------------
    if com_audio:
        g["separa2"] = {"class_type": "LTXVSeparateAVLatent",
                        "inputs": {"av_latent": ["passo2", 0]}}
        video_final, audio_final = ["separa2", 0], ["separa2", 1]
    else:
        video_final, audio_final = ["passo2", 0], None

    lad = p["decode_ladrilho"]
    g["decodifica"] = {"class_type": "VAEDecodeTiled",
                       "inputs": {"samples": video_final, "vae": ["vae_v", 0],
                                  "tile_size": lad[0], "overlap": lad[1],
                                  "temporal_size": lad[2], "temporal_overlap": lad[3]}}

    entradas_video = {"images": ["decodifica", 0], "fps": fps}
    if com_audio:
        g["som"] = {"class_type": "LTXVAudioVAEDecode",
                    "inputs": {"samples": audio_final, "audio_vae": ["vae_a", 0]}}
        entradas_video["audio"] = ["som", 0]

    g["monta"] = {"class_type": "CreateVideo", "inputs": entradas_video}
    g["salva"] = {"class_type": "SaveVideo",
                  "inputs": {"video": ["monta", 0], "filename_prefix": prefixo,
                             "format": "auto", "codec": "auto"}}
    return g


def gerar_video_ltx_msr(prompt, seed, referencias, fundo=None, largura=1280,
                        altura=704, duracao=5, com_audio=True, negativo=None,
                        audio_referencia=None, forca_audio_referencia=3.0,
                        prefixo="video"):
    """Video pelo LTX 2.5 a partir de ate 4 referencias, mais um fundo.

    MSR = multi-subject reference. Ao contrario do MiniMax, que empilha
    referencias, aqui cada uma ocupa um SLOT com identidade propria — pic1,
    pic2, pic3, pic4 e um slot separado de fundo. O desenho serve a sujeitos
    DISTINTOS (pessoa A, pessoa B, um objeto), nao a varios angulos do mesmo.

    Mantem os dois estagios do `gerar_video_ltx`: meia resolucao, upsample,
    refino. O guia MSR entra DUAS vezes, uma por estagio — e assim que o
    workflow de exemplo do proprio pacote faz.

    TRES armadilhas, todas silenciosas:

    1. Sem a IC-LoRA `Licon-MSR` o no aceita as imagens e as trata como guias
       comuns, "sem slot embeddings". Gera, entrega, e nao e MSR. Por isso o
       carregador da LoRA nao e opcional aqui.
    2. O guia espera o latente SO DE VIDEO, antes do `LTXVConcatAVLatent`.
       Passar o latente AV ja concatenado e erro de forma.
    3. O MSR prega as referencias como quadros em posicoes temporais
       NEGATIVAS. Sem `LTXVCropGuides` antes de decodificar, elas saem no
       video como quadros de verdade. O `gerar_video_ltx` comum nao corta
       porque nao prega nada; aqui cortar e obrigatorio, nos dois estagios.
    """
    p = VIDEO_LTX
    fps = p["fps"]
    quadros = int(duracao) * fps + 1
    baixa_l, baixa_a = int(largura) // 2, int(altura) // 2
    refs = [r for r in (referencias or []) if r][:p["max_referencias"]]
    if not refs:
        raise ValueError("envie ao menos uma imagem de referência")

    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae_v": {"class_type": "VAELoader",
                  "inputs": {"vae_name": win(p["vae_video"])}},
        "upsampler": {"class_type": "LatentUpscaleModelLoader",
                      "inputs": {"model_name": win(p["upsampler"])}},
        # A LoRA que traz os slot embeddings. Devolve (model, msr_parameters).
        "msr_lora": {"class_type": "ComfyUILTX25MSRICLoRALoader",
                     "inputs": {"model": ["unet", 0],
                                "lora_name": win(p["lora_msr"]),
                                "strength_model": p["forca_msr"]}},
    }
    modelo = _modelo_ltx_com_memoria(
        g, ["msr_lora", 0], p, largura, altura)

    for i, nome in enumerate(refs):
        g["pic%d" % (i + 1)] = {"class_type": "LoadImage", "inputs": {"image": nome}}
    if fundo:
        g["fundo"] = {"class_type": "LoadImage", "inputs": {"image": fundo}}

    g["pos"] = {"class_type": "CLIPTextEncode",
                "inputs": {"clip": ["clip", 0], "text": prompt}}
    g["neg"] = {"class_type": "CLIPTextEncode",
                "inputs": {"clip": ["clip", 0],
                           "text": negativo if negativo is not None else p["negativo"]}}
    g["cond"] = {"class_type": "LTXVConditioning",
                 "inputs": {"positive": ["pos", 0], "negative": ["neg", 0],
                            "frame_rate": fps}}

    if com_audio:
        g["vae_a"] = {"class_type": "VAELoader",
                      "inputs": {"vae_name": win(p["vae_audio"])}}
    modelo, cond_pos, cond_neg = _referencia_audio_ltx(
        g, modelo, ["cond", 0], ["cond", 1], p,
        audio_referencia if com_audio else None, forca_audio_referencia)

    lad = p["ladrilho_referencia"]

    def guia_msr(chave, latente):
        """O guia MSR, igual nos dois estagios; so muda o latente que entra."""
        entradas = {"positive": cond_pos, "negative": cond_neg,
                    "vae": ["vae_v", 0], "latent": latente,
                    "strength": p["forca_referencia"],
                    "reference_frames": p["quadros_referencia"],
                    "use_tiled_encode": True,
                    "tile_size": lad[0], "tile_overlap": lad[1],
                    "msr_parameters": ["msr_lora", 1]}
        for i in range(len(refs)):
            entradas["pic%d" % (i + 1)] = ["pic%d" % (i + 1), 0]
        if fundo:
            entradas["background"] = ["fundo", 0]
        g[chave] = {"class_type": "ComfyUILTX25MSRMultiReferenceGuide",
                    "inputs": entradas}
        return [chave, 0], [chave, 1], [chave, 2]

    # ---- estagio 1, em meia resolucao -------------------------------------
    g["vazio"] = {"class_type": "EmptyLTXVLatentVideo",
                  "inputs": {"width": baixa_l, "height": baixa_a,
                             "length": quadros, "batch_size": 1}}
    pos1, neg1, lat1 = guia_msr("msr1", ["vazio", 0])

    g["amostrador"] = {"class_type": "KSamplerSelect",
                       "inputs": {"sampler_name": p["sampler"]}}
    g["sig1"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": p["sigmas_1"]}}
    g["sig2"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": p["sigmas_2"]}}
    g["ruido1"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["guia1"] = {"class_type": "LTXVDualCFGGuider",
                  "inputs": {"model": modelo, "positive": pos1, "negative": neg1,
                             "video_cfg": p["cfg_video"],
                             "audio_cfg": p["cfg_audio"]}}

    if com_audio:
        g["audio_vazio"] = {"class_type": "LTXVEmptyLatentAudio",
                            "inputs": {"audio_vae": ["vae_a", 0],
                                       "frames_number": quadros,
                                       "frame_rate": fps, "batch_size": 1}}
        g["junta1"] = {"class_type": "LTXVConcatAVLatent",
                       "inputs": {"video_latent": lat1,
                                  "audio_latent": ["audio_vazio", 0]}}
        entra1 = ["junta1", 0]
    else:
        entra1 = lat1

    g["passo1"] = {"class_type": "SamplerCustomAdvanced",
                   "inputs": {"noise": ["ruido1", 0], "guider": ["guia1", 0],
                              "sampler": ["amostrador", 0], "sigmas": ["sig1", 0],
                              "latent_image": entra1}}

    if com_audio:
        g["separa1"] = {"class_type": "LTXVSeparateAVLatent",
                        "inputs": {"av_latent": ["passo1", 0]}}
        video_do_1, audio_do_1 = ["separa1", 0], ["separa1", 1]
    else:
        video_do_1, audio_do_1 = ["passo1", 0], None

    # Tira os quadros de referencia ANTES de subir de resolucao: subir um
    # latente que ainda os carrega gastaria memoria com o que vai fora.
    g["corta1"] = {"class_type": "LTXVCropGuides",
                   "inputs": {"positive": pos1, "negative": neg1,
                              "latent": video_do_1}}

    # ---- upsampling e estagio 2 -------------------------------------------
    g["sobe"] = {"class_type": "LTXVLatentUpsampler",
                 "inputs": {"samples": ["corta1", 2],
                            "upscale_model": ["upsampler", 0],
                            "vae": ["vae_v", 0]}}
    pos2, neg2, lat2 = guia_msr("msr2", ["sobe", 0])

    if com_audio:
        g["junta2"] = {"class_type": "LTXVConcatAVLatent",
                       "inputs": {"video_latent": lat2,
                                  "audio_latent": audio_do_1}}
        entra2 = ["junta2", 0]
    else:
        entra2 = lat2

    g["ruido2"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}}
    g["guia2"] = {"class_type": "LTXVDualCFGGuider",
                  "inputs": {"model": modelo, "positive": pos2, "negative": neg2,
                             "video_cfg": p["cfg_video"],
                             "audio_cfg": p["cfg_audio"]}}
    g["passo2"] = {"class_type": "SamplerCustomAdvanced",
                   "inputs": {"noise": ["ruido2", 0], "guider": ["guia2", 0],
                              "sampler": ["amostrador", 0], "sigmas": ["sig2", 0],
                              "latent_image": entra2}}

    if com_audio:
        g["separa2"] = {"class_type": "LTXVSeparateAVLatent",
                        "inputs": {"av_latent": ["passo2", 0]}}
        video_final, audio_final = ["separa2", 0], ["separa2", 1]
    else:
        video_final, audio_final = ["passo2", 0], None

    g["corta2"] = {"class_type": "LTXVCropGuides",
                   "inputs": {"positive": pos2, "negative": neg2,
                              "latent": video_final}}

    # O MSR carrega o LoRA de referencias e as imagens: decodificar o video
    # inteiro de uma vez (4096) estourou os 16 GB em 24/10/2026 ("Allocation
    # ... would exceed allowed memory", 13,3 GiB ocupados + 2,8 pedidos). Aqui
    # vale o 192/48 do editor original, medido la sem as quedas de nitidez.
    dec = p["decode_ladrilho"][:2] + [192, 48]
    g["decodifica"] = {"class_type": "VAEDecodeTiled",
                       "inputs": {"samples": ["corta2", 2], "vae": ["vae_v", 0],
                                  "tile_size": dec[0], "overlap": dec[1],
                                  "temporal_size": dec[2], "temporal_overlap": dec[3]}}

    entradas_video = {"images": ["decodifica", 0], "fps": fps}
    if com_audio:
        g["som"] = {"class_type": "LTXVAudioVAEDecode",
                    "inputs": {"samples": audio_final, "audio_vae": ["vae_a", 0]}}
        entradas_video["audio"] = ["som", 0]

    g["monta"] = {"class_type": "CreateVideo", "inputs": entradas_video}
    g["salva"] = {"class_type": "SaveVideo",
                  "inputs": {"video": ["monta", 0], "filename_prefix": prefixo,
                             "format": "auto", "codec": "auto"}}
    return g


def gerar_video_ltx_flf(prompt, seed, imagem_inicial, imagem_final,
                        largura=1280, altura=720, duracao=5, com_audio=True,
                        prompt_automatico=False, negativo=None,
                        audio_referencia=None, forca_audio_referencia=3.0,
                        prefixo="video"):
    """Primeiro e ultimo quadro: o modelo inventa o movimento entre as duas.

    TRADUZIDO de video_ltx2_5_flf2v.json, do usuario. E um pipeline DIFERENTE
    do i2v, nao uma variacao dele:

      - UM estagio so, em resolucao cheia. Nao ha upsampler nem refino.
      - As duas imagens entram como GUIAS (LTXVAddGuide), presas ao quadro 0 e
        ao quadro -1, com forca 0,7 — nao como latente inicial.
      - `LTXVCropGuides` remove os quadros-guia do latente antes de decodificar;
        sem isso os quadros presos apareceriam duplicados na saida.
      - Usa `SamplerEulerAncestral` (eta 0) e a SAIDA 1 do amostrador, a
        "denoised", nao a 0.

    O negativo do workflow original NAO foi copiado: ele estava viciado numa
    cena especifica (cita um bone escrito "PNTR", o slogan "JUST DO IT" e um
    microfone). Restricoes de outro projeto estragariam pecas que nada tem a
    ver. Vale o negativo generico do preset.
    """
    p = VIDEO_LTX
    fps = p["fps"]
    quadros = int(duracao) * fps + 1

    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae_v": {"class_type": "VAELoader",
                  "inputs": {"vae_name": win(p["vae_video"])}},
    }
    # Janelas temporais excluem os guias fora do trecho: o meio do video
    # perderia ambas as referencias. Mantem apenas o feed-forward dividido.
    modelo = _modelo_ltx_com_memoria(
        g, ["unet", 0], p, largura, altura)

    # As duas imagens vao para o tamanho EXATO da saida, com corte ao centro.
    # Aqui nao ha "maior lado": os guias precisam casar com o latente.
    for chave, arquivo in (("ini", imagem_inicial), ("fim", imagem_final)):
        g[f"img_{chave}"] = {"class_type": "LoadImage", "inputs": {"image": arquivo}}
        g[f"redim_{chave}"] = {
            "class_type": "ResizeImageMaskNode",
            "inputs": {"input": [f"img_{chave}", 0],
                       "resize_type": "scale dimensions",
                       "resize_type.width": int(largura),
                       "resize_type.height": int(altura),
                       "resize_type.crop": "center",
                       "scale_method": "nearest-exact"}}
        g[f"pre_{chave}"] = {
            "class_type": "LTXVPreprocess",
            "inputs": {"image": [f"redim_{chave}", 0],
                       "img_compression": p["preprocess"]}}

    # ---- texto -----------------------------------------------------------
    if prompt_automatico:
        # O gerador le o PRIMEIRO quadro, que e onde a cena comeca.
        g["clip_p"] = {"class_type": "CLIPLoader",
                       "inputs": {"clip_name": win(p["clip_prompt"]),
                                  "type": p["clip_type"], "device": "default"}}
        g["auto"] = {"class_type": "TextGenerateLTX2Prompt",
                     "inputs": {"clip": ["clip_p", 0], "image": ["pre_ini", 0],
                                "prompt": prompt,
                                "max_length": p["auto_max_tokens"],
                                "sampling_mode": "on",
                                "sampling_mode.temperature": 0.7,
                                "sampling_mode.top_k": 64,
                                "sampling_mode.top_p": 0.95,
                                "sampling_mode.min_p": 0.05,
                                "sampling_mode.repetition_penalty": 1.15,
                                "sampling_mode.seed": seed}}
        g["pos"] = {"class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["clip", 0], "text": ["auto", 0]}}
    else:
        g["pos"] = {"class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["clip", 0], "text": prompt}}

    g["neg"] = {"class_type": "CLIPTextEncode",
                "inputs": {"clip": ["clip", 0],
                           "text": negativo if negativo is not None else p["negativo"]}}
    g["cond"] = {"class_type": "LTXVConditioning",
                 "inputs": {"positive": ["pos", 0], "negative": ["neg", 0],
                            "frame_rate": fps}}

    if com_audio:
        g["vae_a"] = {"class_type": "VAELoader",
                      "inputs": {"vae_name": win(p["vae_audio"])}}
    modelo, cond_pos, cond_neg = _referencia_audio_ltx(
        g, modelo, ["cond", 0], ["cond", 1], p,
        audio_referencia if com_audio else None, forca_audio_referencia)

    # ---- latente e guias --------------------------------------------------
    g["vazio"] = {"class_type": "EmptyLTXVLatentVideo",
                  "inputs": {"width": int(largura), "height": int(altura),
                             "length": quadros, "batch_size": 1}}
    # Guia do PRIMEIRO quadro (indice 0), depois do ULTIMO (indice -1). O
    # segundo encadeia sobre as saidas do primeiro.
    g["guia_ini"] = {"class_type": "LTXVAddGuide",
                     "inputs": {"positive": cond_pos, "negative": cond_neg,
                                "vae": ["vae_v", 0], "latent": ["vazio", 0],
                                "image": ["pre_ini", 0],
                                "frame_idx": 0, "strength": p["forca_guia"]}}
    g["guia_fim"] = {"class_type": "LTXVAddGuide",
                     "inputs": {"positive": ["guia_ini", 0], "negative": ["guia_ini", 1],
                                "vae": ["vae_v", 0], "latent": ["guia_ini", 2],
                                "image": ["pre_fim", 0],
                                "frame_idx": -1, "strength": p["forca_guia"]}}

    if com_audio:
        g["audio_vazio"] = {"class_type": "LTXVEmptyLatentAudio",
                            "inputs": {"audio_vae": ["vae_a", 0],
                                       "frames_number": quadros,
                                       "frame_rate": fps, "batch_size": 1}}
        g["junta"] = {"class_type": "LTXVConcatAVLatent",
                      "inputs": {"video_latent": ["guia_fim", 2],
                                 "audio_latent": ["audio_vazio", 0]}}
        latente = ["junta", 0]
    else:
        latente = ["guia_fim", 2]

    # ---- amostragem, estagio unico ----------------------------------------
    g["ruido"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["amostrador"] = {"class_type": "SamplerEulerAncestral",
                       "inputs": {"eta": p["flf_eta"], "s_noise": 1.0}}
    g["sigmas"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": p["sigmas_1"]}}
    g["guia"] = {"class_type": "LTXVDualCFGGuider",
                 "inputs": {"model": modelo,
                            "positive": ["guia_fim", 0], "negative": ["guia_fim", 1],
                            "video_cfg": p["cfg_video"], "audio_cfg": p["cfg_audio"]}}
    g["passo"] = {"class_type": "SamplerCustomAdvanced",
                  "inputs": {"noise": ["ruido", 0], "guider": ["guia", 0],
                             "sampler": ["amostrador", 0], "sigmas": ["sigmas", 0],
                             "latent_image": latente}}

    # ATENCAO: saida 1, nao 0. O workflow usa a "denoised_output"; a 0 traz o
    # latente com o ruido residual do ultimo passo.
    saida_amostra = ["passo", 1]

    if com_audio:
        g["separa"] = {"class_type": "LTXVSeparateAVLatent",
                       "inputs": {"av_latent": saida_amostra}}
        video_lat, audio_lat = ["separa", 0], ["separa", 1]
    else:
        video_lat, audio_lat = saida_amostra, None

    # Remove os quadros-guia antes de decodificar. Sem isto os dois quadros
    # presos sairiam repetidos no video.
    g["corta"] = {"class_type": "LTXVCropGuides",
                  "inputs": {"positive": ["guia_fim", 0],
                             "negative": ["guia_fim", 1],
                             "latent": video_lat}}

    lad = p["decode_ladrilho"]
    g["decodifica"] = {"class_type": "VAEDecodeTiled",
                       "inputs": {"samples": ["corta", 2], "vae": ["vae_v", 0],
                                  "tile_size": lad[0], "overlap": lad[1],
                                  "temporal_size": lad[2], "temporal_overlap": lad[3]}}

    entradas_video = {"images": ["decodifica", 0], "fps": fps}
    if com_audio:
        g["som"] = {"class_type": "LTXVAudioVAEDecode",
                    "inputs": {"samples": audio_lat, "audio_vae": ["vae_a", 0]}}
        entradas_video["audio"] = ["som", 0]

    g["monta"] = {"class_type": "CreateVideo", "inputs": entradas_video}
    g["salva"] = {"class_type": "SaveVideo",
                  "inputs": {"video": ["monta", 0], "filename_prefix": prefixo,
                             "format": "auto", "codec": "auto"}}
    return g


def limpar_video(caminho, seed, resolucao=1088, fps=24, lote=None,
                 sobreposicao=None, com_audio=True, prefixo="video_limpo"):
    """Limpeza e ampliacao de video pelo SeedVR2 temporal, local.

    TRADUZIDO de "SeedVR2 - limpeza temporal.json", do usuario.

    E o mesmo SeedVR2 da ampliacao de imagem, mas pelo no de VIDEO: ele
    processa em lotes de quadros COM SOBREPOSICAO, e e isso que mantem a
    textura coerente de um quadro para o outro. Um upscaler de imagem
    aplicado quadro a quadro faria a pele e o cabelo tremerem.

    `caminho` e absoluto — o VHS_LoadVideoPath le do disco, nao aceita upload.
    Quem chama monta o caminho a partir da pasta de saida do motor.

    O AUDIO do original atravessa intacto: sai do LoadVideoPath (saida 2) e
    entra direto no VideoCombine, sem passar pelo modelo.
    """
    p = VIDEO_LIMPAR
    g = {
        "entrada": {
            "class_type": "VHS_LoadVideoPath",
            "inputs": {"video": caminho, "force_rate": 0,
                       "custom_width": 0, "custom_height": 0,
                       "frame_load_cap": 0, "skip_first_frames": 0,
                       "select_every_nth": 1}},
        "dit": {
            "class_type": "SeedVR2LoadDiTModel",
            "inputs": {"model": p["dit"], "device": "cuda:0",
                       # 16 blocos ficam na RAM e sobem por vez. E o que faz
                       # um modelo de 3B com contexto de video caber em 16 GB.
                       "blocks_to_swap": p["blocos_trocados"],
                       "swap_io_components": False,
                       "offload_device": p["descarregar_para"],
                       "cache_model": False,
                       "attention_mode": p["atencao"]}},
        "vae": {
            "class_type": "SeedVR2LoadVAEModel",
            "inputs": {"model": p["vae"], "device": "cuda:0",
                       # Ladrilho nos dois sentidos: sem isso um quadro de
                       # 1280 px estoura a memoria na codificacao.
                       "encode_tiled": True,
                       "encode_tile_size": p["ladrilho"],
                       "encode_tile_overlap": p["sobreposicao_ladrilho"],
                       "decode_tiled": True,
                       "decode_tile_size": p["ladrilho"],
                       "decode_tile_overlap": p["sobreposicao_ladrilho"],
                       "tile_debug": "false",
                       "offload_device": p["descarregar_para"],
                       "cache_model": False}},
        "limpa": {
            "class_type": "SeedVR2VideoUpscaler",
            "inputs": {"image": ["entrada", 0], "dit": ["dit", 0],
                       # Este nó aceita apenas unsigned 32-bit. A seed geral
                       # da aplicação pode ter 52 bits; reduzir de modo estável.
                       "vae": ["vae", 0], "seed": seed % (2**32),
                       "resolution": int(resolucao), "max_resolution": 0,
                       # O LOTE e a alavanca contra o tremor: a coerencia
                       # temporal vem de o modelo ver os quadros JUNTOS. Com
                       # lote pequeno ele reinventa o microdetalhe a cada
                       # grupo, e a textura oscila.
                       "batch_size": int(lote or p["lote"]),
                       "uniform_batch_size": True,
                       "color_correction": p["correcao_cor"],
                       "temporal_overlap": int(
                           p["sobreposicao_temporal"] if sobreposicao is None
                           else sobreposicao),
                       "prepend_frames": 0,
                       "input_noise_scale": 0.0, "latent_noise_scale": 0.0,
                       "offload_device": p["descarregar_para"],
                       "enable_debug": False}},
    }
    # O VideoCombine do VHS grava direto; nao passa pelo SaveVideo.
    #
    # ATENCAO a cadencia. A saida 1 do LoadVideoPath NAO e o fps: e a CONTAGEM
    # de quadros. Liguei ali por engano e um clipe de 73 quadros saiu com
    # 73 fps — tres segundos viraram um. O fps tem de vir de fora, medido do
    # arquivo de origem.
    g["salva"] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {"images": ["limpa", 0],
                   # So pede a saida de audio quando ela EXISTE. Pedi-la de um
                   # video mudo faz o proprio LoadVideoPath falhar, antes de
                   # qualquer processamento.
                   **({"audio": ["entrada", 2]} if com_audio else {}),
                   "frame_rate": float(fps),
                   "loop_count": 0,
                   "filename_prefix": prefixo,
                   # pix_fmt, crf e save_metadata NAO sao entradas do no:
                   # pertencem ao formato e a tela os monta a partir dele. No
                   # formato API o motor usa os padroes do proprio formato.
                   "format": "video/h264-mp4",
                   "pingpong": False,
                   "save_output": True}}
    return g


def previa_latente(caminho, fps=24, pular=0, quadros=25, prefixo="previa/latente"):
    """So o ida-e-volta pelo VAE do LTX, para ver o que o latente perde.

    Nao amplia e nao amostra: e exatamente a etapa que destroi o que for
    pequeno no quadro. O metodo de ampliacao no latente passa por aqui de
    qualquer jeito, entao o que sair daqui e o teto do que ele pode preservar.

    Carrega uma JANELA de quadros em vez do clipe inteiro (`skip_first_frames`
    + `frame_load_cap`): a resposta e a mesma e sai em poucos segundos, em vez
    dos 9 a 33 s de um clipe de 5 s. O minimo tem de passar de um pedaco
    temporal do VAE — abaixo disso a compressao no tempo nao tem o que fazer.
    """
    v = VIDEO_LTX
    p = VIDEO_AMPLIAR_LTX
    return {
        "vae_v": {"class_type": "VAELoader",
                  "inputs": {"vae_name": win(v["vae_video"])}},
        "entrada": {"class_type": "VHS_LoadVideoPath",
                    "inputs": {"video": caminho, "force_rate": 0,
                               "custom_width": 0, "custom_height": 0,
                               "frame_load_cap": int(quadros),
                               "skip_first_frames": int(pular),
                               "select_every_nth": 1}},
        "encode": {"class_type": "VAEEncodeTiled",
                   "inputs": {"pixels": ["entrada", 0], "vae": ["vae_v", 0],
                              "tile_size": p["ladrilho_vae"],
                              "overlap": p["sobreposicao_vae"],
                              "temporal_size": 64, "temporal_overlap": 8}},
        "decodifica": {"class_type": "VAEDecodeTiled",
                       "inputs": {"samples": ["encode", 0], "vae": ["vae_v", 0],
                                  "tile_size": p["ladrilho_vae"],
                                  "overlap": p["sobreposicao_vae"],
                                  "temporal_size": 64, "temporal_overlap": 16}},
        "salva": {"class_type": "VHS_VideoCombine",
                  "inputs": {"images": ["decodifica", 0],
                             "frame_rate": float(fps), "loop_count": 0,
                             "filename_prefix": prefixo,
                             "format": "video/h264-mp4",
                             "pingpong": False, "save_output": True}},
    }


def ampliar_video_ltx(caminho, seed, largura, altura, descricao="", fps=24,
                      com_audio=True, origem=None,
                      prefixo="video_ampliado"):
    """Amplia um video no LATENTE, com o proprio modelo do LTX 2.5.

    `caminho` e absoluto: o VHS_LoadVideoPath le do disco.
    `largura`/`altura` sao o ALVO — o dobro da origem e o caso natural, porque
    o modelo de upscale trabalha em 2x e depois redimensiona.

    Comparado ao SeedVR2 (`limpar_video`), que faz o mesmo trabalho em pixels:
    aqui o contexto temporal e de dezenas de quadros e o modelo entende o
    movimento, porque e o mesmo que gera video.

    TRES armadilhas, todas medidas — ver os comentarios em VIDEO_AMPLIAR_LTX:
    sem divisao espacial, sigmas baixos, e latente AUDIOVISUAL.
    """
    p, v = VIDEO_AMPLIAR_LTX, VIDEO_LTX
    # O VAE do LTX exige lados multiplos de 32. Os videos gerados aqui ja vem
    # alinhados; um enviado de fora (854x480, 20/10/2026) quebrava o
    # VAEEncodeTiled. O carregador leva a origem ao multiplo de 32 mais
    # proximo (854 -> 864); 0 deixa como esta.
    larg_o = alt_o = 0
    if origem:
        al = lambda x: max(32, round(x / 32) * 32)
        if origem[0] % 32 or origem[1] % 32:
            larg_o, alt_o = al(origem[0]), al(origem[1])
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(v["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(v["clip"]), "type": v["clip_type"],
                            "device": "default"}},
        "vae_v": {"class_type": "VAELoader",
                  "inputs": {"vae_name": win(v["vae_video"])}},
        "vae_a": {"class_type": "VAELoader",
                  "inputs": {"vae_name": win(v["vae_audio"])}},
        "upmodel": {"class_type": "LatentUpscaleModelLoader",
                    "inputs": {"model_name": win(v["upsampler"])}},

        "entrada": {"class_type": "VHS_LoadVideoPath",
                    "inputs": {"video": caminho, "force_rate": 0,
                               "custom_width": larg_o, "custom_height": alt_o,
                               "frame_load_cap": 0, "skip_first_frames": 0,
                               "select_every_nth": 1}},
        # Ladrilhado tambem na codificacao: um lote de mais de cem quadros de
        # uma vez estoura na conversao para latente.
        "encode_v": {"class_type": "VAEEncodeTiled",
                     "inputs": {"pixels": ["entrada", 0], "vae": ["vae_v", 0],
                                "tile_size": p["ladrilho_vae"],
                                "overlap": p["sobreposicao_vae"],
                                "temporal_size": 128, "temporal_overlap": 32}},
        # Blocos de tempo do VAE em 128/32 (codificar E decodificar). Com 64/8
        # cada emenda (a cada ~56 quadros) borrava e "fantasmava" rostos por
        # ~5 quadros: MEDIDO em 20/10/2026, 433 quadros, minimo 27 dB nas
        # emendas -> 31,6 dB sem queda, mesmo tempo, menos VRAM.
        # O no de ampliacao EXIGE latente audiovisual, entao um video mudo
        # nao pode simplesmente ficar sem o ramo: precisa de um latente de
        # audio SILENCIOSO, do mesmo comprimento. A contagem de quadros vem da
        # saida 1 do carregador — que e a contagem, nao o fps.
        "encode_a": ({"class_type": "LTXVAudioVAEEncode",
                      "inputs": {"audio": ["entrada", 2],
                                 "audio_vae": ["vae_a", 0]}}
                     if com_audio else
                     {"class_type": "LTXVEmptyLatentAudio",
                      "inputs": {"audio_vae": ["vae_a", 0],
                                 "frames_number": ["entrada", 1],
                                 "frame_rate": float(fps), "batch_size": 1}}),
        # O no EXIGE o latente audiovisual aninhado; recusa video puro.
        "av": {"class_type": "LTXVConcatAVLatent",
               "inputs": {"video_latent": ["encode_v", 0],
                          "audio_latent": ["encode_a", 0]}},

        # Uma descricao curta da cena da ancora ao refino. Sem texto o modelo
        # melhora no vazio e tende a inventar mais.
        "pos": {"class_type": "CLIPTextEncode",
                "inputs": {"clip": ["clip", 0],
                           "text": descricao or "sharp natural detail, "
                                                "realistic texture"}},
        "neg": {"class_type": "CLIPTextEncode",
                "inputs": {"clip": ["clip", 0], "text": v["negativo"]}},
        "cond": {"class_type": "LTXVConditioning",
                 "inputs": {"positive": ["pos", 0], "negative": ["neg", 0],
                            "frame_rate": fps}},

        "ruido": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "amostrador": {"class_type": "KSamplerSelect",
                       "inputs": {"sampler_name": v["sampler"]}},
        "sigmas": {"class_type": "ManualSigmas", "inputs": {"sigmas": p["sigmas"]}},

        "up_param": {"class_type": "LTX25LatentUpscaleParams",
                     "inputs": {"upscale_model": ["upmodel", 0],
                                "vae": ["vae_v", 0],
                                "width": int(largura), "height": int(altura)}},
        "temporal": {"class_type": "LTX25TemporalSplitParams",
                     "inputs": {"chunk_length": p["pedaco_temporal"],
                                "temporal_overlap": p["sobreposicao_temporal"],
                                "anchor_mode": p["ancora"],
                                "anchor_strength": p["forca_ancora"]}},

        # SEM spatial_split_param, de proposito. Ver VIDEO_AMPLIAR_LTX.
        "sobe": {"class_type": "LTX25UltimateUpscale",
                 "inputs": {"model": ["unet", 0], "conditioning": ["cond", 0],
                            "negative": ["cond", 1], "latent": ["av", 0],
                            "noise": ["ruido", 0], "sampler": ["amostrador", 0],
                            "sigmas": ["sigmas", 0], "cfg": p["cfg"],
                            "bypass_audio": True,
                            "latent_upscale_param": ["up_param", 0],
                            "temporal_split_param": ["temporal", 0]}},

        "separa": {"class_type": "LTXVSeparateAVLatent",
                   "inputs": {"av_latent": ["sobe", 0]}},
        "decodifica": {"class_type": "VAEDecodeTiled",
                       "inputs": {"samples": ["separa", 0], "vae": ["vae_v", 0],
                                  "tile_size": p["ladrilho_vae"],
                                  "overlap": p["sobreposicao_vae"],
                                  "temporal_size": 128, "temporal_overlap": 32}},
        # O audio volta do ARQUIVO, nao do latente: nao passou pelo modelo e
        # nao tem por que ser reconstruido.
        "salva": {"class_type": "VHS_VideoCombine",
                  "inputs": {"images": ["decodifica", 0],
                             **({"audio": ["entrada", 2]} if com_audio else {}),
                             "frame_rate": float(fps), "loop_count": 0,
                             "filename_prefix": prefixo,
                             "format": "video/h264-mp4",
                             "pingpong": False, "save_output": True}},
    }
    return g


def gerar_video_minimax_nuvem(prompt, seed, modo="texto", proporcao="16:9",
                              resolucao="480p", duracao=5, imagem=None,
                              imagem_final=None, prefixo="video"):
    """MiniMax H3 pelo Comfy Cloud. Nao usa a placa.

    Tres nos, um por modo, ao contrario do local — onde um no faz os tres.
    Por isso o `modo` escolhe a classe, em vez de so ligar ou nao os
    quadros-guia.

    O tamanho aqui e PROPORCAO + RESOLUCAO, nao pixels: o servidor decide as
    dimensoes finais. E a duracao vai em segundos direto, sem o alinhamento de
    17 que o modelo local exige — o servidor cuida disso.

    A chave de API nao aparece no grafo: viaja em extra_data, como nos demais
    nos de parceiro. Ver chaves.py.
    """
    p = VIDEO_MINIMAX_NUVEM
    classe = p["nos"].get(modo)
    if not classe:
        raise ValueError(f"modo desconhecido para a nuvem: {modo}")

    g = {}
    entradas = {"prompt": prompt, "seed": seed, "aspect_ratio": proporcao,
                "resolution": resolucao, "duration_seconds": int(duracao)}

    if modo in ("imagem", "primeiro_ultimo"):
        if not imagem:
            raise ValueError("este modo precisa da imagem de partida")
        g["img_ini"] = {"class_type": "LoadImage", "inputs": {"image": imagem}}
        entradas["first_frame"] = ["img_ini", 0]
    if modo == "primeiro_ultimo":
        if not imagem_final:
            raise ValueError("envie tambem o ultimo quadro")
        g["img_fim"] = {"class_type": "LoadImage", "inputs": {"image": imagem_final}}
        entradas["last_frame"] = ["img_fim", 0]

    g["nuvem"] = {"class_type": classe, "inputs": entradas}
    g["salva"] = {"class_type": "SaveVideo",
                  "inputs": {"video": ["nuvem", 0], "filename_prefix": prefixo,
                             "format": "auto", "codec": "auto"}}
    return g


def gerar_video_minimax_ref_nuvem(prompt, seed, referencias,
                                  variante="MiniMax H3", resolucao="768P",
                                  proporcao="adaptive", duracao=5,
                                  detalhe_ref=None, prefixo="video"):
    """Referencia por VARIAS imagens, no servidor da MiniMax. Nao usa a placa.

    Outra familia, nao os `ComfyCloudMiniMaxH3*` que ja usamos: aqueles fazem
    texto, imagem e primeiro+ultimo, e nenhum faz referencia.

    A TERCEIRA convencao de nome autogrow do mesmo projeto, e isto vale ser
    dito por extenso, porque ja me custou um teste:

        GPT Image        model.images.image_1          (base UM, sublinhado)
        Wan 3.0          model.reference_images.image1 (base UM, sem sublinhado)
        MiniMax local    ref_images.ref_image_0        (base ZERO)
        MiniMax nuvem    model.reference_images.image_1

    Nao ha regra a deduzir: cada no declara a sua, e o /prompt ACEITA nome
    errado calado quando ele cai fora do contrato do executor. So a fonte do
    no, ou o teste, dizem qual e.

    Os rotulos no prompt tambem mudam: o no LOCAL usa `<Picture 1>` e este usa
    `Image 1`. Mesmo modelo, duas gramaticas.
    """
    p = VIDEO_MINIMAX_REF_NUVEM
    refs = [r for r in (referencias or []) if r][:p["max_referencias"]]
    if not refs:
        raise ValueError("envie ao menos uma imagem de referência")
    if variante not in dict(p["variantes"]):
        variante = p["variante_padrao"]
    permitidas = p["resolucoes_por_variante"][variante]
    if resolucao not in permitidas:
        resolucao = permitidas[0]

    g = {}
    entradas = {
        "seed": int(seed) % 4294967296,
        "watermark": False,
        "model": variante,
        "model.prompt": prompt,
        "model.resolution": resolucao,
        "model.ratio": proporcao if proporcao in p["proporcoes"] else p["proporcao_padrao"],
        "model.duration": max(p["duracao_min"], min(p["duracao_max"], int(duracao))),
    }
    # DynamicCombo: os sub-campos do ramo escolhido vao TODOS, com o prefixo do
    # combo. O Topaz ja ensinou isso — faltando um, o motor recusa.
    if variante == "MiniMax H3 Max":
        entradas["model.reference_detail"] = detalhe_ref or p["detalhe_referencia"]
        entradas["model.prompt_expansion_mode"] = p["modo_expansao"]

    for i, nome in enumerate(refs):
        chave = "ref%d" % i
        g[chave] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        entradas["model.reference_images.image_%d" % (i + 1)] = [chave, 0]

    g["gera"] = {"class_type": p["no"], "inputs": entradas}
    # Este no devolve VIDEO pronto, nao quadros: nao ha CreateVideo aqui.
    g["salva"] = {"class_type": "SaveVideo",
                  "inputs": {"video": ["gera", 0], "filename_prefix": prefixo,
                             "format": "auto", "codec": "auto"}}
    return g


def gerar_video_wan3(prompt, seed, modo="imagem", variante="wan3.0-video",
                     resolucao="480P", proporcao="adaptive", duracao=5,
                     imagem=None, imagem_final=None, referencias=None,
                     com_audio=True, melhorar_prompt=True, prefixo="video"):
    """Wan 3.0 pelo Comfy Cloud.

    Dois nos: um para quadros-guia (primeiro e, opcionalmente, ultimo) e outro
    para REFERENCIA por varias imagens. O de guia EXIGE o primeiro quadro —
    nao ha texto para video neste modelo.

    `variante` escolhe entre o padrao e o "prime", que custa ~40% mais.

    ATENCAO ao prefixo: `model` e um DynamicCombo, entao tudo que pertence ao
    ramo escolhido vai com o nome dele na frente ("model.prompt"), e as
    referencias sao um Autogrow DENTRO dele
    ("model.reference_images.image1"). Mesma familia de armadilha do Topaz e
    do GPT Image.
    """
    p = VIDEO_WAN3
    classe = p["nos"].get(modo)
    if not classe:
        raise ValueError(f"o Wan 3.0 não tem o modo {modo}")
    if variante not in dict(p["variantes"]):
        variante = p["variante_padrao"]

    g = {}
    entradas = {
        "model": variante,
        "model.prompt": prompt,
        "model.resolution": resolucao,
        "model.ratio": proporcao,
        # A duracao vai como TEXTO: as opcoes do no sao strings, e "auto"
        # convive com os numeros na mesma lista.
        "model.duration": str(duracao),
        "model.audio": bool(com_audio),
        # O proprio servico enriquece o prompt. Deixado ligado por padrao,
        # como no no, mas exposto para quem escreveu a frase exata.
        "model.prompt_extend": bool(melhorar_prompt),
        # O no da Comfy recusa seed acima de 2^31-1 (como os outros nos de parceiro de video).
        "seed": seed % 2147483647,
        # Marca d'agua desligada: e uma peca do usuario, nao uma demonstracao.
        "watermark": False,
    }

    if modo in ("imagem", "primeiro_ultimo"):
        if not imagem:
            raise ValueError("o Wan 3.0 precisa do primeiro quadro")
        g["img_ini"] = {"class_type": "LoadImage", "inputs": {"image": imagem}}
        entradas["first_frame"] = ["img_ini", 0]
        if modo == "primeiro_ultimo":
            if not imagem_final:
                raise ValueError("envie tambem o ultimo quadro")
            g["img_fim"] = {"class_type": "LoadImage",
                            "inputs": {"image": imagem_final}}
            entradas["last_frame"] = ["img_fim", 0]
    else:
        refs = referencias or []
        if not refs:
            raise ValueError("envie ao menos uma imagem de referência")
        if len(refs) > p["max_referencias"]:
            raise ValueError(
                f'o Wan 3.0 aceita ate {p["max_referencias"]} referencias; '
                f"foram {len(refs)}")
        # Uma entrada por imagem, nomeadas image1..image10 pelo Autogrow.
        for i, nome in enumerate(refs, start=1):
            g[f"ref{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
            entradas[f"model.reference_images.image{i}"] = [f"ref{i}", 0]

    g["nuvem"] = {"class_type": classe, "inputs": entradas}
    g["salva"] = {"class_type": "SaveVideo",
                  "inputs": {"video": ["nuvem", 0], "filename_prefix": prefixo,
                             "format": "auto", "codec": "auto"}}
    return g


def girar_camera(referencia, yaw, elevation, distance, extra="", seed=0,
                 prefixo="edicao", previa=False):
    """Mostra a mesma pessoa de outro angulo (Krea 2 Anygles).

    TRES COISAS QUE NAO SAO OBVIAS NESTE GRAFO:

    1. O `Krea2AnyglesCameraNativo` NAO e do autor do LoRA — e nosso, em
       `custom_nodes/krea2-anygles-nativo`. O no publicado por ele faz a
       recuperacao da malha com a inferencia propria do SAM 3D Body, que exige
       o repositorio GATED da Meta inteiro (liberacao manual) mais MoGe,
       hydra e pytorch-lightning. O nosso pega a malha do `SAM3DBody_Predict`
       NATIVO — cujo checkpoint ja estava no disco — e chama o render DELES,
       sem alterar.

    2. `run_hand_refinement: False` nao e economia. O codigo do autor chama a
       inferencia com `inference_type="body"`, e no no nativo e essa chave que
       decide entre "body" e "full". Deixar o padrao `True` daria outra malha,
       parecida e diferente da que o LoRA viu no treino.

    3. A largura e a altura saem do PROPRIO no de camera, nao do pedido. Ele
       reenquadra para o corpo inteiro (`_base_fit`), entao um plano medio
       volta como plano aberto — comportamento do modelo, nao defeito.

    previa=True: so a malha do corpo vista da camera nova (`target_normal`, o
    mesmo guia que o modelo recebe), sem carregar o Krea nem amostrar. Segundos,
    e mostra o angulo exato antes de gerar.
    """
    p = EDICAO["anygles"]
    g = {
        "img": {"class_type": "LoadImage", "inputs": {"image": referencia}},

        "sam": {"class_type": "SAM3DBody_Loader",
                "inputs": {"model_file": win(p["sam3d"])}},
        "pose": {"class_type": "SAM3DBody_Predict",
                 "inputs": {"sam3d_body_model": ["sam", 0], "image": ["img", 0],
                            "run_hand_refinement": False, "fov": 0.0,
                            "batch_size": 64}},
        "cam": {"class_type": "Krea2AnyglesCameraNativo",
                "inputs": {"source": ["img", 0], "mhr_pose_data": ["pose", 0],
                           "yaw": float(yaw), "elevation": float(elevation),
                           "distance": float(distance),
                           "extra_prompt": extra or ""}},

    }
    if previa:
        g["salva"] = {"class_type": "SaveImage",
                      "inputs": {"images": ["cam", 1], "filename_prefix": prefixo + "_previa"}}
        return g
    g |= {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        # O LoRA NAO entra por um LoraLoader comum: ele carrega projecoes
        # espaciais que o carregador padrao descarta em silencio, e o
        # resultado sairia parecido com uma imagem normal, sem girar nada.
        "lora": {"class_type": "Krea2AnyglesLoadLoRA",
                 "inputs": {"model": ["unet", 0], "lora_name": win(p["lora"]),
                            "strength": 1.0}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},

        "cond": {"class_type": "Krea2AnyglesEncode",
                 "inputs": {"clip": ["clip", 0], "vae": ["vae", 0],
                            "prompt": ["cam", 2], "source": ["cam", 0],
                            "target_normal": ["cam", 1],
                            "reference_max_edge": p["referencia_max"],
                            "vlm_reference": True}},
        "patch": {"class_type": "Krea2AnyglesModelPatch",
                  "inputs": {"model": ["lora", 0], "anygles_control": ["cond", 1],
                             "anygles_projection": ["lora", 1], "kv_cache": True}},

        "latente": {"class_type": "EmptySD3LatentImage",
                    "inputs": {"width": ["cam", 3], "height": ["cam", 4],
                               "batch_size": 1}},
        "neg": {"class_type": "CLIPTextEncode",
                "inputs": {"clip": ["clip", 0], "text": ""}},
        "ks": {"class_type": "KSampler",
               "inputs": {"model": ["patch", 0], "positive": ["cond", 0],
                          "negative": ["neg", 0], "latent_image": ["latente", 0],
                          "seed": seed, "steps": p["steps"], "cfg": p["cfg"],
                          "sampler_name": p["sampler"], "scheduler": p["scheduler"],
                          "denoise": 1.0}},
        "dec": {"class_type": "VAEDecode",
                "inputs": {"samples": ["ks", 0], "vae": ["vae", 0]}},
        "salva": {"class_type": "SaveImage",
                  "inputs": {"images": ["dec", 0], "filename_prefix": prefixo}},
    }
    return g


def medir_rotacao_corpo(referencia):
    """Grafo que so mede quantos graus o corpo ja esta virado na foto (saida
    `body_yaw` do no de camera, num PreviewAny). O valor e o giro que poe a
    pessoa de frente para a camera."""
    g = girar_camera(referencia, 0.0, 0.0, 1.0, previa=True)
    g["salva"] = {"class_type": "PreviewAny", "inputs": {"source": ["cam", 5]}}
    return g


def editar_qwen21(instrucao, referencias, seed, steps=None, cfg=None,
                  prefixo="edicao", mascara=None, largura=0, altura=0):
    """Edicao por instrucao com o Qwen Image 2.1.

    TRES COISAS LIDAS DO TEMPLATE OFICIAL, nao deduzidas:

    1. O `TextEncodeQwenImage21` devolve TRES saidas: positivo, negativo e um
       LATENTE. Na edicao o latente vem dele — e a referencia codificada — e
       NAO de um EmptyLatentImage. Trocar isso gera "outra imagem parecida" em
       vez de editar a que entrou.

    2. As referencias entram por autogrow com a grafia `images.image_N`, base
       UM. Neste projeto ja houve quatro grafias diferentes de autogrow entre
       nos; esta foi lida do template, no `names`.

    3. O `QwenImage21Cache` fica entre a UNET e o amostrador. Ele guarda o
       calculo das referencias, e e o que torna a segunda referencia barata:
       21 s com uma, 27 s com duas.

    Com largura e altura de uma proporcao DIFERENTE da imagem 1, o latente vem de
    um EmptyLatentImage nesse tamanho: a foto guia o conteudo e a proporcao e a
    escolhida (o latente da referencia teria o formato da foto). Na mesma
    proporcao (ou sem tamanho) fica o latente da referencia, para editar a foto.
    """
    p = EDICAO["qwen21edit"]
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
        "cache": {"class_type": "QwenImage21Cache",
                  "inputs": {"model": ["unet", 0], "device": "auto",
                             "dtype": "default"}},
    }
    imagens = {}
    for i, nome in enumerate(referencias[:p["max_referencias"]], start=1):
        g["img%d" % i] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        imagens["images.image_%d" % i] = ["img%d" % i, 0]

    g["cond"] = {"class_type": "TextEncodeQwenImage21",
                 "inputs": {"clip": ["clip", 0], "vae": ["vae", 0],
                            "prompt": instrucao, "negative_prompt": "",
                            "resolution": p["resolucao_referencia"], **imagens}}
    if largura and altura:
        g["vazio"] = {"class_type": "EmptyLatentImage",
                      "inputs": {"width": largura, "height": altura, "batch_size": 1}}
    g["amostra"] = {"class_type": "KSampler",
                    "inputs": {"model": ["cache", 0], "positive": ["cond", 0],
                               "negative": ["cond", 1],
                               "latent_image": ["vazio", 0] if largura and altura else ["cond", 2],
                               "seed": seed,
                               "steps": steps or p["steps"],
                               "cfg": cfg if cfg is not None else p["cfg"],
                               "sampler_name": p["sampler"],
                               "scheduler": p["scheduler"], "denoise": 1.0}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["amostra", 0], "vae": ["vae", 0]}}
    if mascara:
        # O _aplicar_mascara ja grava o "salva" (o composto); devolver o grafo dele.
        # Antes o retorno virava "o no a salvar" e o ComfyUI acusava referencia circular.
        return _aplicar_mascara(g, "img1", "decodifica", mascara, prefixo)
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}}
    return g


def validar_magnific(largura, altura, escala):
    if escala not in (2, 4, 8, 16):
        raise ValueError("Magnific aceita escalas 2×, 4×, 8× e 16×")
    if not largura or not altura or min(largura, altura) < 160:
        raise ValueError("Magnific exige pelo menos 160 pixels em cada lado")
    if not 1 / 3 <= largura / altura <= 3:
        raise ValueError("Magnific aceita proporções entre 1:3 e 3:1")
    if largura * altura * escala ** 2 > 25_300_000:
        raise ValueError("A saída ultrapassa 25,3 MP. Reduza a escala ou a imagem")


def ampliar_magnific(imagem, escala=2, prompt="", criatividade=0, hdr=0,
                     semelhanca=0, fractalidade=0, prefixo="editor/ampliar"):
    if escala not in (2, 4, 8, 16):
        raise ValueError("Escala inválida para Magnific")
    return {
        "img": {"class_type": "LoadImage", "inputs": {"image": imagem}},
        "nuvem": {"class_type": "MagnificImageUpscalerCreativeNode", "inputs": {
            "image": ["img", 0], "prompt": prompt,
            "scale_factor": f"{int(escala)}x", "optimized_for": "standard",
            "creativity": criatividade, "hdr": hdr, "resemblance": semelhanca,
            "fractality": fractalidade, "engine": "automatic", "auto_downscale": False}},
        "salva": {"class_type": "SaveImage", "inputs": {
            "images": ["nuvem", 0], "filename_prefix": prefixo}},
    }


def editar_flux3(prompt, refs, seed, steps=25, cfg=3.5, prefixo="saida", largura=0, altura=0):
    """Flux 3 Image Klein com referencias, como o template oficial
    image_flux3_klein_image_edit: as imagens entram no ReferenceMultiLatent,
    que tambem devolve o latente vazio no tamanho da primeira (~1 MP).
    Com largura e altura (a proporcao escolhida), o latente vem do
    EmptyFlux2LatentImage nesse tamanho e a foto so guia o conteudo."""
    p = EDICAO["flux3ref"]
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": "flux3",
                            "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae"])}},
    }
    _texto(g, "pos", "clip", prompt)
    _texto(g, "neg", "clip", "")
    refer = {"positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
             "resolution": "resize", "resolution.megapixels": 1.0}
    for i, nome in enumerate(refs):
        g[f"ref{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        refer[f"images.image{i}"] = [f"ref{i}", 0]
    g["refs"] = {"class_type": "ReferenceMultiLatent", "inputs": refer}
    if largura and altura:
        g["lat"] = {"class_type": "EmptyFlux2LatentImage",
                    "inputs": {"width": largura, "height": altura, "batch_size": 1}}
    g["amostra"] = {"class_type": "KSampler",
                    "inputs": {"model": ["unet", 0], "positive": ["refs", 0],
                               "negative": ["refs", 1],
                               "latent_image": ["lat", 0] if largura and altura else ["refs", 2],
                               "seed": seed, "steps": steps, "cfg": cfg,
                               "sampler_name": "euler", "scheduler": "simple",
                               "denoise": 1.0}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["amostra", 0], "vae": ["vae", 0]}}
    g["salva"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["decodifica", 0], "filename_prefix": prefixo}}
    return g


def video_rtx(entrada, metodo, largura=0, altura=0, prefixo="editor/video_rtx"):
    """Nos RTX da NVIDIA sobre um video da pasta de entrada.

    "rtx": Super Resolution para largura x altura, qualidade ULTRA.
    "rtx48": Frame Generation 2x; o fps de saida e o dobro do de entrada.
    O audio original passa intacto.
    """
    g = {"carga": {"class_type": "LoadVideo", "inputs": {"file": entrada}},
         "partes": {"class_type": "GetVideoComponents", "inputs": {"video": ["carga", 0]}}}
    if metodo == "rtx":
        g["fx"] = {"class_type": "RTXVideoSuperResolution", "inputs": {
            "images": ["partes", 0], "resize_type": "target dimensions",
            "resize_type.width": largura, "resize_type.height": altura,
            "quality": "ULTRA", "strength": 1.0, "image_encoding": "8-bit RGB"}}
        fps = ["partes", 2]
    else:
        g["fx"] = {"class_type": "RTXVideoFrameGeneration", "inputs": {
            "images": ["partes", 0], "generation_type": "frame rate multiplier",
            "generation_type.multiplier": 2, "mode": "HIGH",
            "automatic_shot_change_detection": True, "shot_change": False,
            "image_encoding": "8-bit RGB"}}
        g["fps"] = {"class_type": "ComfyMathExpression",
                    "inputs": {"expression": "a*2", "values.a": ["partes", 2]}}
        fps = ["fps", 0]
    g["video"] = {"class_type": "CreateVideo", "inputs": {
        "images": ["fx", 0], "fps": fps, "audio": ["partes", 1],
        "bit_depth": "auto", "color_space": "sRGB", "codec": "none"}}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {
        "video": ["video", 0], "filename_prefix": prefixo,
        "format": "auto", "format.codec": "auto", "codec": "auto"}}
    return g


# Decodificacao do LTX: o video inteiro numa peca so no tempo; so os ladrilhos
# ESPACIAIS (512) poupam VRAM. Com pedacos de 64 quadros e 8 de sobreposicao,
# os primeiros quadros de cada pedaco saiam moles: MEDIDO em 23/10/2026, a
# nitidez (variancia do laplaciano) caia ate 47% nos quadros 56 e 112 da troca
# de personagem e 11-27% nos VFX. 4096 e o que o template oficial do LTX 2.3
# (Lip Sync, grafos/ltx23_ia2v.json) ja usa, testado com 30 s em 1280x704.
TEMPORAL_LTX = (4096, 4)


def transformar_video(entrada, lora, texto, quadros, largura, altura, seed=42,
                      com_audio=True, prefixo="editor/video_transformado"):
    """IC-LoRA do LTX 2.5 Creative Lab sobre um video da pasta de entrada.

    Molde do exemplo LTX-2.5_V2V_ICLoRA_Single_Stage_Distilled da Lightricks,
    com os pesos INT8 que o app ja usa. O modelo gera audio junto (o LTX e
    audio+video), mas o que sai no arquivo e o audio ORIGINAL do video.
    """
    p = VIDEO_LTX
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "lora": {"class_type": "LTXICLoRALoaderModelOnly",
                 "inputs": {"model": ["unet", 0], "lora_name": win(lora), "strength_model": 1.0}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"], "device": "default"}},
        "vae_v": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_video"])}},
        "vae_a": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_audio"])}},
        "carga": {"class_type": "LoadVideo", "inputs": {"file": entrada}},
        "partes": {"class_type": "GetVideoComponents", "inputs": {"video": ["carga", 0]}},
        "corte": {"class_type": "ImageFromBatch",
                  "inputs": {"image": ["partes", 0], "batch_index": 0, "length": quadros}},
        "tam": {"class_type": "ResizeImageMaskNode", "inputs": {
            "input": ["corte", 0], "resize_type": "scale dimensions",
            "resize_type.width": largura, "resize_type.height": altura,
            "resize_type.crop": "center", "scale_method": "lanczos"}},
    }
    _texto(g, "pos", "clip", texto)
    _texto(g, "neg", "clip", "")
    g["cond"] = {"class_type": "LTXVConditioning", "inputs": {
        "positive": ["pos", 0], "negative": ["neg", 0], "frame_rate": ["partes", 2]}}
    g["vazio"] = {"class_type": "EmptyLTXVLatentVideo", "inputs": {
        "width": largura, "height": altura, "length": quadros, "batch_size": 1}}
    g["guia"] = {"class_type": "LTXAddVideoICLoRAGuide", "inputs": {
        "positive": ["cond", 0], "negative": ["cond", 1], "vae": ["vae_v", 0],
        "latent": ["vazio", 0], "image": ["tam", 0], "frame_idx": 0, "strength": 1.0,
        "latent_downscale_factor": ["lora", 1], "crop": "disabled",
        "use_tiled_encode": False, "tile_size": 256, "tile_overlap": 64,
        "use_streaming": False, "tile_frames": 97}}
    ultima = "guia"
    g["som"] = {"class_type": "LTXVEmptyLatentAudio", "inputs": {
        "frames_number": quadros, "frame_rate": ["partes", 2], "batch_size": 1,
        "audio_vae": ["vae_a", 0]}}
    g["av"] = {"class_type": "LTXVConcatAVLatent", "inputs": {
        "video_latent": [ultima, 2], "audio_latent": ["som", 0]}}
    g["guiador"] = {"class_type": "CFGGuider", "inputs": {
        "model": ["lora", 0], "positive": [ultima, 0], "negative": [ultima, 1], "cfg": 1}}
    g["ruido"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["amostrador"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}}
    g["sigmas"] = {"class_type": "ManualSigmas", "inputs": {
        "sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}}
    g["amostra"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["ruido", 0], "guider": ["guiador", 0], "sampler": ["amostrador", 0],
        "sigmas": ["sigmas", 0], "latent_image": ["av", 0]}}
    g["separa"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["amostra", 0]}}
    g["tira_guia"] = {"class_type": "LTXVCropGuides", "inputs": {
        "positive": [ultima, 0], "negative": [ultima, 1], "latent": ["separa", 0]}}
    g["decodifica"] = {"class_type": "VAEDecodeTiled", "inputs": {
        "samples": ["tira_guia", 2], "vae": ["vae_v", 0], "tile_size": 512,
        "overlap": 64, "temporal_size": TEMPORAL_LTX[0], "temporal_overlap": TEMPORAL_LTX[1]}}
    video = {"images": ["decodifica", 0], "fps": ["partes", 2], "bit_depth": "auto",
             "color_space": "sRGB", "codec": "none"}
    if com_audio:
        video["audio"] = ["partes", 1]
    g["video"] = {"class_type": "CreateVideo", "inputs": video}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {
        "video": ["video", 0], "filename_prefix": prefixo,
        "format": "auto", "format.codec": "auto", "codec": "auto"}}
    return g


def aplicar_camera_lenta(g, velocidade):
    """Poe o LoRA Slow-Motion-Control num grafo do LTX 2.5 ja montado.

    O LoRA entra logo depois do UNETLoader, e todo condicionamento passa a
    dizer fps / velocidade ao modelo. Ver CAMERA_LENTA em presets.
    """
    from presets import CAMERA_LENTA
    unet = next(k for k, v in g.items() if v["class_type"] == "UNETLoader")
    g["camera_lenta"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": [unet, 0], "lora_name": win(CAMERA_LENTA["lora"]), "strength_model": 1.0}}
    for k, v in g.items():
        if k == "camera_lenta":
            continue
        for e, x in v["inputs"].items():
            if x == [unet, 0]:
                v["inputs"][e] = ["camera_lenta", 0]
    for v in g.values():
        if v["class_type"] == "LTXVConditioning":
            v["inputs"]["frame_rate"] = round(float(v["inputs"]["frame_rate"]) / velocidade, 3)
    return g


def ingredientes_ltx(folha, texto, quadros, largura, altura, seed=42, fps=24,
                     prefixo="editor/video_ingredientes"):
    """IC-LoRA Ingredients: a folha (uma imagem) e repetida em todos os quadros
    e entra como guia; o modelo gera um video novo com aqueles elementos. O som
    e gerado junto. Ver INGREDIENTES em presets."""
    from presets import INGREDIENTES
    p = VIDEO_LTX
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "lora": {"class_type": "LTXICLoRALoaderModelOnly", "inputs": {
            "model": ["unet", 0], "lora_name": win(INGREDIENTES["lora"]),
            "strength_model": INGREDIENTES["forca"]}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"], "device": "default"}},
        "vae_v": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_video"])}},
        "vae_a": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_audio"])}},
        "folha": {"class_type": "LoadImage", "inputs": {"image": folha}},
        "repete": {"class_type": "RepeatImageBatch", "inputs": {"image": ["folha", 0], "amount": quadros}},
    }
    _texto(g, "pos", "clip", texto)
    _texto(g, "neg", "clip", "")
    g["cond"] = {"class_type": "LTXVConditioning", "inputs": {
        "positive": ["pos", 0], "negative": ["neg", 0], "frame_rate": fps}}
    g["vazio"] = {"class_type": "EmptyLTXVLatentVideo", "inputs": {
        "width": largura, "height": altura, "length": quadros, "batch_size": 1}}
    g["guia"] = {"class_type": "LTXAddVideoICLoRAGuide", "inputs": {
        "positive": ["cond", 0], "negative": ["cond", 1], "vae": ["vae_v", 0],
        "latent": ["vazio", 0], "image": ["repete", 0], "frame_idx": 0, "strength": 1.0,
        "latent_downscale_factor": ["lora", 1], "crop": "disabled",
        "use_tiled_encode": False, "tile_size": 256, "tile_overlap": 64,
        "use_streaming": False, "tile_frames": 97}}
    g["som"] = {"class_type": "LTXVEmptyLatentAudio", "inputs": {
        "frames_number": quadros, "frame_rate": fps, "batch_size": 1, "audio_vae": ["vae_a", 0]}}
    g["av"] = {"class_type": "LTXVConcatAVLatent", "inputs": {
        "video_latent": ["guia", 2], "audio_latent": ["som", 0]}}
    g["guiador"] = {"class_type": "CFGGuider", "inputs": {
        "model": ["lora", 0], "positive": ["guia", 0], "negative": ["guia", 1], "cfg": 1}}
    g["ruido"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["amostrador"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}}
    g["sigmas"] = {"class_type": "ManualSigmas", "inputs": {
        "sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}}
    g["amostra"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["ruido", 0], "guider": ["guiador", 0], "sampler": ["amostrador", 0],
        "sigmas": ["sigmas", 0], "latent_image": ["av", 0]}}
    g["separa"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["amostra", 0]}}
    g["tira_guia"] = {"class_type": "LTXVCropGuides", "inputs": {
        "positive": ["guia", 0], "negative": ["guia", 1], "latent": ["separa", 0]}}
    g["decodifica"] = {"class_type": "VAEDecodeTiled", "inputs": {
        "samples": ["tira_guia", 2], "vae": ["vae_v", 0], "tile_size": 512,
        "overlap": 64, "temporal_size": TEMPORAL_LTX[0], "temporal_overlap": TEMPORAL_LTX[1]}}
    g["somdec"] = {"class_type": "LTXVAudioVAEDecode", "inputs": {
        "samples": ["separa", 1], "audio_vae": ["vae_a", 0]}}
    g["video"] = {"class_type": "CreateVideo", "inputs": {
        "images": ["decodifica", 0], "fps": fps, "audio": ["somdec", 0],
        "bit_depth": "auto", "color_space": "sRGB", "codec": "none"}}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {
        "video": ["video", 0], "filename_prefix": prefixo,
        "format": "auto", "format.codec": "auto", "codec": "auto"}}
    return g


def montar_folha(imagens: list[bytes], largura: int, altura: int) -> bytes:
    """As imagens lado a lado (video deitado) ou empilhadas (em pe), cada uma
    inteira na sua celula, sobre fundo escuro. Devolve o PNG."""
    import cv2
    import numpy as np
    folha = np.full((altura, largura, 3), 16, np.uint8)
    n = len(imagens)
    deitado = largura >= altura
    for i, dados in enumerate(imagens):
        im = cv2.imdecode(np.frombuffer(dados, np.uint8), cv2.IMREAD_COLOR)
        if deitado:
            x0, x1, y0, y1 = largura * i // n, largura * (i + 1) // n, 0, altura
        else:
            x0, x1, y0, y1 = 0, largura, altura * i // n, altura * (i + 1) // n
        cw, ch = x1 - x0, y1 - y0
        f = min(cw / im.shape[1], ch / im.shape[0])
        w, h = max(1, int(im.shape[1] * f)), max(1, int(im.shape[0] * f))
        im = cv2.resize(im, (w, h), interpolation=cv2.INTER_AREA)
        ox, oy = x0 + (cw - w) // 2, y0 + (ch - h) // 2
        folha[oy:oy + h, ox:ox + w] = im
    ok, png = cv2.imencode(".png", folha)
    return png.tobytes()


def maquete_ltx(entrada, lora, texto, quadros, largura, altura, estilo, chaves=(),
                seed=42, com_audio=True, prefixo="editor/video_maquete", inicio=0):
    """Layout-To-Render em DUAS etapas, como o fluxo oficial da Lightricks
    (LTX-2.5_ICLoRA_Layout_To_Render_Two_Stage_Distilled).

    Etapa 1 em meia resolucao (8 passos); etapa 2 amplia o latente 2x,
    REAPLICA os guias e refina em 3 passos. Os guias sao a maquete (posicao 0),
    a imagem de estilo (-1) e os quadros-chave opcionais (meio e fim).
    MEDIDO em 17/10/2026: em uma etapa so, os quadros-chave nao mudavam nada;
    em duas, aproximaram o resultado do alvo em ~3 dB nas duas posicoes.
    `largura` e `altura` sao da saida e precisam ser multiplos de 64.
    """
    p = VIDEO_LTX
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "lora": {"class_type": "LTXICLoRALoaderModelOnly", "inputs": {
            "model": ["unet", 0], "lora_name": win(lora), "strength_model": 1.0}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"], "device": "default"}},
        "vae_v": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_video"])}},
        "vae_a": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_audio"])}},
        "ups": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": win(p["upsampler"])}},
        "carga": {"class_type": "LoadVideo", "inputs": {"file": entrada}},
        "partes": {"class_type": "GetVideoComponents", "inputs": {"video": ["carga", 0]}},
        # inicio: o trecho de ate 14,7 s que a pessoa escolheu no render (quadro, contado de 0).
        "corte": {"class_type": "ImageFromBatch", "inputs": {"image": ["partes", 0], "batch_index": inicio, "length": quadros}},
        "tam": {"class_type": "ResizeImageMaskNode", "inputs": {
            "input": ["corte", 0], "resize_type": "scale dimensions", "resize_type.width": largura,
            "resize_type.height": altura, "resize_type.crop": "center", "scale_method": "lanczos"}},
        "estilo": {"class_type": "LoadImage", "inputs": {"image": estilo}},
        "cond": {"class_type": "LTXVConditioning", "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "frame_rate": 24}},
        "vazio": {"class_type": "EmptyLTXVLatentVideo", "inputs": {
            "width": largura // 2, "height": altura // 2, "length": quadros, "batch_size": 1}},
        "som": {"class_type": "LTXVEmptyLatentAudio", "inputs": {
            "frames_number": quadros, "frame_rate": 24, "batch_size": 1, "audio_vae": ["vae_a", 0]}},
    }
    _texto(g, "pos", "clip", texto)
    _texto(g, "neg", "clip", "")
    for i, (nome, _) in enumerate(chaves):
        g[f"chave{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}

    # Acima de ~1 MP (o teste de 1080p) os guias sao codificados em ladrilhos: a maquete
    # inteira de uma vez nao caberia junto com o modelo na placa de 16 GB.
    ladrilhos = largura * altura > 1024 * 576 * 2

    def guias(suf, pos, neg, latente):
        base = {"vae": ["vae_v", 0], "strength": 1.0, "latent_downscale_factor": ["lora", 1],
                "use_tiled_encode": ladrilhos, "tile_size": 256, "tile_overlap": 64,
                "use_streaming": False, "tile_frames": 97}
        g[f"g_maq{suf}"] = {"class_type": "LTXAddVideoICLoRAGuide", "inputs": {**base,
            "positive": pos, "negative": neg, "latent": latente, "image": ["tam", 0],
            "frame_idx": 0, "crop": "disabled"}}
        ult = f"g_maq{suf}"
        for nome_no, imagem, posicao in ([(f"g_est{suf}", ["estilo", 0], -1)]
                                         + [(f"g_ch{i}{suf}", [f"chave{i}", 0], q)
                                            for i, (_, q) in enumerate(chaves)]):
            g[nome_no] = {"class_type": "LTXAddVideoICLoRAGuide", "inputs": {**base,
                "positive": [ult, 0], "negative": [ult, 1], "latent": [ult, 2], "image": imagem,
                "frame_idx": posicao, "crop": "center"}}
            ult = nome_no
        return ult

    def amostrar(suf, ult, latente_av, sigmas, semente):
        g[f"guiador{suf}"] = {"class_type": "CFGGuider", "inputs": {
            "model": ["lora", 0], "positive": [ult, 0], "negative": [ult, 1], "cfg": 1}}
        g[f"ruido{suf}"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": semente}}
        g[f"amostrador{suf}"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}}
        g[f"sigmas{suf}"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}}
        g[f"amostra{suf}"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": [f"ruido{suf}", 0], "guider": [f"guiador{suf}", 0], "sampler": [f"amostrador{suf}", 0],
            "sigmas": [f"sigmas{suf}", 0], "latent_image": latente_av}}
        g[f"separa{suf}"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": [f"amostra{suf}", 0]}}
        g[f"tira{suf}"] = {"class_type": "LTXVCropGuides", "inputs": {
            "positive": [ult, 0], "negative": [ult, 1], "latent": [f"separa{suf}", 0]}}

    u1 = guias("1", ["cond", 0], ["cond", 1], ["vazio", 0])
    g["av1"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": [u1, 2], "audio_latent": ["som", 0]}}
    amostrar("1", u1, ["av1", 0], "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0", seed)
    g["amplia"] = {"class_type": "LTXVLatentUpsampler", "inputs": {
        "samples": ["tira1", 2], "upscale_model": ["ups", 0], "vae": ["vae_v", 0]}}
    u2 = guias("2", ["tira1", 0], ["tira1", 1], ["amplia", 0])
    g["av2"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": [u2, 2], "audio_latent": ["separa1", 1]}}
    amostrar("2", u2, ["av2", 0], "0.909375, 0.725, 0.421875, 0.0", seed + 1)
    # O video inteiro de uma vez (TEMPORAL_LTX) estourou a memoria aqui em 28/10
    # (12,97 GiB ocupados + 2,2 pedidos): os guias de quadro-chave e a imagem de
    # estilo ficam na placa. Em fatias de 192 quadros, como no MSR.
    g["decodifica"] = {"class_type": "VAEDecodeTiled", "inputs": {
        "samples": ["tira2", 2], "vae": ["vae_v", 0], "tile_size": 512, "overlap": 64,
        "temporal_size": 192, "temporal_overlap": 48}}
    video = {"images": ["decodifica", 0], "fps": 24, "bit_depth": "auto", "color_space": "sRGB", "codec": "none"}
    if com_audio:
        video["audio"] = ["partes", 1]
    g["video"] = {"class_type": "CreateVideo", "inputs": video}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {
        "video": ["video", 0], "filename_prefix": prefixo, "format": "auto", "format.codec": "auto", "codec": "auto"}}
    return g


def trocar_personagem_video(entrada, lora, texto, quadros, largura, altura, primeiro,
                      controle="pose", seed=42, com_audio=True,
                      prefixo="editor/video_trocar"):
    """Troca de personagem com o IC-LoRA Union Control, molde do exemplo oficial
    LTX-2.5_ICLoRA_Union_Control_Distilled: o video vira um sinal de controle
    (pose DWPose, profundidade Video-Depth-Anything ou contornos Canny), e o
    primeiro quadro (ja com o personagem novo) fica preso nas duas etapas.
    Etapa 2 amplia 2x e refina SEM reaplicar o controle, como o oficial.
    `largura`/`altura` multiplos de 128 (ver tamanho_troca)."""
    p = VIDEO_LTX
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "lora": {"class_type": "LTXICLoRALoaderModelOnly", "inputs": {"model": ["unet", 0], "lora_name": win(lora), "strength_model": 1.0}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"], "device": "default"}},
        "vae_v": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_video"])}},
        "vae_a": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_audio"])}},
        "ups": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": win(p["upsampler"])}},
        "carga": {"class_type": "LoadVideo", "inputs": {"file": entrada}},
        "partes": {"class_type": "GetVideoComponents", "inputs": {"video": ["carga", 0]}},
        "corte": {"class_type": "ImageFromBatch", "inputs": {"image": ["partes", 0], "batch_index": 0, "length": quadros}},
        "tam": {"class_type": "ResizeImageMaskNode", "inputs": {"input": ["corte", 0], "resize_type": "scale dimensions",
                "resize_type.width": largura, "resize_type.height": altura, "resize_type.crop": "center", "scale_method": "lanczos"}},
        "q1": {"class_type": "LoadImage", "inputs": {"image": primeiro}},
        "q1_tam": {"class_type": "ResizeImageMaskNode", "inputs": {"input": ["q1", 0], "resize_type": "scale dimensions",
                   "resize_type.width": largura, "resize_type.height": altura, "resize_type.crop": "center", "scale_method": "lanczos"}},
        "cond": {"class_type": "LTXVConditioning", "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "frame_rate": 24}},
        "vazio": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": largura // 2, "height": altura // 2, "length": quadros, "batch_size": 1}},
        "som": {"class_type": "LTXVEmptyLatentAudio", "inputs": {"frames_number": quadros, "frame_rate": 24, "batch_size": 1, "audio_vae": ["vae_a", 0]}},
    }
    _texto(g, "pos", "clip", texto)
    _texto(g, "neg", "clip", "")
    if controle == "pronto":
        # O video JA e o sinal (ex.: passe de profundidade do Blender).
        g["sinal"] = {"class_type": "ImageFromBatch", "inputs": {"image": ["tam", 0], "batch_index": 0, "length": quadros}}
    elif controle == "pose":
        # Modelos ONNX copiados para o v0.41 (o TorchScript tentava baixar e falhava).
        g["sinal"] = {"class_type": "DWPreprocessor", "inputs": {"image": ["tam", 0], "detect_hand": "enable",
            "detect_body": "enable", "detect_face": "enable", "resolution": 512, "bbox_detector": "yolox_l.onnx",
            "pose_estimator": "dw-ll_ucoco_384.onnx", "scale_stick_for_xinsr_cn": "disable"}}
    elif controle == "contornos":
        g["sinal"] = {"class_type": "CannyEdgePreprocessor", "inputs": {
            "image": ["tam", 0], "low_threshold": 92, "high_threshold": 200, "resolution": 512}}
    else:
        g["dmodelo"] = {"class_type": "LoadVideoDepthAnythingModel", "inputs": {"model": "video_depth_anything_vits.pth"}}
        g["dproc"] = {"class_type": "VideoDepthAnythingProcess", "inputs": {"vda_model": ["dmodelo", 0], "images": ["tam", 0],
            "input_size": 518, "max_res": 960, "precision": "fp16"}}
        g["sinal"] = {"class_type": "VideoDepthAnythingOutput", "inputs": {"depths": ["dproc", 0], "colormap": "gray"}}
    g["sinal_tam"] = {"class_type": "ResizeImageMaskNode", "inputs": {"input": ["sinal", 0], "resize_type": "scale dimensions",
        "resize_type.width": largura, "resize_type.height": altura, "resize_type.crop": "center", "scale_method": "lanczos"}}
    # Sem primeiro quadro (so no "Seguir mapa de profundidade"), a aparencia vem
    # so do texto: o latente vazio vai direto para a guia.
    if primeiro:
        g["inplace1"] = {"class_type": "LTXVImgToVideoInplace", "inputs": {"vae": ["vae_v", 0], "image": ["q1_tam", 0],
            "latent": ["vazio", 0], "strength": 1.0, "bypass": False}}
    else:
        for no in ("q1", "q1_tam"):
            del g[no]
    g["guia"] = {"class_type": "LTXAddVideoICLoRAGuide", "inputs": {"positive": ["cond", 0], "negative": ["cond", 1],
        "vae": ["vae_v", 0], "latent": ["inplace1" if primeiro else "vazio", 0], "image": ["sinal_tam", 0], "frame_idx": 0, "strength": 1.0,
        "latent_downscale_factor": ["lora", 1], "crop": "disabled", "use_tiled_encode": False, "tile_size": 256,
        "tile_overlap": 64, "use_streaming": False, "tile_frames": 97}}
    g["av1"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["guia", 2], "audio_latent": ["som", 0]}}

    def amostrar(suf, pos, neg, latente, sigmas, semente):
        g[f"guiador{suf}"] = {"class_type": "CFGGuider", "inputs": {"model": ["lora", 0], "positive": pos, "negative": neg, "cfg": 1}}
        g[f"ruido{suf}"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": semente}}
        g[f"amostrador{suf}"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}}
        g[f"sigmas{suf}"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}}
        g[f"amostra{suf}"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": [f"ruido{suf}", 0],
            "guider": [f"guiador{suf}", 0], "sampler": [f"amostrador{suf}", 0], "sigmas": [f"sigmas{suf}", 0], "latent_image": latente}}
        g[f"separa{suf}"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": [f"amostra{suf}", 0]}}

    amostrar("1", ["guia", 0], ["guia", 1], ["av1", 0], "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0", seed)
    g["tira1"] = {"class_type": "LTXVCropGuides", "inputs": {"positive": ["guia", 0], "negative": ["guia", 1], "latent": ["separa1", 0]}}
    g["amplia"] = {"class_type": "LTXVLatentUpsampler", "inputs": {"samples": ["tira1", 2], "upscale_model": ["ups", 0], "vae": ["vae_v", 0]}}
    if primeiro:
        g["inplace2"] = {"class_type": "LTXVImgToVideoInplace", "inputs": {"vae": ["vae_v", 0], "image": ["q1_tam", 0],
            "latent": ["amplia", 0], "strength": 1.0, "bypass": False}}
    g["av2"] = {"class_type": "LTXVConcatAVLatent", "inputs": {
        "video_latent": ["inplace2" if primeiro else "amplia", 0], "audio_latent": ["separa1", 1]}}
    amostrar("2", ["tira1", 0], ["tira1", 1], ["av2", 0], "0.909375, 0.725, 0.421875, 0.0", seed + 1)
    g["decodifica"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["separa2", 0], "vae": ["vae_v", 0],
                       "tile_size": 512, "overlap": 64, "temporal_size": TEMPORAL_LTX[0], "temporal_overlap": TEMPORAL_LTX[1]}}
    video = {"images": ["decodifica", 0], "fps": 24, "bit_depth": "auto", "color_space": "sRGB", "codec": "none"}
    if com_audio:
        video["audio"] = ["partes", 1]
    g["video"] = {"class_type": "CreateVideo", "inputs": video}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {"video": ["video", 0], "filename_prefix": prefixo,
                  "format": "auto", "format.codec": "auto", "codec": "auto"}}
    return g


def expandir_enquadramento(entrada, lora, texto, quadros, origem, saida, seed=42,
                           com_audio=True, prefixo="editor/video_expandir"):
    """Outpainting com o IC-LoRA In/Outpainting, molde do exemplo oficial
    LTX-2.5_ICLoRA_Outpaint_Two_Stage_Distilled: o original entra inteiro,
    centralizado no quadro novo; as bordas (verde) sao geradas. Etapa 1 na
    metade, mescla piramidal com o original, etapa 2 refina 2 passos na
    resolucao cheia, mescla final. Sem texto, o modelo continua a cena.
    O audio original entra "congelado" (LTXVSetAudioRefTokens), como no oficial.
    `origem`/`saida` sao (largura, altura); a saida em multiplos de 64."""
    p = VIDEO_LTX
    (lo, ao), (larg, alt) = origem, saida
    f = min(larg / lo, alt / ao)
    sl, sa = min(larg, round(lo * f / 2) * 2), min(alt, round(ao * f / 2) * 2)
    esq, topo = (larg - sl) // 2, (alt - sa) // 2
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "lora": {"class_type": "LTXICLoRALoaderModelOnly", "inputs": {"model": ["unet", 0], "lora_name": win(lora), "strength_model": 1.0}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"], "device": "default"}},
        "vae_v": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_video"])}},
        "vae_a": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_audio"])}},
        "carga": {"class_type": "LoadVideo", "inputs": {"file": entrada}},
        "partes": {"class_type": "GetVideoComponents", "inputs": {"video": ["carga", 0]}},
        "corte": {"class_type": "ImageFromBatch", "inputs": {"image": ["partes", 0], "batch_index": 0, "length": quadros}},
        "encaixe": {"class_type": "ResizeImageMaskNode", "inputs": {"input": ["corte", 0], "resize_type": "scale dimensions",
                    "resize_type.width": sl, "resize_type.height": sa, "resize_type.crop": "disabled", "scale_method": "lanczos"}},
        "borda": {"class_type": "ImagePadForOutpaint", "inputs": {"image": ["encaixe", 0], "left": esq, "top": topo,
                  "right": larg - sl - esq, "bottom": alt - sa - topo, "feathering": 0}},
        # A mascara do pad sai com 1 quadro; com trim_to_shortest a mescla
        # cortava o video para 1 quadro (medido em 19/10/2026).
        "masc_img": {"class_type": "MaskToImage", "inputs": {"mask": ["borda", 1]}},
        "masc_rep": {"class_type": "RepeatImageBatch", "inputs": {"image": ["masc_img", 0], "amount": quadros}},
        "mascara": {"class_type": "ImageToMask", "inputs": {"image": ["masc_rep", 0], "channel": "red"}},
        "preparo": {"class_type": "LTXVInpaintPreprocess", "inputs": {"images": ["borda", 0], "mask": ["mascara", 0]}},
        "preparo_meia": {"class_type": "ResizeImageMaskNode", "inputs": {"input": ["preparo", 0], "resize_type": "scale by multiplier",
                         "resize_type.multiplier": 0.5, "scale_method": "area"}},
        "mascara_meia": {"class_type": "ResizeImageMaskNode", "inputs": {"input": ["mascara", 0], "resize_type": "scale by multiplier",
                         "resize_type.multiplier": 0.5, "scale_method": "area"}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": texto}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": "pc game, console game, video game, cartoon, childish, ugly"}},
        "cond": {"class_type": "LTXVConditioning", "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "frame_rate": 24}},
        "vazio": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": larg // 2, "height": alt // 2, "length": quadros, "batch_size": 1}},
        "guia": {"class_type": "LTXAddVideoICLoRAGuideAdvanced", "inputs": {"positive": ["cond", 0], "negative": ["cond", 1],
                 "vae": ["vae_v", 0], "latent": ["vazio", 0], "image": ["preparo_meia", 0], "frame_idx": 0, "strength": 1.0,
                 "latent_downscale_factor": ["lora", 1], "crop": "disabled", "use_tiled_encode": False, "tile_size": 256,
                 "tile_overlap": 64, "attention_strength": 1.0, "use_streaming": False, "tile_frames": 97}},
    }
    if com_audio:
        g["audio_lat"] = {"class_type": "VAEEncodeAudio", "inputs": {"audio": ["partes", 1], "vae": ["vae_a", 0]}}
        g["ref1"] = {"class_type": "LTXVSetAudioRefTokens", "inputs": {"positive": ["guia", 0], "negative": ["guia", 1], "audio_latent": ["audio_lat", 0]}}
        pos1, neg1, som1 = ["ref1", 0], ["ref1", 1], ["ref1", 2]
    else:
        g["som"] = {"class_type": "LTXVEmptyLatentAudio", "inputs": {"frames_number": quadros, "frame_rate": 24, "batch_size": 1, "audio_vae": ["vae_a", 0]}}
        pos1, neg1, som1 = ["guia", 0], ["guia", 1], ["som", 0]
    g["av1"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["guia", 2], "audio_latent": som1}}

    def amostrar(suf, pos, neg, latente, sigmas, semente, amostrador):
        g[f"guiador{suf}"] = {"class_type": "CFGGuider", "inputs": {"model": ["lora", 0], "positive": pos, "negative": neg, "cfg": 1}}
        g[f"ruido{suf}"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": semente}}
        g[f"amostrador{suf}"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": amostrador}}
        g[f"sigmas{suf}"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}}
        g[f"amostra{suf}"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": [f"ruido{suf}", 0],
            "guider": [f"guiador{suf}", 0], "sampler": [f"amostrador{suf}", 0], "sigmas": [f"sigmas{suf}", 0], "latent_image": latente}}
        g[f"separa{suf}"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": [f"amostra{suf}", 0]}}

    amostrar("1", pos1, neg1, ["av1", 0],
             "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0", seed, "euler_ancestral")
    g["tira1"] = {"class_type": "LTXVCropGuides", "inputs": {"positive": pos1, "negative": neg1, "latent": ["separa1", 0]}}
    g["dec1"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["tira1", 2], "vae": ["vae_v", 0],
                 "tile_size": 512, "overlap": 64, "temporal_size": TEMPORAL_LTX[0], "temporal_overlap": TEMPORAL_LTX[1]}}
    g["mescla1"] = {"class_type": "LTXVLaplacianPyramidBlend", "inputs": {"image_a": ["dec1", 0], "image_b": ["preparo_meia", 0],
                    "mask": ["mascara_meia", 0], "trim_to_shortest": True, "mask_low_res_dilation": 5}}
    g["amplia"] = {"class_type": "ResizeImageMaskNode", "inputs": {"input": ["mescla1", 0], "resize_type": "scale dimensions",
                   "resize_type.width": larg, "resize_type.height": alt, "resize_type.crop": "disabled", "scale_method": "lanczos"}}
    g["cod2"] = {"class_type": "VAEEncodeTiled", "inputs": {"pixels": ["amplia", 0], "vae": ["vae_v", 0],
                 "tile_size": 512, "overlap": 64, "temporal_size": TEMPORAL_LTX[0], "temporal_overlap": TEMPORAL_LTX[1]}}
    if com_audio:
        g["ref2"] = {"class_type": "LTXVSetAudioRefTokens", "inputs": {"positive": ["tira1", 0], "negative": ["tira1", 1], "audio_latent": ["audio_lat", 0]}}
        pos2, neg2, som2 = ["ref2", 0], ["ref2", 1], ["ref2", 2]
    else:
        pos2, neg2, som2 = ["tira1", 0], ["tira1", 1], ["separa1", 1]
    g["av2"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["cod2", 0], "audio_latent": som2}}
    amostrar("2", pos2, neg2, ["av2", 0], "0.7250, 0.4219, 0.0", seed + 1, "euler")
    g["dec2"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["separa2", 0], "vae": ["vae_v", 0],
                 "tile_size": 512, "overlap": 64, "temporal_size": TEMPORAL_LTX[0], "temporal_overlap": TEMPORAL_LTX[1]}}
    g["mescla2"] = {"class_type": "LTXVLaplacianPyramidBlend", "inputs": {"image_a": ["dec2", 0], "image_b": ["preparo", 0],
                    "mask": ["mascara", 0], "trim_to_shortest": True, "mask_low_res_dilation": 6}}
    video = {"images": ["mescla2", 0], "fps": 24, "bit_depth": "auto", "color_space": "sRGB", "codec": "none"}
    if com_audio:
        video["audio"] = ["partes", 1]
    g["video"] = {"class_type": "CreateVideo", "inputs": video}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {"video": ["video", 0], "filename_prefix": prefixo,
                  "format": "auto", "format.codec": "auto", "codec": "auto"}}
    return g


def chaves_ltx(texto, chaves, quadros, largura, altura, forca=0.7, seed=42,
               com_audio=True, prefixo="editor/video_chaves"):
    """Video so a partir de quadros-chave, sem video base: LTX 2.5 em duas
    etapas, cada imagem presa ao seu quadro (LTXVAddGuide) nas duas etapas;
    o texto conduz o movimento entre elas. `chaves` = [(nome, posicao)], com
    posicao multipla de 8 (a ultima pode ser quadros-1).
    MEDIDO em 19/10/2026 (supercarro, 1024x576): a chave do meio ganha 12,5 dB
    contra o controle so com inicio e fim. Com forca 1,0, chaves vizinhas de
    ponto de vista muito diferente se FUNDEM (dupla exposicao); 0,7 quase
    elimina e ainda segura a chave (+9 dB); 0,5 quase nao segura. 5 chaves em
    353 quadros: 121 s, 15,3 GiB. Teste de 361 quadros em 720p: 265 s.
    A saida e alinhada para cima em 64 e recortada apos decode; base 640x384
    para saida 1280x720. Decode 192/48 elimina as quedas periodicas do 64/8."""
    saida_largura, saida_altura = largura, altura
    largura, altura = ((v + 63) // 64 * 64 for v in (largura, altura))
    p = VIDEO_LTX
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"], "device": "default"}},
        "vae_v": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_video"])}},
        "vae_a": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_audio"])}},
        "ups": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": win(p["upsampler"])}},
        "cond": {"class_type": "LTXVConditioning", "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "frame_rate": 24}},
        "vazio": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": largura // 2, "height": altura // 2, "length": quadros, "batch_size": 1}},
        "som": {"class_type": "LTXVEmptyLatentAudio", "inputs": {"frames_number": quadros, "frame_rate": 24, "batch_size": 1, "audio_vae": ["vae_a", 0]}},
    }
    _texto(g, "pos", "clip", texto)
    _texto(g, "neg", "clip", "")
    for i, (nome, _) in enumerate(chaves):
        g[f"img{i}"] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        g[f"tam{i}"] = {"class_type": "ResizeImageMaskNode", "inputs": {"input": [f"img{i}", 0], "resize_type": "scale dimensions",
                        "resize_type.width": largura, "resize_type.height": altura, "resize_type.crop": "center", "scale_method": "lanczos"}}

    def guias(suf, pos, neg, latente):
        for i, (_, q) in enumerate(chaves):
            no = f"guia{i}_{suf}"
            g[no] = {"class_type": "LTXVAddGuide", "inputs": {"positive": pos, "negative": neg, "vae": ["vae_v", 0],
                     "latent": latente, "image": [f"tam{i}", 0], "frame_idx": q, "strength": forca}}
            pos, neg, latente = [no, 0], [no, 1], [no, 2]
        return no

    def amostrar(suf, ult, latente, sigmas, semente):
        g[f"guiador{suf}"] = {"class_type": "CFGGuider", "inputs": {"model": ["unet", 0], "positive": [ult, 0], "negative": [ult, 1], "cfg": 1}}
        g[f"ruido{suf}"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": semente}}
        g[f"amostrador{suf}"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}}
        g[f"sigmas{suf}"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}}
        g[f"amostra{suf}"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": [f"ruido{suf}", 0],
            "guider": [f"guiador{suf}", 0], "sampler": [f"amostrador{suf}", 0], "sigmas": [f"sigmas{suf}", 0], "latent_image": latente}}
        g[f"separa{suf}"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": [f"amostra{suf}", 0]}}
        g[f"tira{suf}"] = {"class_type": "LTXVCropGuides", "inputs": {"positive": [ult, 0], "negative": [ult, 1], "latent": [f"separa{suf}", 0]}}

    u1 = guias("1", ["cond", 0], ["cond", 1], ["vazio", 0])
    g["av1"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": [u1, 2], "audio_latent": ["som", 0]}}
    amostrar("1", u1, ["av1", 0], "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0", seed)
    g["amplia"] = {"class_type": "LTXVLatentUpsampler", "inputs": {"samples": ["tira1", 2], "upscale_model": ["ups", 0], "vae": ["vae_v", 0]}}
    u2 = guias("2", ["tira1", 0], ["tira1", 1], ["amplia", 0])
    g["av2"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": [u2, 2], "audio_latent": ["separa1", 1]}}
    amostrar("2", u2, ["av2", 0], "0.909375, 0.725, 0.421875, 0.0", seed + 1)
    g["dec"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["tira2", 2], "vae": ["vae_v", 0],
                "tile_size": 512, "overlap": 64, "temporal_size": TEMPORAL_LTX[0], "temporal_overlap": TEMPORAL_LTX[1]}}
    imagens = ["dec", 0]
    if (largura, altura) != (saida_largura, saida_altura):
        g["recorte_saida"] = {"class_type": "ImageCrop", "inputs": {
            "image": imagens, "width": saida_largura, "height": saida_altura,
            "x": (largura - saida_largura) // 2, "y": (altura - saida_altura) // 2}}
        imagens = ["recorte_saida", 0]
    video = {"images": imagens, "fps": 24, "bit_depth": "auto", "color_space": "sRGB", "codec": "none"}
    if com_audio:
        g["dec_a"] = {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["separa2", 1], "audio_vae": ["vae_a", 0]}}
        video["audio"] = ["dec_a", 0]
    g["video"] = {"class_type": "CreateVideo", "inputs": video}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {"video": ["video", 0], "filename_prefix": prefixo,
                  "format": "auto", "format.codec": "auto", "codec": "auto"}}
    return g


def gerar_video_minimax(prompt, seed, largura, altura, duracao, imagem=None,
                        imagem_final=None, turbo=True, com_audio=True, prefixo="video"):
    """MiniMax H3 de pesos abertos, local ou na Comfy Cloud (mesmos nomes).

    O `MiniMaxH3ImageToVideo` cobre os tres modos: os quadros-guia sao
    opcionais (nenhum = texto, o primeiro = imagem, os dois = primeiro+ultimo)
    e ele devolve condicionamento e latente ja casados. O mesmo latente
    alimenta os decodificadores de video e de audio."""
    from presets import VIDEO_MINIMAX as p, quadros_minimax
    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"], "device": "default"}},
        "vae_v": {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_video"])}},
    }
    if turbo:
        g["lora"] = {"class_type": "LoraLoaderModelOnly",
                     "inputs": {"model": ["unet", 0], "lora_name": win(p["lora_turbo"]),
                                "strength_model": p["forca_lora"]}}
        modelo, passos = ["lora", 0], p["passos_turbo"]
    else:
        modelo, passos = ["unet", 0], p["passos_qualidade"]
    entradas = {"clip": ["clip", 0], "vae": ["vae_v", 0], "prompt": prompt,
                "width": int(largura), "height": int(altura),
                "length": quadros_minimax(duracao, p["fps"])}
    if imagem:
        g["img_ini"] = {"class_type": "LoadImage", "inputs": {"image": imagem}}
        entradas["first_frame"] = ["img_ini", 0]
    if imagem_final:
        g["img_fim"] = {"class_type": "LoadImage", "inputs": {"image": imagem_final}}
        entradas["last_frame"] = ["img_fim", 0]
    g["prep"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": entradas}
    g["guia"] = {"class_type": "BasicGuider", "inputs": {"model": modelo, "conditioning": ["prep", 0]}}
    g["sigmas"] = {"class_type": "BasicScheduler",
                   "inputs": {"model": modelo, "scheduler": p["scheduler"], "steps": passos, "denoise": 1.0}}
    g["amostrador"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": p["sampler"]}}
    g["ruido"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["passo"] = {"class_type": "SamplerCustomAdvanced",
                  "inputs": {"noise": ["ruido", 0], "guider": ["guia", 0], "sampler": ["amostrador", 0],
                             "sigmas": ["sigmas", 0], "latent_image": ["prep", 1]}}
    g["decodifica"] = {"class_type": "VAEDecode", "inputs": {"samples": ["passo", 0], "vae": ["vae_v", 0]}}
    entradas_video = {"images": ["decodifica", 0], "fps": p["fps"]}
    if com_audio:
        g["vae_a"] = {"class_type": "VAELoader", "inputs": {"vae_name": win(p["vae_audio"])}}
        g["som"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["passo", 0], "vae": ["vae_a", 0]}}
        entradas_video["audio"] = ["som", 0]
    g["monta"] = {"class_type": "CreateVideo", "inputs": entradas_video}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {"video": ["monta", 0], "filename_prefix": prefixo,
                                                        "format": "auto", "codec": "auto"}}
    return g


def gerar_video_api(provedor, prompt, seed, modo, proporcao, resolucao, duracao,
                    imagem=None, imagem_final=None, com_audio=True, prefixo="video",
                    referencias=()):
    """Video por no de API (Kling, Veo, Seedance, Runway, Luma): um no por modo,
    com o quadro inicial/final quando houver. Ver presets.VIDEO_API."""
    from presets import VIDEO_API
    cfg = VIDEO_API[provedor]
    # Kling e Seedance aceitam seed ate 2^31-1, Veo e Runway ate 2^32-1; a do app
    # vai ate 2^52 e a Comfy Cloud recusava o pedido (value_bigger_than_max).
    seed = seed % 2147483646
    g = {}
    if modo in ("imagem", "primeiro_ultimo"):
        if not imagem:
            raise ValueError("envie a imagem do primeiro quadro")
        g["img_ini"] = {"class_type": "LoadImage", "inputs": {"image": imagem}}
    if modo == "primeiro_ultimo":
        if not imagem_final:
            raise ValueError("envie também o último quadro")
        g["img_fim"] = {"class_type": "LoadImage", "inputs": {"image": imagem_final}}
    ini, fim = ["img_ini", 0], ["img_fim", 0]
    duracao = int(round(duracao))
    if modo == "referencia":
        refs = list(referencias)[:cfg["max_referencias"]]
        if not refs:
            raise ValueError("envie ao menos uma imagem de referência")
        for i, r in enumerate(refs):
            g[f"ref{i}"] = {"class_type": "LoadImage", "inputs": {"image": r}}
        if provedor == "kling":
            g["lote"] = {"class_type": "BatchImagesNode",
                         "inputs": {f"images.image{i}": [f"ref{i}", 0] for i in range(len(refs))}}
            no = "KlingOmniProImageToVideoNode"
            ent = {"model_name": "kling-v3-omni", "prompt": prompt, "aspect_ratio": proporcao,
                   "duration": max(3, min(15, duracao)), "reference_images": ["lote", 0],
                   "resolution": resolucao if resolucao in ("720p", "1080p", "4k") else "720p",
                   "storyboards": "disabled", "generate_audio": com_audio, "seed": seed}
        else:
            no = "ByteDance2ReferenceNodeV2"
            ent = {"model": cfg["ramo"], "model.prompt": prompt, "model.resolution": resolucao,
                   "model.ratio": proporcao, "model.duration": duracao, "model.generate_audio": com_audio,
                   "model.task_type": "reference", "model.output_format": "mp4",
                   "model.auto_downscale": True, "model.auto_upscale": False,
                   "seed": seed, "watermark": False,
                   **{f"model.reference_images.image_{i + 1}": [f"ref{i}", 0] for i in range(len(refs))}}
        g["gera"] = {"class_type": no, "inputs": ent}
        g["salva"] = {"class_type": "SaveVideo", "inputs": {"video": ["gera", 0], "filename_prefix": prefixo,
                                                            "format": "auto", "codec": "auto"}}
        return g

    if provedor == "kling":
        if modo == "primeiro_ultimo":
            no = "KlingFirstLastFrameNode"
            ent = {"prompt": prompt, "duration": duracao, "first_frame": ini, "end_frame": fim,
                   "generate_audio": com_audio, "model": cfg["ramo"],
                   "model.resolution": resolucao, "seed": seed}
        else:
            no = "KlingVideoNode"
            ent = {"multi_shot": "disabled", "multi_shot.prompt": prompt,
                   "multi_shot.negative_prompt": "", "multi_shot.duration": duracao,
                   "generate_audio": com_audio, "model": cfg["ramo"],
                   "model.resolution": resolucao, "model.aspect_ratio": proporcao, "seed": seed}
            if modo == "imagem":
                ent["start_frame"] = ini
    elif provedor == "veo":
        if modo == "primeiro_ultimo":
            no = "Veo3FirstLastFrameNode"
            ent = {"prompt": prompt, "negative_prompt": "", "resolution": resolucao,
                   "aspect_ratio": proporcao, "duration": duracao, "seed": seed,
                   "first_frame": ini, "last_frame": fim, "model": cfg["modelo"],
                   "generate_audio": com_audio}
        else:
            no = "Veo3VideoGenerationNode"
            ent = {"prompt": prompt, "aspect_ratio": proporcao, "resolution": resolucao,
                   "duration_seconds": duracao, "seed": seed, "model": cfg["modelo"],
                   "generate_audio": com_audio, "enhance_prompt": True}
            if modo == "imagem":
                ent["image"] = ini
    elif provedor == "seedance":
        base = {"model": cfg["ramo"], "model.prompt": prompt, "model.resolution": resolucao,
                "model.duration": duracao, "model.generate_audio": com_audio,
                "model.output_format": "mp4", "seed": seed, "watermark": False}
        if modo == "texto":
            no, ent = "ByteDance2TextToVideoNode", {**base, "model.ratio": proporcao}
        else:
            # Imagem -> video e o mesmo no de primeiro+ultimo, so com o primeiro.
            no, ent = "ByteDance2FirstLastFrameNode", {**base, "first_frame": ini}
            if modo == "primeiro_ultimo":
                ent["last_frame"] = fim
    elif provedor == "runway":
        dur = 10 if duracao >= 8 else 5
        if modo == "primeiro_ultimo":
            no = "RunwayFirstLastFrameNode"
            ent = {"prompt": prompt, "start_frame": ini, "end_frame": fim, "duration": dur,
                   "ratio": "768:1280" if proporcao == "9:16" else "1280:768", "seed": seed}
        else:
            no = "RunwayImageToVideoNodeGen4"
            ent = {"prompt": prompt, "start_frame": ini, "duration": dur, "seed": seed,
                   "ratio": {"9:16": "720:1280", "1:1": "960:960"}.get(proporcao, "1280:720")}
    elif provedor == "luma":
        if modo == "texto":
            no = "LumaRay32TextToVideoNode"
            ent = {"prompt": prompt, "aspect_ratio": proporcao, "resolution": resolucao,
                   "duration": "10s" if duracao >= 8 else "5s", "loop": False, "seed": seed}
        else:
            no = "LumaRay32ImageToVideoNode"
            ent = {"prompt": prompt, "resolution": resolucao, "loop": False, "seed": seed,
                   "start_frame": ini}
            if modo == "primeiro_ultimo":
                ent["end_frame"] = fim
    else:
        raise ValueError("provedor de video desconhecido")

    g["gera"] = {"class_type": no, "inputs": ent}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {"video": ["gera", 0], "filename_prefix": prefixo,
                                                        "format": "auto", "codec": "auto"}}
    return g


# Base do LTX 2.3 (checkpoint destilado, com o VAE dentro) para os IC-LoRAs na
# Comfy Cloud: la so existem as versoes 2.3 deles, e em cima do 2.5 quase nao
# fazem efeito (teste de 22/10/2026: dia -> noite saiu de dia).
CKPT_LTX23_DESTILADO = "ltx-2.3-22b-distilled-fp8.safetensors"


def em_base_ltx23(g):
    """Troca os carregadores do LTX 2.5 de um grafo pelos do 2.3."""
    g["unet"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT_LTX23_DESTILADO}}
    g["clip"] = {"class_type": "LTXAVTextEncoderLoader", "inputs": {
        "text_encoder": "gemma_3_12B_it_fp4_mixed.safetensors", "ckpt_name": CKPT_LTX23_DESTILADO,
        "device": "default"}}
    g["vae_a"] = {"class_type": "LTXVAudioVAELoader", "inputs": {"ckpt_name": CKPT_LTX23_DESTILADO}}
    del g["vae_v"]
    for no in g.values():
        for k, v in no["inputs"].items():
            if v == ["vae_v", 0]:
                no["inputs"][k] = ["unet", 2]
    return g


def gerar_video_fasth3(prompt, seed, largura=1344, altura=768, duracao=5,
                       imagem=None, imagem_final=None, com_audio=True,
                       prefixo="video"):
    """Video pelo FastH3, local: o MiniMax H3 destilado em 8 passos.

    TRADUZIDO de video_fastvideo_fasth3_i2v.json. E quase o mesmo grafo do
    `gerar_video_minimax` — mesmo no de condicionamento, mesmo sampler, mesmo
    scheduler — com tres nos a mais entre o modelo e o amostrador:

        UNETLoader -> MiniMaxH3SigmaShift -> ModelAttentionBackend
                   -> BlockSparseAttention -> guider e scheduler

    A ORDEM importa e nao e a que eu teria adivinhado: o deslocamento de sigma
    vem ANTES do backend de atencao, e a atencao esparsa por ultimo. Foi lida
    das ligacoes do template, nao deduzida.

    Sem LoRA: os 8 passos sao da destilacao. Por isso nao ha chave turbo.

    NAO faz o modo de referencia — o ref2va nao foi destilado. Quem precisa de
    referencia usa o MiniMax base.
    """
    p = VIDEO_FASTH3
    fps = p["fps"]
    # A mesma conta do MiniMax base: o template a escreve como expressao
    # matematica, e ela bate letra por letra com `quadros_minimax`.
    quadros = quadros_minimax(duracao, fps)

    g = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": win(p["unet"]), "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": win(p["clip"]), "type": p["clip_type"],
                            "device": "default"}},
        "vae_v": {"class_type": "VAELoader",
                  "inputs": {"vae_name": win(p["vae_video"])}},

        "desloca": {"class_type": "MiniMaxH3SigmaShift",
                    "inputs": {"model": ["unet", 0],
                               "shift_video": p["shift_video"],
                               "shift_audio": p["shift_audio"]}},
        "backend": {"class_type": "ModelAttentionBackend",
                    "inputs": {"model": ["desloca", 0],
                               "attention": p["backend_atencao"]}},
        # `selection` e DynamicCombo: o sub-campo do ramo escolhido leva o nome
        # do combo como prefixo, como no Topaz e no Wan.
        "esparsa": {"class_type": "BlockSparseAttention",
                    "inputs": {"model": ["backend", 0],
                               "selection": p["atencao_selecao"],
                               "selection.keep_percent": p["atencao_percentual"],
                               "start_percent": p["atencao_inicio"],
                               "end_percent": p["atencao_fim"],
                               "dense_blocks": "",
                               "min_tokens": p["atencao_min_tokens"],
                               "extra_tokens": p["atencao_extra_tokens"],
                               "sink_conditioning": p["atencao_sink"],
                               "verbose": False}},
    }
    modelo = ["esparsa", 0]

    entradas = {"clip": ["clip", 0], "vae": ["vae_v", 0], "prompt": prompt,
                "width": int(largura), "height": int(altura), "length": quadros}
    if imagem:
        g["img_ini"] = {"class_type": "LoadImage", "inputs": {"image": imagem}}
        g["img_ini_esc"] = {"class_type": "ImageResizeKJv2",
                            "inputs": {"image": ["img_ini", 0],
                                       "width": int(largura),
                                       "height": int(altura),
                                       "upscale_method": "lanczos",
                                       "keep_proportion": "pillarbox_blur",
                                       "pad_color": "0, 0, 0",
                                       "crop_position": "center",
                                       "divisible_by": 2}}
        entradas["first_frame"] = ["img_ini_esc", 0]
    if imagem_final:
        g["img_fim"] = {"class_type": "LoadImage", "inputs": {"image": imagem_final}}
        g["img_fim_esc"] = {"class_type": "ImageResizeKJv2",
                            "inputs": {"image": ["img_fim", 0],
                                       "width": int(largura),
                                       "height": int(altura),
                                       "upscale_method": "lanczos",
                                       "keep_proportion": "pillarbox_blur",
                                       "pad_color": "0, 0, 0",
                                       "crop_position": "center",
                                       "divisible_by": 2}}
        entradas["last_frame"] = ["img_fim_esc", 0]
    g["prep"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": entradas}

    g["guia"] = {"class_type": "BasicGuider",
                 "inputs": {"model": modelo, "conditioning": ["prep", 0]}}
    g["sigmas"] = {"class_type": "BasicScheduler",
                   "inputs": {"model": modelo, "scheduler": p["scheduler"],
                              "steps": p["passos"], "denoise": p["denoise"]}}
    g["amostrador"] = {"class_type": "KSamplerSelect",
                       "inputs": {"sampler_name": p["sampler"]}}
    g["ruido"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["passo"] = {"class_type": "SamplerCustomAdvanced",
                  "inputs": {"noise": ["ruido", 0], "guider": ["guia", 0],
                             "sampler": ["amostrador", 0], "sigmas": ["sigmas", 0],
                             "latent_image": ["prep", 1]}}
    g["decodifica"] = {"class_type": "VAEDecode",
                       "inputs": {"samples": ["passo", 0], "vae": ["vae_v", 0]}}

    entradas_video = {"images": ["decodifica", 0], "fps": fps}
    if com_audio:
        g["vae_a"] = {"class_type": "VAELoader",
                      "inputs": {"vae_name": win(p["vae_audio"])}}
        g["som"] = {"class_type": "VAEDecodeAudio",
                    "inputs": {"samples": ["passo", 0], "vae": ["vae_a", 0]}}
        entradas_video["audio"] = ["som", 0]

    g["monta"] = {"class_type": "CreateVideo", "inputs": entradas_video}
    g["salva"] = {"class_type": "SaveVideo",
                  "inputs": {"video": ["monta", 0], "filename_prefix": prefixo,
                             "format": "auto", "codec": "auto"}}
    return g


def mapa_profundidade(entrada, quadros, colormap="gray", exr_pasta=None, max_res=1280,
                      prefixo="editor/video_profundidade"):
    """Video -> mapa de profundidade com o Video Depth Anything (segundo motor).

    Mesmo no que o "Follow depth" usa por dentro, aqui entregue como resultado:
    um video (cinza: perto claro, longe escuro; ou "inferno", colorido) na
    cadencia do original, e opcionalmente os quadros em EXR (canal Z, 32 bits)
    para Blender/After Effects, gravados em <saida>/<exr_pasta>."""
    g = {
        "carga": {"class_type": "LoadVideo", "inputs": {"file": entrada}},
        "partes": {"class_type": "GetVideoComponents", "inputs": {"video": ["carga", 0]}},
        "dmodelo": {"class_type": "LoadVideoDepthAnythingModel", "inputs": {"model": "video_depth_anything_vits.pth"}},
        # So os primeiros `quadros`: todos os quadros ficam na RAM de uma vez.
        "corte": {"class_type": "ImageFromBatch", "inputs": {"image": ["partes", 0], "batch_index": 0, "length": quadros}},
        "dproc": {"class_type": "VideoDepthAnythingProcess", "inputs": {
            "vda_model": ["dmodelo", 0], "images": ["corte", 0],
            "input_size": 518, "max_res": max_res, "precision": "fp16"}},
        "mapa": {"class_type": "VideoDepthAnythingOutput", "inputs": {"depths": ["dproc", 0], "colormap": colormap}},
        "video": {"class_type": "CreateVideo", "inputs": {"images": ["mapa", 0], "fps": ["partes", 2]}},
        "salva": {"class_type": "SaveVideo", "inputs": {
            "video": ["video", 0], "filename_prefix": prefixo, "format": "auto", "codec": "auto"}},
    }
    if exr_pasta:
        g["exr"] = {"class_type": "VideoDepthAnythingSaveEXR", "inputs": {"depths": ["dproc", 0], "folder_name": exr_pasta}}
    return g
