"""Geradores de video leves, para placas pequenas (6-8 GB).

LTX-Video 2B (0.9.8 destilado), Wan 2.2 5B (texto e imagem) e Wan 2.1 1.3B
(so texto). Os grafos seguem os templates oficiais do ComfyUI, com os nos que
ja vem no proprio ComfyUI (nada a instalar alem dos pesos).
"""

from presets import win

T5 = "T5/t5xxl_fp8_e4m3fn_scaled.safetensors"
UMT5 = "Wan/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
NEGATIVO_PADRAO = ("blurry, low quality, distorted, deformed, static, still frame, "
                   "watermark, text, jpeg artifacts, worst quality")

VIDEO_LEVES = {
    "ltxv2b": {
        "rotulo": "LTX-Video 2B", "modos": ["texto", "imagem"],
        "resolucoes": ["480p", "720p"], "duracao_max": 10, "fps": 24,
        "passo_quadros": 8, "alinhamento": 32, "segundos_estimados": 40,
    },
    "wan22_5b": {
        "rotulo": "Wan 2.2 5B", "modos": ["texto", "imagem"],
        "resolucoes": ["720p"], "duracao_max": 5, "fps": 24,
        "passo_quadros": 4, "alinhamento": 32, "segundos_estimados": 300,
    },
    "wan21_13b": {
        "rotulo": "Wan 2.1 1.3B", "modos": ["texto"],
        "resolucoes": ["480p"], "duracao_max": 5, "fps": 16,
        "passo_quadros": 4, "alinhamento": 16, "segundos_estimados": 180,
    },
    # Geradores abertos maiores, dos templates oficiais do ComfyUI (27/10/2026).
    # Wan 2.2 14B: duas etapas (ruido alto -> baixo) com o LoRA lightx2v de 4 passos.
    "wan22_14b": {
        "rotulo": "Wan 2.2 14B", "modos": ["texto", "imagem", "primeiro_ultimo"],
        "resolucoes": ["480p", "720p"], "duracao_max": 5, "fps": 16,
        "passo_quadros": 4, "alinhamento": 16, "segundos_estimados": 240,
    },
    # HunyuanVideo 1.5 720p: so a etapa base do template (sem a super-resolucao 1080p).
    "hunyuan15": {
        "rotulo": "HunyuanVideo 1.5", "modos": ["texto", "imagem"],
        "resolucoes": ["480p", "720p"], "duracao_max": 5, "fps": 24,
        "passo_quadros": 4, "alinhamento": 16, "segundos_estimados": 420,
    },
    # Kandinsky 5 Lite: so texto (a versao de imagem do template pede nos extras de latente).
    "kandinsky5": {
        "rotulo": "Kandinsky 5 Lite", "modos": ["texto"],
        "resolucoes": ["480p"], "duracao_max": 5, "fps": 24,
        "passo_quadros": 4, "alinhamento": 16, "segundos_estimados": 300,
    },
}

# Negativo oficial dos templates Wan (em chines, como o modelo foi treinado).
NEGATIVO_WAN = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，"
                "JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，"
                "形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")


def quadros(modelo, duracao):
    """Quadros que o modelo aceita: passo*k + 1, dentro do limite."""
    c = VIDEO_LEVES[modelo]
    s = min(float(duracao), c["duracao_max"])
    k = max(1, round(s * c["fps"] / c["passo_quadros"]))
    return k * c["passo_quadros"] + 1


def _fim(g, imagens, vae, fps, prefixo, tiled=False):
    if tiled:
        g["decodifica"] = {"class_type": "VAEDecodeTiled", "inputs": {
            # 256 quadros de uma vez: os clipes daqui (ate 241) saem num bloco so.
            # Com 64/8 havia uma emenda a cada 56 quadros (nitidez caia nela).
            "samples": imagens, "vae": vae, "tile_size": 512, "overlap": 64,
            "temporal_size": 256, "temporal_overlap": 64}}
    else:
        g["decodifica"] = {"class_type": "VAEDecode", "inputs": {"samples": imagens, "vae": vae}}
    g["monta"] = {"class_type": "CreateVideo", "inputs": {"images": ["decodifica", 0], "fps": fps}}
    g["salva"] = {"class_type": "SaveVideo", "inputs": {
        "video": ["monta", 0], "filename_prefix": prefixo, "format": "auto", "codec": "auto"}}
    return g


