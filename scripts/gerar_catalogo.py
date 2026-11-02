"""Gera catalogo/pacotes.json: cada pacote, seus arquivos e de onde baixar.

Uso: backend/.venv/Scripts/python.exe scripts/gerar_catalogo.py

Para cada arquivo: a pasta e a subpasta EXATAS que os grafos pedem (o
instalador grava ali), e a origem no Hugging Face. Tamanho, licenca e se o
repositorio exige aceite sao lidos do proprio Hugging Face na hora, para o
catalogo nao envelhecer escrito a mao. O nome local pode diferir do nome na
origem (ex.: o Flux 3 "base" que o app chama de flux3_image_klein_bf16).

Arquivos sem origem publica ficam com repo None: a tela os mostra como
"instalar manualmente", e o modo que depende deles nao e oferecido sem eles.
"""
import json
import pathlib
import ssl
import sys
import time
import urllib.request

import truststore

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

# (pasta, subpasta/arquivo local, repo, caminho no repo, opcional, rotulo)
# repo None = sem origem publica conhecida.
P = {}


def pacote(id, nome, tipo, descricao, vram, modos, arquivos, nos=()):
    P[id] = {"id": id, "nome": nome, "tipo": tipo, "descricao": descricao,
             "vram_min_gb": vram, "modos": modos, "nos_extras": list(nos),
             "requisitos": REQ[id], "_arquivos": arquivos}


# Memoria por pacote. vram_min: abaixo disso nao roda. vram_rec: a partir
# disso roda bem; entre os dois, "limitado" (o motivo vai em nota_limitado).
# `medido` diz o que foi rodado de verdade numa RTX 5070 Ti 16 GB / 64 GB RAM;
# o resto e estimativa a partir do tamanho dos arquivos, e assim aparece.
M16 = "Measured on a 16 GB card."
REQ = {
    "ltx25": {"vram_min": 16, "vram_rec": 16, "ram_min": 32, "medido": M16 + " Peak 12.9 GB at 1080p/15 s."},
    "ltx23": {"vram_min": 16, "vram_rec": 16, "ram_min": 32, "medido": M16},
    "krea2": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": M16},
    "kroma": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": M16},
    "flux3": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": M16},
    "flux2_klein": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": M16},
    "qwen21": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": M16},
    "qwen_edit": {"vram_min": 16, "vram_rec": 24, "ram_min": 48, "medido": M16 + " The 20.5 GB model spills into system RAM.",
                  "nota_limitado": "Runs, but part of the model sits in RAM: slower."},
    "trellis": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": M16 + " The 3D model takes about 40 s."},
    "zimage": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": M16},
    # Modelos leves para placas pequenas. Estimados pelos arquivos e pelo que os
    # autores indicam; o "medido" diz o que rodou nesta placa de 16 GB.
    "flux1s": {"vram_min": 8, "vram_rec": 12, "ram_min": 32, "medido": M16},
    "sd35m": {"vram_min": 8, "vram_rec": 10, "ram_min": 16, "medido": M16},
    "sdxl": {"vram_min": 6, "vram_rec": 8, "ram_min": 16, "medido": M16},
    "sd15": {"vram_min": 4, "vram_rec": 6, "ram_min": 8, "medido": M16},
    "ltxv2b": {"vram_min": 6, "vram_rec": 8, "ram_min": 16, "medido": M16},
    "wan22_5b": {"vram_min": 8, "vram_rec": 12, "ram_min": 32, "medido": M16,
                 "nota_limitado": "Runs on 8 GB, slowly: part of the model sits in RAM."},
    "wan21_13b": {"vram_min": 8, "vram_rec": 8, "ram_min": 16, "medido": M16},
    "profundidade": {"vram_min": 4, "vram_rec": 6, "ram_min": 16, "medido": M16},
    # Estimados pelos arquivos e pelos templates oficiais (nao rodados nesta placa).
    "wan22_14b": {"vram_min": 12, "vram_rec": 24, "ram_min": 64, "medido": "Estimated from the files (not run here).",
                  "nota_limitado": "Two 14B models in fp8: on 12-16 GB part of them sits in RAM, slower."},
    "hunyuan15": {"vram_min": 16, "vram_rec": 24, "ram_min": 64, "medido": "Estimated from the files (not run here).",
                  "nota_limitado": "The 8.3B model in fp16 is large for 16 GB: slower, part of it in RAM."},
    "kandinsky5": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": "Estimated from the files (not run here)."},
    "flux1dev": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": "Estimated from the files (not run here)."},
    "flux1krea": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": "Estimated from the files (not run here)."},
    "flux2dev": {"vram_min": 24, "vram_rec": 32, "ram_min": 64, "medido": "Estimated from the files (not run here).",
                 "nota_limitado": "32B model plus a 24B text encoder: on 16 GB most of it sits in RAM, very slow."},
    "hidream": {"vram_min": 16, "vram_rec": 24, "ram_min": 64, "medido": "Estimated from the files (not run here).",
                "nota_limitado": "17B model and four text encoders: tight on 16 GB."},
    "chroma": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": "Estimated from the files (not run here)."},
    "sd35l": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": "Estimated from the files (not run here)."},
    "kandinsky5i": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": "Estimated from the files (not run here)."},
    # Medido em 22/09/2026 antes de ser removido: 121 s para 5 s em 1280x704,
    # pico ~15,2 GB; 15 s coube no limite (~15,1 GB).
    "fasth3": {"vram_min": 16, "vram_rec": 24, "ram_min": 64, "medido": M16 + " 5 s in about 2 min; 15 s fits at the limit.",
               "nota_limitado": "Fits on 16 GB at the limit: close other programs."},
    "mage": {"vram_min": 8, "vram_rec": 12, "ram_min": 16, "medido": M16},
    "ideogram4": {"vram_min": 16, "vram_rec": 16, "ram_min": 48, "medido": M16},
    "upscale": {"vram_min": 8, "vram_rec": 12, "ram_min": 16, "medido": M16},
    "minimax_h3": {"vram_min": 16, "vram_rec": 32, "ram_min": 64,
                   "medido": M16 + " Only low resolution and few steps fit; good results need ~40 steps.",
                   "nota_limitado": "Runs on 16 GB only at low resolution: use Comfy Cloud or a 32 GB card."},
    # Estimado pelos arquivos (H3 Ref2VA 20 GB + Qwen3-VL 32B + SAM 3.1), nao medido:
    # o mesmo H3 base ja mal cabia em 16 GB, e aqui ha mais o SAM e o guia de video.
    "h3_swap": {"vram_min": 24, "vram_rec": 32, "ram_min": 64,
                "medido": "Estimated from the file sizes; not measured.",
                "nota_limitado": "Needs a 32 GB card for good speed; on 24 GB it spills into RAM. Comfy Cloud runs it as is."},
    # Estimado: o 14B em fp8 tem ~17 GB; em 16 GB parte vai para a RAM. Nao medido.
    "wan22_animate": {"vram_min": 16, "vram_rec": 24, "ram_min": 64,
                      "medido": "Estimated from the file sizes; not measured.",
                      "nota_limitado": "The 14B model is ~17 GB: on a 16 GB card part of it sits in RAM, so it is slow."},
    "avatar_ltx": {"vram_min": 16, "vram_rec": 16, "ram_min": 48, "medido": M16 + " Up to 30 s of speech."},
    "avatar": {"vram_min": 16, "vram_rec": 24, "ram_min": 48, "medido": M16,
               "nota_limitado": "Runs on 16 GB by swapping blocks to RAM: slow."},
    "musica": {"vram_min": 12, "vram_rec": 16, "ram_min": 32, "medido": M16},
}


