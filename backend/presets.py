"""Catalogo de modelos de geracao.

Cada entrada foi conferida contra os templates oficiais do ComfyUI e testada
nesta maquina. Ver NOTAS-MOTOR.md.
"""

import re

# A API do ComfyUI so valida nomes de arquivo com a barra do Windows.
def win(path: str) -> str:
    return path.replace("/", "\\")


# Fragmentos que descrevem a LENTE. Quando o prompt foi expandido, o LLM ja
# nomeou uma — a propria orientacao do estilo manda nomear —, e repetir a do
# preset punha duas no mesmo prompt, brigando entre si.
_LENTE = re.compile(r"\b(\d+\s*mm|wide[- ]angle|telephoto|prime lens|macro lens)\b",
                    re.I)


def sem_lente(positivo: str) -> str:
    """Tira os trechos de lente de um acrescimo de estilo.

    Trabalha por fragmento separado por virgula: assim "shallow depth of
    field, 50mm lens" perde so o segundo, e nao a profundidade de campo.
    """
    partes = [f.strip() for f in positivo.split(",")]
    return ", ".join(f for f in partes if f and not _LENTE.search(f))


# Pipelines simples: UNETLoader -> CLIPLoader -> KSampler -> VAEDecode.
SIMPLE = {
    "krea": {
        "rotulo": "Krea 2 Turbo",
        "descricao": "Fotorrealismo. Rápido. Padrão para a maioria dos casos.",
        "unet": "Krea/krea2_turbo_fp8_scaled.safetensors",
        "clip": "Qwen/qwen3vl_4b_fp8_scaled.safetensors",
        "clip_type": "krea2",
        "vae": "Qwen/qwen_image_vae.safetensors",
        "latent": "EmptyLatentImage",
        "steps": 8,
        "cfg": 1.0,
        "sampler": "euler",
        "scheduler": "simple",
        "zero_negative": True,
        "segundos_estimados": 24,
    },
    # Kroma (lodestones), ajuste fino do Krea 2 sem censura, voltado a
    # ilustracao (anime/furry); mesmo CLIP e VAE do Krea. int8 convrot do
    # silveroxides: MEDIDO em 19/10/2026, 22 s em 1024x1024 e 27,1 dB do BF16
    # (o fp8 que eu gerei ficou em 26,1 dB e 27 s).
    "kroma": {
        "rotulo": "Kroma",
        "descricao": "Ilustração e anime, sem censura. Ajuste fino do Krea 2.",
        "unet": "Krea/kroma-v0.3.1-turbo-opd-int8-convrot.safetensors",
        "clip": "Qwen/qwen3vl_4b_fp8_scaled.safetensors",
        "clip_type": "krea2",
        "vae": "Qwen/qwen_image_vae.safetensors",
        "latent": "EmptyLatentImage",
        "steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple",
        "zero_negative": True,
        "segundos_estimados": 24,
    },
    # Kroma com o LoRA nicegirls_v2 (Danrisi) a 0,8 FUNDIDO nos pesos BF16 e
    # quantizado em fp8 (scripts/fundir_lora.py + converter_fp8_como.py).
    # Aplicado na hora, o LoRA levava 403 s por imagem (VRAM no limite); fundido,
    # 26 s, com a mesma cena. Sem a palavra de ativacao "l3n0v0": com ela, o
    # modelo ESCREVIA a palavra num cartao na cena.
    "kroma_foto": {
        "rotulo": "Kroma Foto",
        "descricao": "Foto amadora realista (celular, filme), sem censura.",
        "unet": "Krea/kroma-v0.3.1-nicegirls08_fp8_scaled.safetensors",
        "clip": "Qwen/qwen3vl_4b_fp8_scaled.safetensors",
        "clip_type": "krea2",
        "vae": "Qwen/qwen_image_vae.safetensors",
        "latent": "EmptyLatentImage",
        "steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple",
        "zero_negative": True,
        "segundos_estimados": 26,
    },
    "qwen21": {
        "rotulo": "Qwen Image 2.1",
        "descricao": ("Texto na cena com acerto alto, e o único local que "
                      "gera em 2K nativo (2048×2048). Mesma qualidade do "
                      "Krea em fotografia comum, e mais lento."),
        "unet": "Qwen/qwen_image_2.1_int8_convrot.safetensors",
        # O codificador NAO e intercambiavel. Testei com o qwen3vl_8b_fp8_scaled
        # que ja estava no disco, para poupar 8,7 GB: o letreiro "PADARIA AURORA"
        # saiu "PAMARIA". Com este, sai certo. Mesma seed, mesmo resto.
        "clip": "Qwen/qwen3vl_8b_int8_convrot.safetensors",
        "clip_type": "qwen_image",
        "vae": "Qwen/qwen_image_2.1_vae_bf16.safetensors",
        "latent": "EmptyLatentImage",
        # O no proprio devolve positivo E negativo; nao passa por CLIPTextEncode.
        "encoder": "qwen21",
        # Valores do template oficial do ComfyUI, nao chutados.
        "steps": 25,
        "cfg": 1.0,
        "sampler": "euler",
        "scheduler": "simple",
        "zero_negative": False,
        # MEDIDO: 18 a 20 s em 1024x1024. Em 2048x2048 sao 70 s, com pico de
        # 13,3 GB — menos que os 14,9 GB de uma edicao com duas referencias.
        "segundos_estimados": 20,
    },
    "klein": {
        "rotulo": "Flux 2 Klein 9B",
        "descricao": "Máximo microdetalhe e textura. Mais lento.",
        "unet": "Flux2/flux-2-klein-base-9b-fp8.safetensors",
        "clip": "Qwen/qwen_3_8b_fp8mixed.safetensors",
        "clip_type": "flux2",
        "vae": "Flux2/flux2-vae.safetensors",
        "latent": "EmptySD3LatentImage",
        "steps": 28,
        "cfg": 4.0,
        "sampler": "euler",
        "scheduler": "simple",
        "zero_negative": False,
        "segundos_estimados": 54,
    },
    # Roda no SEGUNDO motor (ComfyUI v0.41, porta 8189): o v0.37 do app nao
    # conhece o Flux 3. Checkpoint completo em BF16, nao o destilado: medido em
    # 15/10/2026, edicao com 2 referencias em 91 s e pico de 14,5 GiB.
    "flux3": {
        "rotulo": "Flux 3 Klein",
        "descricao": "Modelo novo da BFL. Fotorrealismo e texto bem escrito.",
        "unet": "Flux3/flux3_image_klein_bf16.safetensors",
        "clip": "Flux3/qwen3vl_4b_int8_convrot.safetensors",
        "clip_type": "flux3",
        "vae": "Flux2/flux2-vae.safetensors",
        "latent": "EmptyFlux2LatentImage",
        # Template oficial image_flux3_klein_t2i: 25 passos, CFG 3,5.
        "steps": 25,
        "cfg": 3.5,
        "sampler": "euler",
        "scheduler": "simple",
        "zero_negative": False,
        "segundos_estimados": 45,
        # MEDIDO em 16/10/2026: 3840x2176 em 448 s, pico de 15,9 GiB (o
        # limite da placa). Detalhe real (poros, fios do bordado) que um
        # 1080p ampliado 2x pelo RTX nao tem.
        "nativo_4k": {"segundos": 450},
    },
    "zimage": {
        "rotulo": "Z-Image Turbo",
        "descricao": "Rascunho rápido. Aceita ControlNet.",
        "unet": "Z_Image/z_image_turbo_bf16.safetensors",
        "clip": "Qwen/qwen_3_4b.safetensors",
        "clip_type": "stable_diffusion",
        "vae": "AE/ae.safetensors",
        "latent": "EmptySD3LatentImage",
        "steps": 8,
        "cfg": 1.0,
        "sampler": "euler",
        "scheduler": "simple",
        "zero_negative": True,
        "segundos_estimados": 24,
    },
    "mage": {
        "rotulo": "Mage Flow",
        "descricao": "Leve. Base do modo de edição por instrução.",
        "unet": "Mage/mage_flow_int8_convrot.safetensors",
        "clip": "Qwen/qwen3vl_4b_bf16.safetensors",
        "clip_type": "mage",
        "vae": "Mage/mage_flow_vae_bf16.safetensors",
        "latent": "EmptySD3LatentImage",
        "steps": 20,
        "cfg": 3.5,
        "sampler": "euler",
        "scheduler": "simple",
        "zero_negative": False,
        "segundos_estimados": 30,
    },
    # Modelos mais antigos e leves, para placas pequenas. Os quatro vem num
    # arquivo so (checkpoint com modelo, texto e VAE): gerar_simples usa o
    # CheckpointLoaderSimple quando a ficha tem "checkpoint". "escala" reduz
    # o tamanho onde o modelo foi treinado menor (SD 1.5: 512 px).
    "flux1s": {
        "rotulo": "FLUX.1 schnell",
        "descricao": "Leve e rápido (4 passos). Apache 2.0. Placas de 8-12 GB.",
        "checkpoint": "Flux1/flux1-schnell-fp8.safetensors",
        "latent": "EmptySD3LatentImage",
        "steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "simple",
        "zero_negative": True,
        "segundos_estimados": 15,
    },
    "sd35m": {
        "rotulo": "SD 3.5 Medium",
        "descricao": "Bom com texto na imagem. Placas de 8 GB.",
        "checkpoint": "SD35/sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors",
        "latent": "EmptySD3LatentImage",
        "steps": 28, "cfg": 4.5, "sampler": "euler", "scheduler": "sgm_uniform",
        "zero_negative": False,
        "segundos_estimados": 25,
    },
    "sdxl": {
        "rotulo": "SDXL (RealVisXL 5)",
        "descricao": "O clássico SDXL, fotorrealista. Placas de 6-8 GB.",
        "checkpoint": "SDXL/RealVisXL_V5.0_fp16.safetensors",
        "latent": "EmptyLatentImage",
        "steps": 25, "cfg": 5.0, "sampler": "dpmpp_2m", "scheduler": "karras",
        "zero_negative": False,
        "segundos_estimados": 12,
    },
    # Mais geradores dos templates oficiais do ComfyUI (27/10/2026). "clips" com
    # 2 a 4 arquivos usa o Dual/Triple/QuadrupleCLIPLoader; "shift" poe o
    # ModelSamplingSD3 (ou AuraFlow com "shift_aura"); "guidance" o FluxGuidance.
    "flux1dev": {
        "rotulo": "FLUX.1 dev",
        "descricao": "O FLUX.1 classico, 20 passos. Licenca nao comercial.",
        "checkpoint": "Flux1/flux1-dev-fp8.safetensors",
        "latent": "EmptySD3LatentImage",
        "steps": 20, "cfg": 1.0, "sampler": "euler", "scheduler": "simple",
        "zero_negative": True, "segundos_estimados": 40,
    },
    "flux1krea": {
        "rotulo": "FLUX.1 Krea dev",
        "descricao": "FLUX.1 ajustado pela Krea: fotos com menos cara de IA.",
        "unet": "Flux1/flux1-krea-dev_fp8_scaled.safetensors",
        "clips": ["CLIP/clip_l.safetensors", "T5/t5xxl_fp8_e4m3fn_scaled.safetensors"], "clip_type": "flux",
        "vae": "AE/ae.safetensors", "latent": "EmptySD3LatentImage",
        "steps": 20, "cfg": 1.0, "sampler": "euler", "scheduler": "simple",
        "zero_negative": True, "segundos_estimados": 40,
    },
    "flux2dev": {
        "rotulo": "FLUX.2 dev",
        "descricao": "O FLUX.2 grande (32B). Muito detalhe; pesado.",
        "familia": "flux2",
        "unet": "Flux2/flux2_dev_fp8mixed.safetensors",
        "clip": "Mistral/mistral_3_small_flux2_fp8.safetensors", "clip_type": "flux2",
        "vae": "Flux2/flux2-vae.safetensors", "latent": "EmptyFlux2LatentImage",
        "steps": 20, "cfg": 1.0, "sampler": "euler", "scheduler": "simple",
        "guidance": 4.0, "zero_negative": True, "segundos_estimados": 120,
    },
    "hidream": {
        "rotulo": "HiDream I1 Fast",
        "descricao": "HiDream I1 rapido (16 passos), bom em seguir o texto.",
        "unet": "HiDream/hidream_i1_fast_fp8.safetensors",
        "clips": ["HiDream/clip_l_hidream.safetensors", "HiDream/clip_g_hidream.safetensors",
                  "T5/t5xxl_fp8_e4m3fn_scaled.safetensors", "HiDream/llama_3.1_8b_instruct_fp8_scaled.safetensors"],
        "vae": "AE/ae.safetensors", "latent": "EmptySD3LatentImage", "shift": 3.0,
        "steps": 16, "cfg": 1.0, "sampler": "lcm", "scheduler": "normal",
        "zero_negative": False, "negativo_padrao": "bad ugly jpeg artifacts", "segundos_estimados": 45,
    },
    "chroma": {
        "rotulo": "Chroma1 HD",
        "descricao": "Chroma: FLUX aberto (Apache 2.0) e sem censura de estilo.",
        "unet": "Chroma/Chroma1-HD-fp8mixed.safetensors",
        "clip": "T5/t5xxl_fp8_e4m3fn_scaled.safetensors", "clip_type": "chroma", "t5_opcoes": True,
        "vae": "AE/ae.safetensors", "latent": "EmptySD3LatentImage", "shift_aura": 1.0,
        "steps": 26, "cfg": 3.5, "sampler": "euler", "scheduler": "beta",
        "zero_negative": False,
        "negativo_padrao": "low quality, ugly, unfinished, out of focus, deformed, disfigure, blurry, smudged, restricted palette, flat colors",
        "segundos_estimados": 60,
    },
    "sd35l": {
        "rotulo": "SD 3.5 Large",
        "descricao": "O SD 3.5 grande (8B): bom com texto e composicao.",
        "checkpoint": "SD35/sd3.5_large_fp8_scaled.safetensors",
        "latent": "EmptySD3LatentImage",
        "steps": 20, "cfg": 4.0, "sampler": "euler", "scheduler": "sgm_uniform",
        "zero_negative": False, "segundos_estimados": 40,
    },
    "kandinsky5i": {
        "rotulo": "Kandinsky 5 Image",
        "descricao": "Kandinsky 5.0 Lite para imagem (Apache 2.0).",
        "unet": "Kandinsky5/kandinsky5lite_t2i.safetensors",
        "clips": ["Qwen/qwen_2.5_vl_7b_fp8_scaled.safetensors", "CLIP/clip_l.safetensors"], "clip_type": "kandinsky5_image",
        "vae": "AE/ae.safetensors", "latent": "EmptyLatentImage", "shift": 3.0,
        "steps": 50, "cfg": 3.5, "sampler": "euler", "scheduler": "simple",
        "zero_negative": False, "segundos_estimados": 60,
    },
    "sd15": {
        "rotulo": "SD 1.5 (DreamShaper 8)",
        "descricao": "O mais leve: roda em placas de 4 GB. Imagens de 512 px.",
        "checkpoint": "SD15/DreamShaper_8_pruned.safetensors",
        "latent": "EmptyLatentImage",
        "steps": 25, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras",
        "zero_negative": False,
        "escala": 0.5,
        "segundos_estimados": 6,
    },
}

# Estilos para a aba de geracao.
#
# O mecanismo principal e o POSITIVO, porque ele vale para todos os modelos.
# O negativo so tem efeito onde o CFG e maior que 1 — medido: no Krea (CFG 1),
# gerar "maca vermelha" com negativo "red, crimson, scarlet" devolveu a imagem
# byte por byte identica a sem negativo. 100% dos pixels iguais.
#
# `llm` orienta a expansao de prompt quando ela esta ligada; costuma render
# mais que concatenar adjetivos no fim da frase.
ESTILOS = {
    "livre": {
        "rotulo": "Livre",
        "nota": "Nada é acrescentado. Seu prompt vale como escrito.",
        "positivo": "", "negativo": "", "llm": "",
    },
    "fotorrealismo": {
        "rotulo": "Fotorrealismo",
        "nota": "Foto crível, luz natural, lente real.",
        "positivo": ("photorealistic photograph, natural light, realistic "
                     "materials and skin, shallow depth of field, 50mm lens"),
        "negativo": "illustration, painting, 3d render, cgi, plastic look, cartoon",
        "llm": "Write it as a realistic photograph: name the lens, the light and the materials.",
    },
    "cinema": {
        "rotulo": "Cinema",
        "nota": "Cor de cinema, grão preservado, luz motivada.",
        "positivo": ("cinematic still, anamorphic framing, motivated practical "
                     "lighting, filmic colour grading, subtle film grain"),
        "negativo": "flat lifeless contrast, plastic digital look, oversaturated",
        "llm": "Write it as a shot from a film: describe the light source, the mood and the colour grade.",
    },
    "editorial": {
        "rotulo": "Editorial / Fashion",
        "nota": "Moda de revista: recorte limpo, tecido com caimento.",
        "positivo": ("high-end editorial fashion photograph, controlled studio "
                     "lighting, crisp fabric texture and drape, clean styling"),
        "negativo": "amateur snapshot, cluttered background, flat lighting",
        "llm": "Write it as a fashion editorial: describe the styling, the fabric and the studio light.",
    },
    "retrato": {
        "rotulo": "Retrato de estúdio",
        "nota": "Pele natural, luz de estúdio, foco nos olhos.",
        "positivo": ("studio portrait, soft key light with gentle falloff, "
                     "natural skin texture with visible pores, sharp focus on the eyes"),
        "negativo": "plastic waxy skin, over-sharpened, harsh flash, blown highlights",
        "llm": "Write it as a studio portrait: describe the person, the light shaping and the mood.",
    },
    "produto": {
        "rotulo": "Produto",
        "nota": "Fundo limpo, material definido, reflexo controlado.",
        # A luz dura e a legibilidade do mostrador moram AQUI, nao na orientacao
        # do LLM: daqui vao direto ao modelo de imagem. Tentar impo-las pelo
        # gabarito exigia uma regra de angulo que brigava com a regra de
        # enquadramento do modo fiel, e o modelo de 8B nao sustentava as duas —
        # o relogio saia de perfil, sem mostrador. Ver prompting.EXPANSOES.
        "positivo": ("clean product photograph, seamless backdrop, precise "
                     "material definition, hard directional key light with a "
                     "visible specular streak, dial and label legible, front of "
                     "the object facing the camera"),
        "negativo": "cluttered background, distracting props, blown-out highlights",
        # MEDIDO: a orientacao antiga — "describe the material, the finish and
        # the lighting setup" — era vaga demais e perdia para o gabarito geral,
        # que puxa para luz suave por padrao. Os dois prompts expandidos
        # pediram "soft, even illumination, no harsh shadows", e em foto de
        # produto e o contrario: metal escovado so mostra o risco do acabamento
        # sob luz dura e direcionada. O mostrador do relogio ficou ilegivel.
        "llm": ("Write it as a product shot. The light is hard and directional, "
                "with a defined key that reveals the finish of the material and "
                "leaves a visible specular streak on metal; never describe the "
                "light as soft, even or diffuse. Keep any dial, label or face of "
                "the object legible and facing the camera."),
    },
    "ilustracao": {
        "rotulo": "Ilustração",
        "nota": "Traço e cor chapada, sem grão fotográfico.",
        "positivo": ("clean vector-like illustration, confident linework, flat "
                     "even colour, crisp edges, graphic composition"),
        "negativo": "photographic grain, film grain, photorealism, skin pores, noisy texture",
        "llm": "Write it as an illustration brief: describe the linework, the palette and the shapes.",
    },
    "pintura": {
        "rotulo": "Pintura",
        "nota": "Pincelada visível, tinta com corpo.",
        "positivo": ("painterly artwork, visible brushwork and impasto, layered "
                     "pigment, canvas texture"),
        "negativo": "photographic, digital smoothness, vector flatness",
        "llm": "Write it as a painting: describe the brushwork, the medium and the palette.",
    },
    "render3d": {
        "rotulo": "3D / Render",
        "nota": "Render limpo, material PBR, luz de estúdio.",
        "positivo": ("high quality 3d render, physically based materials, soft "
                     "studio HDRI lighting, clean geometry, subtle ambient occlusion"),
        "negativo": "photographic grain, hand-drawn, painterly brushwork",
        "llm": "Write it as a 3D render brief: describe the materials, the lighting rig and the surfacing.",
    },
    "arquitetura": {
        "rotulo": "Arquitetura",
        "nota": "Linha reta, perspectiva corrigida, luz de hora azul.",
        "positivo": ("architectural photograph, corrected vertical perspective, "
                     "clean straight lines, considered natural light, wide angle"),
        "negativo": "distorted converging verticals, chromatic aberration, cluttered foreground",
        "llm": "Write it as architectural photography: describe the structure, the materials and the hour of day.",
    },
    "manual": {
        "rotulo": "Manual",
        "nota": "Você escreve o acréscimo de estilo; nada vem por cima.",
        "positivo": "", "negativo": "", "llm": "",
    },
}
ESTILO_PADRAO = "livre"


def honra_negativo(modelo: str) -> bool:
    """Diz se o negativo tem efeito neste modelo.

    Com CFG 1 a orientacao sem classificador esta desligada e o negativo e
    ignorado — medido, resultado identico pixel a pixel.
    """
    if modelo in SIMPLE:
        return not SIMPLE[modelo]["zero_negative"]
    return False        # o Ideogram zera o negativo por construcao