def _wan22_14b(g, prompt, seed, largura, altura, n, imagem, imagem_final):
    """Template video_wan2_2_14B_*: ruido alto (passos 0-2) e baixo (2-4), lightx2v 4 passos, CFG 1."""
    tipo = "i2v" if imagem else "t2v"
    lora_v = "v1" if tipo == "i2v" else "v1.1"
    for k in ("alto", "baixo"):
        ruido = "high" if k == "alto" else "low"
        g[f"unet_{k}"] = {"class_type": "UNETLoader", "inputs": {
            "unet_name": win(f"Wan22/wan2.2_{tipo}_{ruido}_noise_14B_fp8_scaled.safetensors"), "weight_dtype": "default"}}
        g[f"lora_{k}"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": [f"unet_{k}", 0],
            "lora_name": win(f"Wan22/wan2.2_{tipo}_lightx2v_4steps_lora_{lora_v}_{ruido}_noise.safetensors"), "strength_model": 1.0}}
        g[f"shift_{k}"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": [f"lora_{k}", 0], "shift": 5.0}}
    g["clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": win(UMT5), "type": "wan", "device": "default"}}
    g["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": win("Wan21/wan_2.1_vae.safetensors")}}
    g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}}
    g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": NEGATIVO_WAN}}
    base = {"positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
            "width": largura, "height": altura, "length": n, "batch_size": 1}
    if imagem_final:
        g["fim"] = {"class_type": "LoadImage", "inputs": {"image": imagem_final}}
        g["cond"] = {"class_type": "WanFirstLastFrameToVideo", "inputs": {**base, "start_image": ["imagem", 0], "end_image": ["fim", 0]}}
    elif imagem:
        g["cond"] = {"class_type": "WanImageToVideo", "inputs": {**base, "start_image": ["imagem", 0]}}
    else:
        g["cond"] = None
        g["latente"] = {"class_type": "EmptyHunyuanLatentVideo", "inputs": {"width": largura, "height": altura, "length": n, "batch_size": 1}}
    if g["cond"] is None:
        del g["cond"]
        pos, neg, lat = ["pos", 0], ["neg", 0], ["latente", 0]
    else:
        pos, neg, lat = ["cond", 0], ["cond", 1], ["cond", 2]
    comum = {"positive": pos, "negative": neg, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"}
    g["amostra_alto"] = {"class_type": "KSamplerAdvanced", "inputs": {**comum, "model": ["shift_alto", 0], "latent_image": lat,
        "add_noise": "enable", "noise_seed": seed, "start_at_step": 0, "end_at_step": 2, "return_with_leftover_noise": "enable"}}
    g["amostra"] = {"class_type": "KSamplerAdvanced", "inputs": {**comum, "model": ["shift_baixo", 0], "latent_image": ["amostra_alto", 0],
        "add_noise": "disable", "noise_seed": 0, "start_at_step": 2, "end_at_step": 10000, "return_with_leftover_noise": "disable"}}
    return ["vae", 0]


def _hunyuan15(g, prompt, seed, largura, altura, n, imagem):
    """Template video_hunyuan_video_1.5_720p_*: etapa base, 20 passos, CFG 6, shift 7."""
    tipo = "i2v" if imagem else "t2v"
    g["unet"] = {"class_type": "UNETLoader", "inputs": {"unet_name": win(f"HunyuanVideo15/hunyuanvideo1.5_720p_{tipo}_fp16.safetensors"), "weight_dtype": "default"}}
    g["shift"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": ["unet", 0], "shift": 7.0}}
    g["clip"] = {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": win("Qwen/qwen_2.5_vl_7b_fp8_scaled.safetensors"),
        "clip_name2": win("HunyuanVideo15/byt5_small_glyphxl_fp16.safetensors"), "type": "hunyuan_video_15", "device": "default"}}
    g["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": win("HunyuanVideo15/hunyuanvideo15_vae_fp16.safetensors")}}
    g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}}
    g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": ""}}
    if imagem:
        g["visao"] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": win("SigCLIP/sigclip_vision_patch14_384.safetensors")}}
        g["visao_img"] = {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["visao", 0], "image": ["imagem", 0], "crop": "center"}}
        g["cond"] = {"class_type": "HunyuanVideo15ImageToVideo", "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
            "width": largura, "height": altura, "length": n, "batch_size": 1, "start_image": ["imagem", 0], "clip_vision_output": ["visao_img", 0]}}
        pos, neg, lat = ["cond", 0], ["cond", 1], ["cond", 2]
    else:
        g["latente"] = {"class_type": "EmptyHunyuanVideo15Latent", "inputs": {"width": largura, "height": altura, "length": n, "batch_size": 1}}
        pos, neg, lat = ["pos", 0], ["neg", 0], ["latente", 0]
    g["guia"] = {"class_type": "CFGGuider", "inputs": {"model": ["shift", 0], "positive": pos, "negative": neg, "cfg": 6.0}}
    g["sigmas"] = {"class_type": "BasicScheduler", "inputs": {"model": ["shift", 0], "scheduler": "simple", "steps": 20, "denoise": 1.0}}
    g["amostrador"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
    g["ruido"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["amostra"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["ruido", 0], "guider": ["guia", 0],
        "sampler": ["amostrador", 0], "sigmas": ["sigmas", 0], "latent_image": lat}}
    return ["vae", 0]


def _kandinsky5(g, prompt, seed, largura, altura, n):
    """Template video_kandinsky5_t2v: 50 passos, CFG 5, euler_ancestral/beta, shift 5."""
    g["unet"] = {"class_type": "UNETLoader", "inputs": {"unet_name": win("Kandinsky5/kandinsky5lite_t2v_sft_5s.safetensors"), "weight_dtype": "default"}}
    g["shift"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": ["unet", 0], "shift": 5.0}}
    g["clip"] = {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": win("Qwen/qwen_2.5_vl_7b_fp8_scaled.safetensors"),
        "clip_name2": win("CLIP/clip_l.safetensors"), "type": "kandinsky5", "device": "default"}}
    g["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": win("HunyuanVideo/hunyuan_video_vae_bf16.safetensors")}}
    g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}}
    g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": ""}}
    g["cond"] = {"class_type": "Kandinsky5ImageToVideo", "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0],
        "width": largura, "height": altura, "length": n, "batch_size": 1}}
    g["amostra"] = {"class_type": "KSampler", "inputs": {"model": ["shift", 0], "positive": ["cond", 0], "negative": ["cond", 1],
        "latent_image": ["cond", 2], "seed": seed, "steps": 50, "cfg": 5.0, "sampler_name": "euler_ancestral", "scheduler": "beta", "denoise": 1.0}}
    return ["vae", 0]