L25 = "Lightricks/LTX-2.5"
pacote("ltx25", "LTX 2.5 Video", "video",
       "Text/image-to-video with audio, first/last frame, keyframes, outpainting and IC-LoRA VFX (Lightricks).",
       16, ["video LTX", "first/last frame", "VFX effects", "ingredients", "MSR"], [
    ("diffusion_models", "LTX/2.5/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors", L25, "diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors", False, "Transformer (int8)"),
    ("text_encoders", "Gemma/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", L25, "text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", False, "Text encoder Gemma 4 12B (int8)"),
    ("vae", "LTX/2.5/ltx-2.5-video-vae-bf16.safetensors", L25, "vae/ltx-2.5-video-vae-bf16.safetensors", False, "Video VAE"),
    ("vae", "LTX/2.5/ltx-2.5-audio-vae-bf16.safetensors", L25, "vae/ltx-2.5-audio-vae-bf16.safetensors", False, "Audio VAE"),
    ("latent_upscale_models", "LTX/2.5/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors", L25, "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors", False, "Spatial upscaler x2"),
    ("text_encoders", "Gemma/gemma4_e2b_it_int8_convrot.safetensors", "Comfy-Org/gemma-4", "text_encoders/gemma4_e2b_it_int8_convrot.safetensors", True, "Gemma 4 2B (automatic prompt)"),
    *[("loras", f"LTX/2.5/creative_lab/{a}.safetensors", f"Lightricks/LTX-2.5-22b-{r}", f"{a}.safetensors", True, rot)
      for r, a, rot in [
          ("IC-LoRA-Ingredients", "ltx-2.5-22b-ic-lora-ingredients-0.9", "Ingredients"),
          ("IC-LoRA-Clean-Plate", "ltx-2.5-22b-ic-lora-clean-plate-1.0", "Clean Plate"),
          ("IC-LoRA-Colorization", "ltx-2.5-22b-ic-lora-colorization-0.9", "Colorization"),
          ("IC-LoRA-Day-To-Night", "ltx-2.5-22b-ic-lora-day-to-night-0.9", "Day To Night"),
          ("IC-LoRA-Deblur", "ltx-2.5-22b-ic-lora-deblur-0.9", "Deblur"),
          ("IC-LoRA-Decompression", "ltx-2.5-22b-ic-lora-decompression-0.9", "Decompression"),
          ("IC-LoRA-Layout-To-Render", "ltx-2.5-22b-ic-lora-layout-to-render-1.0", "Layout To Render"),
          ("IC-LoRA-Refine-Details", "ltx-2.5-22b-ic-lora-refine-details-1.0", "Refine Details"),
          ("IC-LoRA-Restore", "ltx-2.5-22b-ic-lora-restore-1.0", "Restore"),
          ("IC-LoRA-Water-Simulation", "ltx-2.5-22b-ic-lora-water-simulation-0.9", "Water Simulation"),
          ("IC-LoRA-Alpha-Gen", "ltx-2.5-22b-ic-lora-alpha-gen-0.9", "Alpha Gen (remove background)"),
          ("LoRA-Slow-Motion-Control", "ltx-2.5-22b-lora-slow-motion-control-1.0", "Slow Motion Control")]],
    ("loras", "LTX/2.5/LTX-2.5-Licon-MSR-V1.safetensors", "LiconStudio/LTX-2.5-Multiple-Subject-Reference", "LTX-2.5-Licon-MSR-V1.safetensors", True, "Multi-subject reference (MSR)"),
])

pacote("ltx23", "LTX 2.3 add-ons", "video",
       "LTX 2.3 IC-LoRAs used by Expand frame and Character swap in video.",
       16, ["expand frame", "character swap (video)"], [
    ("loras", "LTX/2.3/ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors", "Lightricks/LTX-2.3-22b-IC-LoRA-In-Outpainting", "ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors", False, "In/Outpainting IC-LoRA"),
    ("loras", "LTX/2.3/ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors", "Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control", "ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors", False, "Union Control IC-LoRA"),
    # O "Follow depth" calcula a profundidade com ele (no segundo motor).
    ("videodepthanything", "video_depth_anything_vits.pth", "depth-anything/Video-Depth-Anything-Small", "video_depth_anything_vits.pth", False, "Video Depth Anything Small"),
])

K2 = "Comfy-Org/Krea-2"
KREA_BASE = [
    ("diffusion_models", "Krea/krea2_turbo_fp8_scaled.safetensors", K2, "diffusion_models/krea2_turbo_fp8_scaled.safetensors", False, "Krea 2 Turbo (fp8)"),
    ("text_encoders", "Qwen/qwen3vl_4b_fp8_scaled.safetensors", K2, "text_encoders/qwen3vl_4b_fp8_scaled.safetensors", False, "Qwen3-VL 4B (fp8)"),
    ("vae", "Qwen/qwen_image_vae.safetensors", K2, "vae/qwen_image_vae.safetensors", False, "Qwen Image VAE"),
]
pacote("krea2", "Krea 2", "imagem",
       "Image generation and editing: style reference, camera angles (Anygles), head swap, identity edit, character sheet.",
       12, ["image Krea", "style", "rotate camera", "head swap", "character sheet"], KREA_BASE + [
    ("loras", "Krea/krea2_style_reference.safetensors", K2, "loras/krea2_style_reference.safetensors", True, "Style reference"),
    ("loras", "Krea/krea2_anygles_rank32.safetensors", "yijunwang2/krea2-anygles", "krea2_anygles_rank32.safetensors", True, "Anygles (rotate camera)"),
    ("detection", "SAM3/sam_3d_body_dinov3_bf16.safetensors", "Comfy-Org/sam-3d-body", "detection/sam_3d_body_dinov3_bf16.safetensors", True, "SAM 3D Body (for Anygles)"),
    ("loras", "Krea/bfs_head_swap_v1.1_krea2.safetensors", "Alissonerdx/BFS-Best-Face-Swap", "bfs_head_swap_v1.1_krea2.safetensors", True, "BFS head swap"),
    ("loras", "Krea/krea2_identity_edit_v1_2_r64.safetensors", "conradlocke/krea2-identity-edit", "krea2_identity_edit_v1_2_r64.safetensors", True, "Identity edit"),
    ("loras", "Krea/QuadView_krea2_v1.safetensors", None, None, True, "QuadView (character sheet)"),
])