# O Ideogram 4 tem pipeline proprio: dois UNETs via DualModelGuider, agendador
# dedicado e prompt em JSON com bounding boxes.
IDEOGRAM = {
    "rotulo": "Ideogram 4",
    "descricao": "Tipografia e layout controlado por bounding box.",
    "unet_cond": "Ideogram4/ideogram4_int8_convrot.safetensors",
    "unet_uncond": "Ideogram4/ideogram4_unconditional_int8_convrot.safetensors",
    "clip": "Qwen/qwen3vl_8b_fp8_scaled.safetensors",
    "clip_type": "ideogram4",
    "vae": "Flux2/flux2-vae.safetensors",
    "guider_cfg": 7.0,
    "override_cfg": 3.0,
    "override_start": 0.7,
    "override_end": 1.0,
    "qualidades": {
        # nome: (steps, mu, std) — valores do template oficial
        "turbo": (12, 0.5, 1.75),
        "padrao": (20, 0.0, 1.75),
        "maxima": (48, 0.0, 1.5),
    },
    "segundos_estimados": 90,
    # Texto sobre uma imagem enviada pelo usuario.
    #
    # Medimos tres caminhos. Por conditioning (`Ideogram4EditRebalance`) o
    # fundo e REINTERPRETADO e a peca vira um mockup de cartaz colado na
    # parede. Por latente da foto, o texto some abaixo de 0.7 de denoise e
    # acima disso sai pintado em perspectiva, ignorando as bboxes. O terceiro
    # funciona: o Ideogram escreve sobre preto chapado, a luminancia da peca
    # vira mascara e a foto entra so na composicao — diferenca media medida
    # fora das letras: 0.00/255, com o brilho identico ao original.
    "fundo": {
        # Corte de preto aplicado SO no ramo da mascara. Sem ele, o grao do
        # preto vira alfa parcial e deixa um veu sobre a foto inteira
        # (diferenca media 3.96/255 e a imagem escurecendo 4 niveis).
        "corte_preto": 0.28,
        "branco": 0.75,
        # Os pixels de BORDA da peca ja vem misturados com o preto do fundo.
        # Usa-los como fonte deixa uma franja escura em volta de cada glifo;
        # com tinta chapada a borda mistura tinta com a foto direto.
        "tinta_padrao": "#F2EBDC",
        # Mesma paleta oferecida na interface. Serve para sugerir uma cor
        # melhor quando a escolhida some sobre a foto.
        "paleta": ["#F2EBDC", "#FFFFFF", "#111111", "#C8A87C", "#C8342B"],
    },
}

# Modos de edicao. Os tres foram testados nesta maquina com resultado medido;
# ver NOTAS-MOTOR.md para a comparacao.
# ATENCAO: estas chaves NAO podem repetir as de SIMPLE. "klein" e "mage" sao
# nomes de modelo de geracao; usa-los aqui fazia o roteamento mandar uma
# geracao para o caminho de edicao e exigir uma imagem que nao existia.
EDICAO = {
    "anygles": {
        "grupo": "pessoa",
        # O nome antigo era "Girar a camera", e prometia o que a ferramenta NAO
        # entrega: em 14 geracoes, a PESSOA girou sempre — inclusive 180 graus,
        # de costas — mas o ponto de vista do CENARIO so mudou em duas das
        # quatro cenas. Nas duas de rua ele ficou identico. O proprio cartao do
        # modelo diz "scene context", nao geometria de cena.
        "rotulo": "Outro ângulo da pessoa",
        "descricao": ("Mostra a MESMA pessoa de outro ângulo, preservando "
                      "rosto, roupa e o tipo de cena. O cenário é recriado, "
                      "não girado junto."),
        # O mesmo stack do gerador "krea": mesma UNET, mesmo CLIP, mesmo VAE.
        # Nada novo entra em VRAM alem do LoRA de 0,2 GB.
        "unet": "Krea/krea2_turbo_fp8_scaled.safetensors",
        "clip": "Qwen/qwen3vl_4b_fp8_scaled.safetensors",
        "clip_type": "krea2",
        "vae": "Qwen/qwen_image_vae.safetensors",
        "lora": "Krea/krea2_anygles_rank32.safetensors",
        # Malha humana: o checkpoint vive na pasta `detection`, que precisou
        # ser mapeada no extra_model_paths.yaml — sem isso o seletor do
        # SAM3DBody_Loader vem VAZIO e a geracao e recusada na validacao.
        "sam3d": "SAM3/sam_3d_body_dinov3_bf16.safetensors",
        # Valores do workflow do autor, nao chutados. O LoRA e destilado sobre
        # o Krea 2 Turbo: CFG acima de 1 queima a imagem.
        "steps": 8,
        "cfg": 1.0,
        "sampler": "euler",
        "scheduler": "simple",
        "referencia_max": 384,
        "min_referencias": 1,
        # UMA pessoa. O no falha com frase clara se houver mais de uma: seguir
        # com a primeira deteccao giraria a pessoa errada, e isso passa por
        # "o modelo nao entendeu".
        "max_referencias": 1,
        # MEDIDO nesta maquina: 37 s na primeira chamada e 24 s na segunda,
        # em 1024x1536. A diferenca e o SAM 3D Body entrando em VRAM.
        "segundos_estimados": 30,
        # Os tres controles proprios desta ferramenta. Vao para a tela a
        # partir daqui — um campo novo no preset NAO aparece sozinho na
        # interface, e ja perdi uma `nota` assim.
        "camera": [
            {"id": "yaw", "rotulo": "Girar", "min": -180.0, "max": 180.0,
             "passo": 10.0, "padrao": 50.0, "unidade": "°",
             "nota": "Negativo gira para o outro lado. Se o cenário não "
                     "acompanhar, acrescente Altura."},
            # As faixas sao MAIS ESTREITAS que as do no, e de proposito. Medido
            # numa foto de corpo inteiro, com o giro travado em 0 e um
            # controle (0/0/1,0) que devolveu a foto como entrou:
            #
            #   elevacao -45 ... contra-plongee forte, ela EM PE, coerente
            #   elevacao -60 ... perde a leitura de "em pe": parece recostada
            #                    na bancada, pernas projetadas a frente
            #   distancia 0,8 .. plano mais fechado, cabeca e pes no quadro
            #   distancia 0,6 .. CORTA A CABECA — o reenquadramento centra no
            #                    corpo e o rosto sai do quadro
            #
            # Uma posicao de deslizante que entrega corpo quebrado e pior que
            # uma opcao a menos. Medido em UMA cena; se aparecer evidencia de
            # que -60 ou 0,6 servem noutra foto, alargar e barato.
            #
            # GIRO + ALTURA COMPOEM, e isso foi medido em quatro pares na
            # marcenaria: +60/+60, +60/-45, -60/+30 e 180/+60. Nenhum efeito
            # cancelou o outro e o corpo ficou integro ate no par mais
            # arriscado (giro com angulo baixo).
            #
            # E a Altura DESTRAVA o giro do cenario: na cena da rua, onde o
            # giro sozinho nao movia o fundo (a 180 graus o homem virou de
            # costas e o poste ficou parado), com +60 de altura a faixa da
            # estrada passou a ATRAVESSAR o quadro na diagonal. Daí a nota do
            # controle de giro. E uma comparacao, numa cena — nao uma regra.
            {"id": "elevation", "rotulo": "Altura", "min": -45.0, "max": 60.0,
             "passo": 5.0, "padrao": 0.0, "unidade": "°",
             "nota": "Positivo olha de cima — e aí o cenário acompanha."},
            {"id": "distance", "rotulo": "Distância", "min": 0.8, "max": 1.8,
             "passo": 0.1, "padrao": 1.0, "unidade": "×",
             "nota": "Abaixo de 1 aproxima."},
        ],
        # As duas frases sao MEDIDAS, nao palpite. O corte foi isolado num par
        # A/B: mesma cena, mesma seed, mesmo texto, so o enquadramento mudando
        # — o degrau sob os pes apareceu SO na cortada.
        "dica": ("Use fotos de CORPO INTEIRO. Numa imagem cortada na cintura o "
                 "modelo inventa as pernas e o chão, e costuma inventar um "
                 "degrau sob os pés — medido, num par com tudo igual menos o "
                 "enquadramento. Ele também REENQUADRA para o corpo todo, "
                 "então a pessoa volta menor no quadro. O cenário é "
                 "recriado: girando, às vezes acompanha o novo ângulo e às "
                 "vezes fica como estava — mas com Altura ele acompanhou até "
                 "na cena em que o giro sozinho falhava. Se o fundo não girar, "
                 "acrescente Altura."),
    },
    # O id NAO pode ser "qwen21": esse ja e o do GERADOR, em SIMPLE, e os dois
    # dicionarios dividem o mesmo espaco de nomes. O despachante consulta
    # EDICAO primeiro, entao a colisao fazia todo pedido do gerador cair na
    # edicao e ser recusado com "envie ao menos uma imagem de referencia" —
    # mensagem correta para a ferramenta errada.
    "qwen21edit": {
        "grupo": "instrucao",
        "rotulo": "Qwen 2.1",
        "descricao": ("Muda o que você pedir e preserva o resto. Aceita até "
                      "**8 imagens** — dá para pôr a pessoa de uma foto na "
                      "cena de outra. Quatro vezes mais rápida que a "
                      "Completa, e um terço do tamanho em disco."),
        "unet": "Qwen/qwen_image_2.1_int8_convrot.safetensors",
        # Ver a nota em SIMPLE["qwen21"]: o codificador NAO e intercambiavel.
        "clip": "Qwen/qwen3vl_8b_int8_convrot.safetensors",
        "clip_type": "qwen_image",
        "vae": "Qwen/qwen_image_2.1_vae_bf16.safetensors",
        "steps": 25,
        "cfg": 1.0,
        "sampler": "euler",
        "scheduler": "simple",
        # A resolucao com que as referencias entram, do template oficial.
        "resolucao_referencia": 1024,
        "min_referencias": 1,
        # O no aceita 16. Paro em 8 porque so testei com 2, e oferecer teto que
        # ninguem exerceu e prometer o que nao se sabe. Subir e uma linha.
        "max_referencias": 8,
        # MEDIDO: 21 s com uma referencia, 27 s com duas, em 1024. A "Completa"
        # (Qwen Edit 2511) leva ~85 s e ocupa 20,5 GB contra 6,76 GB desta.
        "segundos_estimados": 21,
        "dica": ("Diga o que muda E o que fica. Com mais de uma imagem, "
                 "refira-se a elas na ordem em que foram enviadas — \"a "
                 "pessoa da primeira imagem, na cena da segunda\". Para tirar "
                 "o fundo, peça \"remova o fundo, mantenha só a pessoa "
                 "sobre fundo branco\"."),
    },
    "flux3ref": {
        "grupo": "referencia",
        "rotulo": "Flux 3 com referências",
        "descricao": ("Edita ou compõe a partir de até 10 imagens: troca uma "
                      "roupa, põe a pessoa de uma imagem no cenário de outra."),
        "unet": "Flux3/flux3_image_klein_bf16.safetensors",
        "clip": "Flux3/qwen3vl_4b_int8_convrot.safetensors",
        "vae": "Flux2/flux2-vae.safetensors",
        # Template oficial image_flux3_klein_image_edit.
        "steps": 25,
        "cfg": 3.5,
        "min_referencias": 1,
        "max_referencias": 10,
        # MEDIDO a frio: 57 s com 1 referencia, 91 s com 2.
        "segundos_estimados": 70,
        "dica": ("Cite as imagens como @imagem1, @imagem2 (a ordem da lista): "
                 "\"the woman from @imagem1, in the café of @imagem2\". Diga o "
                 "que muda e o que fica igual."),
    },
    "trocar": {
        "grupo": "pessoa",
        "rotulo": "Trocar por referência",
        "descricao": ("Mantém a cena e troca quem ou o que está nela, usando outra "
                      "imagem como referência. O modo mais fiel à identidade."),
        "unet": "Flux2/flux-2-klein-base-9b-fp8.safetensors",
        "clip": "Qwen/qwen_3_8b_fp8mixed.safetensors",
        "clip_type": "flux2",
        # Decodificador pequeno do Flux 2, e o que o template oficial de edicao usa.
        "vae": "AE/full_encoder_small_decoder.safetensors",
        "steps": 20,
        "cfg": 5.0,
        "min_referencias": 1,
        "max_referencias": 4,
        "segundos_estimados": 104,
        "dica": ("A primeira imagem é a base. As seguintes são referências de quem "
                 "ou do que entra na cena. Diga na instrução o que deve ser "
                 "preservado — ele tende a trazer junto detalhes da referência, "
                 "como a roupa."),
    },
    "instrucao": {
        "grupo": "instrucao",
        "rotulo": "Rápida",
        # O tamanho preservado e ESTRUTURAL, nao amostra: o motor Qwen
        # normaliza por megapixels e devolve outro tamanho (832x1216 entrou,
        # 1032x1512 saiu). O Mage mantem o que entrou.
        "descricao": ("Muda um atributo e preserva o resto quase intacto, no "
                      "tamanho original. Três vezes mais rápida; mais fraca "
                      "em instruções compostas e para trocar pessoas."),
        "unet": "Mage/mage_flow_edit_int8_convrot.safetensors",
        "clip": "Qwen/qwen3vl_4b_bf16.safetensors",
        "clip_type": "mage",
        "vae": "Mage/mage_flow_vae_bf16.safetensors",
        "steps": 30,
        "cfg": 5.0,
        "min_referencias": 1,
        "max_referencias": 3,
        "segundos_estimados": 30,
        "dica": ("Descreva a mudança e diga explicitamente o que fica igual. "
                 "Ex.: 'deixe o mostrador azul-marinho, mantenha o resto idêntico'."),
    },
    "qwen": {
        "grupo": "instrucao",
        "rotulo": "Completa",
        "descricao": ("Entende instruções complexas e troca atributos mantendo "
                      "o resto intacto. O melhor para edição descrita em "
                      "palavras — mas devolve a imagem em outro tamanho."),
        "unet": "Qwen/qwen_image_edit_2511_int8_convrot.safetensors",
        # nvfp4: a Blackwell executa este formato nativamente, e sao 3,3 GB a
        # menos indo e voltando pelo PCIe do que o fp8 — o gargalo real num
        # modelo de 20 GB que nao cabe nos 16 GB de VRAM.
        "clip": "Qwen/qwen_2.5_vl_7b_nvfp4.safetensors",
        "clip_type": "qwen_image",
        "vae": "Qwen/qwen_image_vae.safetensors",
        "steps": 20,
        "cfg": 2.5,
        "shift": 3.0,
        "min_referencias": 1,
        # O no TextEncodeQwenImageEditPlus aceita image1, image2 e image3.
        "max_referencias": 3,
        "segundos_estimados": 85,
        # Medido nesta maquina, mesma instrucao e mesma seed. Nenhuma estourou
        # a VRAM: o pico ficou em 11,6 GB dos 16,3 GB, e o tempo cresce quase
        # em linha reta com os pixels — sinal de que o gargalo e calculo, nao
        # troca de memoria. Acima de 2 MP, a saida e ampliar no modo Ampliar.
        "resolucoes": [
            {"id": "baixa", "rotulo": "Baixa", "megapixels": 1.0,
             "nota": "~1232x840 · 60s", "segundos": 60},
            {"id": "media", "rotulo": "Média", "megapixels": 1.5,
             "nota": "~1512x1032 · 85s. A textura fina já aparece.", "segundos": 85},
            {"id": "alta", "rotulo": "Alta", "megapixels": 2.0,
             "nota": "~1744x1192 · 105s. Ganho pequeno sobre a média.",
             "segundos": 105},
        ],
        "resolucao_padrao": "media",
        "dica": ("Descreva a mudança e diga o que fica igual. Ex.: 'troque o terno "
                 "escuro por linho bege, mantendo o rosto, a pose e a luz'. "
                 "Para sair maior que 2 MP, edite aqui e depois use Ampliar."),
    },
    "luzref": {
        "grupo": "luz",
        "rotulo": "Copiar a luz de outra imagem",
        "descricao": ("Pega a iluminação e o tom de uma foto e aplica em outra, "
                      "sem mexer no conteúdo de nenhuma das duas."),
        "unet": "Qwen/qwen_image_edit_2511_int8_convrot.safetensors",
        "clip": "Qwen/qwen_2.5_vl_7b_nvfp4.safetensors",
        "clip_type": "qwen_image",
        "vae": "Qwen/qwen_image_vae.safetensors",
        "lora": "Qwen/Qwen-Image-Edit-2509-Light-Migration.safetensors",
        # A ficha da LoRA da esta frase pronta, em chines. Traduzida: "referencie
        # o tom, remova a iluminacao original da figura 1 e reilumine a figura 1
        # referenciando a luz e o tom da figura 2". Ela vai literal — e o texto
        # em que a LoRA foi treinada.
        "gatilho": ("参考色调，移除图1原有的光照并参考图2的光照和色调对图1重新照明"),
        "steps": 20,
        "cfg": 2.5,
        "megapixels": 1.5,
        "min_referencias": 2,
        "max_referencias": 2,
        # Duas imagens de 1,5 MP dobram o trabalho de condicionamento.
        "segundos_estimados": 174,
        "papeis": ["Imagem a reiluminar", "Referência de luz"],
        "dica": ("A 1ª imagem é a que muda. A 2ª entra só como exemplo de luz: "
                 "o conteúdo dela não aparece no resultado. Diferente de "
                 "Reiluminar, aqui você não descreve a luz — mostra."),
    },
    # Folha de personagem em quatro vistas, do workflow "Krea 2 Quad View".
    #
    # Roda no MESMO stack do modo "krea" — mesma UNET, mesmo CLIP, mesmo VAE.
    # O que muda e o FORMATO do grafo: aqui nao e geracao pura, e edicao por
    # referencia. A foto e redimensionada, codificada, e o modelo e remendado
    # com esse latente de origem (Krea2EditModelPatch) antes de amostrar numa
    # tela vazia deitada. A identidade vem do remendo, nao do prompt.
    #
    # O LoRA QuadView_krea2_v1 e treinado NESTA frase. Por isso ela e um
    # "gatilho" fixo, como no luzref, e nao um prompt livre: reescrever o
    # pedido afasta da distribuicao em que ele foi treinado. O que o usuario
    # escrever entra como complemento, depois.
    #
    # Existe um segundo caminho possivel: QuadView_klein9b_v1, em disco desde
    # 22/09/2026, para o Flux 2 Klein. NAO esta implementado — os nos
    # Krea2Edit* sao especificos do Krea 2, e montar o equivalente para Klein
    # sem um workflow de referencia seria inventar fiacao sem como conferir.
    "folha": {
        "grupo": "referencia",
        "rotulo": "Folha de personagem",
        "descricao": ("De uma foto, monta uma folha com quatro vistas: rosto em "
                      "close, corpo de frente, de lado e de costas."),
        "unet": "Krea/krea2_turbo_fp8_scaled.safetensors",
        "lora": "Krea/QuadView_krea2_v1.safetensors",
        "clip": "Qwen/qwen3vl_4b_fp8_scaled.safetensors",
        "clip_type": "krea2",
        "vae": "Qwen/qwen_image_vae.safetensors",
        "gatilho": ("Convert the character in the image to a Character Sheet "
                    "showing a face close-up, front full body, side full body "
                    "and back full body views"),
        # A foto entra em pe (a pessoa ocupa a altura) e a folha sai deitada
        # (as quatro vistas ocupam a largura). Nao e o mesmo numero trocado de
        # lugar: sao duas telas diferentes, e o grafo usa as duas.
        "entrada": [1024, 1536],
        "saida": [1536, 1024],
        "steps": 10,
        "cfg": 1.0,
        "min_referencias": 1,
        # Uma so: o remendo tem um unico latente de origem. O no aceita um
        # segundo (source_latent_b), mas o LoRA nao foi treinado assim.
        "max_referencias": 1,
        # Sem isto a tela chamaria a foto de "Imagem base", que aqui engana:
        # ela nao e a base que sera editada, e a pessoa a ser retratada.
        "papeis": ["A pessoa"],
        "segundos_estimados": 35,
        "dica": ("Mande uma foto do corpo inteiro, de frente e desobstruida — "
                 "o que estiver escondido na foto, o modelo inventa nas outras "
                 "vistas. O texto e opcional: serve para fixar o que a foto nao "
                 "mostra, como 'bota preta de cano curto'."),
    },
    "cabeca": {
        "grupo": "pessoa",
        "rotulo": "Trocar cabeça (BFS)",
        "descricao": ("Troca a cabeça da pessoa na cena pela cabeça de uma segunda "
                      "imagem, mantendo a composição da cena base."),
        "unet": "Krea/krea2_turbo_fp8_scaled.safetensors",
        "lora": "Krea/bfs_head_swap_v1.1_krea2.safetensors",
        "clip": "Qwen/qwen3vl_4b_fp8_scaled.safetensors",
        "clip_type": "krea2",
        "vae": "Qwen/qwen_image_vae.safetensors",
        "gatilho": "head_swap: replace the head with the reference head.",
        "entrada": [1024, 1024],
        "steps": 10,
        "cfg": 1.0,
        "min_referencias": 2,
        "max_referencias": 2,
        "papeis": ["Cena base", "Cabeça de referência"],
        "segundos_estimados": 35,
        "dica": ("Envie primeiro a cena que será editada e depois uma foto com a "
                 "cabeça desejada bem visível. O resultado segue o tamanho da "
                 "cena base, limitado a 1024 px por lado. O texto é opcional."),
    },
    "estilo": {
        "grupo": "referencia",
        "rotulo": "Gerar no estilo de",
        "descricao": ("Cria uma imagem nova imitando a estética das referências. "
                      "Não edita a imagem enviada."),
        "unet": "Krea/krea2_turbo_fp8_scaled.safetensors",
        "lora": "Krea/krea2_style_reference.safetensors",
        "clip": "Qwen/qwen3vl_4b_fp8_scaled.safetensors",
        "clip_type": "krea2",
        "vae": "Qwen/qwen_image_vae.safetensors",
        "steps": 8,
        "min_referencias": 1,
        "max_referencias": 3,
        "segundos_estimados": 30,
        "dica": ("Aqui o prompt descreve o que você quer ver, e as referências "
                 "dizem com que cara. Substitui o fotorrealismo pela estética da "
                 "referência."),
    },
}