def grafo(modelo, prompt, seed, largura, altura, duracao, imagem=None, prefixo="video", imagem_final=None):
    c = VIDEO_LEVES[modelo]
    n = quadros(modelo, duracao)
    g = {}
    if imagem:
        g["imagem"] = {"class_type": "LoadImage", "inputs": {"image": imagem}}
    if modelo in ("wan22_14b", "hunyuan15", "kandinsky5"):
        vae = (_wan22_14b(g, prompt, seed, largura, altura, n, imagem, imagem_final) if modelo == "wan22_14b"
               else _hunyuan15(g, prompt, seed, largura, altura, n, imagem) if modelo == "hunyuan15"
               else _kandinsky5(g, prompt, seed, largura, altura, n))
        return _fim(g, ["amostra", 0], vae, c["fps"], prefixo, tiled=True)

    if modelo == "ltxv2b":
        g["ckpt"] = {"class_type": "CheckpointLoaderSimple",
                     "inputs": {"ckpt_name": win("LTXV/ltxv-2b-0.9.8-distilled.safetensors")}}
        g["clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": win(T5), "type": "ltxv", "device": "default"}}
        g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}}
        g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": NEGATIVO_PADRAO}}
        if imagem:
            g["i2v"] = {"class_type": "LTXVImgToVideo", "inputs": {
                "positive": ["pos", 0], "negative": ["neg", 0], "vae": ["ckpt", 2], "image": ["imagem", 0],
                "width": largura, "height": altura, "length": n, "batch_size": 1, "strength": 1.0}}
            pos, neg, lat = ["i2v", 0], ["i2v", 1], ["i2v", 2]
        else:
            g["latente"] = {"class_type": "EmptyLTXVLatentVideo", "inputs": {
                "width": largura, "height": altura, "length": n, "batch_size": 1}}
            pos, neg, lat = ["pos", 0], ["neg", 0], ["latente", 0]
        g["cond"] = {"class_type": "LTXVConditioning", "inputs": {"positive": pos, "negative": neg, "frame_rate": c["fps"]}}
        # Destilado: 8 passos, sem CFG.
        g["sigmas"] = {"class_type": "LTXVScheduler", "inputs": {
            "steps": 8, "max_shift": 2.05, "base_shift": 0.95, "stretch": True, "terminal": 0.1, "latent": lat}}
        g["amostrador"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
        g["amostra"] = {"class_type": "SamplerCustom", "inputs": {
            "model": ["ckpt", 0], "add_noise": True, "noise_seed": seed, "cfg": 1.0,
            "positive": ["cond", 0], "negative": ["cond", 1], "sampler": ["amostrador", 0],
            "sigmas": ["sigmas", 0], "latent_image": lat}}
        return _fim(g, ["amostra", 0], ["ckpt", 2], c["fps"], prefixo, tiled=True)

    # Wan 2.2 5B e Wan 2.1 1.3B: mesmo texto (UMT5), modelo e VAE proprios.
    if modelo == "wan22_5b":
        unet, vae = "Wan22/wan2.2_ti2v_5B_fp16.safetensors", "Wan22/wan2.2_vae.safetensors"
        passos, cfg = 20, 5.0
    else:
        unet, vae = "Wan21/wan2.1_t2v_1.3B_fp16.safetensors", "Wan21/wan_2.1_vae.safetensors"
        passos, cfg = 30, 6.0
    g["unet"] = {"class_type": "UNETLoader", "inputs": {"unet_name": win(unet), "weight_dtype": "default"}}
    g["shift"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": ["unet", 0], "shift": 8.0}}
    g["clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": win(UMT5), "type": "wan", "device": "default"}}
    g["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": win(vae)}}
    g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}}
    g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": NEGATIVO_PADRAO}}
    if modelo == "wan22_5b":
        g["latente"] = {"class_type": "Wan22ImageToVideoLatent", "inputs": {
            "vae": ["vae", 0], "width": largura, "height": altura, "length": n, "batch_size": 1,
            **({"start_image": ["imagem", 0]} if imagem else {})}}
    else:
        g["latente"] = {"class_type": "EmptyHunyuanLatentVideo", "inputs": {
            "width": largura, "height": altura, "length": n, "batch_size": 1}}
    g["amostra"] = {"class_type": "KSampler", "inputs": {
        "model": ["shift", 0], "positive": ["pos", 0], "negative": ["neg", 0],
        "latent_image": ["latente", 0], "seed": seed, "steps": passos, "cfg": cfg,
        "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}}
    return _fim(g, ["amostra", 0], ["vae", 0], c["fps"], prefixo, tiled=modelo == "wan22_5b")