pacote("kroma", "Kroma v0.3.1 Turbo", "imagem",
       "Krea 2 fine-tune by lodestones (community int8 quantization). Uses the Krea 2 text encoder and VAE.",
       12, ["image Kroma"], KREA_BASE[1:] + [
    ("diffusion_models", "Krea/kroma-v0.3.1-turbo-opd-int8-convrot.safetensors", "cicalooo/kroma-v0.3.1-turbo-opd-int8-convrot-learned", "kroma-v0.3.1-turbo-opd_int8_convrot_learned.safetensors", False, "Kroma Turbo (int8)"),
])

BFL3 = "black-forest-labs/flux-3-image-klein-comfy"
pacote("flux3", "FLUX 3 Image Klein", "imagem",
       "Black Forest Labs FLUX 3 Klein (base): generation and multi-reference editing.",
       12, ["image FLUX 3", "edit with references (FLUX 3)"], [
    ("diffusion_models", "Flux3/flux3_image_klein_bf16.safetensors", BFL3, "diffusion_models/flux3-image-klein-base-bf16.safetensors", False, "FLUX 3 Klein base (bf16)"),
    ("text_encoders", "Flux3/qwen3vl_4b_int8_convrot.safetensors", BFL3, "text_encoders/qwen3vl_4b_int8_convrot.safetensors", False, "Qwen3-VL 4B (int8)"),
    ("vae", "Flux2/flux2-vae.safetensors", BFL3, "vae/flux2-vae.safetensors", False, "FLUX 2 VAE"),
])

pacote("flux2_klein", "FLUX 2 Klein 9B", "imagem",
       "FLUX 2 Klein base 9B: image generation and character swap.",
       12, ["image Klein", "character swap"], [
    ("diffusion_models", "Flux2/flux-2-klein-base-9b-fp8.safetensors", "black-forest-labs/FLUX.2-klein-base-9b-fp8", "flux-2-klein-base-9b-fp8.safetensors", False, "Klein base 9B (fp8)"),
    ("text_encoders", "Qwen/qwen_3_8b_fp8mixed.safetensors", "Comfy-Org/vae-text-encorder-for-flux-klein-9b", "split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors", False, "Qwen 3 8B (fp8)"),
    ("vae", "Flux2/flux2-vae.safetensors", BFL3, "vae/flux2-vae.safetensors", False, "FLUX 2 VAE"),
    ("vae", "AE/full_encoder_small_decoder.safetensors", "black-forest-labs/FLUX.2-small-decoder", "full_encoder_small_decoder.safetensors", True, "Small decoder (character swap)"),
])

Q21 = "Comfy-Org/Qwen-Image-2.1"
pacote("qwen21", "Qwen Image 2.1", "imagem", "Qwen Image 2.1: generation and instruction editing.",
       12, ["image Qwen 2.1", "edit Qwen 2.1"], [
    ("diffusion_models", "Qwen/qwen_image_2.1_int8_convrot.safetensors", Q21, "diffusion_models/qwen_image_2.1_int8_convrot.safetensors", False, "Qwen Image 2.1 (int8)"),
    ("text_encoders", "Qwen/qwen3vl_8b_int8_convrot.safetensors", Q21, "text_encoders/qwen3vl_8b_int8_convrot.safetensors", False, "Qwen3-VL 8B (int8)"),
    ("vae", "Qwen/qwen_image_2.1_vae_bf16.safetensors", Q21, "vae/qwen_image_2.1_vae_bf16.safetensors", False, "VAE"),
    # Edit an area (Edit): recorta pelo nome ("the jacket") e so ali o Qwen 2.1 edita.
    ("checkpoints", "SAM3/sam3.1_multiplex_fp16.safetensors", "Comfy-Org/sam3.1", "checkpoints/sam3.1_multiplex_fp16.safetensors", False, "SAM 3.1 (edit an area)"),
])

QE = "Comfy-Org/Qwen-Image-Edit_ComfyUI"
pacote("qwen_edit", "Qwen Image Edit 2511", "imagem", "Instruction editing, relight and light transfer, multiple angles.",
       16, ["edit Qwen", "relight", "light reference", "angles"], [
    ("diffusion_models", "Qwen/qwen_image_edit_2511_int8_convrot.safetensors", QE, "split_files/diffusion_models/qwen_image_edit_2511_int8_convrot.safetensors", False, "Qwen Image Edit 2511 (int8)"),
    ("text_encoders", "Qwen/qwen_2.5_vl_7b_nvfp4.safetensors", "Comfy-Org/Qwen-Image_ComfyUI", "split_files/text_encoders/qwen_2.5_vl_7b_nvfp4.safetensors", False, "Qwen2.5-VL 7B (nvfp4)"),
    ("vae", "Qwen/qwen_image_vae.safetensors", K2, "vae/qwen_image_vae.safetensors", False, "Qwen Image VAE"),
    ("loras", "Qwen/Qwen-Image-Edit-2509-Light-Migration.safetensors", QE, "split_files/loras/Qwen-Image-Edit-2509-Light-Migration.safetensors", True, "Light migration"),
    ("loras", "Qwen/Qwen-Image-Edit-2509-Relight.safetensors", "Comfy-Org/Qwen-Image-Edit_ComfyUI", "split_files/loras/Qwen-Image-Edit-2509-Relight.safetensors", True, "Relight"),
    ("loras", "Qwen/Qwen-Edit-2509-Multiple-angles.safetensors", QE, "split_files/loras/Qwen-Edit-2509-Multiple-angles.safetensors", True, "Multiple angles"),
    # Orbit (Edit): 96 poses de camera, preserva a pessoa. Obrigatoria: e o motor padrao do Orbit.
    ("loras", "Qwen/Qwen-Image-Edit-2511-Multiple-Angles.safetensors", "fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA", "qwen-image-edit-2511-multiple-angles-lora.safetensors", False, "Multiple angles 2511 (96 camera poses)"),
])