# Troca de personagem em tres imagens, do workflow "Flux 2 Banana (V2)".
#
# A novidade nao e o modelo, e o PROTOCOLO: cada imagem tem um papel declarado
# e a instrucao diz explicitamente o que NAO copiar de cada uma. Foi assim que
# o autor resolveu o vazamento que eu via no modo "Trocar por referencia" —
# a referencia trazia junto a roupa e o angulo da cabeca.
#
# Usa a variante DESTILADA do Klein (4 passos, CFG 1), nao a base (20 / 5).
PERSONAGEM = {
    "grupo": "pessoa",
    "rotulo": "Trocar personagem (3 imagens)",
    "descricao": ("Protocolo de três papéis: cena e pose, quem entra, e o rosto. "
                  "Trava a postura e a direção do olhar."),
    # O workflow original usa o Klein 9B DESTILADO (4 passos, CFG 1). Ele mora
    # num repositorio RESTRITO da Black Forest Labs: baixar exige aceitar a
    # licenca e autenticar. Sem ele o modo cai no Klein base, que ja esta no
    # disco e faz o mesmo protocolo em 20 passos com CFG 5 — mais lento, mesma
    # instrucao. Quem decide e comfy.unets_disponiveis(), perguntando ao motor.
    "unet": "Flux2/flux-2-klein-9b-fp8.safetensors",
    "unet_alternativo": "Flux2/flux-2-klein-base-9b-fp8.safetensors",
    "clip": "Qwen/qwen_3_8b_fp8mixed.safetensors",
    "clip_type": "flux2",
    "vae": "AE/full_encoder_small_decoder.safetensors",
    # Os dois Klein resolvem coisas diferentes, e medimos a diferença nesta
    # máquina com a mesma cena e a mesma seed:
    #   destilado  4 passos   23 s   preserva melhor o cenário, mas devolve um
    #                                rosto a meio caminho entre a cena e a
    #                                referência — a identidade não chega inteira
    #   base      20 passos  129 s   transfere a estrutura facial de verdade
    # O destilado roda em CFG 1, onde o prompt negativo é ignorado — nada se
    # perde aqui, porque este modo não usa negativo.
    #
    # A ORDEM DESTE DICIONARIO E O PADRAO. Quem abre o painel cai na primeira
    # chave que estiver disponivel — ver app.escolher_modelo_personagem e o
    # catalogo em app.py, que filtra "rapido" quando o destilado nao esta no
    # disco. Por isso "rapido" vem primeiro.
    #
    # Ate 22/09/2026 o padrao era "fiel", justificado pela medicao acima: o
    # destilado devolvia "um rosto a meio caminho". A medicao de 18/09 revogou
    # isso — lado a lado, com a mesma base e a mesma referencia, o destilado
    # empatou. O padrao ficou para tras da propria nota que o painel mostrava,
    # que ja mandava comecar pelo Rapido. Agora manda e abre no mesmo lugar.
    "prioridades": {
        "rapido": {
            "rotulo": "Rápido",
            # MEDIDO em 18/09/2026: com a mesma base e a mesma referencia, o
            # resultado saiu equivalente ao Fiel em 20 s contra 150 s. E uma
            # imagem so, entao a nota sugere sem prometer — mas a antiga
            # afirmava que "o rosto sai so parecido", e isso nao se sustentou.
            "nota": "4 passos no Klein destilado, cerca de 7x mais rápido. "
                    "Num teste lado a lado empatou com o Fiel; troque para "
                    "Fiel se a identidade não vier.",
            "destilado": True, "steps": 4, "cfg": 1.0, "segundos": 25,
        },
        "fiel": {
            "rotulo": "Fiel",
            "nota": "20 passos no Klein base. Transfere a identidade de verdade.",
            "destilado": False, "steps": 20, "cfg": 5.0, "segundos": 130,
        },
    },
    "sampler": "euler",
    "scheduler": "simple",
    "min_referencias": 2,
    "max_referencias": 3,
    "segundos_estimados": 30,
    "dica": ("1ª imagem: a cena e a pose, tratadas como imutáveis. "
             "2ª: a pessoa que entra. "
             "3ª (opcional): rosto e roupa exatos. Sem ela, a 2ª faz os dois papéis."),
    "papeis": ["Cena e pose", "Pessoa que entra", "Rosto e roupa"],
    # Blocos da instrucao. Ficam separados para o usuario poder desligar o que
    # nao se aplica — travar o olhar atrapalha se ele DEVE olhar para a camera.
    "blocos": {
        "pose": {
            "rotulo": "Travar a pose",
            "padrao": True,
            "texto": ("Figure 1 is the pose and body orientation reference. Treat it "
                      "as immutable. The replacement must occupy the exact same "
                      "position, size, silhouette, camera perspective and composition. "
                      "Copy the body orientation exactly, including foot placement, "
                      "leg position, weight distribution, pelvis direction, spine "
                      "angle, chest direction, shoulder angle, arm position, elbow "
                      "angle, wrist rotation and hand placement. Do not rotate, "
                      "straighten, rebalance, recentre or reinterpret any part of "
                      "the pose."),
        },
        "cabeca": {
            "rotulo": "Travar cabeça e olhar",
            "padrao": True,
            "texto": ("Lock the head to the body. The neck, head and torso must remain "
                      "rigidly aligned exactly as in Figure 1. Preserve the exact head "
                      "yaw, pitch, roll, chin angle, eye-line and facing direction. "
                      "Maintain the identical gaze direction from Figure 1."),
        },
        "identidade": {
            "rotulo": "Só a identidade do rosto",
            "padrao": True,
            "texto": ("Transfer only the identity from Figure 3. Match the facial "
                      "structure, proportions, features, skin tone, hairstyle, facial "
                      "hair and natural expression exactly. Do NOT copy the pose, head "
                      "angle, gaze direction, body orientation or camera angle from "
                      "Figure 3."),
        },
        "roupa": {
            "rotulo": "Copiar a roupa da referência",
            "padrao": False,
            "texto": ("Use Figure 3 as the exact clothing reference. Match the "
                      "clothing, colours, textures, folds and fit precisely without "
                      "changing the pose."),
        },
        "integracao": {
            "rotulo": "Integrar à cena",
            "padrao": True,
            "texto": ("Seamless in-camera realism, anatomically correct proportions, "
                      "realistic skin texture, physically accurate lighting, natural "
                      "shadows and perfect environmental integration. Preserve the "
                      "original light direction of Figure 1."),
        },
    },
}

# Controle de estrutura com o ControlNet Union do Z-Image. O modelo entra como
# um "model patch", nao como um ControlNet classico.
CONTROLE = {
    "grupo": "enquadramento",
    "rotulo": "Guiar pela estrutura",
    "descricao": ("Gera uma imagem nova seguindo a composição, a pose ou o "
                  "relevo de uma imagem de referência."),
    "unet": "Z_Image/z_image_turbo_bf16.safetensors",
    "patch": "Z-Image/Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors",
    "clip": "Qwen/qwen_3_4b.safetensors",
    "clip_type": "lumina2",
    "vae": "AE/ae.safetensors",
    "steps": 8,
    "cfg": 1.0,
    # O template oficial usa este amostrador e este shift; euler simples perde
    # aderencia ao mapa de controle.
    "sampler": "res_multistep",
    "scheduler": "simple",
    "shift": 3.0,
    "lado_maximo": 1024,
    "min_referencias": 1,
    "max_referencias": 1,
    "segundos_estimados": 35,
    "dica": ("A referência dá só a estrutura; o prompt diz o que desenhar nela. "
             "Contorno segue bordas, profundidade segue volume, pose segue o "
             "esqueleto da pessoa."),
    # Cada tipo produz um mapa diferente a partir da mesma imagem.
    "tipos": {
        "contorno": {"rotulo": "Contorno", "no": "Canny",
                     "inputs": {"low_threshold": 0.1, "high_threshold": 0.32}},
        "profundidade": {"rotulo": "Profundidade", "no": "DepthAnythingV2Preprocessor",
                         "inputs": {"ckpt_name": "depth_anything_v2_vitl.pth",
                                    "resolution": 1024}},
        "pose": {"rotulo": "Pose", "no": "DWPreprocessor",
                 "inputs": {"detect_hand": "enable", "detect_body": "enable",
                            "detect_face": "enable", "resolution": 1024}},
        "linhas": {"rotulo": "Linhas", "no": "HEDPreprocessor",
                   "inputs": {"safe": "enable", "resolution": 1024}},
    },
}

# Ampliacao e restauracao. Dois caminhos com custos bem diferentes.
AMPLIAR = {
    "grupo": "acabamento",
    "rotulo": "Restaurar e ampliar",
    "descricao": "Aumenta a resolução e recupera detalhe. Não precisa de prompt.",
    "min_referencias": 1,
    "max_referencias": 1,
    "segundos_estimados": 60,
    # MEDIDO em 18/09/2026, mesma imagem, 2x: SeedVR2 16 s, clássico 33 s,
    # criativo 36 s. O clássico era rotulado "instantâneo" e leva o DOBRO do
    # SeedVR2 — ele é rápido por pixel, mas roda em 4x nativo e reduz depois.
    "dica": ("O SeedVR2 refaz o detalhe com um modelo de difusão — melhor em "
             "textura de pele, tecido e tipografia, e o mais rápido dos três. "
             "O clássico só interpola o que já existe."),
    "metodos": {
        "magnific": {"rotulo": "Magnific Upscale Creative (nuvem)", "nota": "Ampliação guiada por prompt via Comfy. Pode inventar detalhes; máximo de 25,3 MP.", "motor": "nuvem", "custo_usd": 0.172},
        "topaz": {
            "rotulo": "Topaz (nuvem)",
            "nota": "Padrão da indústria para textura de pele e cabelo. Não "
                    "inventa detalhe como o Criativo. Custa cerca de "
                    "US$ 0,11 por 8 MP de saída, e a foto sai da sua máquina.",
            "motor": "nuvem",
            "custo_usd": 0.1144,
            "modelo_topaz": "Wonder 3.5",
        },
        "seedvr": {
            "rotulo": "SeedVR2 (qualidade)",
            "nota": "O mais rápido e o de melhor textura nos testes.",
            "unet": "SeedVR/seedvr2_3b_int8_convrot.safetensors",
            "vae": "SeedVR/seedvr2_ema_vae_fp16.safetensors",
            # O modelo roda em um unico passo; nao adianta subir.
            "steps": 1,
            "cfg": 1.0,
            "ladrilho": 512,
            "sobreposicao": 128,
            "correcao_cor": "wavelet",  # cor do original por regiao; o "lab" deixava os olhos verde-agua (teste de 31/10/2026)
        },
        "criativo": {
            "rotulo": "Criativo (inventa detalhe)",
            "nota": "Reconstrói: além de textura, desloca levemente o "
                    "enquadramento e amacia a pele. O que menos preserva.",
            # Amplia com ESRGAN e re-difunde por cima com o Z-Image, guiado por
            # prompt. E a receita dos ampliadores "criativos": o denoise e
            # literalmente o controle de criatividade.
            "unet": "Z_Image/z_image_turbo_bf16.safetensors",
            "clip": "Qwen/qwen_3_4b.safetensors",
            "clip_type": "lumina2",
            "vae": "AE/ae.safetensors",
            # RealESRGAN e o que o template oficial usa. O UltraSharpV2 deixa
            # uma trama diagonal fina na pele que a transferencia de alta
            # frequencia amplifica — testado lado a lado.
            "ampliador": "RealESRGAN_x4plus.safetensors",
            "fator_nativo": 4,
            "steps": 5,
            "cfg": 1.0,
            "sampler": "dpmpp_2m_sde",
            "scheduler": "beta",
            "shift": 3.0,
            "megapixels_entrada": 1.0,
            # Teto do tamanho em que a DIFUSAO roda. Sem ele o modo travava a
            # maquina em 3x e 4x: a entrada normalizada de 1 MP passa pelo
            # ESRGAN 4x e vira 16 MP, e o VAEEncode de 16 MP nao cabe nos 16 GB
            # — a GPU ficava em 100% com 15,9 GB ocupados, sem terminar nunca.
            # Pior, o /interrupt nao resolve: o ComfyUI so checa interrupcao
            # ENTRE nos, e aquilo era uma operacao unica de CUDA.
            #
            # Com o teto, a difusao acontece em no maximo 2,25 MP e o resto do
            # aumento e feito depois, por reescala. Isso tambem conserta a
            # escala: antes o modo entregava o tamanho que sobrava do seu
            # proprio encadeamento, nao o que foi pedido.
            "megapixels_difusao": 2.25,
        },
        "classico": {
            "rotulo": "Ampliador clássico (plano B)",
            # Num rosto a 1:1 ele devolve a trama fina do UltraSharpV2 que
            # este projeto ja documentou. Serve quando o SeedVR2 nao couber.
            "nota": "Mais macio e sem inventar nada. Deixa uma trama fina na "
                    "pele, visível a 100%.",
            "modelo": "4x-UltraSharpV2.safetensors",
            # Os modelos ESRGAN sao fixos em 4x; reduzimos depois se preciso.
            "fator_nativo": 4,
        },
    },
    "escalas": [1.5, 2.0, 3.0, 4.0],
    # "Otimizado para": cada preset traz um prompt positivo e um ponto de
    # partida para os controles. Sao valores escolhidos pela logica de cada
    # uso, nao otimos medidos — o usuario mexe a partir dai.
    #
    # A logica geral: quanto mais a imagem depende de forma exata (letras,
    # produto), menos criatividade e mais semelhanca; quanto mais ela depende
    # de textura (pele, folhagem), o contrario.
    "otimizacoes": {
        "geral": {
            "rotulo": "Geral",
            "prompt": "high quality photograph, sharp, natural detail",
            # Estes valores sao do modo CRIATIVO — repare que cada preset
            # carrega um "prompt", e so o criativo usa prompt.
            #
            # O SeedVR2 NAO tem preset: ele roda CRU, e o acabamento fica nos
            # controles manuais. O passo de detalhe transplanta alta frequencia
            # de uma imagem-fonte, e as tres fontes possiveis estragam:
            #   lanczos      -> borra (e a fonte mais macia do grafo)
            #   UltraSharpV2 -> trama diagonal na pele
            #   RealESRGAN   -> pele plastica, cilios virando traco
            # E a dose nao resolve: ja em 0,15 a textura some quase toda, entao
            # nao ha meio-termo entre cru e borrado. Ver o README.
            #
            # MEDIDO: com o SeedVR2 o microcontraste piora. Reduzindo uma
            # imagem nitida a metade e ampliando de volta, com o original como
            # verdade (nitidez 3,11):
            #   SeedVR2 puro ................ 4,54  (ja passa da verdade)
            #   + detalhe 0,40 .............. 3,06  <- quase exato
            #   + detalhe e micro 0,05 ...... 3,58
            #   + detalhe e micro 0,25 ...... 3,71  (era o padrao daqui)
            # O SeedVR2 de 1 passo ja devolve mais borda que o real, e o
            # ImageCASharpening+ e forte mesmo em 0,05. O passo de detalhe
            # sozinho reancora a imagem na verdade; o microcontraste so
            # empurra de volta para o exagero, com halo na borda.
            # Este bloco continua com 0.25: ele vale para o CRIATIVO, que
            # re-difunde e de fato suaviza. So o SeedVR2 foi medido.
            "padroes": {"criatividade": 0.33, "semelhanca": 0.0,
                        "detalhe": 0.40, "microcontraste": 0.25, "granulacao": 0.0},
        },
        "retrato_suave": {
            "rotulo": "Retratos suaves",
            "prompt": ("soft natural portrait, gentle diffused light, smooth even skin, "
                       "delicate transitions, shallow depth of field, film-like"),
            # Criatividade baixa: pele inventada vira textura artificial. Um
            # grao leve devolve o aspecto fotografico que a suavizacao tira.
            "padroes": {"criatividade": 0.22, "semelhanca": 0.20,
                        "detalhe": 0.30, "microcontraste": 0.15, "granulacao": 0.06},
        },
        "pele_detalhe": {
            "rotulo": "Pele e detalhe",
            "prompt": ("highly detailed skin with visible pores and fine hair, crisp "
                       "eyelashes, realistic subsurface scattering, sharp facial detail"),
            "padroes": {"criatividade": 0.40, "semelhanca": 0.0,
                        "detalhe": 0.60, "microcontraste": 0.35, "granulacao": 0.10},
        },
        "paisagem": {
            "rotulo": "Paisagem",
            "prompt": ("expansive landscape photograph, crisp foliage and rock texture, "
                       "atmospheric depth, fine distant detail, high dynamic range"),
            # Folhagem e rocha aguentam invencao: nao ha forma exata a respeitar.
            "padroes": {"criatividade": 0.45, "semelhanca": 0.0,
                        "detalhe": 0.55, "microcontraste": 0.30, "granulacao": 0.0},
        },
        "produto": {
            "rotulo": "Produto",
            "prompt": ("clean product photograph, precise material definition, crisp "
                       "edges, accurate reflections and specular highlights, studio light"),
            # O produto precisa continuar sendo o mesmo produto.
            "padroes": {"criatividade": 0.20, "semelhanca": 0.25,
                        "detalhe": 0.45, "microcontraste": 0.35, "granulacao": 0.0},
        },
        "ilustracao": {
            "rotulo": "Ilustração",
            "prompt": ("clean illustration, confident linework, flat even colour, crisp "
                       "edges, no photographic grain"),
            # Arte chapada nao tem microdetalhe a recuperar, e grao a estraga.
            "padroes": {"criatividade": 0.25, "semelhanca": 0.15,
                        "detalhe": 0.20, "microcontraste": 0.20, "granulacao": 0.0},
        },
        "tipografia": {
            "rotulo": "Tipografia",
            "prompt": ("crisp legible typography, clean letterforms with sharp edges, "
                       "even stroke weight, print quality"),
            # O caso mais sensivel: letra reinventada vira letra errada.
            "padroes": {"criatividade": 0.15, "semelhanca": 0.35,
                        "detalhe": 0.50, "microcontraste": 0.30, "granulacao": 0.0},
        },
    },
    # Acabamento aplicado depois da difusao, na ordem em que aparece aqui.
    "acabamento": {
        # Traz de volta a alta frequencia da versao so-ESRGAN, que a difusao
        # tende a suavizar. Nao inventa detalhe: recupera o que havia.
        # keep_high_freq acima do padrao do no (64) produz trama e desvio de
        # cor; o controle 0..1 mapeia ate esse teto, nao alem dele.
        "detalhe": {"no": "LayerUtility: HLFrequencyDetailRestore",
                    "keep_high_freq_max": 64, "erase_low_freq": 32,
                    "mask_blur": 16,
                    "recor_no": "SeedVR2PostProcessing", "recor_metodo": "lab"},
        "microcontraste": {"no": "ImageCASharpening+"},
        "granulacao": {"no": "LayerFilter: AddGrain", "escala": 1.0, "saturacao": 0.3},
    },
}