ZI = "Comfy-Org/z_image_turbo"
pacote("zimage", "Z-Image Turbo", "imagem",
       "Fast image generation, pose/edge/depth control (ControlNet Union) and creative upscaling.",
       12, ["image Z-Image", "control", "creative upscale"], [
    ("diffusion_models", "Z_Image/z_image_turbo_bf16.safetensors", ZI, "split_files/diffusion_models/z_image_turbo_bf16.safetensors", False, "Z-Image Turbo (bf16)"),
    ("text_encoders", "Qwen/qwen_3_4b.safetensors", ZI, "split_files/text_encoders/qwen_3_4b.safetensors", False, "Qwen 3 4B"),
    ("vae", "AE/ae.safetensors", ZI, "split_files/vae/ae.safetensors", False, "AE VAE"),
    ("model_patches", "Z-Image/Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors", "alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1", "Z-Image-Turbo-Fun-Controlnet-Union-2.1-2602-8steps.safetensors", True, "ControlNet Union 2.1"),
], nos=["comfyui_controlnet_aux"])

MG = "Comfy-Org/Mage-Flow"
pacote("mage", "Mage Flow", "imagem", "Mage Flow: generation and instruction editing.",
       10, ["image Mage", "edit Mage"], [
    ("diffusion_models", "Mage/mage_flow_int8_convrot.safetensors", MG, "diffusion_models/mage_flow_int8_convrot.safetensors", False, "Mage Flow (int8)"),
    ("diffusion_models", "Mage/mage_flow_edit_int8_convrot.safetensors", MG, "diffusion_models/mage_flow_edit_int8_convrot.safetensors", True, "Mage Flow Edit (int8)"),
    ("text_encoders", "Qwen/qwen3vl_4b_bf16.safetensors", MG, "text_encoders/qwen3vl_4b_bf16.safetensors", False, "Qwen3-VL 4B"),
    ("vae", "Mage/mage_flow_vae_bf16.safetensors", MG, "vae/mage_flow_vae_bf16.safetensors", False, "VAE"),
])

IG = "Comfy-Org/Ideogram-4"
pacote("ideogram4", "Ideogram 4 (open weights)", "imagem", "Ideogram 4 local: strong typography and graphic design.",
       16, ["image Ideogram"], [
    ("diffusion_models", "Ideogram4/ideogram4_int8_convrot.safetensors", IG, "diffusion_models/ideogram4_int8_convrot.safetensors", False, "Ideogram 4 (int8)"),
    ("diffusion_models", "Ideogram4/ideogram4_unconditional_int8_convrot.safetensors", IG, "diffusion_models/ideogram4_unconditional_int8_convrot.safetensors", False, "Ideogram 4 unconditional (int8)"),
    ("text_encoders", "Qwen/qwen3vl_8b_fp8_scaled.safetensors", IG, "text_encoders/qwen3vl_8b_fp8_scaled.safetensors", False, "Qwen3-VL 8B (fp8)"),
    ("vae", "Flux2/flux2-vae.safetensors", IG, "vae/flux2-vae.safetensors", False, "FLUX 2 VAE"),
])

PX = "Comfy-Org/Pixal3D"
# Orbit 3D (Edit): foto -> malha 3D com textura, girada no angulo exato; o Qwen Image Edit 2511 refaz como foto.
pacote("trellis", "TRELLIS 2 (3D)", "imagem", "Turns a photo into a textured 3D model for the 3D Orbit in Edit (the photo pass uses Qwen Image Edit 2511).",
       12, ["3D orbit"], [
    ("diffusion_models", "Trellis/trellis_2_int8_convrot.safetensors", "Comfy-Org/TRELLIS.2", "diffusion_models/trellis_2_int8_convrot.safetensors", False, "TRELLIS 2 (int8)"),
    ("vae", "Trellis/trellis_2_shape_vae_bf16.safetensors", PX, "vae/trellis_2_shape_vae_bf16.safetensors", False, "Shape VAE"),
    ("vae", "Trellis/trellis_2_texture_vae_bf16.safetensors", PX, "vae/trellis_2_texture_vae_bf16.safetensors", False, "Texture VAE"),
    ("clip_vision", "dino_v3_L_naf_fp32.safetensors", PX, "clip_vision/dino_v3_L_naf_fp32.safetensors", False, "DINOv3 L"),
    ("background_removal", "birefnet.safetensors", "Comfy-Org/BiRefNet", "background_removal/birefnet.safetensors", False, "BiRefNet (cut-out)"),
])

SV = "Comfy-Org/SeedVR2"
pacote("upscale", "Upscalers", "imagem", "SeedVR2 (image and video), 4x UltraSharp V2 and Real-ESRGAN.",
       8, ["upscale image", "clean video"], [
    ("diffusion_models", "SeedVR/seedvr2_3b_int8_convrot.safetensors", SV, "diffusion_models/seedvr2_3b_int8_convrot.safetensors", False, "SeedVR2 3B (int8)"),
    ("vae", "SeedVR/seedvr2_ema_vae_fp16.safetensors", SV, "vae/seedvr2_ema_vae_fp16.safetensors", False, "SeedVR2 VAE"),
    ("upscale_models", "4x-UltraSharpV2.safetensors", "Kim2091/UltraSharpV2", "4x-UltraSharpV2.safetensors", True, "4x UltraSharp V2"),
    ("upscale_models", "RealESRGAN_x4plus.safetensors", "Comfy-Org/Real-ESRGAN_repackaged", "RealESRGAN_x4plus.safetensors", True, "Real-ESRGAN x4"),
    ("seedvr2", "seedvr2_ema_3b_fp8_e4m3fn.safetensors", "numz/SeedVR2_comfyUI", "seedvr2_ema_3b_fp8_e4m3fn.safetensors", True, "SeedVR2 3B fp8 (video clean-up)"),
    ("seedvr2", "ema_vae_fp16.safetensors", "numz/SeedVR2_comfyUI", "ema_vae_fp16.safetensors", True, "SeedVR2 VAE (video clean-up)"),
])

MH = "Comfy-Org/MiniMax-H3"
pacote("minimax_h3", "MiniMax H3 Video", "video",
       "Open-weight MiniMax H3: text, image and first/last frame to video with sound. Best on 32 GB+ cards or Comfy Cloud.",
       16, ["video MiniMax H3"], [
    ("diffusion_models", "Minimax/minimax_h3_fl2va_pruned_int8_convrot.safetensors", MH, "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors", False, "MiniMax H3 fl2va (int8)"),
    ("text_encoders", "Qwen/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", MH, "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", False, "Qwen3-VL 32B (nvfp4)"),
    ("vae", "Minimax/minimax_h3_video_vae_fp16.safetensors", MH, "vae/minimax_h3_video_vae_fp16.safetensors", False, "Video VAE"),
    ("vae", "Minimax/minimax_h3_audio_vae_fp32.safetensors", MH, "vae/minimax_h3_audio_vae_fp32.safetensors", False, "Audio VAE"),
    ("loras", "Minimax/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", MH, "loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", False, "Turbo LoRA (8 steps)"),
])

pacote("h3_swap", "MiniMax H3 Character Swap", "video",
       "Replace a person in a video with your character, keeping motion, camera, light and sound (SAM 3 + MiniMax H3 Ref2VA). "
       "Genjutsu tab. Also needs MDMZ's free workflow file H3_Character_Swap_MDMZ_v1.json (https://www.patreon.com/MDMZ/posts/h3-character-172119619) in backend/terceiros.",
       24, ["character swap (H3)"], [
    ("diffusion_models", "Minimax/minimax_h3_ref2va_pruned_int8_convrot.safetensors", MH, "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors", False, "MiniMax H3 Ref2VA (int8)"),
    ("text_encoders", "Qwen/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", MH, "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", False, "Qwen3-VL 32B (nvfp4)"),
    ("vae", "Minimax/minimax_h3_video_vae_fp16.safetensors", MH, "vae/minimax_h3_video_vae_fp16.safetensors", False, "Video VAE"),
    ("vae", "Minimax/minimax_h3_audio_vae_fp32.safetensors", MH, "vae/minimax_h3_audio_vae_fp32.safetensors", False, "Audio VAE"),
    ("checkpoints", "SAM3/sam3.1_multiplex_fp16.safetensors", "Comfy-Org/sam3.1", "checkpoints/sam3.1_multiplex_fp16.safetensors", False, "SAM 3.1 (who to replace)"),
    ("loras", "Minimax/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors", "lightx2v/Minimax-h3-Turbo", "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors", True, "Turbo LoRA (Ref2V)"),
])

KJ = "Kijai/WanVideo_comfy"
W21 = "Comfy-Org/Wan_2.1_ComfyUI_repackaged"
pacote("wan22_animate", "Wan 2.2 Animate · Replace", "video",
       "Genjutsu: replace a person inside a video with your character, keeping the place, with relit lighting "
       "(Wan 2.2 Animate 14B + SAM 3 + DWPose). About 5 s per clip.",
       16, ["character replace (Wan 2.2)"], [
    ("diffusion_models", "Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors", "Kijai/WanVideo_comfy_fp8_scaled", "Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors", False, "Wan 2.2 Animate 14B (fp8)"),
    ("loras", "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors", KJ, "Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors", False, "LightX2V speed LoRA"),
    ("loras", "WanAnimate_relight_lora_fp16.safetensors", KJ, "LoRAs/Wan22_relight/WanAnimate_relight_lora_fp16.safetensors", False, "Relight LoRA"),
    ("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors", W21, "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", False, "UMT5 XXL (fp8)"),
    ("clip_vision", "clip_vision_h.safetensors", W21, "split_files/clip_vision/clip_vision_h.safetensors", False, "CLIP Vision H"),
    ("vae", "Wan2_1_VAE_bf16.safetensors", KJ, "Wan2_1_VAE_bf16.safetensors", False, "Wan 2.1 VAE"),
    ("checkpoints", "SAM3/sam3.1_multiplex_fp16.safetensors", "Comfy-Org/sam3.1", "checkpoints/sam3.1_multiplex_fp16.safetensors", False, "SAM 3.1 (who to replace)"),
])

# Arquivo que o instalador RECRIA a partir de outro ja baixado, em vez de
# baixar: (arquivo de origem, prefixos dos tensores que ficam). Ver
# instalador.extrair_tensores.
DERIVADO = "@derivado"
DERIVADOS = {
    "LTX/LTX_2.3/ltx-2.3-22b-dev-fp8_so_texto.safetensors": {
        "de": "checkpoints/LTX/LTX_2.3/ltx-2.3-22b-dev-fp8.safetensors",
        # So a projecao e os conectores de texto: ler o checkpoint de 29 GB
        # inteiro no codificador derrubava o motor (ver backend/ltx23.py).
        "prefixos": ["model.diffusion_model.video_embeddings_connector.",
                     "model.diffusion_model.audio_embeddings_connector.",
                     "text_embedding_projection."],
        "tamanho": 6344527560},
}

pacote("avatar_ltx", "LTX 2.3 Talking Avatar", "video",
       "Lip sync: a photo and a voice track become a talking video, up to 30 s (Lightricks LTX 2.3).",
       16, ["lip sync"], [
    ("checkpoints", "LTX/LTX_2.3/ltx-2.3-22b-dev-fp8.safetensors", "Lightricks/LTX-2.3-fp8", "ltx-2.3-22b-dev-fp8.safetensors", False, "LTX 2.3 22B dev (fp8)"),
    ("checkpoints", "LTX/LTX_2.3/ltx-2.3-22b-dev-fp8_so_texto.safetensors", DERIVADO, None, False, "Text connectors (extracted from the checkpoint)"),
    ("text_encoders", "Gemma/gemma_3_12B_it_fp4_mixed.safetensors", "Comfy-Org/ltx-2", "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors", False, "Gemma 3 12B (fp4)"),
    ("loras", "LTX/2.3/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors", "Kijai/LTX2.3_comfy", "loras/ltx-2.3-22b-distilled-1.1_lora-dynamic_fro09_avg_rank_111_bf16.safetensors", False, "Distilled LoRA 1.1"),
    ("latent_upscale_models", "LTX/2.3/ltx-2.3-spatial-upscaler-x2-1.1.safetensors", "Lightricks/LTX-2.3", "ltx-2.3-spatial-upscaler-x2-1.1.safetensors", False, "Spatial upscaler x2"),
])

pacote("avatar", "LongCat Avatar 1.5", "video", "Talking avatar from a photo and an audio track (Meituan LongCat).",
       16, ["avatar"], [
    ("diffusion_models", "LongCat/LongCat-Avatar-15_comfy-Q8_0.gguf", "vantagewithai/LongCat-Video-Avatar-1.5-GGUF-ComfyUI", "LongCat-Avatar-15_comfy-Q8_0.gguf", False, "LongCat Avatar 1.5 (GGUF Q8)"),
    ("loras", "LongCat-Avatar15_dmd_lora_bf16.safetensors", None, None, False, "DMD LoRA (converted locally)"),
    ("audio_encoders", "whisper-large-v3.safetensors", None, None, False, "Whisper large v3"),
    ("text_encoders", "umt5-xxl-enc-bf16.safetensors", None, None, False, "UMT5-XXL encoder"),
    ("vae", "Wan2_1_VAE_bf16.safetensors", "Comfy-Org/Wan-Animate-2", "vae/Wan2_1_VAE_bf16.safetensors", False, "Wan 2.1 VAE"),
])