# Mudar o angulo e reiluminar. Os dois rodam sobre o Flux 2 Klein Edit, que e
# o modo mais fiel a identidade — aqui o que muda e a instrucao.
#
# Ressalva medida: o Klein gira o SUJEITO, nao a camera. O fundo mantem a
# perspectiva original. Serve para virar uma pessoa ou um objeto, nao para
# andar em volta da cena.
ANGULO = {
    "grupo": "enquadramento",
    "rotulo": "Mudar o ângulo",
    "descricao": ("Vira o sujeito para outro ponto de vista, mantendo cenário, "
                  "roupa e iluminação."),
    "min_referencias": 1,
    "max_referencias": 1,
    "segundos_estimados": 70,
    "dica": ("Ele gira o sujeito, não a câmera: o fundo mantém a perspectiva "
             "original. Para virar uma pessoa ou um objeto funciona bem; para "
             "recompor a cena inteira, não."),
    "preservar": ("Keep the same subject, the same clothing, the same setting and "
                  "the same lighting. Change only the point of view."),
    "vistas": {
        # "frase" gira o CORPO (caminho Klein). "frase_camera" move a CAMERA
        # (caminho Qwen + LoRA) e usa a redacao que a ficha da LoRA documenta —
        # ela so responde bem ao vocabulario em que foi treinada.
        "tres_quartos_esq": {"rotulo": "3/4 pela esquerda",
                             "frase": "Turn the subject to a three-quarter view from their left side",
                             "frase_camera": "Rotate the camera 45 degrees to the left."},
        "tres_quartos_dir": {"rotulo": "3/4 pela direita",
                             "frase": "Turn the subject to a three-quarter view from their right side",
                             "frase_camera": "Rotate the camera 45 degrees to the right."},
        # "Rotate the camera 90 degrees" QUEBRA: a LoRA le isso como ROLAR a
        # camera, e no retrato de rua ela devolveu a imagem inteira deitada de
        # lado. O vocabulario dela para orbita e "45 degrees"; 90 nao existe.
        # "Turn the camera to a side view" resolve, e foi verificado nas duas
        # cenas. Os 180 graus, ao contrario, funcionaram direto.
        "perfil": {"rotulo": "Perfil",
                   "frase": "Turn the subject to a full side profile",
                   "frase_camera": "Turn the camera to a side view."},
        "de_tras": {"rotulo": "De trás",
                    "frase": "Show the subject from behind, seen over the shoulder",
                    "frase_camera": "Rotate the camera 180 degrees to view the subject from behind."},
        "contra_plongee": {"rotulo": "De baixo",
                           "frase": "Move the camera low, looking up at the subject from below eye level",
                           "frase_camera": "Turn the camera to a low-angle view, looking up."},
        "plongee": {"rotulo": "De cima",
                    "frase": "Move the camera high, looking down at the subject from above",
                    "frase_camera": "Turn the camera to a top-down view."},
        "aproximar": {"rotulo": "Aproximar",
                      "frase": "Move the camera closer for a tighter framing of the subject",
                      "frase_camera": "Turn the camera to a close-up."},
        "afastar": {"rotulo": "Afastar",
                    "frase": "Move the camera back for a wider framing, showing more of the surroundings",
                    "frase_camera": "Turn the camera to a wide-angle lens."},
    },
    # Duas operacoes diferentes, nao duas qualidades da mesma coisa. Medido em
    # 2 cenas x 3 vistas: o Klein gira o CORPO e mantem o enquadramento; a LoRA
    # move a CAMERA. Na cena do cafe, sentado a mesa, o Klein quase nao mudou
    # nada (14,3 de diferenca contra 55,0 da LoRA), porque nao havia espaco
    # para girar o corpo. Ja na vista de cima o Klein foi melhor.
    "direcoes_96": ["front view", "front-right quarter view", "right side view", "back-right quarter view",
                    "back view", "back-left quarter view", "left side view", "front-left quarter view"],
    "alturas_96": ["low-angle shot", "eye-level shot", "elevated shot", "high-angle shot"],
    "distancias_96": ["close-up", "medium shot", "wide shot"],
    "metodos": {
        "camera": {
            "rotulo": "Mover a câmera",
            "nota": "O ponto de vista muda de verdade, e o fundo acompanha.",
            "motor": "qwen",
            "lora": "Qwen/Qwen-Edit-2509-Multiple-angles.safetensors",
            "segundos": 108,
        },
        # Orbit com o Qwen (31/10/2026): LoRA da fal para o Qwen Image Edit 2511,
        # 96 poses (8 direcoes x 4 alturas x 3 distancias) treinadas com renders de
        # Gaussian Splatting. A frase e a do treino: "<sks> direcao altura distancia".
        "camera96": {
            "rotulo": "Câmera em 96 posições",
            "nota": "Direcao de 45 em 45 graus, 4 alturas e 3 distancias; preserva a pessoa.",
            "motor": "qwen",
            "lora": "Qwen/Qwen-Image-Edit-2511-Multiple-Angles.safetensors",
            "forca": 0.9,
            "segundos": 120,
        },
        "personagem": {
            "rotulo": "Girar o personagem",
            "nota": "O corpo se vira e o enquadramento fica. Mais rápido, e "
                    "melhor para a vista de cima.",
            "motor": "klein",
            "segundos": 61,
        },
    },
    "metodo_padrao": "camera",
}

RELUZ = {
    "grupo": "luz",
    "rotulo": "Reiluminar",
    "descricao": "Troca a luz da cena preservando quem e o que está nela.",
    "min_referencias": 1,
    "max_referencias": 1,
    "segundos_estimados": 130,
    "dica": ("Arraste a luz na esfera. A direção horizontal o modelo segue bem; "
             "a altura ele segue só em parte — é aproximação, não luz física."),
    "preservar": ("Keep the subject, their face, their clothing, the background and "
                  "the framing exactly the same. Change only the lighting."),
    "temperaturas": {"quente": "Quente", "neutra": "Neutra", "fria": "Fria"},
    # Medido em duas cenas com temperaturas OPOSTAS (quente pela direita,
    # fria pela esquerda), e o padrao se repetiu nas duas — entao nao e
    # caracteristica de uma cena:
    #   Klein  -> clima geral: clareia e tinge a imagem inteira. No primeiro
    #             teste somou +51 de calor, mas tingiu o terno de marrom.
    #   Qwen   -> luz direcional: da para ver de onde vem a luz, e o lado
    #             oposto fica na sombra. Somou +31, sem mexer na cor dos
    #             materiais. E o caminho que faz a esfera 3D valer a pena,
    #             porque o modelo obedece a direcao.
    "metodos": {
        "direcional": {
            "rotulo": "Luz direcional",
            "nota": "Cria uma fonte de luz com sombra coerente. Segue a esfera.",
            "motor": "qwen",
            "lora": "Qwen/Qwen-Image-Edit-2509-Relight.safetensors",
            # A ficha da LoRA exige este gatilho, em chines, antes da descricao.
            "gatilho": "重新照明，",
            "segundos": 106,
        },
        "nuvem": {
            "rotulo": "Magnific (nuvem)",
            "nota": "Reilumina por descrição OU copia a luz de uma referência, "
                    "num passo só. Não tem seed: repetir devolve o mesmo. "
                    "Custa US$ 0,11 e a foto sai da sua máquina.",
            "motor": "nuvem",
            "segundos": 30,
            "custo_usd": 0.11,
            # Duas imagens: a que sera reiluminada e, opcionalmente, aquela de
            # onde copiar a luz. Os outros metodos so aceitam uma — o mapa da
            # esfera e acrescentado pelo servidor, nao pelo usuario.
            "max_referencias": 2,
            "estilos": [
                ("standard", "Padrão"),
                ("darker_but_realistic", "Mais escuro, realista"),
                ("clean", "Limpo"),
                ("smooth", "Suave"),
                ("brighter", "Mais claro"),
                ("contrasted_n_hdr", "Contrastado / HDR"),
                ("just_composition", "Só a composição"),
            ],
        },
        "clima": {
            "rotulo": "Clima geral",
            "nota": "Muda a atmosfera da imagem toda. Mais forte e mais rápido, "
                    "mas pode tingir as roupas.",
            "motor": "klein",
            "segundos": 61,
        },
    },
    "metodo_padrao": "direcional",
}

# Freio do artefato, por tipo de imagem.
#
# Quando a mesma imagem passa varias vezes pelo modelo, a textura vai virando
# crosta. Medido num retrato, no mesmo recorte de rosto (desvio padrao da alta
# frequencia):
#
#     original ................ 6,8
#     1 passagem .............. 9,4
#     2 passagens ............ 14,9
#     3 passagens ............ 16,3   <- "nenhum"
#     3 passagens ............. 7,0   <- "moderado"  (= nivel do original)
#     3 passagens ............. 6,3   <- "forte"     (alisa um pouco alem)
#
# Ate aqui os modos de edicao mandavam negativo VAZIO, o que com CFG 5 e
# desperdicio: o negativo e metade da direcao.
#
# Cada tipo tem seu proprio negativo porque o defeito nao e o mesmo: num
# retrato e poro virando crosta; numa paisagem e halo e HDR agressivo; em
# cinema o grao e DESEJADO, entao nao entra no negativo; em ilustracao o grao
# e o defeito.
#
# Baixar o CFG NAO ajuda — testado, piora, porque enfraquece justamente o
# negativo (CFG 3,5 deu 9,2 e CFG 2,5 deu 11,1 onde CFG 5 deu 6,3).
#
# Honestidade: so o caso "retrato" foi medido. Os demais sao escolhidos pela
# logica do defeito de cada tipo, nao por varredura.
TIPOS_IMAGEM = {
    "retrato": {
        "rotulo": "Retrato",
        "nota": "Pele virando crosta, poro exagerado, ruga riscada.",
        "moderado": ("over-sharpened skin, crunchy over-processed texture, "
                     "etched engraved wrinkles, halo artifacts around edges"),
        "forte": ("plastic waxy skin, over-sharpened, crunchy over-processed "
                  "texture, etched engraved wrinkles, exaggerated enlarged pores, "
                  "dry cracked skin, halo artifacts around edges, harsh HDR "
                  "micro-contrast, digital noise, oversaturated detail"),
    },
    "fotografia": {
        "rotulo": "Fotografia",
        "nota": "Uso geral. Segura nitidez artificial e halo de borda.",
        "moderado": ("over-sharpened, halo artifacts around edges, "
                     "crunchy over-processed texture"),
        "forte": ("over-sharpened, halo artifacts around edges, crunchy "
                  "over-processed texture, harsh HDR micro-contrast, plastic "
                  "surfaces, oversaturated detail, digital noise"),
    },
    "cinema": {
        "rotulo": "Cinema",
        "nota": "Preserva o grão: ele não entra no negativo, de propósito.",
        "moderado": ("over-sharpened, halo artifacts around edges, "
                     "plastic digital look, waxy skin"),
        "forte": ("over-sharpened, halo artifacts around edges, plastic digital "
                  "look, waxy skin, harsh HDR micro-contrast, flat lifeless "
                  "contrast, oversaturated detail"),
    },
    "fashion": {
        "rotulo": "Fashion",
        "nota": "Pele e caimento do tecido ao mesmo tempo.",
        "moderado": ("over-sharpened skin, plastic waxy skin, flattened fabric "
                     "texture, halo artifacts around edges"),
        "forte": ("plastic waxy skin, over-sharpened, etched wrinkles, "
                  "exaggerated pores, flattened fabric texture, muddy fabric "
                  "weave, halo artifacts around edges, harsh HDR micro-contrast"),
    },
    "paisagem": {
        "rotulo": "Paisagem",
        "nota": "Folhagem e rocha viram ruído com facilidade.",
        "moderado": ("over-sharpened foliage, halo artifacts around edges, "
                     "harsh HDR look"),
        "forte": ("over-sharpened foliage, halo artifacts around edges, harsh "
                  "HDR look, oversaturated colour, crunchy over-processed "
                  "texture, muddy noisy detail"),
    },
    "produto": {
        "rotulo": "Produto",
        "nota": "Borda limpa e reflexo sem estouro.",
        "moderado": ("halo artifacts around edges, over-sharpened, "
                     "blown-out highlights"),
        "forte": ("halo artifacts around edges, over-sharpened, blown-out "
                  "highlights, plastic fake material, crunchy over-processed "
                  "texture, oversaturated detail"),
    },
    "ilustracao": {
        "rotulo": "Ilustração",
        "nota": "Aqui o grão é o defeito, não a virtude.",
        "moderado": ("photographic grain, film grain, skin pores, "
                     "over-sharpened, noisy texture"),
        "forte": ("photographic grain, film grain, skin pores, over-sharpened, "
                  "noisy texture, halo artifacts around edges, muddy colour, "
                  "photographic realism"),
    },
    "arquitetura": {
        "rotulo": "Arquitetura",
        "nota": "Linha reta e aresta, sem franja de contorno.",
        "moderado": ("halo artifacts around edges, over-sharpened, "
                     "chromatic aberration"),
        "forte": ("halo artifacts around edges, over-sharpened, chromatic "
                  "aberration, harsh HDR look, crunchy over-processed texture, "
                  "oversaturated detail"),
    },
}
# "manual" nao e um tipo: e a saida para quando nenhum preset serve. O texto
# vem do proprio usuario, sem nada acrescentado por cima.
TIPO_MANUAL = "manual"
TIPO_IMAGEM_PADRAO = "retrato"
NIVEL_PELE_PADRAO = "moderado"


def negativo_do_tipo(tipo: str, nivel: str, manual: str = "") -> str:
    """Negativo do freio, escolhido pelo tipo e pela intensidade.

    No modo manual o nivel nao se aplica: vale exatamente o que o usuario
    escreveu, inclusive vazio.
    """
    if tipo == TIPO_MANUAL:
        return manual.strip()
    if nivel == "nenhum":
        return ""
    t = TIPOS_IMAGEM.get(tipo, TIPOS_IMAGEM[TIPO_IMAGEM_PADRAO])
    return t.get(nivel, t["moderado"])


# Mascara por segmentacao. Nao e um modo: e um complemento dos modos de edicao.
# O SAM 3 acha a regiao a partir de um texto e so ela recebe o resultado do
# modelo — o resto da imagem e copiado do original, sem passar pela difusao.
# Orbit 3D (31/10/2026): TRELLIS 2 nativo do ComfyUI faz a malha com textura da foto
# (37 s numa placa de 16 GB) e a renderiza no angulo pedido; o Qwen Image Edit 2511
# refaz o render como foto, com a original como referencia de rosto e lugar.
# Ajustes do template oficial 3d_pixal3d_trellis2_image_to_model.
TRELLIS = {
    "unet": "Trellis/trellis_2_int8_convrot.safetensors",
    "vae_forma": "Trellis/trellis_2_shape_vae_bf16.safetensors",
    "vae_textura": "Trellis/trellis_2_texture_vae_bf16.safetensors",
    "dino": "dino_v3_L_naf_fp32.safetensors",
    "recorte": "birefnet.safetensors",
    "instrucao": ("Turn @image1 into a real photograph of the person from @image2, in exactly the same pose, body angle "
                  "and camera angle as @image1. The person has the face, hair and clothes of @image2. Place them in the "
                  "same location as @image2, with the same light, seen from this new angle. Photorealistic, natural "
                  "skin, not a 3D render."),
}


MASCARA = {
    "checkpoint": "SAM3/sam3.1_multiplex_fp16.safetensors",
    "limiar": 0.5,
    "expandir": 12,
    "suavizar": 12,
}

# Modelo usado para escrever o JSON de layout do Ideogram e para expandir
# prompts. E um Qwen3-VL carregado como CLIP e usado via no TextGenerate.
LLM = {
    "clip": "Qwen/qwen3vl_8b_fp8_scaled.safetensors",
    "clip_type": "ideogram4",
}

PROPORCOES = {
    "1:1": (1024, 1024),
    "4:5": (896, 1152),
    "2:3": (832, 1216),
    "9:16": (768, 1344),
    "3:2": (1216, 832),
    "16:9": (1344, 768),
    "3:1": (1728, 576),
}


def dimensoes_4k(proporcao: str) -> tuple[int, int]:
    """A proporcao escolhida com a area de 3840x2160 (~8,3 MP), multiplos de 16."""
    w, h = PROPORCOES.get(proporcao, PROPORCOES["1:1"])
    fator = (3840 * 2160 / (w * h)) ** 0.5
    return (round(w * fator / 16) * 16, round(h * fator / 16) * 16)