YU = "Comfy-Org/YuE2"
ACE = "Comfy-Org/ace_step_1.5_ComfyUI_files"
MM = "Comfy-Org/MiniMax-Music-3"
SA = "Comfy-Org/stable-audio-3"
pacote("musica", "Music models", "audio", "Songs with lyrics (YuE2, ACE-Step 1.5, MiniMax Music 3) and Stable Audio 3.",
       12, ["music"], [
    ("checkpoints", "yue2_3b_int8_convrot.safetensors", YU, "checkpoints/yue2_3b_int8_convrot.safetensors", True, "YuE2 3B"),
    ("audio_encoders", "sheetsage2_bf16.safetensors", YU, "audio_encoders/sheetsage2_bf16.safetensors", True, "SheetSage2"),
    ("diffusion_models", "ACE-Step/acestep_v1.5_turbo.safetensors", ACE, "split_files/diffusion_models/acestep_v1.5_turbo.safetensors", True, "ACE-Step 1.5 Turbo"),
    ("text_encoders", "ACE-Step/qwen_0.6b_ace15.safetensors", ACE, "split_files/text_encoders/qwen_0.6b_ace15.safetensors", True, "ACE-Step text encoder 0.6B"),
    ("text_encoders", "ACE-Step/qwen_1.7b_ace15.safetensors", ACE, "split_files/text_encoders/qwen_1.7b_ace15.safetensors", True, "ACE-Step text encoder 1.7B"),
    ("vae", "ACE-Step/ace_1.5_vae.safetensors", ACE, "split_files/vae/ace_1.5_vae.safetensors", True, "ACE-Step VAE"),
    ("diffusion_models", "Minimax/minimax_music3_dit_fp16.safetensors", MM, "diffusion_models/minimax_music3_dit_fp16.safetensors", True, "MiniMax Music 3"),
    ("text_encoders", "Minimax/minimax_music3_text_encoder_pruned_int8_convrot.safetensors", MM, "text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors", True, "MiniMax Music 3 text encoder"),
    ("vae", "minimax/minimax_music3_dav.safetensors", MM, "vae/minimax_music3_dav.safetensors", True, "MiniMax Music 3 VAE"),
    ("checkpoints", "StableAudio/stable_audio_3_medium_base.safetensors", SA, "checkpoints/stable_audio_3_medium_base.safetensors", True, "Stable Audio 3 medium"),
    ("text_encoders", "Gemma/t5gemma_b_b_ul2.safetensors", SA, "text_encoders/t5gemma_b_b_ul2.safetensors", True, "T5Gemma (Stable Audio)"),
    ("loras", "ar_lora_inst_v3abc_comfyui.safetensors", None, None, True, "AR instrumental LoRA"),
])


FH = "FastVideo/FastVideo-FastH3-Comfy"
pacote("fasth3", "FastH3 (MiniMax H3 distilled)", "video",
       "MiniMax H3 distilled to 8 steps by FastVideo: text, image and first/last frame to video with sound, up to 15 s. No reference mode.",
       16, ["video FastH3", "first/last frame"], [
    ("diffusion_models", "Minimax/fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors", FH, "diffusion_models/fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors", False, "FastH3 8-step v2 (int8)"),
    ("text_encoders", "Qwen/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", MH, "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", False, "Qwen3-VL 32B (nvfp4)"),
    ("vae", "Minimax/minimax_h3_video_vae_fp16.safetensors", MH, "vae/minimax_h3_video_vae_fp16.safetensors", False, "Video VAE"),
    ("vae", "Minimax/minimax_h3_audio_vae_fp32.safetensors", MH, "vae/minimax_h3_audio_vae_fp32.safetensors", False, "Audio VAE"),
])

pacote("profundidade", "Video depth map", "video",
       "Video Depth Anything: turns any video into a stable depth map (video or EXR frames). Runs on the video engine.",
       4, ["video depth map"], [
    ("videodepthanything", "video_depth_anything_vits.pth", "depth-anything/Video-Depth-Anything-Small", "video_depth_anything_vits.pth", False, "Video Depth Anything Small"),
], nos=["ComfyUI-Video-Depth-Anything"])

W22 = "Comfy-Org/Wan-2.2"
pacote("wan22_14b", "Wan 2.2 14B Video", "video",
       "Wan 2.2 14B (text, image and first/last frame to video), 4 steps with the lightx2v LoRA, from ComfyUI's official templates.",
       12, ["video Wan 2.2 14B", "first/last frame"], [
    ("diffusion_models", "Wan22/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors", W22, "split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors", False, "T2V high noise 14B (fp8)"),
    ("diffusion_models", "Wan22/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors", W22, "split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors", False, "T2V low noise 14B (fp8)"),
    ("diffusion_models", "Wan22/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", W22, "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", False, "I2V high noise 14B (fp8)"),
    ("diffusion_models", "Wan22/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", W22, "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", False, "I2V low noise 14B (fp8)"),
    ("loras", "Wan22/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors", W22, "split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors", False, "lightx2v 4 steps T2V (high)"),
    ("loras", "Wan22/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors", W22, "split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors", False, "lightx2v 4 steps T2V (low)"),
    ("loras", "Wan22/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", W22, "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", False, "lightx2v 4 steps I2V (high)"),
    ("loras", "Wan22/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors", W22, "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors", False, "lightx2v 4 steps I2V (low)"),
    ("text_encoders", "Wan/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "Comfy-Org/Wan-2.1", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", False, "UMT5-XXL (fp8)"),
    ("vae", "Wan21/wan_2.1_vae.safetensors", "Comfy-Org/Wan-2.1", "split_files/vae/wan_2.1_vae.safetensors", False, "Wan 2.1 VAE"),
])

HY = "Comfy-Org/Hunyuan-Video-1.5"
pacote("hunyuan15", "HunyuanVideo 1.5", "video",
       "Tencent HunyuanVideo 1.5 at 720p: text and image to video, from ComfyUI's official template (base stage).",
       16, ["video HunyuanVideo 1.5"], [
    ("diffusion_models", "HunyuanVideo15/hunyuanvideo1.5_720p_t2v_fp16.safetensors", HY, "split_files/diffusion_models/hunyuanvideo1.5_720p_t2v_fp16.safetensors", False, "720p T2V (fp16)"),
    ("diffusion_models", "HunyuanVideo15/hunyuanvideo1.5_720p_i2v_fp16.safetensors", HY, "split_files/diffusion_models/hunyuanvideo1.5_720p_i2v_fp16.safetensors", False, "720p I2V (fp16)"),
    ("text_encoders", "Qwen/qwen_2.5_vl_7b_fp8_scaled.safetensors", HY, "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors", False, "Qwen2.5-VL 7B (fp8)"),
    ("text_encoders", "HunyuanVideo15/byt5_small_glyphxl_fp16.safetensors", HY, "split_files/text_encoders/byt5_small_glyphxl_fp16.safetensors", False, "ByT5 Glyph"),
    ("vae", "HunyuanVideo15/hunyuanvideo15_vae_fp16.safetensors", HY, "split_files/vae/hunyuanvideo15_vae_fp16.safetensors", False, "HunyuanVideo 1.5 VAE"),
    ("clip_vision", "SigCLIP/sigclip_vision_patch14_384.safetensors", "Comfy-Org/sigclip_vision_384", "sigclip_vision_patch14_384.safetensors", False, "SigCLIP vision (image to video)"),
])

pacote("kandinsky5", "Kandinsky 5 Lite", "video",
       "Kandinsky 5.0 Video Lite: text to video, 5 s, from ComfyUI's official template.",
       12, ["video Kandinsky 5"], [
    ("diffusion_models", "Kandinsky5/kandinsky5lite_t2v_sft_5s.safetensors", "kandinskylab/Kandinsky-5.0-T2V-Lite-sft-5s", "model/kandinsky5lite_t2v_sft_5s.safetensors", False, "Kandinsky 5 Lite T2V"),
    ("text_encoders", "Qwen/qwen_2.5_vl_7b_fp8_scaled.safetensors", HY, "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors", False, "Qwen2.5-VL 7B (fp8)"),
    ("text_encoders", "CLIP/clip_l.safetensors", "comfyanonymous/flux_text_encoders", "clip_l.safetensors", False, "CLIP-L"),
    ("vae", "HunyuanVideo/hunyuan_video_vae_bf16.safetensors", "Kijai/HunyuanVideo_comfy", "hunyuan_video_vae_bf16.safetensors", False, "HunyuanVideo VAE"),
])

AE_Z = ("vae", "AE/ae.safetensors", "Comfy-Org/z_image_turbo", "split_files/vae/ae.safetensors", False, "AE VAE")
CLIP_L = ("text_encoders", "CLIP/clip_l.safetensors", "comfyanonymous/flux_text_encoders", "clip_l.safetensors", False, "CLIP-L")
T5_FP8 = ("text_encoders", "T5/t5xxl_fp8_e4m3fn_scaled.safetensors", "comfyanonymous/flux_text_encoders", "t5xxl_fp8_e4m3fn_scaled.safetensors", False, "T5-XXL (fp8)")
pacote("flux1dev", "FLUX.1 dev", "imagem",
       "Black Forest Labs' FLUX.1 dev (fp8, all-in-one file). Non-commercial license.", 12, ["image FLUX.1 dev"], [
    ("checkpoints", "Flux1/flux1-dev-fp8.safetensors", "Comfy-Org/Flux-1-Dev", "flux1-dev-fp8.safetensors", False, "FLUX.1 dev (fp8, all-in-one)"),
])
pacote("flux1krea", "FLUX.1 Krea dev", "imagem",
       "FLUX.1 fine-tuned by Krea for natural, less 'AI-looking' photos. Non-commercial license.", 12, ["image FLUX.1 Krea"], [
    ("diffusion_models", "Flux1/flux1-krea-dev_fp8_scaled.safetensors", "Comfy-Org/Flux-1-Krea-Dev", "split_files/diffusion_models/flux1-krea-dev_fp8_scaled.safetensors", False, "FLUX.1 Krea dev (fp8)"),
    CLIP_L, T5_FP8, AE_Z,
])
F2 = "Comfy-Org/Flux-2-Dev"
pacote("flux2dev", "FLUX.2 dev", "imagem",
       "FLUX.2 dev (32B) with the Mistral Small text encoder. Very detailed, very heavy. Non-commercial license.", 24, ["image FLUX.2 dev"], [
    ("diffusion_models", "Flux2/flux2_dev_fp8mixed.safetensors", F2, "split_files/diffusion_models/flux2_dev_fp8mixed.safetensors", False, "FLUX.2 dev (fp8 mixed)"),
    ("text_encoders", "Mistral/mistral_3_small_flux2_fp8.safetensors", F2, "split_files/text_encoders/mistral_3_small_flux2_fp8.safetensors", False, "Mistral 3 Small (fp8)"),
    ("vae", "Flux2/flux2-vae.safetensors", F2, "split_files/vae/flux2-vae.safetensors", False, "FLUX.2 VAE"),
])
HD = "Comfy-Org/HiDream"
pacote("hidream", "HiDream I1 Fast", "imagem",
       "HiDream I1 Fast (17B, 16 steps): strong prompt following. MIT license.", 16, ["image HiDream I1"], [
    ("diffusion_models", "HiDream/hidream_i1_fast_fp8.safetensors", HD, "split_files/diffusion_models/hidream_i1_fast_fp8.safetensors", False, "HiDream I1 Fast (fp8)"),
    ("text_encoders", "HiDream/clip_l_hidream.safetensors", HD, "split_files/text_encoders/clip_l_hidream.safetensors", False, "CLIP-L (HiDream)"),
    ("text_encoders", "HiDream/clip_g_hidream.safetensors", HD, "split_files/text_encoders/clip_g_hidream.safetensors", False, "CLIP-G (HiDream)"),
    ("text_encoders", "HiDream/llama_3.1_8b_instruct_fp8_scaled.safetensors", HD, "split_files/text_encoders/llama_3.1_8b_instruct_fp8_scaled.safetensors", False, "Llama 3.1 8B (fp8)"),
    T5_FP8, AE_Z,
])
pacote("chroma", "Chroma1 HD", "imagem",
       "Chroma1 HD: an open FLUX-based model (Apache 2.0), trained to follow any style.", 12, ["image Chroma"], [
    ("diffusion_models", "Chroma/Chroma1-HD-fp8mixed.safetensors", "Comfy-Org/Chroma1-HD", "split_files/diffusion_models/Chroma1-HD-fp8mixed.safetensors", False, "Chroma1 HD (fp8 mixed)"),
    T5_FP8, AE_Z,
])
pacote("sd35l", "SD 3.5 Large", "imagem",
       "Stability's SD 3.5 Large (8B, fp8 all-in-one with text encoders).", 12, ["image SD 3.5 Large"], [
    ("checkpoints", "SD35/sd3.5_large_fp8_scaled.safetensors", "Comfy-Org/stable-diffusion-3.5", "sd3.5_large_fp8_scaled.safetensors", False, "SD 3.5 Large (fp8)"),
])
pacote("kandinsky5i", "Kandinsky 5 Image", "imagem",
       "Kandinsky 5.0 Lite for images (Apache 2.0).", 12, ["image Kandinsky 5"], [
    ("diffusion_models", "Kandinsky5/kandinsky5lite_t2i.safetensors", "kandinskylab/Kandinsky-5.0-T2I-Lite", "model/kandinsky5lite_t2i.safetensors", False, "Kandinsky 5 Lite T2I"),
    ("text_encoders", "Qwen/qwen_2.5_vl_7b_fp8_scaled.safetensors", "Comfy-Org/Hunyuan-Video-1.5", "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors", False, "Qwen2.5-VL 7B (fp8)"),
    CLIP_L, AE_Z,
])