def dimensoes(proporcao: str, escala: float = 1.0) -> tuple[int, int]:
    """Dimensoes multiplas de 16, como os templates oficiais exigem."""
    w, h = PROPORCOES.get(proporcao, PROPORCOES["1:1"])
    w, h = int(w * escala), int(h * escala)
    arredonda = lambda v: max(((v + 15) // 16) * 16, 256)
    return arredonda(w), arredonda(h)


# Ajuste fino de rosto pelo ExpressionEditor (comfyui-advancedliveportrait).
#
# NAO e difusao: e deformacao por pontos-chave. O modelo nao regenera a imagem,
# empurra a malha do rosto. Por isso leva 1,1 s em vez de 60 a 110 s, nao mexe
# no fundo nem na identidade, e repete igual — nao ha seed.
#
# Os pesos sao baixados sob demanda na PRIMEIRA execucao (repositorio aberto
# Kijai/LivePortrait_safetensors). As duas primeiras chamadas falharam enquanto
# isso acontecia, entao quem chama precisa tratar essa falha e tentar de novo.
ROSTO = {
    "grupo": "acabamento",
    "rotulo": "Ajustar o rosto",
    "descricao": ("Olhar, expressão e micro-rotação da cabeça. Instantâneo, e "
                  "não toca em mais nada da imagem."),
    "dica": ("Só funciona onde há um rosto detectável, e mexe apenas no rosto. "
             "Diferente dos outros modos, o resultado é sempre o mesmo: não há "
             "sorteio."),
    "min_referencias": 1,
    "max_referencias": 1,
    "segundos_estimados": 2,
    # Faixas conforme o no declara. O passo e generoso de proposito: um decimo
    # de grau nao e perceptivel, e atrapalha arrastar.
    "grupos": [
        {"rotulo": "Olhar", "controles": [
            {"id": "pupil_x", "rotulo": "Olhar horizontal", "min": -15, "max": 15,
             "passo": 0.5, "padrao": 0, "dica": "Negativo olha para a câmera."},
            {"id": "pupil_y", "rotulo": "Olhar vertical", "min": -15, "max": 15,
             "passo": 0.5, "padrao": 0},
        ]},
        {"rotulo": "Cabeça", "controles": [
            {"id": "rotate_yaw", "rotulo": "Virar", "min": -20, "max": 20,
             "passo": 0.5, "padrao": 0, "dica": "Graus para os lados."},
            {"id": "rotate_pitch", "rotulo": "Inclinar", "min": -20, "max": 20,
             "passo": 0.5, "padrao": 0, "dica": "Queixo para cima ou para baixo."},
            {"id": "rotate_roll", "rotulo": "Tombar", "min": -20, "max": 20,
             "passo": 0.5, "padrao": 0},
        ]},
        {"rotulo": "Olhos e sobrancelhas", "controles": [
            # blink negativo ESTREITA os olhos; positivo abre. Medido — o nome
            # do parametro sugere o contrario.
            {"id": "blink", "rotulo": "Abertura dos olhos", "min": -20, "max": 5,
             "passo": 0.5, "padrao": 0, "dica": "Negativo estreita, positivo abre."},
            {"id": "wink", "rotulo": "Piscada", "min": 0, "max": 25,
             "passo": 0.5, "padrao": 0},
            {"id": "eyebrow", "rotulo": "Sobrancelha", "min": -10, "max": 15,
             "passo": 0.5, "padrao": 0},
        ]},
        {"rotulo": "Boca", "controles": [
            {"id": "smile", "rotulo": "Sorriso", "min": -0.3, "max": 1.3,
             "passo": 0.05, "padrao": 0},
            {"id": "aaa", "rotulo": "Abrir (á)", "min": -30, "max": 120,
             "passo": 1, "padrao": 0},
            {"id": "eee", "rotulo": "Esticar (ê)", "min": -20, "max": 15,
             "passo": 0.5, "padrao": 0},
            {"id": "woo", "rotulo": "Bico (u)", "min": -20, "max": 15,
             "passo": 0.5, "padrao": 0},
        ]},
    ],
    # Nao aparecem na interface: mudam o recorte, nao a expressao.
    "fixos": {"src_ratio": 1, "sample_ratio": 0, "crop_factor": 1.5},
}


def controles_do_rosto() -> dict:
    """Todos os controles achatados: id -> definicao."""
    return {c["id"]: c for g in ROSTO["grupos"] for c in g["controles"]}


# Agrupamento do menu de edicao POR INTENCAO, nao por modelo.
#
# A lista tinha onze itens soltos, com "Editar por instrucao" e "Editar por
# instrucao (Qwen)" lado a lado — dois nomes quase iguais cuja unica diferenca
# era o motor. Agrupar por modelo resolveria isso, mas quebraria as chaves que
# atravessam motores (Angulo e Reiluminar escolhem entre Klein e Qwen) e faria
# o usuario ter de saber qual motor faz o que — exatamente o que a interface
# existe para evitar.
GRUPOS_EDICAO = [
    ("pessoa", "Trocar quem está na cena"),
    ("instrucao", "Editar por instrução"),
    ("luz", "Luz"),
    ("enquadramento", "Enquadramento e estrutura"),
    ("acabamento", "Acabamento"),
    ("referencia", "Criar a partir de referências"),
]


# Qual familia de modelo cada modo carrega na GPU. So cabe UM por vez: o Qwen
# Edit sozinho ocupa 20 GB dos 16 GB de VRAM, entao trocar de motor significa
# descarregar e ler o outro do disco.
#
# E o que fazia a estimativa errar: medidas com o modelo ja quente diziam 104 s
# para o modo "trocar", que levou 470 s quando veio logo depois do Ideogram.
# Nos dados desta maquina a troca somou de 2 a 3 minutos.
MOTOR_DO_MODO = {
    "krea": "krea", "klein": "klein", "zimage": "zimage", "mage": "mage",
    "kroma": "kroma", "kroma_foto": "kroma_foto",
    "flux3": "flux3", "flux3ref": "flux3",
    "ideogram": "ideogram",
    "trocar": "klein", "personagem": "klein",
    "instrucao": "mage", "qwen": "qwen", "luzref": "qwen",
    "estilo": "krea", "cabeca": "krea",
    "controle": "zimage",
    "ampliar": "seedvr", "rosto": "liveportrait",
    # Estes dependem da chave escolhida; o valor aqui e o do metodo padrao.
    "angulo": "qwen", "reluz": "qwen",
}

# Modos cuja chave troca o motor: id do modo -> {id do metodo: motor}.
MOTOR_POR_METODO = {
    "angulo": {"camera": "qwen", "personagem": "klein"},
    # "nuvem" nao carrega nada na placa: e chamada de API. Sem isto, escolher
    # o Magnific faria o motor trocar de modelo local a toa.
    "reluz": {"direcional": "qwen", "clima": "klein", "nuvem": "nuvem"},
    "ampliar": {"topaz": "nuvem", "magnific": "nuvem"},
    "personagem": {"fiel": "klein", "rapido": "klein"},
}


def motor_do(modo: str, metodo: str = "") -> str:
    por_metodo = MOTOR_POR_METODO.get(modo)
    if por_metodo and metodo in por_metodo:
        return por_metodo[metodo]
    return MOTOR_DO_MODO.get(modo, modo)


# ---------------------------------------------------------------------------
# Modelos por nuvem (creditos de API)
#
# Rompem a premissa do resto do projeto: nao rodam na sua placa, custam
# dinheiro por imagem e mandam o que voce enviar para um servidor de terceiros.
# Por isso ficam numa tabela separada, e a interface deve mostrar o custo ANTES
# do botao — nunca como padrao de nenhuma ferramenta.
#
# Os precos sao os do proprio no do motor (GEMINI_IMAGE_2_PRICE_BADGE em
# comfy_api_nodes/nodes_gemini.py), copiados na versao v0.34.6. Sao dolares por
# imagem e podem mudar do lado do provedor: valem como ordem de grandeza para
# a decisao, nao como cobranca. Quem cobra e o extrato do ComfyUI.
#
# O "modelo" nao e um nome de API: e o rotulo que o Combo do no espera, e ele
# mesmo traduz para gemini-3-pro-image / gemini-3.1-flash-image no execute().
# Mandar o nome da API direto faz o no cair no ramo errado.
NUVEM = {
    "nano-pro": {
        "familia": "gemini",
        "rotulo": "Nano Banana Pro",
        "descricao": "Google. O mais forte em texto dentro da imagem e em "
                     "seguir instrução longa. Chega a 4K.",
        "no": "GeminiImage2Node",
        "modelo": "gemini-3-pro-image-preview",
        "resolucoes": ["1K", "2K", "4K"],
        "preco_usd": {"1K": 0.1608, "2K": 0.1608, "4K": 0.288},
        "max_referencias": 14,
        "segundos_estimados": 30,
    },
    "nano-2": {
        "familia": "gemini",
        "rotulo": "Nano Banana 2",
        "descricao": "Google. Cerca de metade do preço do Pro em 1K e mais "
                     "rápido; perde em texto e em cena complicada.",
        "no": "GeminiImage2Node",
        "modelo": "Nano Banana 2 (Gemini 3.1 Flash Image)",
        "resolucoes": ["1K", "2K", "4K"],
        "preco_usd": {"1K": 0.0835, "2K": 0.1217, "4K": 0.1848},
        "max_referencias": 14,
        "segundos_estimados": 20,
    },
}

# Os outros geradores de imagem pagos da Comfy Cloud, os mesmos que o Cinematic
# Studio da Comfy oferece. Lidos do /object_info da nuvem em 24/10/2026. Cada
# um tem campos proprios; a ficha diz so o que muda e workflows.gerar_api_generico
# monta o grafo. O preco nao fica aqui: /api/estimar avalia o price_badge do
# proprio no, a mesma conta que a Comfy mostra.
#
#   no           classe do no de parceiro
#   campos       entradas fixas (as de ramo dinamico vao como "model.x")
#   prompt/seed  nome da entrada
#   formato      ("ar", entrada, opcoes)       proporcao mais proxima da lista
#                ("px", entrada, opcoes)       "1024x1024" / "(2K) 2048x2048 (1:1)" / "1920:1080"
#                ("wh", largura, altura)       pixels calculados da proporcao e do nivel
#   nivel        (entrada, opcoes) quando a resolucao e um campo proprio
#   refs         ("autogrow", entrada, max) | ("lote", entrada, max) | ("uma", entrada)
_AR_COMUM = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
_SEEDREAM_PRESETS = [
    "(1K) 1024x1024 (1:1)", "(1K) 864x1152 (3:4)", "(1K) 1152x864 (4:3)", "(1K) 1312x736 (16:9)",
    "(1K) 736x1312 (9:16)", "(1K) 832x1248 (2:3)", "(1K) 1248x832 (3:2)", "(1K) 1568x672 (21:9)",
    "(2K) 2048x2048 (1:1)", "(2K) 1728x2304 (3:4)", "(2K) 2304x1728 (4:3)", "(2K) 2848x1600 (16:9)",
    "(2K) 1600x2848 (9:16)", "(2K) 1664x2496 (2:3)", "(2K) 2496x1664 (3:2)", "(2K) 3136x1344 (21:9)"]
_RECRAFT_PX = ["1024x1024", "1536x768", "768x1536", "1280x832", "832x1280", "1216x896", "896x1216",
               "1152x896", "896x1152", "832x1344", "1280x896", "896x1280", "1344x768", "768x1344"]
_IDEOGRAM45_PX = [
    "(2K) 2048x2048 (1:1)", "(2K) 1440x2880 (1:2)", "(2K) 2880x1440 (2:1)", "(2K) 1664x2496 (2:3)",
    "(2K) 2496x1664 (3:2)", "(2K) 1792x2240 (4:5)", "(2K) 2240x1792 (5:4)", "(2K) 1440x2560 (9:16)",
    "(2K) 2560x1440 (16:9)", "(2K) 1728x2304 (3:4)", "(2K) 2304x1728 (4:3)"]


def _api(rotulo, descricao, no, segundos=30, **ficha):
    return {"familia": "generico", "rotulo": rotulo, "descricao": descricao, "no": no,
            "preco_usd": {}, "segundos_estimados": segundos,
            "resolucoes": [n for n in ficha.get("nivel", (None, ["1K", "2K"]))[1]],
            "max_referencias": {"autogrow": 10, "lote": 8, "uma": 1}.get((ficha.get("refs") or ("",))[0], 0)
            if not ficha.get("refs") or len(ficha["refs"]) < 3 else ficha["refs"][2], **ficha}


NUVEM.update({
    "seedream5": _api("Seedream 5.0 Pro", "ByteDance. Sharp realism and strong prompt following, up to 2K.",
                      "ByteDanceSeedreamNodeV3",
                      campos={"model": "seedream 5.0 pro", "model.prompt_optimization": "standard",
                              "model.watermark": False, "model.thinking": True, "model.width": 2048, "model.height": 2048},
                      prompt="prompt", seed="model.seed", formato=("px", "model.size_preset", _SEEDREAM_PRESETS),
                      refs=("autogrow", "model.images", 10)),
    "flux2pro": _api("FLUX 2 Pro", "Black Forest Labs. Fast, photographic, up to 8 references.", "Flux2ProImageNode",
                     campos={"prompt_upsampling": True}, prompt="prompt", seed="seed",
                     formato=("wh", "width", "height"), refs=("lote", "images", 8)),
    "flux2max": _api("FLUX 2 Max", "Black Forest Labs. The highest quality FLUX 2.", "Flux2MaxImageNode",
                     campos={"prompt_upsampling": True}, prompt="prompt", seed="seed",
                     formato=("wh", "width", "height"), refs=("lote", "images", 8)),
    "flux3api": _api("FLUX 3", "Black Forest Labs, hosted. Up to 4K and 10 references.", "Flux3ImageNode",
                     campos={"grounding": True, "safety_tolerance": 4}, prompt="prompt", seed="seed",
                     formato=("ar", "aspect_ratio", ["21:9", "2:1", "16:9", "3:2", "7:5", "4:3", "5:4", "1:1", "4:5",
                                                     "3:4", "5:7", "2:3", "9:16", "1:2", "9:21"]),
                     nivel=("resolution", ["1K", "2K", "4K"]), refs=("autogrow", "images", 10)),
    "krea2large": _api("Krea 2 Large", "Krea. Rich, artistic photographic look.", "Krea2ImageNode",
                       campos={"model": "Krea 2 Large", "model.resolution": "1K", "model.creativity": "medium",
                               "model.moodboard_id": "", "model.moodboard_strength": 0.35},
                       prompt="prompt", seed="seed",
                       formato=("ar", "model.aspect_ratio", ["1:1", "4:3", "3:2", "16:9", "2.35:1", "4:5", "2:3", "9:16"]),
                       nivel=("", ["1K"])),
    "krea3": _api("Krea 3", "Krea. Newest model, with reasoning and up to 10 references.", "Krea3ImageNode",
                  campos={"model": "Krea 3", "model.thinking_mode": "fast", "model.precise_edit": False},
                  prompt="model.prompt", seed="model.seed",
                  formato=("ar", "model.aspect_ratio", _AR_COMUM), nivel=("model.resolution", ["1K", "2K"]),
                  refs=("autogrow", "model.images", 10)),
    "qwen3pro": _api("Qwen Image 3.0 Pro", "Alibaba. Strong with text inside the image.", "QwenImageTextToImageApi",
                     campos={"model": "qwen-image-3.0-pro", "model.negative_prompt": "", "n": 1,
                             "prompt_extend": True, "watermark": False},
                     prompt="model.prompt", seed="seed", formato=("wh", "model.width", "model.height")),
    "qwen3": _api("Qwen Image 3.0", "Alibaba. The faster, cheaper Qwen 3.", "QwenImageTextToImageApi",
                  campos={"model": "qwen-image-3.0", "model.negative_prompt": "", "n": 1,
                          "prompt_extend": True, "watermark": False},
                  prompt="model.prompt", seed="seed", formato=("wh", "model.width", "model.height")),
    "gpt2": _api("GPT Image 2", "OpenAI. Follows long instructions; can edit one image.", "OpenAIGPTImage1",
                 campos={"model": "gpt-image-2", "quality": "medium", "background": "auto", "n": 1,
                         "custom_width": 1024, "custom_height": 1024},
                 prompt="prompt", seed="seed",
                 formato=("px", "size", ["1024x1024", "1024x1536", "1536x1024", "2048x2048", "2048x1152",
                                         "1152x2048", "3840x2160", "2160x3840"]),
                 nivel=("", ["1K", "2K", "4K"]), refs=("uma", "image")),
    "grok2": _api("Grok Imagine Image 2.0", "xAI. Bold, fast images.", "GrokImageNode",
                  campos={"model": "grok-imagine-image-2.0", "number_of_images": 1, "quality": "medium"},
                  prompt="prompt", seed="seed",
                  formato=("ar", "aspect_ratio", ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "1:2", "2:1"]),
                  nivel=("resolution", ["1K", "2K"])),
    "recraft4": _api("Recraft V4.1", "Recraft. Design, illustration and clean graphics.", "RecraftV4TextToImageNode",
                     campos={"model": "recraftv4_1", "negative_prompt": "", "n": 1, "style_id": ""},
                     prompt="prompt", seed="seed", formato=("px", "model.size", _RECRAFT_PX), nivel=("", ["1K"])),
    "ideogram45": _api("Ideogram 4.5", "Ideogram. Posters and typography, hosted.", "IdeogramTextToImageApi",
                       campos={"model": "ideogram-4.5", "model.quality": "medium", "model.magic_prompt": "auto"},
                       prompt="model.prompt", seed="model.seed", formato=("px", "model.size", _IDEOGRAM45_PX),
                       nivel=("", ["2K"])),
    "kling3img": _api("Kling 3.0 Image", "Kuaishou. Cinematic stills; can follow one subject image.",
                      "KlingImageGenerationNode",
                      campos={"model_name": "kling-v3", "negative_prompt": "", "image_type": "subject",
                              "image_fidelity": 0.5, "human_fidelity": 0.45, "n": 1},
                      prompt="prompt", seed="seed",
                      formato=("ar", "aspect_ratio", ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9"]),
                      nivel=("", ["1K"]), refs=("uma", "image")),
    "luma1": _api("Luma UNI-1", "Luma. Natural light and texture, up to 9 references.", "LumaImageNode2",
                  campos={"model": "uni-1", "model.style": "auto", "model.web_search": False},
                  prompt="prompt", seed="seed",
                  formato=("ar", "model.aspect_ratio", ["3:1", "2:1", "16:9", "3:2", "1:1", "2:3", "9:16", "1:2", "1:3"]),
                  nivel=("", ["1K"]), refs=("autogrow", "model.image_ref", 9)),
    # Fora do menu desde 27/10/2026: o no da Comfy recebe "Method Not Allowed" da Reve.
    "reve": {"fora_do_menu": True, **_api("Reve Image", "Reve. Aesthetic, well composed images.", "ReveImageCreateNode",
                 campos={"model": "reve-create@20250915", "model.test_time_scaling": 1, "upscale": "disabled",
                         "remove_background": False},
                 prompt="prompt", seed="seed",
                 formato=("ar", "model.aspect_ratio", ["3:2", "16:9", "9:16", "2:3", "4:3", "3:4", "1:1"]),
                 nivel=("", ["1K"]))},
    "wan25img": _api("Wan 2.5 Image", "Alibaba Wan. Text to image.", "WanTextToImageApi",
                     campos={"model": "wan2.5-t2i-preview", "negative_prompt": "", "prompt_extend": True,
                             "watermark": False},
                     prompt="prompt", seed="seed", formato=("wh", "width", "height"), nivel=("", ["1K"]), lados=(768, 1440)),
    "hunyuan35": _api("Hunyuan Image 3.5", "Tencent. Up to 4K.", "HunyuanImageTextToImageApi",
                      campos={"model": "hy-image-3.5-preview", "model.width": 2048, "model.height": 2048,
                              "model.watermark": False},
                      prompt="model.prompt", seed="model.seed",
                      formato=("ar", "model.aspect_ratio", ["1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "21:9", "9:21"]),
                      nivel=("model.resolution", ["1K", "2K", "4K"])),
    "muse1": _api("Meta Muse Image", "Meta. Reasons about the prompt before drawing.", "MetaMuseImageTextToImageApi",
                  campos={"model": "muse-image-1.0", "model.reasoning_strength": "low",
                          "model.enable_web_search": False, "model.enable_image_search": False,
                          "model.enable_shell": False},
                  prompt="model.prompt", seed="model.seed",
                  formato=("ar", "model.aspect_ratio", ["1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9",
                                                        "9:16", "21:9", "9:21", "2:1", "1:2"]),
                  nivel=("", ["1K"])),
    "runway": _api("Runway Image", "Runway. Cinematic frames; can follow one reference.", "RunwayTextToImageNode",
                   campos={}, prompt="prompt", seed=None,
                   formato=("px", "ratio", ["1920:1080", "1080:1920", "1024:1024", "1360:768", "1080:1080",
                                            "1168:880", "1440:1080", "1080:1440", "1808:768", "2112:912"]),
                   nivel=("", ["1K"]), refs=("uma", "reference_image")),
})


# GPT Image 2.5. Duas variantes do mesmo modelo, com o mesmo preco; a OpenAI
# nao documenta a diferenca entre elas, entao ficam as duas e quem decide e o
# resultado medido.
#
# O preco depende de qualidade E tamanho, e a faixa e enorme: de US$ 0,0084 em
# "low" 1024 ate US$ 0,6123 em "max" 2048 — setenta vezes. A tabela inteira
# continua no catalogo para o botao Gerar calcular o valor exato, mas a tela
# oferece apenas os niveis 1K/2K/4K; a proporcao escolhe o tamanho real.
#
# "auto" foi deixado DE FORA dos tamanhos de proposito: ele nao esta na tabela
# de precos, e mostrar o custo antes do clique vale mais que a comodidade.
_TAMANHOS_GPT = ["1024x1024", "1024x1536", "1536x1024", "2048x2048",
                 "2048x1152", "1152x2048", "3840x2160", "2160x3840"]

_TAMANHOS_GPT_POR_NIVEL = {
    "1K": {"quadrado": "1024x1024", "retrato": "1024x1536",
           "paisagem": "1536x1024"},
    "2K": {"quadrado": "2048x2048", "retrato": "1152x2048",
           "paisagem": "2048x1152"},
    # O no nao oferece 4K quadrado. A interface desabilita essa combinacao;
    # a ausencia aqui tambem impede o backend de inventar uma resolucao.
    "4K": {"retrato": "2160x3840", "paisagem": "3840x2160"},
}


def tamanho_gpt(nivel, proporcao):
    """Traduz nivel legivel + proporcao para um tamanho aceito pelo no."""
    try:
        largura, altura = (float(n) for n in proporcao.split(":", 1))
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        largura = altura = 1
    orientacao = ("quadrado" if largura == altura else
                  "paisagem" if largura > altura else "retrato")
    por_orientacao = _TAMANHOS_GPT_POR_NIVEL.get(
        nivel, _TAMANHOS_GPT_POR_NIVEL["1K"])
    # Pedido adulterado de 4K quadrado cai no maior quadrado valido, em vez de
    # sair 16:9 apesar de a proporcao dizer 1:1.
    return (por_orientacao.get(orientacao)
            or _TAMANHOS_GPT_POR_NIVEL["2K"][orientacao])

_PRECO_GPT = {
    "low":    {"1024x1024": 0.0084, "1024x1536": 0.0068, "1536x1024": 0.0068,
               "2048x2048": 0.0170, "2048x1152": 0.0067, "1152x2048": 0.0067,
               "3840x2160": 0.0159, "2160x3840": 0.0159},
    "medium": {"1024x1024": 0.0188, "1024x1536": 0.0147, "1536x1024": 0.0147,
               "2048x2048": 0.0383, "2048x1152": 0.0157, "1152x2048": 0.0157,
               "3840x2160": 0.0371, "2160x3840": 0.0371},
    "high":   {"1024x1024": 0.0753, "1024x1536": 0.0589, "1536x1024": 0.0589,
               "2048x2048": 0.1531, "2048x1152": 0.0606, "1152x2048": 0.0606,
               "3840x2160": 0.1431, "2160x3840": 0.1431},
    "xhigh":  {"1024x1024": 0.1339, "1024x1536": 0.1055, "1536x1024": 0.1055,
               "2048x2048": 0.2721, "2048x1152": 0.1077, "1152x2048": 0.1077,
               "3840x2160": 0.2544, "2160x3840": 0.2544},
    "max":    {"1024x1024": 0.3013, "1024x1536": 0.2354, "1536x1024": 0.2354,
               "2048x2048": 0.6123, "2048x1152": 0.2424, "1152x2048": 0.2424,
               "3840x2160": 0.5724, "2160x3840": 0.5724},
}

for _id, _rot, _desc in (
    ("sunburst", "GPT Image 2.5 Sunburst",
     "OpenAI. Raciocina antes de desenhar: planeja o layout e confere o "
     "resultado. Faz fundo transparente sozinho."),
    ("flare", "GPT Image 2.5 Flare",
     "OpenAI. Mesma familia e mesmo preço do Sunburst. A diferenca entre as "
     "duas não e documentada — compare no seu caso."),
):
    NUVEM[_id] = {
        "rotulo": _rot,
        "familia": "openai",
        "descricao": _desc,
        "no": "OpenAIGPTImageNodeV2",
        "modelo": f"gpt-image-2.5-{_id}",
        "tamanhos": _TAMANHOS_GPT,
        "niveis": ["1K", "2K", "4K"],
        "tamanhos_por_nivel": _TAMANHOS_GPT_POR_NIVEL,
        "qualidades": ["low", "medium", "high", "xhigh", "max"],
        "fundos": [("auto", "Automático"), ("opaque", "Opaco"),
                   ("transparent", "Transparente")],
        "preco_usd": _PRECO_GPT,
        "max_referencias": 16,
        "segundos_estimados": 40,
    }


# O que o no aceita. "auto" copia a proporcao da referencia; sem referencia,
# o proprio Google costuma devolver 16:9.
PROPORCOES_NUVEM = ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                    "9:16", "16:9", "21:9"]


def custo_estimado(modelo: str, resolucao: str, quantidade: int = 1,
                   qualidade: str = "medium") -> float:
    """Dolares que a geracao deve custar. 0.0 se o modelo nao for de nuvem.

    Duas formas de tabela: os do Google indexam so por resolucao; os da OpenAI,
    por qualidade E tamanho.
    """
    p = NUVEM.get(modelo)
    if not p:
        return 0.0
    tabela = p["preco_usd"]
    if p.get("familia") == "openai":
        tabela = tabela.get(qualidade, {})
    return tabela.get(resolucao, 0.0) * max(1, quantidade)


# ---------------------------------------------------------------------------
# Recorte de fundo (nuvem)
#
# Nao existe equivalente local no projeto — e a unica ferramenta desta leva
# que preenche uma lacuna em vez de disputar com algo que ja temos.
#
# Recraft e nao Bria: custa US$ 0,010 contra US$ 0,018, e devolve IMAGE **e**
# MASK, enquanto o Bria devolve so a imagem. A mascara e o que abre a porta
# para compor texto ATRAS do sujeito, que e para onde isto aponta.
RECORTE = {
    "grupo": "acabamento",
    "rotulo": "Recortar o fundo",
    "descricao": "Deixa só o sujeito, com fundo transparente.",
    "dica": "Sem opções: o modelo decide o recorte. A saída é um PNG com "
            "transparência, pronto para compor sobre outra imagem.",
    "min_referencias": 1,
    "max_referencias": 1,
    "segundos_estimados": 15,
    "custo_usd": 0.01,
    "motor": "nuvem",
}


# ---------------------------------------------------------------------------
# Video local: LTX 2.5
#
# Traduzido do workflow do usuario (user/default/workflows/video_ltx2_5_i2v.json,
# 12/09/2026), que ja produzia bom resultado nesta placa. Os valores abaixo sao
# os DELE, nao derivados por mim.
#
# O truque que faz caber em 16 GB e nao ser lento: gera na METADE da resolucao
# pedida, sobe o latente com o upsampler x2 e refina num segundo estagio curto.
# Gerar direto no tamanho final seria muito mais caro.
#
# O LTX 2.5 gera AUDIO junto, por um VAE proprio. Os nos de audio formam um
# ramo separavel — desligar o som e nao montar esse ramo.
# LTX 2.3 (dev fp8 + LoRA destilada 0,5, duas etapas), o mesmo grafo do
# avatar. Medido em 14/10/2026 com audio de fala: 14,5 s em 3,5 min, 28 s em
# 7,2 min, a 1280x704. So 720p e abaixo: 1080p nunca foi medido nesta placa.
VIDEO_LTX23 = {
    "rotulo": "LTX 2.3",
    "descricao": "Vídeo local a partir do primeiro quadro, com último quadro e áudio opcionais.",
    "alinhamento": 64,
    "fps": 24,
    "duracao_min": 2,
    "duracao_max": 30,
    "duracao_padrao": 5,
    "segundos_estimados": 75,
    "max_pixels": 1280 * 720,
    # Um arquivo que vira o som do video (fala, musica); nao e referencia.
    "max_audios_trilha": 1,
}

VIDEO_LTX = {
    "rotulo": "LTX 2.5",
    "descricao": "Vídeo local, com áudio. Gera em meia resolução e refina.",
    "unet": "LTX/2.5/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
    # Dois codificadores: o de 12B escreve o condicionamento; o de 2B so serve
    # ao gerador automatico de prompt, e nem e carregado quando ele esta off.
    "clip": "Gemma/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
    "clip_prompt": "Gemma/gemma4_e2b_it_int8_convrot.safetensors",
    "clip_type": "ltxv",
    "vae_video": "LTX/2.5/ltx-2.5-video-vae-bf16.safetensors",
    "vae_audio": "LTX/2.5/ltx-2.5-audio-vae-bf16.safetensors",
    "upsampler": "LTX/2.5/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
    # Uma voz de referencia, recomendada em torno de 5 s. A escala 3 e o
    # padrao do no oficial; acima de zero acrescenta uma passada por passo.
    "max_audios_identidade": 1,
    "forca_audio_referencia": 3.0,

    # Nove passos no primeiro estagio, quatro no segundo. Sao sigmas manuais,
    # nao um scheduler: o modelo distilled espera esta curva.
    "sigmas_1": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0",
    "sigmas_2": "0.85, 0.7250, 0.4219, 0.0",
    "sampler": "euler_ancestral",
    # Sao os dois CFG do guia dual, nao "estagio 1 e 2": um vale
    # para o video, o outro para o audio. O workflow usa 1,0 nos dois.
    "cfg_video": 1.0,
    "cfg_audio": 1.0,
    "auto_max_tokens": 600,
    # So do primeiro+ultimo quadro. Aquele pipeline e de um estagio, em
    # resolucao cheia, e as imagens entram como guias presos a quadros.
    "forca_guia": 0.7,
    "flf_eta": 0.0,

    # Forca do encaixe da imagem no latente. 0.7 no primeiro estagio deixa o
    # modelo mover a cena; 1.0 no segundo prende ao que ja foi decidido.
    "forca_imagem_1": 0.7,
    "forca_imagem_2": 1.0,

    "preprocess": 18,          # remove artefato de compressao da entrada
    "entrada_maior_lado": 1536,
    # Sem pedacos no tempo (ver workflows.TEMPORAL_LTX): com 64/16 a nitidez
    # caia ~10% a cada 48 quadros.
    "decode_ladrilho": [512, 64, 4096, 4],

    # Acima de 1,1 MP, divide apenas o feed-forward. O contexto temporal
    # permanece inteiro para preservar referencias e continuidade. O pico
    # de memoria em 1080p depende da duracao e requer validacao na GPU.
    "max_pixels": 2_100_000,
    "otimiza_memoria_acima": 1_100_000,
    "chunks_feed_forward": 4,

    # ALINHAMENTO DE 64, nao 32, e a razao e a arquitetura: este pipeline gera
    # em METADE da resolucao e depois dobra, entao e a METADE que precisa estar
    # alinhada em 32. MEDIDO: pedi 480x832 e saiu 448x832 — 480/2 = 240 nao e
    # multiplo de 32, o modelo cortou para 224 e dobrou para 448.
    #
    # Confere com tudo que ja rodou aqui: 1280, 704 e 832 sao multiplos de 64.
    "alinhamento": 64,
    # So o LTX tem o no que LE A IMAGEM e escreve o prompt de movimento
    # (TextGenerateLTX2Prompt). Os outros geradores nem parametro tem.
    "sugere_prompt": True,

    # ---- modo de REFERENCIA (MSR, multi-subject reference) -----------------
    #
    # Aqui nao troca o checkpoint, como no MiniMax: troca-se a LoRA. A
    # `Licon-MSR` carrega os "slot embeddings" aprendidos, e e por causa deles
    # que cada referencia ocupa uma POSICAO — pessoa A, pessoa B, objeto. Sem
    # essa LoRA o no aceita as imagens e as trata como guias comuns: roda,
    # entrega, e ignora o que faz do MSR um modo de referencia.
    "lora_msr": "LTX/2.5/LTX-2.5-Licon-MSR-V1.safetensors",
    "forca_msr": 1.0,
    # pic1..pic4 mais um slot separado de FUNDO. Nao e autogrow: e fixo.
    "max_referencias": 4,
    # O quinto slot, so para o CENARIO. Declarado para a tela saber que
    # existe sem precisar conhecer o gerador pelo nome.
    "tem_fundo_referencia": True,
    # Quadros a que cada referencia e repetida antes de codificar. "33" da 5
    # quadros latentes por referencia; "25", quatro.
    "quadros_referencia": "33",
    # 1.0 mantem as referencias congeladas; abaixo disso elas podem derivar.
    "forca_referencia": 1.0,
    # Codificacao das referencias em ladrilhos, para nao estourar os 16 GB.
    "ladrilho_referencia": [256, 64],
    "fps": 24,
    # Faixa, nao lista: a interface mostra uma barra. 15 s em 1280x704 foi
    # medido em 21/09/2026: 361 quadros, 15,04 s de saida, 243,6 s de parede,
    # sem estouro nos 16 GB. Os tres quadros conferidos (inicio/meio/fim)
    # mantiveram sujeito, cenario e detalhe. Acima disso continua sem medida.
    "duracao_min": 2,
    "duracao_max": 15,
    "duracao_padrao": 5,
    "tamanhos": [("1280x720", 1280, 720), ("720x1280", 720, 1280),
                 ("960x960", 960, 960), ("1920x1080", 1920, 1080)],
    "tamanho_padrao": "1280x720",

    # O negativo e o do workflow do usuario, palavra por palavra.
    "negativo": ("pc game, console game, video game, cartoon, childish, ugly, "
                 "deformed, distorted, blurry, low quality, watermark, text"),
    # MEDIDO: 78 s para 3 s de video em 1280x720 com audio (i2v, dois
    # estagios) e 94 s no primeiro+ultimo, que roda em resolucao cheia.
    # O valor aqui e para a duracao padrao de 5 s, extrapolado do de 3 s; a
    # partir da primeira rodada a galeria substitui pela mediana real.
    "segundos_estimados": 130,
}


# ---------------------------------------------------------------------------
# Limpeza e ampliacao de VIDEO (SeedVR2 temporal, local)
#
# Traduzido de "SeedVR2 - limpeza temporal.json", do usuario. E o mesmo SeedVR2
# que ja usamos em imagem, mas com o no de VIDEO: ele processa em lotes de
# quadros com sobreposicao, e por isso mantem coerencia entre um quadro e o
# seguinte — um upscaler de imagem aplicado quadro a quadro faria a textura
# tremer.
#
# `blocos_trocados` e o que faz caber nos 16 GB: 16 blocos do transformer ficam
# na RAM e sobem para a placa conforme a vez deles. E o valor do workflow.
#
# ATENCAO: o no le o video por CAMINHO ABSOLUTO, nao por upload. O arquivo tem
# de estar na pasta de saida do motor — que e onde a nossa galeria vive.
VIDEO_LIMPAR = {
    "rotulo": "Limpar e ampliar o vídeo",
    "descricao": "Passa o vídeo pelo SeedVR2 temporal: mais nitidez, textura "
                 "coerente entre quadros, e o áudio original preservado.",
    "dit": "seedvr2_ema_3b_fp8_e4m3fn.safetensors",
    "vae": "ema_vae_fp16.safetensors",
    "blocos_trocados": 16,
    "atencao": "sdpa",
    "descarregar_para": "cpu",
    # Ladrilho na codificacao e na decodificacao do VAE: sem isso um quadro de
    # 1280 px estoura a memoria.
    "ladrilho": 512,
    "sobreposicao_ladrilho": 64,
    # Altura alvo. 1088 e o do workflow; o no ajusta a largura pela proporcao.
    "resolucoes": [720, 1088, 1440],
    "resolucao_padrao": 1088,
    # Quantos quadros por lote, e quantos se repetem entre lotes.
    #
    # MEDIDO, 3 s de video: subir de 5 para 13 deu 19% mais nitidez (82,6 ->
    # 98,0) e foi 35% MAIS RAPIDO (351 s -> 229 s), porque ha menos emendas
    # entre lotes. Custa 3 GB a mais de VRAM (8 -> 11), que sobram.
    #
    # NAO resolve o tremor: a diferenca entre quadros consecutivos foi de
    # 2,52 para 2,48, contra 2,17 do original. Eu supunha que o lote fosse a
    # alavanca contra o flickering; nao e. A causa e o metodo — o SeedVR2
    # amplia em PIXELS, sem saber o que se move, e reinventa microdetalhe.
    "lote": 13,
    "sobreposicao_temporal": 2,
    "correcao_cor": "lab",
    "segundos_estimados": 200,
}


# ---------------------------------------------------------------------------
# Ampliacao de VIDEO no latente (LTX 2.5 Ultimate Upscale, local)
#
# Alternativa ao SeedVR2 para o mesmo fim, com metodo oposto: trabalha no
# LATENTE, com o proprio modelo de video, em pedacos de dezenas de quadros.
# O SeedVR2 trabalha em pixels, em lotes de 13. Foi o usuario que apontou a
# existencia deste caminho.
#
# TRES parametros que precisaram de teste para acertar — nao ha workflow de
# referencia para este no:
#
# 1. NADA de divisao espacial. O VAE comprime 32x, entao um alvo de 1088x1600
#    vira um latente de 34x50. Ladrilhos de 512 PIXELS viram 16x16 em latente:
#    pequenos demais, cada um alucina por conta propria. A primeira tentativa
#    saiu com rosto duplicado e um rastro vertical.
# 2. SIGMAS BAIXOS. Com a curva do segundo estagio da geracao (comeca em 0,85)
#    o modelo REESCREVEU a cena: outra pessoa, outro cabelo, outras ferramentas
#    na parede. Ali aquela curva refina o que o proprio modelo criou; aqui a
#    cena vem de fora. Com 0,30 a identidade se manteve (correlacao 0,998
#    contra 0,985).
# 3. LATENTE AUDIOVISUAL. O no recusa latente de video puro; exige o AV
#    aninhado. `bypass_audio` so evita reamostrar o som, nao dispensa a
#    estrutura.
VIDEO_AMPLIAR_LTX = {
    "rotulo": "Ampliar no latente (LTX)",
    "descricao": "Passa o vídeo pelo espaço latente, e o que for PEQUENO no "
                 "quadro se perde ali: rosto distante, objeto miúdo. Bom em "
                 "plano fechado, ruim em plano aberto.",
    # Os sigmas NAO sao a alavanca que eu pensava. Varri 0,30 / 0,15 / 0,08 e
    # os tres saem iguais. O dano nem depende deles: um encode->decode pelo
    # VAE, SEM amostrar e SEM ampliar, ja derrete um rosto de ~60 px. O VAE
    # comprime 8x, entao esse rosto vira ~7 celulas latentes e nao cabe. Com
    # rosto grande (768x1024, primeiro plano) o mesmo ida-e-volta preserva.
    # Mexer aqui nao conserta plano aberto — e limite do espaco latente.
    "sigmas": "0.30, 0.18, 0.08, 0.0",
    "cfg": 1.0,
    # Quadros por pedaco. 49 usa metade da memoria dos 97 do padrao do no, e
    # ainda e quase quatro vezes o contexto do SeedVR2.
    "pedaco_temporal": 49,
    "sobreposicao_temporal": 9,
    "ancora": "full",
    "forca_ancora": 0.999,
    "ladrilho_vae": 512,
    "sobreposicao_vae": 64,
    # TETO do maior lado. Sem ele, ampliar um video que JA foi ampliado pede
    # 3200x4704 — 15 megapixels por quadro, que a placa nao aguenta. Com teto,
    # o alvo encolhe proporcionalmente em vez de estourar no meio da rodada.
    # 2560 cabe: a rodada medida em 1088x1600 usou 15,4 GB dos 16, e o custo
    # cresce com a area.
    "maior_lado": 2560,
    "segundos_estimados": 145,
}


# O latente do LTX comprime 8x NO TEMPO e so representa 8k+1 quadros. Um clipe
# com outra contagem e truncado para o maior 8k+1 que couber — silenciosamente.
# Medido em tres casos: 121 -> 121 (ja e 8x15+1), 124 -> 121, 192 -> 185.
# Nao e defeito a consertar, e aritmetica do modelo; o que se pode fazer e
# dizer o numero ANTES, que e o que a tela faz agora.
ALINHAMENTO_TEMPORAL_LTX = 8

# No ESPACO o no alinha a 32, e para cima. Descoberto porque a tela prometia
# 1456 de altura e o arquivo saia com 1472.
ALINHAMENTO_ESPACIAL_LTX = 32


def quadros_que_sobrevivem(quadros: int) -> int:
    """Quantos quadros saem de uma passagem pelo latente do LTX."""
    if quadros < 1:
        return 0
    k = ALINHAMENTO_TEMPORAL_LTX
    return (quadros - 1) // k * k + 1


def alvo_de_ampliacao(largura: int, altura: int) -> tuple[int, int]:
    """Dimensoes de saida ao dobrar, respeitando o teto do maior lado.

    Devolve o dobro quando cabe; senao encolhe proporcionalmente ate o teto.
    Se a origem ja passa do teto, devolve a propria origem — ampliar nao faria
    sentido, e e melhor a interface dizer isso do que a placa descobrir.
    """
    teto = VIDEO_AMPLIAR_LTX["maior_lado"]
    if max(largura, altura) >= teto:
        return int(largura), int(altura)
    k = ALINHAMENTO_ESPACIAL_LTX
    l, a = largura * 2, altura * 2
    if max(l, a) <= teto:
        # Alinhar AQUI tambem. Dobrar 794 da 1588, que nao e multiplo de 32, e
        # o no arredondaria para 1600 — a tela prometeria de novo um numero que
        # nao sai. So nao alinha se isso estourasse o teto.
        subiu = (-(-l // k) * k, -(-a // k) * k)
        return subiu if max(subiu) <= teto else (int(l), int(a))
    fator = teto / max(l, a)
    # Multiplo de 32, nao de 8. Com 8 a tela prometia 2560x1456 e o arquivo
    # saia 2560x1472: o no alinha a 32 e ARREDONDA PARA CIMA, e 1456 nao e
    # multiplo de 32. Arredondar aqui do mesmo jeito faz a promessa bater com
    # a entrega — a alternativa, arredondar para baixo, perderia resolucao a
    # toa. O teto de 2560 ja e multiplo de 32, entao o lado maior nao estoura.
    return (-(-int(l * fator) // k) * k, -(-int(a * fator) // k) * k)


# ---------------------------------------------------------------------------
# Video por NUVEM: MiniMax H3 pelo Comfy Cloud
#
# O mesmo MiniMax H3 (o local saiu em 16/10/2026), rodando no servidor deles. Vale quando a
# placa esta ocupada com outra coisa, ou quando se quer gerar rapido em baixa
# resolucao para depois ampliar localmente — foi assim que a cadeia
# nuvem+local foi montada e medida.
#
# MEDIDO: 5 s em 480p levaram 62 s, com a VRAM parada em 3,1 GB (a linha de
# base da maquina). O modelo local nem e tocado.
#
# COBRANCA POR TEMPO, e nao por imagem: US$ 0,001295 por segundo de GPU. E o
# unico item do projeto cobrado assim — os nos de imagem cobram por peca. Por
# isso nao da para mostrar um preco exato antes do clique, so a tarifa.
#
# Tres nos, um por modo, ao contrario do local, onde um no faz os tres.

# MiniMax H3 de pesos abertos (fl2va: texto, imagem e primeiro+ultimo num no
# so). Nomes iguais aos do Comfy-Org/MiniMax-H3, que sao os mesmos da Comfy
# Cloud: o mesmo grafo roda local (placas grandes) e na nuvem. Removido desta
# placa em 16/10/2026: em 16 GB so andava em baixa resolucao e poucos passos,
# e o resultado bom pede ~40 passos. Recuperado do commit 6e9de0d^.
VIDEO_MINIMAX = {
    "rotulo": "MiniMax H3",
    "unet": "Minimax/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "clip": "Qwen/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "clip_type": "minimax",
    "vae_video": "Minimax/minimax_h3_video_vae_fp16.safetensors",
    "vae_audio": "Minimax/minimax_h3_audio_vae_fp32.safetensors",
    "lora_turbo": "Minimax/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
    "forca_lora": 1.0,
    # Turbo: LoRA + 8 passos. Qualidade: sem LoRA, 40 passos (o que os relatos
    # pedem para um bom resultado). LoRA e passos andam SEMPRE juntos.
    "passos_turbo": 8,
    "passos_qualidade": 40,
    "sampler": "res_multistep",
    "scheduler": "simple",
    "alinhamento": 32,
    "fps": 24,
    "duracao_min": 2,
    "duracao_max": 15,
}


# FastH3: o MiniMax H3 destilado por DMD2 para 8 passos (FastVideo).
# Removido em 16/10/2026 por qualidade e devolvido em 27/10 como opcao
# instalavel (pacote fasth3). TRADUZIDO de video_fastvideo_fasth3_i2v.json:
# reaproveita o texto e os dois VAEs do MiniMax base; so o modelo e novo.
# NAO faz referencia (o ref2va nao foi destilado). Sem LoRA: 8 passos.
VIDEO_FASTH3 = {
    "rotulo": "FastH3",
    "descricao": ("MiniMax H3 destilado: 8 passos, sem LoRA. Não faz o modo de "
                  "referência — para isso, use o MiniMax H3. Imagens de outra "
                  "proporção entram inteiras, com laterais desfocadas, sem "
                  "esticar a pessoa."),
    "unet": "Minimax/fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors",
    "clip": "Qwen/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "clip_type": "minimax",
    "vae_video": "Minimax/minimax_h3_video_vae_fp16.safetensors",
    "vae_audio": "Minimax/minimax_h3_audio_vae_fp32.safetensors",

    "passos": 8,
    "denoise": 1.0,
    "sampler": "res_multistep",
    "scheduler": "simple",
    # Deslocamento de sigma proprio do modelo destilado; o template usa 10/3,
    # contra o padrao 12/3 do no.
    "shift_video": 10.0,
    "shift_audio": 3.0,
    # Atencao esparsa por blocos — e o que da o "Fast" do nome. `vsa` guarda
    # 10% dos cubos de video por cubo de consulta, a partir de 20% do percurso.
    "atencao_selecao": "vsa",
    "atencao_percentual": 10.0,
    "atencao_inicio": 0.2,
    "atencao_fim": 1.0,
    "atencao_min_tokens": 12288,
    "atencao_extra_tokens": 256,
    "atencao_sink": "exact_kv_and_rows",
    "backend_atencao": "comfy kitchen attention",

    # Mesma cadencia e mesmo alinhamento do MiniMax base: a expressao de
    # quadros do template e, letra por letra, o nosso `quadros_minimax`.
    "alinhamento": 32,
    "fps": 24,
    "duracao_min": 2,
    # 15 s, e MEDIDO, nao herdado. O teto de 8 s era meu, posto ao montar a
    # barra de duracao, sem medicao nenhuma por tras. O proprio no diz outra
    # coisa: "trained range is ~124-362" quadros, ou seja 5 a 15,1 s a 24 fps —
    # a MESMA faixa que o MiniMax H3 por nuvem oferece.
    #
    # Conferido na placa de 16 GB, e no ARQUIVO, nao so no estado da tarefa:
    #
    #   10 s, 1280x704 ... 243 quadros, 260 s, pico ~15,2 GB
    #   15 s, 1280x704 ... 362 quadros, 425 s, pico ~15,0 GB
    #   15 s, 1344x768 ... 362 quadros, 483 s, pico ~15,1 GB  <- pior caso
    #
    # O ultimo e o maior tamanho que `MAX_PIXELS_VIDEO_LOCAL` deixa passar, com
    # a duracao maxima: se coubesse so o caso pequeno, a barra estouraria no
    # proprio padrao da tela. A folga e fina (~0,8 GB de 15,9) e a VRAM foi
    # amostrada a cada 6 s, entao o que esta provado e que COUBE tres vezes,
    # nao que sobre margem.
    "duracao_max": 15,
    "duracao_padrao": 5,
    # MEDIDO, nao chutado: 121 s para 5 s em 1280x704, com imagem de partida.
    # O chute anterior era 160. Na mesma comparacao o MiniMax turbo levou 209 s,
    # entao o destilado e ~42% mais rapido apesar de dois passos a mais.
    #
    "segundos_estimados": 120,
    # MEDIDO: 121 / 260 / 425 s para 5 / 10 / 15 s em 1280x704. A conta linear
    # daria 121 / 242 / 363 — erra 1,3x no extremo. O expoente 1,14 ajusta os
    # tres pontos.
    #
    # Ele e BAIXO para um modelo de video, e ha razao: o FastH3 usa atencao
    # ESPARSA (`BlockSparseAttention`, 10% das fichas), que escala quase linear
    # no comprimento. O MiniMax usa atencao densa e vai a 1,60. Por isso a
    # vantagem do destilado CRESCE com a duracao: 1,7x em 5 s, 2,9x em 15 s.
    "expoente_duracao": 1.14,
}


def quadros_minimax(duracao: float, fps: int = 24) -> int:
    """Quadros que o MiniMax H3 aceita: alinhamento de 17 com deslocamento de 5."""
    q = max(5, round(duracao * fps))
    return q + (5 - (q % 17)) % 17


# Video por API (nos de parceiro da Comfy; cobram creditos da conta). Um no por
# modo; os limites sao os do proprio no, lidos do /object_info da nuvem em
# 22/10/2026. "ramo" e o valor do DynamicCombo `model`, cujos subcampos levam
# o prefixo "model." no grafo.
VIDEO_API = {
    # "referencia": KlingOmniProImageToVideoNode (ate 7 imagens) e
    # ByteDance2ReferenceNodeV2 (ate 9), lidos da nuvem em 23/10/2026.
    "kling": {"rotulo": "Kling 3.0", "ramo": "kling-v3", "max_referencias": 7,
              "modos": ["texto", "imagem", "primeiro_ultimo", "referencia"],
              "proporcoes": ["16:9", "9:16", "1:1"], "resolucoes": ["720p", "1080p", "4k"],
              "duracao_min": 3, "duracao_max": 15},
    "veo": {"rotulo": "Veo 3.1", "modelo": "veo-3.1-fast-generate",
            "modos": ["texto", "imagem", "primeiro_ultimo"],
            "proporcoes": ["16:9", "9:16"], "resolucoes": ["720p", "1080p", "4k"],
            "duracao_min": 4, "duracao_max": 8},
    "seedance": {"rotulo": "Seedance 2.5", "ramo": "Seedance 2.5", "max_referencias": 9,
                 "modos": ["texto", "imagem", "primeiro_ultimo", "referencia"],
                 "proporcoes": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
                 "resolucoes": ["480p", "720p", "1080p"], "duracao_min": 4, "duracao_max": 30},
    # Runway nao faz texto -> video; a proporcao vira pixels no proprio no.
    "runway": {"rotulo": "Runway Gen-4", "modos": ["imagem", "primeiro_ultimo"],
               "proporcoes": ["16:9", "9:16", "1:1"], "resolucoes": ["720p"],
               "duracao_min": 5, "duracao_max": 10, "sem_audio": True},
    "luma": {"rotulo": "Luma Ray 3", "modos": ["texto", "imagem", "primeiro_ultimo"],
             "proporcoes": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
             "resolucoes": ["540p", "720p", "1080p"], "duracao_min": 5, "duracao_max": 10,
             "sem_audio": True},
}



# Os outros geradores de video pagos da Comfy Cloud, lidos do /object_info em
# 24/10/2026. Um no por modo; a ficha de cada modo diz so o que muda e
# workflows.gerar_video_generico monta o grafo. O preco vem do price_badge.
#
#   ar     (entrada, opcoes)          proporcao mais proxima
#   res    (entrada, opcoes)          a resolucao pedida (720p...) na grafia do no
#   px     (entrada, opcoes)          resolucao em pixels "1280x720", da proporcao + resolucao
#   dur    (entrada, "int"|"str", min, max)
#   audio  entrada booleana do som
#   img    entrada da imagem inicial ("autogrow:" = lista de quadros-chave)
#   fim    entrada da imagem final (primeiro e ultimo quadro)
def _vid(rotulo, modos, proporcoes, resolucoes, dmin, dmax, sem_audio=False, **nos):
    return {"familia": "generico", "rotulo": rotulo, "modos": modos, "proporcoes": proporcoes,
            "resolucoes": resolucoes, "duracao_min": dmin, "duracao_max": dmax,
            "sem_audio": sem_audio, "nos": nos}


_FLUX3_AR = ["21:9", "2:1", "16:9", "4:3", "1:1", "3:4", "9:16"]
_LTX_PX = ["1280x720", "720x1280", "1920x1080", "1080x1920", "2560x1440", "1440x2560", "3840x2160", "2160x3840"]

VIDEO_API.update({
    "flux3video": _vid(
        "FLUX 3 Video", ["texto", "imagem"], ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
        ["720p", "1080p", "1440p", "2160p"], 5, 19,
        texto=dict(no="Flux3TextToVideoNode", campos={"safety_tolerance": 2}, prompt="prompt", seed="seed",
                   ar=("aspect_ratio", _FLUX3_AR), res=("resolution", ["720p", "1080p", "1440p", "2160p"]),
                   dur=("duration", "str", 5, 19), audio="generate_audio"),
        imagem=dict(no="Flux3ImageToVideoNode", campos={"safety_tolerance": 2, "placement": "spread across the clip"},
                    prompt="prompt", seed="seed", ar=("aspect_ratio", _FLUX3_AR),
                    res=("resolution", ["720p", "1080p", "1440p", "2160p"]), dur=("duration", "str", 5, 19),
                    audio="generate_audio", img="autogrow:keyframes")),
    "flux3max": _vid(
        "FLUX 3 Max Video", ["texto", "imagem"], ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
        ["720p", "1080p"], 5, 20,
        texto=dict(no="Flux3MaxTextToVideoNode", campos={"reasoning_level": "low"}, prompt="prompt", seed="seed",
                   ar=("aspect_ratio", _FLUX3_AR), res=("resolution", ["720p", "1080p"]),
                   dur=("duration", "str", 5, 20), audio="generate_audio"),
        imagem=dict(no="Flux3MaxImageToVideoNode", campos={"reasoning_level": "low", "placement": "spread across the clip"},
                    prompt="prompt", seed="seed", ar=("aspect_ratio", _FLUX3_AR), res=("resolution", ["720p", "1080p"]),
                    dur=("duration", "str", 5, 20), audio="generate_audio", img="autogrow:keyframes")),
    "grokvideo": _vid(
        "Grok Imagine Video 1.5", ["texto", "imagem"], ["16:9", "4:3", "3:2", "1:1", "2:3", "3:4", "9:16"],
        ["480p", "720p", "1080p"], 1, 15, sem_audio=True,
        texto=dict(no="GrokVideoNode", campos={"model": "grok-imagine-video-1.5"}, prompt="prompt", seed="seed",
                   ar=("aspect_ratio", ["16:9", "4:3", "3:2", "1:1", "2:3", "3:4", "9:16"]),
                   res=("resolution", ["480p", "720p", "1080p"]), dur=("duration", "int", 1, 15)),
        imagem=dict(no="GrokVideoNode", campos={"model": "grok-imagine-video-1.5", "aspect_ratio": "auto"},
                    prompt="prompt", seed="seed", res=("resolution", ["480p", "720p", "1080p"]),
                    dur=("duration", "int", 1, 15), img="image")),
    "happyhorse": _vid(
        "HappyHorse 1.1", ["texto", "imagem"], ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
        ["720p", "1080p"], 3, 15, sem_audio=True,
        texto=dict(no="HappyHorseTextToVideoApi", campos={"model": "happyhorse-1.1-t2v", "watermark": False},
                   prompt="model.prompt", seed="seed",
                   ar=("model.ratio", ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "9:21", "5:4", "4:5"]),
                   res=("model.resolution", ["720P", "1080P"]), dur=("model.duration", "int", 3, 15)),
        imagem=dict(no="HappyHorseImageToVideoApi", campos={"model": "happyhorse-1.1-i2v", "watermark": False},
                    prompt="model.prompt", seed="seed", res=("model.resolution", ["720P", "1080P"]),
                    dur=("model.duration", "int", 3, 15), img="first_frame")),
    "pixverse6": _vid(
        "PixVerse V6", ["texto", "imagem"], ["16:9", "4:3", "1:1", "3:4", "9:16", "2:3", "3:2", "21:9"],
        ["360p", "540p", "720p", "1080p"], 1, 15,
        texto=dict(no="PixverseV6TextToVideoNode",
                   campos={"model": "PixVerse V6", "model.multi_clip": False, "model.negative_prompt": "", "model.style": "none"},
                   prompt="model.prompt", seed="model.seed",
                   ar=("model.aspect_ratio", ["16:9", "4:3", "1:1", "3:4", "9:16", "2:3", "3:2", "21:9"]),
                   res=("model.quality", ["360p", "540p", "720p", "1080p"]),
                   dur=("model.duration_seconds", "int", 1, 15), audio="model.generate_audio"),
        imagem=dict(no="PixverseV6ImageToVideoNode",
                    campos={"model": "PixVerse V6", "model.multi_clip": False, "model.negative_prompt": "", "model.style": "none"},
                    prompt="model.prompt", seed="model.seed", res=("model.quality", ["360p", "540p", "720p", "1080p"]),
                    dur=("model.duration_seconds", "int", 1, 15), audio="model.generate_audio", img="image")),
    "viduq3": _vid(
        "Vidu Q3 Pro", ["texto", "imagem"], ["16:9", "9:16", "3:4", "4:3", "1:1"], ["720p", "1080p"], 1, 16,
        texto=dict(no="Vidu3TextToVideoNode", campos={"model": "viduq3-pro"}, prompt="prompt", seed="seed",
                   ar=("model.aspect_ratio", ["16:9", "9:16", "3:4", "4:3", "1:1"]),
                   res=("model.resolution", ["720p", "1080p"]), dur=("model.duration", "int", 1, 16), audio="model.audio"),
        imagem=dict(no="Vidu3ImageToVideoNode", campos={"model": "viduq3-pro"}, prompt="prompt", seed="seed",
                    res=("model.resolution", ["720p", "1080p", "2K"]), dur=("model.duration", "int", 1, 16),
                    audio="model.audio", img="image")),
    "viduq4": _vid(
        "Vidu Q4", ["imagem"], ["16:9", "9:16", "1:1"], ["540p", "720p", "1080p", "2K", "4K"], 3, 16,
        imagem=dict(no="Vidu4ImageToVideoNode", campos={"model": "Vidu Q4 Preview"}, prompt="model.prompt",
                    seed="model.seed", res=("model.resolution", ["540p", "720p", "1080p", "2K", "4K"]),
                    dur=("model.duration", "int", 3, 16), audio="model.audio", img="image")),
    "wan27": _vid(
        "Wan 2.7", ["texto", "imagem", "primeiro_ultimo"], ["16:9", "9:16", "1:1", "4:3", "3:4"], ["720p", "1080p"], 2, 15,
        sem_audio=True,
        texto=dict(no="Wan2TextToVideoApi", campos={"model": "wan2.7-t2v", "model.negative_prompt": "",
                                                    "prompt_extend": True, "watermark": False},
                   prompt="model.prompt", seed="seed", ar=("model.ratio", ["16:9", "9:16", "1:1", "4:3", "3:4"]),
                   res=("model.resolution", ["720P", "1080P"]), dur=("model.duration", "int", 2, 15)),
        imagem=dict(no="Wan2ImageToVideoApi", campos={"model": "wan2.7-i2v", "model.negative_prompt": "",
                                                      "prompt_extend": True, "watermark": False},
                    prompt="model.prompt", seed="seed", res=("model.resolution", ["720P", "1080P"]),
                    dur=("model.duration", "int", 2, 15), img="first_frame"),
        primeiro_ultimo=dict(no="Wan2ImageToVideoApi", campos={"model": "wan2.7-i2v", "model.negative_prompt": "",
                                                               "prompt_extend": True, "watermark": False},
                             prompt="model.prompt", seed="seed", res=("model.resolution", ["720P", "1080P"]),
                             dur=("model.duration", "int", 2, 15), img="first_frame", fim="last_frame")),
    "ltx25api": _vid(
        "LTX 2.5 (hosted)", ["texto", "imagem", "primeiro_ultimo"], ["16:9", "9:16"], ["720p", "1080p", "1440p", "2160p"],
        2, 20,
        texto=dict(no="LtxApi25TextToVideo", campos={"model": "LTX-2.5 (Fast)", "model.fps": "24"}, prompt="prompt",
                   seed="seed", px=("model.resolution", _LTX_PX), dur=("model.duration", "str", 2, 20),
                   audio="model.generate_audio"),
        imagem=dict(no="LtxApi25ImageToVideo", campos={"model": "LTX-2.5 (Fast)", "model.fps": "24"}, prompt="prompt",
                    seed="seed", px=("model.resolution", _LTX_PX), dur=("model.duration", "str", 2, 20),
                    audio="model.generate_audio", img="image"),
        primeiro_ultimo=dict(no="LtxApi25ImageToVideo", campos={"model": "LTX-2.5 (Fast)", "model.fps": "24"},
                             prompt="prompt", seed="seed", px=("model.resolution", _LTX_PX),
                             dur=("model.duration", "str", 2, 20), audio="model.generate_audio",
                             img="image", fim="last_frame")),
    "pruna2": _vid(
        "Pruna P-Video 2", ["texto", "imagem", "primeiro_ultimo"], ["16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "1:1"],
        ["720p", "1080p"], 1, 20,
        texto=dict(no="PrunaTextToVideoNode", campos={"model": "p-video-2", "model.fps": "24", "model.draft": False,
                                                      "model.enhance_prompt": True},
                   prompt="model.prompt", seed="model.seed",
                   ar=("model.aspect_ratio", ["16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "1:1"]),
                   res=("model.resolution", ["720p", "1080p"]), dur=("model.duration", "str", 1, 20),
                   audio="model.generate_audio"),
        imagem=dict(no="PrunaImageToVideoNode", campos={"model": "p-video-2", "model.fps": "24", "model.draft": False,
                                                        "model.enhance_prompt": True},
                    prompt="model.prompt", seed="model.seed", res=("model.resolution", ["720p", "1080p"]),
                    dur=("model.duration", "str", 1, 20), audio="model.generate_audio", img="model.first_frame"),
        primeiro_ultimo=dict(no="PrunaImageToVideoNode", campos={"model": "p-video-2", "model.fps": "24",
                                                                 "model.draft": False, "model.enhance_prompt": True},
                             prompt="model.prompt", seed="model.seed", res=("model.resolution", ["720p", "1080p"]),
                             dur=("model.duration", "str", 1, 20), audio="model.generate_audio",
                             img="model.first_frame", fim="model.last_frame")),
    "heygenvideo": _vid(
        "HeyGen Video 1.0", ["imagem"], ["16:9", "9:16", "1:1"], ["480p", "768p", "2k"], 5, 15, sem_audio=True,
        imagem=dict(no="HeyGenImageToVideoNode", campos={"model": "heygen-video-1"}, prompt="model.prompt",
                    seed="model.seed", res=("model.resolution", ["480p", "768p", "2k"]),
                    dur=("model.duration", "int", 5, 15), img="model.image")),
    "geminiomni": _vid(
        "Google Gemini Omni", ["texto", "imagem"], ["16:9", "9:16"], ["360p", "720p", "1080p", "4k"], 8, 8,
        texto=dict(no="GeminiVideoOmniV2", campos={"model": "Omni Flash 1.1", "model.task_type": "text_to_video"},
                   prompt="model.prompt", seed="model.seed", ar=("model.aspect_ratio", ["16:9", "9:16"]),
                   res=("model.resolution", ["360p", "720p", "1080p", "4k"])),
        imagem=dict(no="GeminiVideoOmniV2", campos={"model": "Omni Flash 1.1", "model.task_type": "image_to_video"},
                    prompt="model.prompt", seed="model.seed", ar=("model.aspect_ratio", ["16:9", "9:16"]),
                    res=("model.resolution", ["360p", "720p", "1080p", "4k"]), img="autogrow:model.images")),
})


VIDEO_MINIMAX_NUVEM = {
    "rotulo": "MiniMax H3 (nuvem)",
    "descricao": "O mesmo MiniMax, no servidor do ComfyUI. Não usa a sua "
                 "placa. Cobra por segundo de GPU.",
    "nuvem": True,
    "nos": {
        "texto": "ComfyCloudMiniMaxH3TextToVideoNode",
        "imagem": "ComfyCloudMiniMaxH3ImageToVideoNode",
        "primeiro_ultimo": "ComfyCloudMiniMaxH3FirstLastFrameToVideoNode",
    },
    # Aqui o tamanho vem de proporcao + resolucao, nao de pixels.
    "tipo_tamanho": "proporcao",
    "proporcoes": ["1:1", "3:4", "2:3", "3:2", "4:3", "16:9", "9:16", "21:9"],
    "proporcao_padrao": "16:9",
    "resolucoes": ["480p", "720p"],
    "resolucao_padrao": "480p",
    # MEDIDO pela recusa do proprio no: o minimo e 5 s e o maximo 15. Eu
    # oferecia 3 e o motor devolveu "Value 3 smaller than min of 5" — antes de
    # chamar o provedor, entao a tentativa nao custou nada.
    #
    # O no avisa que quantiza em passos de 17 quadros a 24 fps, ou seja o
    # MESMO alinhamento do modelo local; a diferenca e que aqui o servidor
    # arredonda sozinho, e o clipe sai a menos de dois tercos de segundo do
    # pedido.
    "duracao_min": 5,
    "duracao_max": 15,
    "duracao_padrao": 5,
    # Nomes antigos, ainda usados pela guarda do backend.
    "duracao_minima": 5,
    "duracao_maxima": 15,
    "fps": 24,
    "usd_por_segundo_gpu": 0.001295,
    "segundos_estimados": 70,
}


# ---------------------------------------------------------------------------
# Video por NUVEM: Wan 3.0
#
# Traz tres coisas que nenhum outro gerador nosso tem: ate 30 SEGUNDOS, 1080p,
# e um modo de REFERENCIA que aceita ate 10 imagens, 5 videos e 5 audios.
#
# Em troca e caro: o preco e por segundo de video GERADO, nao por peca nem por
# tempo de GPU. Um clipe de 5 s em 720p custa US$ 0,72 — dez vezes o MiniMax
# por nuvem. Por isso a interface mostra o custo exato antes do clique: aqui
# da para calcular, ao contrario do MiniMax.
#
# NAO tem texto para video: o no de imagem EXIGE o primeiro quadro. Quem quer
# partir so de texto usa outro gerador. Por isso este preset declara os modos
# que suporta — os outros nao aparecem quando ele esta escolhido.

# ---------------------------------------------------------------------------
# Referencia por NUVEM: MiniMax Hailuo 03.
#
# NAO e a mesma familia dos tres nos que ja usamos por nuvem
# (ComfyCloudMiniMaxH3*), que so fazem texto, imagem e primeiro+ultimo — nao
# ha referencia ali. Este e `partner/video/MiniMax`, a API propria da MiniMax,
# cobrada pelos mesmos creditos do Comfy.
#
# O no publica a formula no PriceBadge. Mantemos os coeficientes aqui para a
# interface calcular o valor ANTES de enviar o pedido; a diferenca de saldo
# continua sendo a fonte do custo real gravado na galeria.
VIDEO_MINIMAX_REF_NUVEM = {
    # "Hailuo 03" e o nome do NO; o que interessa a quem usa e que este e o
    # MiniMax H3 fazendo multi-referencia. O nome do no fica nos comentarios.
    "rotulo": "MiniMax H3 - MultiRef (nuvem)",
    "descricao": "Referência por nuvem: até 9 imagens, sem usar a sua placa. "
                 "Custo estimado antes de gerar e medido depois pelo saldo.",
    "no": "MinimaxHailuo03ReferenceNode",
    # Duas variantes, e elas NAO oferecem as mesmas resolucoes.
    "variantes": [("MiniMax H3", "Padrão"), ("MiniMax H3 Max", "Max")],
    "variante_padrao": "MiniMax H3",
    "resolucoes_por_variante": {
        "MiniMax H3": ["768P", "2K"],
        "MiniMax H3 Max": ["480P", "768P"],
    },
    "resolucao_padrao": "768P",
    "proporcoes": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
    "proporcao_padrao": "adaptive",
    # A faixa tambem difere: a Padrao comeca em 4 s, a Max em 5.
    "duracao_min": 5,
    "duracao_max": 15,
    "duracao_padrao": 5,
    "max_referencias": 9,
    "fps": 24,
    "segundos_estimados": 120,
    # Formula publicada pelo PriceBadge de MinimaxHailuo03ReferenceNode. A
    # variante Padrao tem preco exato para pedidos somente com imagens. A Max
    # depende dos tokens realmente produzidos pelas referencias, portanto o
    # no (e a nossa tela) exibem uma faixa aproximada.
    "preco_multiref": {
        "MiniMax H3": {
            "usd_por_segundo": {"768P": 0.1287, "2K": 0.1859},
            "imagens_inclusas": 5,
            "usd_por_imagem_extra": 0.0572,
        },
        "MiniMax H3 Max": {
            "usd_por_unidade": 0.0715,
            "unidades_por_segundo": {"480P": 1.0, "768P": 1.6},
            "tokens_gratis": 4096,
            "unidades_por_token_extra": 0.0004,
            "tokens_min_por_imagem": 576,
            "tokens_max_por_imagem": {"standard": 2560, "high": 10240},
        },
    },
    # So a variante Max aceita estes dois.
    "detalhe_referencia": "standard",
    "modo_expansao": "balanced",
}


def estimar_custo_minimax_ref(variante, resolucao, duracao, imagens,
                               detalhe="standard"):
    """Retorna (minimo, maximo) em USD para um pedido so com imagens."""
    tabela = VIDEO_MINIMAX_REF_NUVEM["preco_multiref"][variante]
    if "usd_por_segundo" in tabela:
        valor = duracao * tabela["usd_por_segundo"][resolucao]
        valor += max(0, imagens - tabela["imagens_inclusas"]) * \
            tabela["usd_por_imagem_extra"]
        return valor, valor

    base = duracao * tabela["unidades_por_segundo"][resolucao]
    tokens_min = imagens * tabela["tokens_min_por_imagem"]
    tokens_max = imagens * tabela["tokens_max_por_imagem"][detalhe]

    def em_usd(tokens):
        extras = max(0, tokens - tabela["tokens_gratis"])
        unidades = base + extras * tabela["unidades_por_token_extra"]
        return unidades * tabela["usd_por_unidade"]

    return em_usd(tokens_min), em_usd(tokens_max)

# Quem roda na nuvem e COBRA. Esta lista existe porque ela estava escrita a
# mao dentro do `_custa_credito`, e ao acrescentar o MultiRef eu esqueci de
# inclui-lo: o medidor de custo nunca rodou, e a galeria gravou US$ 0,00 para
# uma geracao de US$ 0,64. Gerador pago que nao entre aqui nao e medido, e o
# erro e SILENCIOSO — por isso a lista mora junto dos presets, num lugar so.
GERADORES_VIDEO_PAGOS = ("minimax-nuvem", "minimax-ref-nuvem", "wan3")

VIDEO_WAN3 = {
    "rotulo": "Wan 3.0 (nuvem)",
    "descricao": "Até 30 s e 1080p, com modo de referência por várias imagens. "
                 "O mais caro: cobra por segundo de vídeo.",
    "nuvem": True,
    "nos": {
        "imagem": "Wan3ImageToVideoApi",
        "primeiro_ultimo": "Wan3ImageToVideoApi",
        "referencia": "Wan3ReferenceToVideoApi",
    },
    "modos": ["imagem", "primeiro_ultimo", "referencia"],
    "tipo_tamanho": "proporcao",

    "variantes": [("wan3.0-video", "Padrão"), ("wan3.0-video-prime", "Prime")],
    "variante_padrao": "wan3.0-video",
    "resolucoes": ["480P", "720P", "1080P"],
    "resolucao_padrao": "480P",
    # "adaptive" tira a proporcao da propria imagem de entrada.
    "proporcoes": ["adaptive", "16:9", "9:16", "1:1", "4:3", "3:4"],
    "proporcao_padrao": "adaptive",
    "duracao_min": 2,
    "duracao_max": 30,
    "duracao_padrao": 5,

    # Dolares por SEGUNDO de video, copiados da tabela do proprio no. As
    # chaves dela estao em minusculas e as opcoes em maiusculas — normalizamos.
    #
    # ATENCAO: a tabela SUPERESTIMA. Medido num clipe de 2 s em 480p, ela
    # previa US$ 0,143 e a cobranca real foi US$ 0,10 — 30% a menos. Entao o
    # numero na tela e TETO, nao preco exato. Errar para cima e o lado seguro;
    # prometer barato e cobrar caro seria o contrario.
    "preco_por_segundo": {
        "wan3.0-video": {"480P": 0.0715, "720P": 0.143, "1080P": 0.286},
        "wan3.0-video-prime": {"480P": 0.09724, "720P": 0.2002, "1080P": 0.4004},
    },
    "max_referencias": 10,
    "fps": 24,
    "segundos_estimados": 120,
}


# ---------------------------------------------------------------------------
# Tamanho de video por RESOLUCAO + PROPORCAO
#
# Ate aqui cada gerador pedia o tamanho de um jeito: os locais em pixels, os de
# nuvem em proporcao + resolucao. Tres formas na mesma tela. Separando os dois
# eixos, todos passam a ter o mesmo controle.
#
# O "p" e o LADO MENOR, como se usa em video: um clipe em pe a 720p e 720x1280,
# nao 405x720.
#
# ALINHAMENTO de 32, que e o do ResolutionSelector dos workflows do usuario. E
# dele que vem o 704 quando se pede 720 — 704 e multiplo de 32 e 720 nao. Com a
# conta aqui, a interface mostra o tamanho REAL antes de gerar.
RESOLUCOES_VIDEO = [("480p", 480), ("720p", 720), ("768p", 768), ("1080p", 1080)]
PROPORCOES_VIDEO = ["16:9", "9:16", "1:1", "4:3", "3:4"]
ALINHAMENTO_VIDEO = 32


def tamanho_de_video(resolucao: str, proporcao: str,
                     alinhamento: int = ALINHAMENTO_VIDEO) -> tuple[int, int]:
    """Pixels a partir de "720p" e "16:9". Sempre multiplo do alinhamento."""
    menor = dict(RESOLUCOES_VIDEO).get(resolucao, 720)
    # No pipeline LTX o primeiro estagio roda na metade, por isso o tamanho
    # final precisa ser multiplo de 64. Para 1080p, 1088 fica a apenas 8 px
    # do pedido; truncar pela regra geral cairia para 1024 e deformaria 16:9.
    if resolucao.lower() == "1080p" and alinhamento == 64:
        menor = 1088
    try:
        a, b = (float(x) for x in proporcao.split(":"))
    except ValueError:
        a = b = 1.0
    if a >= b:                      # deitado: o menor lado e a altura
        alt, larg = menor, menor * (a / b)
    else:                           # em pe: o menor lado e a largura
        larg, alt = menor, menor * (b / a)
    # TRUNCA, nao arredonda. E o que o modelo faz: pedimos 720 de altura e ele
    # devolveu 704 (22 blocos de 32), nao 736 (23). Arredondar daria 736 e a
    # tela prometeria um tamanho que a saida nao teria.
    #
    # Isto tambem elimina uma divergencia entre Python e JavaScript: round(22.5)
    # da 22 em Python e 23 em JS, entao backend e tela discordariam.
    corta = lambda v: max(alinhamento, int(v) // alinhamento * alinhamento)
    return corta(larg), corta(alt)


# Teto padrao de pixels por quadro nos geradores LOCAIS, MEDIDO e nao estimado:
#
#   LTX 2.5 em 1280x704 (901 mil pixels) .... pico 15,3 GB dos 16
#   MiniMax H3 em 1344x768 (1,03 milhao) .... pico 15,4 GB
#
# Ou seja, ~1 milhao de pixels ja usa a placa inteira. 1080p em 16:9 daria
# 1920x1088, 2,1 milhoes — o dobro, e nao caberia no caminho comum. O LTX tem
# um teto proprio porque acima daqui passa a usar os patches de memoria; os
# outros continuam presos a este limite.
# Os identificadores de GERADOR e de FERRAMENTA dividem o mesmo espaco de
# nomes: o despachante em app.py consulta EDICAO antes de SIMPLE. Um id repetido
# nao da erro nenhum — a ferramenta simplesmente engole os pedidos do gerador, e
# o sintoma e uma mensagem correta vinda do lugar errado ("envie ao menos uma
# imagem de referencia" para quem so escreveu um texto).
#
# Aconteceu ao acrescentar o Qwen 2.1 como os dois. Falhar na subida e melhor
# que descobrir gerando.
_repetidos = sorted(set(SIMPLE) & set(EDICAO))
if _repetidos:
    raise RuntimeError(
        "id repetido entre gerador e ferramenta de edicao: %s. Os dois dividem "
        "o mesmo espaco de nomes, e a ferramenta ganha." % ", ".join(_repetidos))


MAX_PIXELS_VIDEO_LOCAL = 1_100_000


# Modos que rodam no segundo motor (ComfyUI v0.41.1, porta 8189).
MODELOS_MOTOR_FLUX3 = {"flux3", "flux3ref"}

# Nos RTX da NVIDIA (ComfyUI_Nvidia_VFX_Nodes), so no segundo motor. Nao sao
# generativos: nao inventam detalhe. MEDIDO em 16/10/2026 num video do LTX 2.3
# de 8 s em 1280x704: 2x em 17,5 s (o SeedVR2 levou 391 s) com PSNR de 46,4 dB
# contra o original no rosto (SeedVR2: 33,8 dB, e mudou a abertura da boca);
# 24->48 fps em 12,3 s, sem fantasma na boca em quadros seguidos.
METODOS_RTX = {"rtx", "rtx48"}
VIDEO_RTX = {
    "rtx": {"rotulo": "Rápido e fiel (RTX)", "segundos_estimados": 25,
            "descricao": ("Amplia 2x sem redesenhar nada: rosto e boca ficam "
                          "iguais ao original, só mais nítidos. Não recria "
                          "textura onde a imagem está borrada.")},
    "rtx48": {"rotulo": "Suavizar movimento (RTX)", "segundos_estimados": 20,
              "descricao": ("Cria um quadro entre cada par: 24 fps viram 48, "
                            "na mesma resolução e duração. Movimentos rápidos "
                            "ainda não foram testados.")},
}


def usa_motor_flux3(p) -> bool:
    return (p.modelo in MODELOS_MOTOR_FLUX3 or p.modelo in ("transformar_video", "profundidade_video")
            or (p.modelo == "video" and p.modo_video in ("ingredientes", "chaves"))
            or (p.modelo == "musica" and getattr(p, "modelo_musica", "") in ("yue2", "yue2-cover"))
            or (p.modelo == "limpar_video" and p.metodo_video in METODOS_RTX))


# LTX 2.5 Creative Lab (Lightricks): IC-LoRAs de video->video, no segundo
# motor (precisam dos nos ComfyUI-LTXVideo, so instalados na v0.41). Uma etapa,
# destilado, 8 passos, como o exemplo LTX-2.5_V2V_ICLoRA_Single_Stage_Distilled.
# MEDIDO em 17/10/2026 num video de 5 s em 960x544: 67 a 93 s, pico de 14,8 a
# 15,6 GiB. Em dB todos PIORAM contra o original (inventam detalhe que nao
# coincide pixel a pixel); a avaliacao valida foi a olho, nos quadros.
VIDEO_TRANSFORMAR = {
    "lado_menor": 544,          # o tamanho de treino dos LoRAs
    "max_quadros": 193,         # 8 s a 24 fps: o maior testado
    "segundos_por_segundo": 18,
    "lora_pasta": "LTX/2.5/creative_lab/",
    "efeitos": {
        "noite": {"rotulo": "Dia vira noite",
                  "lora": "ltx-2.5-22b-ic-lora-day-to-night-0.9.safetensors",
                  "nota": "Mesma cena à noite: céu escuro, postes e janelas acesos.",
                  "texto": "The same scene at night, streetlights and lit windows, dark sky"},
        "limpar": {"rotulo": "Remover pessoas e veículos",
                   "lora": "ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors",
                   "nota": ("Tira quem se move e reconstrói o fundo. Falha quando o "
                            "objeto cobre quase todo o quadro."),
                   "texto": "The same place, empty, no people, no vehicles"},
        "agua": {"rotulo": "Acrescentar água",
                 "lora": "ltx-2.5-22b-ic-lora-water-simulation-0.9.safetensors",
                 "nota": "Alagamento, chuva, ondas, respingos. Descreva no texto a água que quer.",
                 "texto": ("The ground is flooded with shallow rushing water, splashes "
                           "and wet reflective surfaces")},
        # Alpha Gen (02/10/2026): devolve a MASCARA (branco = primeiro plano). O app junta
        # com o original num video transparente (alpha.py). Prompt vazio, como no cartao
        # do modelo; acima de 145 quadros a imagem vaza para a mascara.
        "alpha": {"rotulo": "Tirar o fundo (alfa)",
                  "lora": "ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors",
                  "nota": "Máscara alfa quadro a quadro, sem fundo verde. O modelo escolhe o primeiro plano.",
                  "texto": "", "max_quadros": 145},
        "nitidez": {"rotulo": "Tirar o desfoque",
                    "lora": "ltx-2.5-22b-ic-lora-deblur-0.9.safetensors",
                    "nota": "Recupera a nitidez de um vídeo borrado.", "texto": ""},
        "compressao": {"rotulo": "Tirar artefatos de compressão",
                       "lora": "ltx-2.5-22b-ic-lora-decompression-0.9.safetensors",
                       "nota": "Remove os blocos de um vídeo muito comprimido, sem inventar objetos.",
                       "texto": ""},
        "detalhe": {"rotulo": "Refinar detalhes",
                    "lora": "ltx-2.5-22b-ic-lora-refine-details-1.0.safetensors",
                    "nota": "Reconstrói textura em vídeo mole ou ampliado. Melhora moderada.",
                    "texto": ("sharp photographic detail, crisp textures, natural grain, "
                              "high resolution footage")},
        "cor": {"rotulo": "Colorir preto e branco",
                "lora": "ltx-2.5-22b-ic-lora-colorization-0.9.safetensors",
                "nota": ("Criativo: as cores são inventadas e podem errar (no teste, "
                         "venezianas azuis saíram cinza). Descreva as cores no texto."),
                "texto": ""},
        # Duas entradas: a animacao de blocos (camera e movimento) e uma
        # imagem de estilo, que entra como guia fixa na posicao -1. MEDIDO em
        # 17/10/2026 com maquete SIMULADA (um video real sem cor nem textura)
        # e o primeiro quadro de uma versao noturna: 86 s, 15,2 GiB, seguiu a
        # maquete quadro a quadro com a cara da imagem. Uma animacao 3D de
        # verdade (Blender, Unreal) nao foi testada.
        "maquete": {"rotulo": "Maquete 3D vira cena",
                    "lora": "ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors",
                    "nota": ("O vídeo é uma animação de blocos (Blender, Unreal…) com a "
                             "câmera e o movimento; a imagem de estilo diz como a cena "
                             "deve ficar. Descreva a cena no texto."),
                    "texto": "", "imagem_estilo": True, "quadros_chave": True,
                    # MEDIDO com renders do Blender: 193, 241 e 281 quadros
                    # (133, 164 e 194 s) em 17/10/2026, e 353 quadros (14,7 s,
                    # com um quadro-chave) em 237 s em 18/10/2026, sem queda;
                    # VRAM no teto (o excedente vai para a RAM) e 69 GB
                    # comprometidos. Acima de 353 nao foi testado.
                    "max_quadros": 353},
        # IC-LoRA Union Control (o do LTX 2.3, que o exemplo oficial do 2.5
        # usa): do video original sai so a pose (ou profundidade/contornos);
        # a aparencia vem do primeiro quadro, ja com o personagem novo.
        # MEDIDO em 18/10/2026, pose, 8 s: 109 s, 15,7 GiB, 1152x640; segue
        # gestos e cabeca quadro a quadro, mantem roupa e barba do novo.
        "trocar": {"rotulo": "Trocar personagem",
                   "lora_completo": "LTX/2.3/ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors",
                   "nota": ("O movimento vem do vídeo; a aparência vem do primeiro quadro, "
                            "que você prepara no Flux 3 com referências (o quadro 1 do vídeo "
                            "como @imagem1 + a foto do personagem como @imagem2)."),
                   "texto": "", "imagem_estilo": True,
                   "rotulo_imagem": "Primeiro quadro com o personagem novo",
                   "controles": {"pose": "Pose (recomendado)", "profundidade": "Profundidade",
                                 "contornos": "Contornos"},
                   # MEDIDO em 18/10/2026 com 353 quadros (14,7 s): profundidade
                   # 209 s / 15,4 GiB, pose 197 s / 15,7 GiB (meme de danca
                   # 640x1152), 71-75 GB comprometidos, sem queda.
                   "max_quadros": 353},
        # Mesmo Union Control, so com profundidade. O mapa vem estimado do
        # video (Video-Depth-Anything) ou pronto (passe Z do Blender), e o
        # primeiro quadro e OPCIONAL: sem ele, a aparencia vem so do texto.
        "profundidade": {"rotulo": "Seguir mapa de profundidade",
                         "lora_completo": "LTX/2.3/ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors",
                         "nota": ("Formas, câmera e movimento vêm da profundidade do vídeo; a "
                                  "aparência vem do primeiro quadro, se você der um, ou só do "
                                  "texto. Aceita um mapa pronto (passe de profundidade do Blender)."),
                         "texto": "", "imagem_estilo": True, "imagem_opcional": True,
                         "rotulo_imagem": "Primeiro quadro (opcional)",
                         "controles": {"profundidade": "Profundidade"},
                         "mapa_pronto": True, "max_quadros": 353},
        # IC-LoRA In/Outpainting (do LTX 2.3, como no exemplo oficial do 2.5).
        # MEDIDO em 19/10/2026: meme 9:16 -> 1024x576, 193 quadros, 123 s,
        # 15,45 GiB; laterais coerentes, sem sobra de verde.
        "expandir": {"rotulo": "Expandir enquadramento",
                     "lora_completo": "LTX/2.3/ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors",
                     "nota": ("Muda o formato do vídeo criando o que falta nas bordas; o "
                              "original fica intacto no centro. Sem texto, o modelo continua "
                              "a cena; com texto, descreve o que deve aparecer nas bordas."),
                     "texto": "",
                     "formatos": {"16:9": (1024, 576), "9:16": (576, 1024), "1:1": (768, 768)},
                     "max_quadros": 353},
        "restaurar": {"rotulo": "Restaurar (criativo)",
                      "lora": "ltx-2.5-22b-ic-lora-restore-1.0.safetensors",
                      "nota": ("Para material muito ruim. Inventa: no teste mudou a cor "
                               "de uma parede e criou placas."),
                      "texto": ""},
    },
}


def tamanho_transformar(largura: int, altura: int) -> tuple[int, int]:
    """Mantem a proporcao com o lado menor no tamanho de treino, multiplos de 32."""
    menor = VIDEO_TRANSFORMAR["lado_menor"]
    f = menor / min(largura, altura)
    r = lambda v: max(32, round(v * f / 32) * 32)
    return r(largura), r(altura)


# LoRA Slow-Motion-Control do LTX 2.5 Creative Lab. O truque do fluxo oficial
# (LTX-2.5_I2V_Speed_Control_flow): o condicionamento recebe fps / velocidade
# (24 / 0,2 = 120), e o modelo gera como se o clipe fosse de alta cadencia; o
# arquivo continua a 24 fps. MEDIDO em 17/10/2026, imagem->video de 5 s, mesma
# seed: diferenca media entre quadros 0,92 sem o LoRA e 0,38 com velocidade 0,2,
# no mesmo tempo de geracao (~2 min). Testado so nos modos texto e imagem.
CAMERA_LENTA = {
    "lora": "LTX/2.5/creative_lab/ltx-2.5-22b-lora-slow-motion-control-1.0.safetensors",
    "velocidades": [1.0, 0.5, 0.25, 0.2],
    "modos": ["texto", "imagem"],
}


# IC-LoRA Ingredients do Creative Lab: de 1 a 4 imagens viram UMA folha de
# referencia, repetida em todos os quadros como guia. Forca 1,3, como o
# exemplo LTX-2.5_ICLoRA_Ingredients_Single_Stage_Distilled. MEDIDO em
# 17/10/2026 (personagem + rua, 960x544, 5 s): 82 s, 15,5 GiB; combinou os
# dois, recriando o cenario no mesmo estilo em vez de copia-lo.
# O TEXTO decide: citar "image 1 / image 2" fez o modelo animar a propria
# folha (os paineis lado a lado); "from the left / on the right of the
# reference sheet", com a MESMA folha, combinou os elementos.
INGREDIENTES = {
    "lora": "LTX/2.5/creative_lab/ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors",
    "forca": 1.3,
    "max_imagens": 4,
}


def tamanho_chaves(largura: int, altura: int) -> tuple[int, int]:
    """Saida ate 720 no lado menor e 1280 no maior; o grafo alinha e recorta."""
    f = min(720 / min(largura, altura), 1280 / max(largura, altura))
    return tuple(max(64, round(v * f / 2) * 2) for v in (largura, altura))


# 3D render -> Video: o lado menor maximo pela VRAM da placa. MEDIDO em 29-30/10/2026
# numa RTX 5070 Ti (16 GB, o ComfyUI ve 15,9): 1080 nao cabe (a etapa 2 trava com a placa
# cheia), 720p roda 14,7 s em 7 min 38 s. Abaixo de 16 GB nao roda. Folga nos cortes: as
# placas de 16 GB aparecem com 15,9 e as de 20/24 GB um pouco abaixo disso.
MAQUETE_MIN_VRAM = 15


def limite_maquete(vram_gb: float | None) -> int | None:
    """Lado menor maximo (720 ou 1088) para esta placa; None se ela nao aguenta.
    Sem saber a VRAM (deteccao falhou), fica no 576 testado."""
    if vram_gb is None:
        return 576
    if vram_gb < MAQUETE_MIN_VRAM:
        return None
    return 720 if vram_gb < 18 else 1088


def tamanho_maquete(largura: int, altura: int, lado: int = 576) -> tuple[int, int]:
    """Saida da maquete (duas etapas): lado menor 576 (ou `lado`, em teste ate 1088),
    multiplos de 64, para a etapa 1 (metade) ainda cair em multiplos de 32."""
    f = lado / min(largura, altura)
    r = lambda v: max(64, round(v * f / 64) * 64)
    return r(largura), r(altura)


# Como cada modelo de edicao chama as imagens de referencia. CONFERIDO no
# codigo do ComfyUI (18/10/2026), nao suposto:
#   Qwen Image Edit  -> o no TextEncodeQwenImageEditPlus poe "Picture N:"
#   Mage Flow        -> comfy/text_encoders/mage_flow.py poe "Image N:"
#   Qwen Image 2.1   -> comfy/text_encoders/qwen_image21.py poe "<imageN>"
#   Flux 2 / Flux 3  -> sem rotulo; o modelo aprende pela ordem ("image N")
# O usuario escreve sempre @imagem1, @imagem2...; o app traduz para o rotulo
# do modelo antes de enviar.
_ROTULO_DE_REFERENCIA = {"qwen": "Picture {}", "mage": "Image {}", "qwen21edit": "<image{}>"}


def traduzir_referencias(texto: str, modo: str, metodo: str = "") -> str:
    import re
    motor = motor_do(modo, metodo)
    molde = (_ROTULO_DE_REFERENCIA.get(motor) or _ROTULO_DE_REFERENCIA.get(modo)
             or "image {}")
    return re.sub(r"@(?:imagem|image|img|imagen)\s*(\d+)",
                  lambda m: molde.format(m.group(1)), texto, flags=re.IGNORECASE)



def tamanho_troca(largura: int, altura: int) -> tuple[int, int]:
    """Troca de personagem: lado menor 640 e MULTIPLOS DE 128. O Union Control
    le a guia na metade da resolucao da etapa 1; com 1024x576 a altura do
    latente ficava impar e o no recusava (medido em 18/10/2026)."""
    f = 640 / min(largura, altura)
    r = lambda v: max(128, round(v * f / 128) * 128)
    return r(largura), r(altura)