# ---- Modelos leves (placas de 4 a 8 GB) ----
pacote("flux1s", "FLUX.1 schnell", "imagem",
       "Light FLUX: good images in 4 steps. One all-in-one file (fp8).", 8, ["image FLUX.1 schnell"], [
    ("checkpoints", "Flux1/flux1-schnell-fp8.safetensors", "Comfy-Org/Flux-1-Schnell", "flux1-schnell-fp8.safetensors", False, "FLUX.1 schnell (fp8, all-in-one)"),
])
pacote("sd35m", "SD 3.5 Medium", "imagem",
       "Stability's mid-size model, good with text in images. One all-in-one file.", 8, ["image SD 3.5 Medium"], [
    ("checkpoints", "SD35/sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors", "Comfy-Org/stable-diffusion-3.5", "sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors", False, "SD 3.5 Medium (with text encoders)"),
])
pacote("sdxl", "SDXL (RealVisXL 5)", "imagem",
       "The classic SDXL, photoreal fine-tune. Runs on 6-8 GB cards.", 6, ["image SDXL"], [
    ("checkpoints", "SDXL/RealVisXL_V5.0_fp16.safetensors", "SG161222/RealVisXL_V5.0", "RealVisXL_V5.0_fp16.safetensors", False, "RealVisXL V5 (fp16)"),
])
pacote("sd15", "SD 1.5 (DreamShaper 8)", "imagem",
       "The lightest image model: runs on 4 GB cards, 512 px images.", 4, ["image SD 1.5"], [
    ("checkpoints", "SD15/DreamShaper_8_pruned.safetensors", "Lykon/DreamShaper", "DreamShaper_8_pruned.safetensors", False, "DreamShaper 8"),
])
pacote("ltxv2b", "LTX-Video 2B", "video",
       "Light LTX (0.9.8 distilled): fast text/image-to-video on 6-8 GB cards, up to 10 s.", 6, ["video LTX-Video 2B"], [
    ("checkpoints", "LTXV/ltxv-2b-0.9.8-distilled.safetensors", "Lightricks/LTX-Video", "ltxv-2b-0.9.8-distilled.safetensors", False, "LTX-Video 2B 0.9.8 distilled"),
    ("text_encoders", "T5/t5xxl_fp8_e4m3fn_scaled.safetensors", "comfyanonymous/flux_text_encoders", "t5xxl_fp8_e4m3fn_scaled.safetensors", False, "T5-XXL (fp8)"),
])
pacote("wan22_5b", "Wan 2.2 5B", "video",
       "Wan 2.2 TI2V 5B: text/image-to-video at 720p, 5 s. Slower, good quality.", 8, ["video Wan 2.2 5B"], [
    ("diffusion_models", "Wan22/wan2.2_ti2v_5B_fp16.safetensors", "Comfy-Org/Wan-2.2", "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors", False, "Wan 2.2 TI2V 5B (fp16)"),
    ("vae", "Wan22/wan2.2_vae.safetensors", "Comfy-Org/Wan-2.2", "split_files/vae/wan2.2_vae.safetensors", False, "Wan 2.2 VAE"),
    ("text_encoders", "Wan/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "Comfy-Org/Wan-2.1", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", False, "UMT5-XXL (fp8)"),
])
pacote("wan21_13b", "Wan 2.1 1.3B", "video",
       "The lightest Wan: text-to-video at 480p, 5 s.", 8, ["video Wan 2.1 1.3B"], [
    ("diffusion_models", "Wan21/wan2.1_t2v_1.3B_fp16.safetensors", "Comfy-Org/Wan-2.1", "split_files/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors", False, "Wan 2.1 T2V 1.3B (fp16)"),
    ("vae", "Wan21/wan_2.1_vae.safetensors", "Comfy-Org/Wan-2.1", "split_files/vae/wan_2.1_vae.safetensors", False, "Wan 2.1 VAE"),
    ("text_encoders", "Wan/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "Comfy-Org/Wan-2.1", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", False, "UMT5-XXL (fp8)"),
])


def api(caminho: str):
    for tentativa in range(4):
        try:
            with urllib.request.urlopen("https://huggingface.co/api/" + caminho, timeout=60, context=CTX) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5 * (tentativa + 1))
                continue
            raise
    raise RuntimeError(caminho)


_repos = {}


def repo(r: str) -> dict:
    if r not in _repos:
        info = api(f"models/{r}")
        arvore = api(f"models/{r}/tree/main?recursive=true")
        lic = next((t.split(":", 1)[1] for t in info.get("tags", []) if t.startswith("license:")), "unknown")
        _repos[r] = {"licenca": lic, "gated": bool(info.get("gated")),
                     "arquivos": {f["path"]: f.get("size") for f in arvore if f.get("type") == "file"}}
    return _repos[r]


def main():
    saida, problemas = [], []
    for p in P.values():
        arquivos = []
        for pasta, rel, rp, caminho, opcional, rotulo in p.pop("_arquivos"):
            sub, _, nome = rel.rpartition("/")
            a = {"arquivo": nome, "pasta": pasta, "subpasta": sub, "repo": rp, "caminho": caminho,
                 "opcional": opcional, "rotulo": rotulo}
            if rp == DERIVADO:
                d = DERIVADOS[rel]
                a.update(repo=None, caminho=None, tamanho=d["tamanho"], licenca="derived", requer_aceite=False,
                         derivado={"de": d["de"], "prefixos": d["prefixos"]})
            elif rp:
                info = repo(rp)
                if caminho not in info["arquivos"]:
                    problemas.append(f"{rp}: nao tem {caminho}")
                    continue
                a.update(tamanho=info["arquivos"][caminho], licenca=info["licenca"], requer_aceite=info["gated"])
            else:
                a.update(tamanho=0, licenca="unknown", requer_aceite=False, sem_origem=True)
            arquivos.append(a)
        licencas = sorted({a["licenca"] for a in arquivos if a["repo"]})
        p["licenca"] = {"nome": ", ".join(licencas), "url": f"https://huggingface.co/{next(a['repo'] for a in arquivos if a['repo'])}"}
        p["arquivos"] = arquivos
        saida.append(p)
        print(f"{p['id']:12} {len(arquivos):3} arquivos  {sum(a['tamanho'] for a in arquivos)/1e9:6.1f} GB  {p['licenca']['nome']}")
    destino = RAIZ / "catalogo" / "pacotes.json"
    destino.write_text(json.dumps({"versao": 2, "pacotes": saida}, ensure_ascii=False, indent=1), encoding="utf-8")
    if problemas:
        print("PROBLEMAS:", *problemas, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
