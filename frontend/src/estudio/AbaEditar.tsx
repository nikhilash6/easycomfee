import type React from 'react'
import { useContext, useEffect, useRef, useState } from 'react'
import { MotorCtx, AvisoInstalar, useFaltaInstalar } from './motor'
import { api, urlImagem, type Referencia } from '../api'
import { pegarParaEditar, referenciaDe, arquivos, BotaoGerar, CartaoTarefa, Chips, SlotImagem, mensagem, useCusto, useTarefas, MAX_PROMPT, TituloPagina } from './comum'
import { ThenNow, abrirVisualizador } from './Visualizador'

// Edit Studio: as ferramentas de edicao herdadas do Editor de Imagens. Cada cartao e
// um modo que o backend ja monta (app.py montar(): reluz, luzref, angulo, anygles,
// cabeca, personagem, folha, controle, recorte). A ordem das imagens e a do backend.

type Ferramenta = {
  id: string; nome: string; frase: string; grupo: string
  imagens: { rotulo: string; opcional?: boolean }[]
  texto?: 'opcional' | 'obrigatorio'; dica: string
  pacote?: string; api?: boolean
}

const FERRAMENTAS: Ferramenta[] = [
  { id: 'reluz', grupo: 'Light', nome: 'Relight', frase: 'Move the light in your photo: direction, height and color.',
    imagens: [{ rotulo: 'Photo' }, { rotulo: 'Light from', opcional: true }], texto: 'opcional', pacote: 'Qwen Image Edit 2511',
    dica: 'Pick where the light comes from. The people and things in the photo stay the same.' },
  { id: 'luzref', grupo: 'Light', nome: 'Copy the light', frase: 'Take the light and mood of one photo and put it on another.',
    imagens: [{ rotulo: 'Photo' }, { rotulo: 'Light from' }], texto: 'opcional', pacote: 'Qwen Image Edit 2511',
    dica: 'Image 1 changes. Image 2 is only the light example: its content does not show up in the result.' },
  { id: 'angulo', grupo: 'Angle', nome: 'Change the angle', frase: 'See the subject from another side, same scene and outfit.',
    imagens: [{ rotulo: 'Photo' }], texto: 'opcional', pacote: 'Qwen Image Edit 2511',
    dica: 'Works best when the subject is clearly visible. Each view is a new shot of the same moment.' },
  { id: 'anygles', grupo: 'Angle', nome: 'Orbit the person', frase: 'Turn the camera around the same person, keeping face and outfit.',
    imagens: [{ rotulo: 'Full-body photo' }], texto: 'opcional', pacote: 'Krea 2',
    dica: 'Use full-body photos: in a photo cut at the waist the model invents the legs and the floor.' },
  { id: 'cabeca', grupo: 'People', nome: 'Head swap', frase: 'Put the head from a second photo on the person in the scene.',
    imagens: [{ rotulo: 'Scene' }, { rotulo: 'Head' }], texto: 'opcional', pacote: 'Krea 2',
    dica: 'First the scene to edit, then a photo where the new head is clearly visible.' },
  { id: 'personagem', grupo: 'People', nome: 'Character swap', frase: 'Replace the person and keep the exact pose, gaze and light.',
    imagens: [{ rotulo: 'Pose' }, { rotulo: 'Person' }, { rotulo: 'Face', opcional: true }], texto: 'opcional', pacote: 'FLUX 2 Klein 9B',
    dica: 'Image 1 is the pose and stays fixed. Image 2 is who enters. Image 3 (optional) gives the exact face and outfit.' },
  { id: 'rosto', grupo: 'People', nome: 'Adjust the face', frase: 'Change the gaze, the smile and the head tilt. Nothing else moves.',
    imagens: [{ rotulo: 'Portrait' }],
    dica: 'Small moves look natural. The first run downloads the face models (a few hundred MB).' },
  { id: 'folha', grupo: 'People', nome: 'Character sheet', frase: 'One photo becomes four views: face, front, side and back.',
    imagens: [{ rotulo: 'Full-body photo' }], texto: 'opcional', pacote: 'Krea 2',
    dica: 'A clear full-body photo from the front. Whatever is hidden in it, the model invents in the other views.' },
  { id: 'area', grupo: 'Tools', nome: 'Edit an area', frase: 'Name a part of the photo and change only that part.',
    imagens: [{ rotulo: 'Photo' }], texto: 'obrigatorio', pacote: 'Qwen Image 2.1',
    dica: 'Write what to change ("the jacket", "the sky") and what it should become. Everything outside that area stays pixel for pixel.' },
  { id: 'controle', grupo: 'Tools', nome: 'Follow the structure', frase: 'A new picture that follows the edges, depth or pose of yours.',
    imagens: [{ rotulo: 'Structure' }], texto: 'obrigatorio', pacote: 'Z-Image Turbo',
    dica: 'The image gives only the structure; the prompt says what to draw on it.' },
  { id: 'ampliar', grupo: 'Tools', nome: 'Upscale', frase: 'Bigger and sharper: 1.5x to 4x on your GPU, up to 16x with Magnific.',
    imagens: [{ rotulo: 'Photo' }], texto: 'opcional', pacote: 'Upscalers',
    dica: 'SeedVR2 has the best texture and is the fastest. Creative invents new detail. Classic only enlarges what is there.' },
  { id: 'recorte', grupo: 'Tools', nome: 'Remove background', frase: 'Keep only the subject, on a transparent background.',
    imagens: [{ rotulo: 'Photo' }], api: true,
    dica: 'Runs on the Recraft API with your Comfy credits. Saves a PNG with transparency.' },
]

// Id do pacote no Config Models (motor.tsx PACOTE usa o id do menu: estes sao os modelos).
const MODELO_DO_PACOTE: Record<string, string> = {
  'Qwen Image 2.1': 'qwen21', 'TRELLIS 2 (3D)': 'trellis', 'Upscalers': 'upscale', 'Z-Image Turbo (creative upscale)': 'zimage',
  'Qwen Image Edit 2511': 'qwen_edit', 'Krea 2': 'krea', 'FLUX 3 Image Klein': 'flux3', 'FLUX 2 Klein 9B': 'klein', 'Z-Image Turbo': 'zimage',
}

// Relight pelo Magnific (presets.RELUZ metodos.nuvem): descreve a luz OU copia de uma foto.
const ESTILOS_LUZ = [
  { id: 'standard', rotulo: 'Standard' }, { id: 'darker_but_realistic', rotulo: 'Darker' }, { id: 'clean', rotulo: 'Clean' },
  { id: 'smooth', rotulo: 'Smooth' }, { id: 'brighter', rotulo: 'Brighter' }, { id: 'contrasted_n_hdr', rotulo: 'HDR' },
]
const VISTAS = [
  { id: 'tres_quartos_esq', rotulo: '¾ from the left' }, { id: 'tres_quartos_dir', rotulo: '¾ from the right' },
  { id: 'perfil', rotulo: 'Profile' }, { id: 'de_tras', rotulo: 'From behind' }, { id: 'contra_plongee', rotulo: 'From below' },
  { id: 'plongee', rotulo: 'From above' }, { id: 'aproximar', rotulo: 'Closer' }, { id: 'afastar', rotulo: 'Further' },
]
// Ajustar o rosto (presets.ROSTO, no ExpressionEditor do Advanced LivePortrait): faixa e passo do backend.
const ROSTO = [
  { grupo: 'Gaze', itens: [{ id: 'pupil_x', rotulo: 'Look left / right', min: -15, max: 15, passo: 0.5 }, { id: 'pupil_y', rotulo: 'Look up / down', min: -15, max: 15, passo: 0.5 }] },
  { grupo: 'Head', itens: [{ id: 'rotate_yaw', rotulo: 'Turn', min: -20, max: 20, passo: 0.5 }, { id: 'rotate_pitch', rotulo: 'Nod', min: -20, max: 20, passo: 0.5 }, { id: 'rotate_roll', rotulo: 'Tilt', min: -20, max: 20, passo: 0.5 }] },
  { grupo: 'Eyes', itens: [{ id: 'blink', rotulo: 'Eyes open', min: -20, max: 5, passo: 0.5 }, { id: 'wink', rotulo: 'Wink', min: 0, max: 25, passo: 0.5 }, { id: 'eyebrow', rotulo: 'Eyebrows', min: -10, max: 15, passo: 0.5 }] },
  { grupo: 'Mouth', itens: [{ id: 'smile', rotulo: 'Smile', min: -0.3, max: 1.3, passo: 0.05 }, { id: 'aaa', rotulo: 'Open (aah)', min: -30, max: 120, passo: 1 }, { id: 'eee', rotulo: 'Wide (eee)', min: -20, max: 15, passo: 0.5 }, { id: 'woo', rotulo: 'Pout (ooo)', min: -20, max: 15, passo: 0.5 }] },
]

// Orbit: motores que giram por frase (o Flux 3 local e os de API), mais o Krea com o boneco 3D.
const MOTORES_ORBITA = [
  { id: 'orbita3d', rotulo: '3D model · exact angle, local' }, { id: 'flux3ref', rotulo: 'Flux 3 · local, free' }, { id: 'nano-2', rotulo: 'Nano Banana 2 · API' },
  { id: 'seedream5', rotulo: 'Seedream 5 Pro · API' }, { id: 'sunburst', rotulo: 'GPT Image 2.5 Sunburst · API' },
  { id: 'krea', rotulo: 'Krea Anygles · 3D body' },
]

const RESOLUCOES_ORBITA: Record<string, string[]> = {
  'orbita3d': ['1K'], 'flux3ref': ['1K', '2K'], 'nano-2': ['1K', '2K', '4K'], 'seedream5': ['1K', '2K'], 'sunburst': ['1K', '2K', '4K'],
}

/** A frase do giro, pronta para a etapa final (o usuario nao digita nada). Os modelos de
 *  edicao giram por palavras, em degraus: leve, 3/4, perfil, 3/4 de costas, costas.
 *  Testado em 31/10/2026: com esta forma o Flux 3 e o Nano Banana giram e mantem pessoa e cenario. */
function fraseOrbita(giro: number, altura: string, extra = '') {
  // O lado da frase e o oposto do sinal: com giro positivo o boneco mostra a pessoa de frente
  // para a esquerda, e "left side" e o que faz o Flux igualar o boneco (teste de 31/10/2026).
  const g = Math.abs(giro), lado = giro >= 0 ? 'left' : 'right'
  const vista = g < 8 ? 'from the same angle as the photo'
    : g < 30 ? `with the camera moved about ${g} degrees to the ${lado} around the person, a slight turn`
    : g < 68 ? `seen from a three-quarter view, the camera ${g} degrees to the ${lado} around the person`
    : g < 113 ? `seen from the ${lado} side, in profile`
    : g < 158 ? `seen from behind and to the ${lado}, a three-quarter back view`
    : 'seen from behind'
  const alto = altura === 'baixo' ? ', from a low camera looking up' : altura === 'alto' ? ', from a high camera looking down' : ''
  const frase = `Show the same person from @image1, in the same place, ${vista}${alto}. `
    + 'Keep the face, hair, body, clothes, the background and the light exactly the same. Only the camera angle changes.'
  return extra.trim() ? `${frase} ${extra.trim()}` : frase
}

// Upscale (presets.AMPLIAR): metodos, escalas de cada um e os ajustes prontos do Criativo.
const METODOS_AMPLIAR = [
  { id: 'seedvr', rotulo: 'SeedVR2 · best texture' }, { id: 'criativo', rotulo: 'Creative · invents detail' },
  { id: 'classico', rotulo: 'Classic · no new detail' }, { id: 'magnific', rotulo: 'Magnific · API' }, { id: 'topaz', rotulo: 'Topaz · API' },
]
const ESCALAS_AMPLIAR: Record<string, number[]> = {
  seedvr: [1.5, 2, 3, 4], criativo: [1.5, 2, 3, 4], classico: [1.5, 2, 3, 4], magnific: [2, 4, 8, 16], topaz: [2, 3, 4],
}
const OTIMIZACOES = [
  { id: 'geral', rotulo: 'General' }, { id: 'retrato_suave', rotulo: 'Soft portrait' }, { id: 'pele_detalhe', rotulo: 'Skin detail' },
  { id: 'paisagem', rotulo: 'Landscape' }, { id: 'produto', rotulo: 'Product' }, { id: 'ilustracao', rotulo: 'Illustration' },
  { id: 'tipografia', rotulo: 'Lettering' },
]

const CONTROLES = [{ id: 'contorno', rotulo: 'Edges' }, { id: 'profundidade', rotulo: 'Depth' }, { id: 'pose', rotulo: 'Pose' }, { id: 'linhas', rotulo: 'Lines' }]

/** Direcao da luz num circulo, visto de frente: o ponto e de onde a luz vem (esquerda,
 *  direita, alto, baixo). x vira o azimute (-90 a 90), y a elevacao (-60 a 75). */
function LuzPad({ azimute, elevacao, aoMudar }: { azimute: number; elevacao: number; aoMudar: (az: number, el: number) => void }) {
  const caixa = useRef<HTMLDivElement>(null)
  const atras = Math.abs(azimute) > 90
  const x = atras ? 0 : Math.max(-1, Math.min(1, azimute / 90)), y = -Math.max(-1, Math.min(1, elevacao / 75))
  const mover = (e: React.PointerEvent) => {
    const r = caixa.current!.getBoundingClientRect()
    let nx = ((e.clientX - r.left) / r.width) * 2 - 1, ny = ((e.clientY - r.top) / r.height) * 2 - 1
    const d = Math.hypot(nx, ny); if (d > 1) { nx /= d; ny /= d }
    aoMudar(Math.round(nx * 90), Math.round(-ny * 75))
  }
  return (
    <div className="hf-luz-pad-area">
      <span data-lado="top">Top</span><span data-lado="left">Left</span><span data-lado="right">Right</span><span data-lado="bottom">Bottom</span>
      <div ref={caixa} className="hf-luz-pad" role="slider" aria-label="Light direction" aria-valuetext={`${azimute} degrees across, ${elevacao} degrees up`}
        tabIndex={0} onPointerDown={(e) => { (e.target as HTMLElement).setPointerCapture?.(e.pointerId); mover(e) }}
        onPointerMove={(e) => { if (e.buttons) mover(e) }}
        onKeyDown={(e) => {
          const p = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, 10], ArrowDown: [0, -10] }[e.key]
          if (p) { e.preventDefault(); aoMudar(Math.max(-90, Math.min(90, azimute + p[0])), Math.max(-75, Math.min(75, elevacao + p[1]))) }
        }}>
        <i className="hf-luz-ponto" style={{ left: `${50 + x * 50}%`, top: `${50 + y * 50}%`, opacity: atras ? 0.4 : 1 }} />
      </div>
    </div>
  )
}

export default function AbaEditar() {
  const { naNuvem } = useContext(MotorCtx)
  const tarefas = useTarefas()
  const faltaInstalar = useFaltaInstalar()
  // Abre na primeira ferramenta (Relight), como no layout: sempre ha controles a direita.
  const [ferramenta, setFerramenta] = useState<Ferramenta | null>(FERRAMENTAS[0])
  const [ultimoId, setUltimoId] = useState<string | null>(null)
  const [verResultado, setVerResultado] = useState<{ nome: string; subpasta: string } | null>(null)
  const [zoom, setZoom] = useState(100)
  const [imgs, setImgs] = useState<(Referencia | null)[]>([])
  const [texto, setTexto] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  // Reiluminar
  const [azimute, setAzimute] = useState(-45)
  const [elevacao, setElevacao] = useState(25)
  const [temperatura, setTemperatura] = useState('neutra')
  const [intensidade, setIntensidade] = useState(1.0)
  const [tempLuz, setTempLuz] = useState(0)   // -50 fria ... +50 quente (o modelo recebe fria/neutra/quente)
  const [metodoLuz, setMetodoLuz] = useState('direcional')   // direcional (Qwen, local) ou nuvem (Magnific)
  const [estiloLuz, setEstiloLuz] = useState('standard')
  const [mudarFundo, setMudarFundo] = useState(false)
  // Change the angle: mover a camera (Qwen) ou girar o personagem (Klein, mantem o enquadramento)
  const [metodoAngulo, setMetodoAngulo] = useState('camera')
  // Angulo / orbita
  const [vista, setVista] = useState('tres_quartos_esq')
  const [yaw, setYaw] = useState(45)
  const [altura, setAltura] = useState(0)
  const [distancia, setDistancia] = useState(1.0)
  // Previa do Orbit: a malha do corpo vista da camera nova (o guia que o modelo recebe).
  const [previa, setPrevia] = useState<{ url: string; chave: string } | null>(null)
  const [previando, setPrevendo] = useState(false)
  // Quantos graus a pessoa ja esta virada na foto (medido pelo boneco 3D); null = ainda nao.
  const [rotacao, setRotacao] = useState<number | null>(null)
  // O giro anda de 15 em 15 a partir de uma base: 0, ou a correcao do "Face the camera".
  const [base, setBase] = useState(0)
  // Motor do Orbit: um modelo de edicao que gira por FRASE (Flux 3 local ou API), montada
  // sozinha a partir do giro; ou o Krea Anygles, que segue o boneco 3D.
  const [motorOrbita, setMotorOrbita] = useState('orbita3d')
  const [giro, setGiro] = useState(45)            // graus a partir da pose da foto
  const [alturaFrase, setAlturaFrase] = useState('olho')
  const [formato, setFormato] = useState('16:9')  // proporcao da foto, para a imagem nova sair igual
  const [resolucao, setResolucao] = useState('1K')
  // Personagem e controle
  const [prioridade, setPrioridade] = useState('rapido')
  const [tipoControle, setTipoControle] = useState('contorno')
  const [rosto, setRosto] = useState<Record<string, number>>({})
  // Upscale
  const [metodoAmpliar, setMetodoAmpliar] = useState('seedvr')
  const [escalaAmpliar, setEscalaAmpliar] = useState(2)
  const [otimizacao, setOtimizacao] = useState('geral')
  const [acabamento, setAcabamento] = useState({ detalhe: 0, microcontraste: 0, granulacao: 0 })
  const [criatividadeMag, setCriatividadeMag] = useState(0)
  // Edit an area: o que recortar (SAM 3 acha pelo nome) e quanto a borda abre
  const [alvoArea, setAlvoArea] = useState('')
  const [bordaArea, setBordaArea] = useState(12)

  // Imagem mandada da galeria ("Edit this image"): fica esperando a ferramenta ser escolhida.
  const [esperando, setEsperando] = useState<Referencia | null>(null)
  useEffect(() => {
    const pegar = () => { const e = pegarParaEditar(); if (e) referenciaDe(e).then(setEsperando).catch(() => {}) }
    pegar()
    window.addEventListener('easycomfee:editar', pegar)
    return () => window.removeEventListener('easycomfee:editar', pegar)
  }, [])
  const abrir = (f: Ferramenta) => {
    setFerramenta(f); setErro(null); setPrevia(null); setUltimoId(null); setVerResultado(null); setZoom(100)
    setImgs(esperando && f.imagens.length ? [esperando] : [])
  }
  const f = ferramenta
  const com3d = f?.id === 'anygles' && motorOrbita === 'orbita3d'
  const comFrase = f?.id === 'anygles' && motorOrbita !== 'krea' && !com3d
  const luzApi = f?.id === 'reluz' && metodoLuz === 'nuvem'
  const ampliarApi = f?.id === 'ampliar' && (metodoAmpliar === 'magnific' || metodoAmpliar === 'topaz')
  const escalasOk = ESCALAS_AMPLIAR[metodoAmpliar] ?? [2]
  const escalaOk = escalasOk.includes(escalaAmpliar) ? escalaAmpliar : escalasOk[0]
  const motorApi = comFrase && motorOrbita !== 'flux3ref'
  const pacoteAtual = com3d ? (faltaInstalar('trellis') ? 'TRELLIS 2 (3D)' : 'Qwen Image Edit 2511')
    : comFrase ? (motorApi ? undefined : 'FLUX 3 Image Klein')
    : luzApi ? undefined
    : f?.id === 'angulo' && metodoAngulo === 'personagem' ? 'FLUX 2 Klein 9B'
    : f?.id === 'ampliar' ? (ampliarApi ? undefined : metodoAmpliar === 'criativo' ? 'Z-Image Turbo (creative upscale)' : 'Upscalers')
    : f?.pacote
  const modeloPacote = pacoteAtual ? MODELO_DO_PACOTE[pacoteAtual] : undefined
  const naoInstalado = !!f && !f.api && !!modeloPacote && faltaInstalar(modeloPacote)
  const soLocal = !!f && !f.api && !motorApi && !ampliarApi && !luzApi && naNuvem
  const nomes = imgs.filter((r): r is Referencia => !!r).map((r) => r.nome)
  const faltaImagem = !!f && f.imagens.some((s, i) => !s.opcional && !imgs[i])
  const faltaTexto = (f?.texto === 'obrigatorio' && !texto.trim()) || (f?.id === 'area' && !alvoArea.trim())
    // Magnific: precisa descrever a luz OU mandar a foto de onde copiar
    || (f?.id === 'reluz' && metodoLuz === 'nuvem' && !texto.trim() && !imgs[1])

  // 1K/2K/4K por motor: cada API tem as suas (presets.NUVEM resolucoes); o Flux local vai
  // ate 2K (escala 1,5: ~2,3 MP), porque 4K nao cabe numa placa de 16 GB.
  const resDoMotor = RESOLUCOES_ORBITA[motorOrbita] ?? ['1K']
  const resOk = resDoMotor.includes(resolucao) ? resolucao : resDoMotor[resDoMotor.length - 1]
  const ALT_GRAUS: Record<string, number> = { baixo: -30, olho: 0, alto: 35 }
  const pedido = f ? {
    modelo: com3d ? 'orbita3d' : comFrase ? motorOrbita : f.id === 'area' ? 'qwen21edit' : f.id,
    // Edit an area: a instrucao sai pronta ("Change the jacket into a red leather jacket"); o usuario so diz o que e o que vira.
    prompt: comFrase ? fraseOrbita(giro, alturaFrase, texto)
      : f.id === 'area' ? `Change ${alvoArea.trim()} in @image1 into ${texto.trim()}. Keep everything else exactly the same.` : texto,
    proporcao: comFrase || com3d ? formato : '1:1', lote: 1, referencias: f.id === 'reluz' && !luzApi ? nomes.slice(0, 1) : nomes,
    ...(motorApi ? { resolucao_nuvem: resOk } : {}),
    ...(comFrase && !motorApi ? { escala: resOk === '2K' ? 1.5 : 1.0 } : {}),
    ...(f.id === 'reluz' ? (luzApi ? { metodo_luz: 'nuvem', estilo_luz: estiloLuz, mudar_fundo_luz: mudarFundo }
      : { metodo_luz: 'direcional', azimute, elevacao, temperatura, intensidade }) : {}),
    ...(f.id === 'angulo' ? { metodo_angulo: metodoAngulo, vista } : {}),
    ...(f.id === 'anygles' && !comFrase && !com3d ? { yaw, elevation: altura, distance: distancia } : {}),
    ...(com3d ? { giro_3d: giro, altura_3d: ALT_GRAUS[alturaFrase] } : {}),
    ...(f.id === 'personagem' ? { prioridade } : {}),
    ...(f.id === 'controle' ? { tipo_controle: tipoControle } : {}),
    ...(f.id === 'rosto' ? { rosto } : {}),
    ...(f.id === 'area' ? { mascara_alvo: alvoArea, mascara_expandir: bordaArea, mascara_suavizar: Math.max(6, bordaArea) } : {}),
    ...(f.id === 'ampliar' ? { metodo_ampliar: metodoAmpliar, escala_ampliar: escalaOk, otimizacao, ...acabamento,
      magnific_criatividade: criatividadeMag } : {}),
  } : null
  const custo = useCusto(pedido && !faltaImagem ? pedido : null)

  const gerar = async () => {
    if (!pedido) return
    setErro(null)
    try {
      const { id } = await api.gerar(pedido as Parameters<typeof api.gerar>[0])
      setUltimoId(id); setVerResultado(null)  // o resultado novo vai para o antes e depois
    } catch (e) { setErro(mensagem(e)) }
  }

  // A previa e sempre o boneco 3D do Krea: na pose da foto (rotacao medida) mais o giro.
  const giroBoneco = ((((rotacao ?? 0) + giro) + 540) % 360) - 180
  const prev = comFrase ? { yaw: Math.round(giroBoneco * 10) / 10, elevation: ALT_GRAUS[alturaFrase], distance: 1.0 }
    : { yaw, elevation: altura, distance: distancia }
  const pedidoPrevia = f?.id !== 'anygles' ? null
    : com3d ? { modelo: 'orbita3d', prompt: '', proporcao: formato, lote: 1, referencias: nomes, giro_3d: giro, altura_3d: ALT_GRAUS[alturaFrase] }
    : { modelo: 'anygles', prompt: '', proporcao: '1:1', lote: 1, referencias: nomes, ...prev }
  const chaveAngulo = com3d ? `3d|${nomes[0]}|${giro}|${alturaFrase}|${formato}` : `${nomes[0]}|${prev.yaw}|${prev.elevation}|${prev.distance}`
  // Previa automatica: ~1 s depois do ultimo ajuste. Uma por vez na placa; se o ajuste
  // mudou enquanto uma rodava, a seguinte sai com os valores novos.
  const ultimo = useRef({ chave: '', pedido: null as typeof pedidoPrevia })
  ultimo.current = { chave: chaveAngulo, pedido: pedidoPrevia }
  const rodando = useRef(false)
  const previsualizar = async () => {
    if (rodando.current) return
    rodando.current = true; setPrevendo(true); setErro(null)
    try {
      for (;;) {
        const { chave, pedido: ped } = ultimo.current
        if (!ped) break
        const { id } = await api.gerar({ ...ped, previa_angulo: true, teste: true, rotulo_teste: 'Orbit preview' } as unknown as Parameters<typeof api.gerar>[0])
        for (;;) {
          await new Promise((r) => setTimeout(r, 1000))
          const t = (await api.tarefas()).find((x) => x.id === id)
          if (t?.estado === 'erro') throw new Error(t.erro || 'The preview failed.')
          if (t?.estado === 'pronto') { setPrevia({ url: urlImagem(arquivos(t)[0]), chave }); break }
        }
        if (ultimo.current.chave === chave) break
      }
    } catch (e) { setErro(mensagem(e)) } finally { rodando.current = false; setPrevendo(false) }
  }
  useEffect(() => {
    const url = imgs[0]?.url
    if (!url) return
    const im = new Image()
    im.onload = () => {
      const r = im.naturalWidth / im.naturalHeight
      const opcoes: [string, number][] = [['1:1', 1], ['4:5', 0.8], ['2:3', 2 / 3], ['9:16', 9 / 16], ['3:2', 1.5], ['16:9', 16 / 9]]
      setFormato(opcoes.reduce((m, o) => (Math.abs(Math.log(o[1] / r)) < Math.abs(Math.log(m[1] / r)) ? o : m))[0])
    }
    im.src = url
  }, [imgs[0]?.url])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setRotacao(null); setBase(0)
    if (f?.id !== 'anygles' || !nomes[0]) return
    fetch('/api/orbita/rotacao', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ referencia: nomes[0] }) })
      .then((r) => (r.ok ? r.json() : null)).then((d) => d && setRotacao(d.graus)).catch(() => {})
  }, [f?.id, nomes[0]])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (f?.id !== 'anygles' || !nomes[0]) return
    const t = setTimeout(previsualizar, 900)
    return () => clearTimeout(t)
  }, [f?.id, chaveAngulo, motorOrbita])  // eslint-disable-line react-hooks/exhaustive-deps

  const ids = new Set(FERRAMENTAS.map((x) => x.id))
  // O Orbit tambem gera por Flux 3 e por APIs (outro "modelo" na tarefa): reconhece pela frase dele.
  const doOrbit = (p: string) => p.startsWith('Show the same person from')
  const minhas = tarefas.filter((t) => (ids.has(t.modelo) || t.modelo === 'qwen21edit' || doOrbit(t.prompt)) && !t.teste)
  const grupos = [...new Set(FERRAMENTAS.map((x) => x.grupo))]

  // Layout de 31/10/2026: ferramentas a esquerda, a foto no centro (antes e depois com
  // cortina, ou foto e previa no Orbit), os controles da ferramenta e o Apply a direita.
  const resultadoTarefa = ultimoId ? minhas.find((t) => t.id === ultimoId && t.estado === 'pronto') : undefined
  const depois = verResultado ?? (resultadoTarefa ? arquivos(resultadoTarefa)[0] : undefined)
  const recentes = minhas.flatMap((t) => (t.estado === 'pronto' ? arquivos(t) : []))
  const emCurso = minhas.filter((t) => t.estado !== 'pronto' && t.estado !== 'erro')

  return (
    <div className="hf-aba hf-img hf-edt">
      <TituloPagina antes="Edit your" destaque="photo" sub="Change the light or the angle, swap a head or a character, upscale or cut out." />
      <div className="hf-edt-grade">
        <aside className="hf-img-col hf-edt-esq" aria-label="Edit tools">
          <div>
            <h2 className="hf-edt-titulo">Edit tools</h2>
            <p className="hf-dica">Change the light, angle, swap a head or a character, make a character sheet. Pick a tool and edit your photo.</p>
          </div>
          {esperando && (
            <div className="hf-editar-esperando">
              <img src={esperando.url} alt="" />
              <span>Image ready. <b>Pick a tool</b> and it goes in.</span>
              <button type="button" className="hf-ajustes-limpar" onClick={() => setEsperando(null)}>Clear</button>
            </div>
          )}
          {grupos.map((g) => (
            <section key={g} className="hf-editar-grupo" data-grupo={g}>
              <span className="hf-editar-grupo-nome">{g}</span>
              <div className="hf-edt-cartoes">
                {FERRAMENTAS.filter((x) => x.grupo === g).map((x) => (
                  <button key={x.id} className="hf-app hf-ferramenta" data-ativo={f?.id === x.id} aria-pressed={f?.id === x.id} onClick={() => abrir(x)}>
                    <img src={`/editar/${x.id}.gif?v=3`} alt="" loading="lazy"
                      onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = 'hidden' }} />
                    <b>{x.nome}{x.api && <small> · API</small>}</b>
                    <span>{x.frase}</span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </aside>

        <section className="hf-edt-centro">
          {f?.id === 'anygles' ? (
            <div className="hf-orbita-par">
              <div className="hf-orbita-caixa">
                <span className="hf-orbita-caixa-nome">Your photo</span>
                <SlotImagem rotulo="Full-body photo" valor={imgs[0] ?? null} aoMudar={(r) => setImgs([r])} />
              </div>
              <div className="hf-orbita-caixa" data-velha={!!previa && previa.chave !== chaveAngulo}>
                <span className="hf-orbita-caixa-nome">{com3d ? 'New angle · 3D model' : 'New angle · body preview'}</span>
                {previa ? <img src={previa.url} alt="The body seen from the new camera" />
                  : <span className="hf-orbita-vazio">{nomes[0] ? (com3d ? 'Building the 3D model… (about 40 s the first time)' : 'Preparing the preview…') : 'Add a photo to see the new angle here'}</span>}
                {previando && <span className="hf-orbita-selo">Updating…</span>}
              </div>
            </div>
          ) : (
            <div className="hf-edt-palco">
              <div className="hf-edt-zoom" style={{ transform: `scale(${zoom / 100})` }}>
                {imgs[0] && depois ? <ThenNow antes={imgs[0].url} depois={urlImagem(depois)} modo="cortina" rotulos={['Before', 'After']} />
                  : depois ? <img src={urlImagem(depois)} alt="Result" />
                  : imgs[0] ? <img src={imgs[0].url} alt="Your photo" />
                  : <div className="hf-img-vazio"><b>{f ? 'Drop a photo to start' : 'Pick a tool'}</b><span>{f ? 'Use the box on the right, or drag one from a gallery.' : 'Choose an edit on the left.'}</span></div>}
              </div>
              {emCurso[0] && <div className="hf-img-andamento"><CartaoTarefa t={emCurso[0]} /></div>}
            </div>
          )}
          {f?.id !== 'anygles' && (
            <div className="hf-edt-barra" role="toolbar" aria-label="View">
              <button type="button" onClick={() => setZoom((z) => Math.max(50, z - 25))} aria-label="Zoom out">−</button>
              <span>{zoom}%</span>
              <button type="button" onClick={() => setZoom((z) => Math.min(300, z + 25))} aria-label="Zoom in">+</button>
              <button type="button" onClick={() => setZoom(100)} title="Fit">⤢</button>
              {depois && <button type="button" onClick={() => abrirVisualizador(depois)} title="Open the result full screen">⛶</button>}
            </div>
          )}
        </section>

        <aside className="hf-img-col hf-img-dir hf-edt-dir" aria-label="Tool settings">
          {f ? (<>
            <div className="hf-edt-cabeca">
              <img src={`/editar/${f.id}.webp`} alt="" />
              <div><b>{f.nome}</b><span>{f.frase}</span></div>
            </div>
            {f.id !== 'anygles' && (
              <div className="hf-campo"><span>{f.imagens.length > 1 ? 'Images' : 'Photo'}</span>
                <div className="hf-slots">
            {f.imagens.map((s, i) => f.id === 'reluz' && i === 1 && !luzApi ? null : (
              <SlotImagem key={`${f.id}-${i}`} rotulo={s.rotulo + (s.opcional ? ' (opt.)' : '')} valor={imgs[i] ?? null}
                aoMudar={(r) => setImgs((a) => { const n = [...a]; n[i] = r; return n })} />
            ))}
          </div>
              </div>
            )}
          <p className="hf-dica">{com3d ? 'Works best with the whole person in the photo, clearly separated from the background.'
            : comFrase ? 'Any framing works. The prompt is written for you from the Turn and Height you pick.'
            : luzApi ? 'Describe the light below, or drop a photo in "Light from" to copy its light. US$ 0.11, runs on Comfy credits.'
            : f.id === 'angulo' && metodoAngulo === 'personagem' ? 'The body turns and the framing stays. Faster, and better for the view from above.'
            : f.dica}</p>
          {f.id === 'reluz' && (<>
            <div className="hf-linha-controles">
              <Chips rotulo="Method" opcoes={[{ id: 'direcional', rotulo: 'Directional · local' }, { id: 'nuvem', rotulo: 'Magnific · API' }]}
                valor={metodoLuz} aoMudar={setMetodoLuz} />
            </div>
            {metodoLuz === 'nuvem' ? (
              <div className="hf-linha-controles">
                <Chips rotulo="Style" opcoes={ESTILOS_LUZ} valor={estiloLuz} aoMudar={setEstiloLuz} />
                <div className="hf-campo"><span>Background</span>
                  <label className="hf-toggle"><input type="checkbox" checked={mudarFundo} onChange={(e) => setMudarFundo(e.target.checked)} /> Relight the background too</label>
                </div>
              </div>
            ) : (
              <div className="hf-luz">
                <div className="hf-campo"><span>Light direction</span>
                  <LuzPad azimute={azimute} elevacao={elevacao} aoMudar={(az, el) => { setAzimute(az); setElevacao(el) }} />
                </div>
                <div className="hf-campo"><span>Strength</span>
                  <div className="hf-luz-linha">
                    <input type="range" min={0} max={100} value={Math.round((intensidade - 0.1) / 1.4 * 100)} aria-label="Strength"
                      onChange={(e) => setIntensidade(Math.round((0.1 + Number(e.target.value) / 100 * 1.4) * 100) / 100)} className="hf-luz-forca" />
                    <b>{Math.round((intensidade - 0.1) / 1.4 * 100)}</b>
                  </div>
                </div>
                <div className="hf-campo"><span>Color temperature</span>
                  <div className="hf-luz-linha">
                    <input type="range" min={-50} max={50} value={tempLuz} aria-label="Color temperature" className="hf-luz-temp"
                      onChange={(e) => { const v = Number(e.target.value); setTempLuz(v); setTemperatura(v > 15 ? 'quente' : v < -15 ? 'fria' : 'neutra') }} />
                    <b>{tempLuz}</b>
                  </div>
                </div>
                <Chips rotulo="Light from behind" opcoes={[{ id: 0, rotulo: 'No' }, { id: 1, rotulo: 'Backlight' }]}
                  valor={Math.abs(azimute) > 90 ? 1 : 0} aoMudar={(v) => setAzimute(v ? 180 : 0)} />
              </div>
            )}
          </>)}
          {f.id === 'angulo' && (
            <div className="hf-linha-controles">
              <Chips rotulo="Method" opcoes={[{ id: 'camera', rotulo: 'Move the camera · Qwen' }, { id: 'personagem', rotulo: 'Turn the character · Klein' }]}
                valor={metodoAngulo} aoMudar={setMetodoAngulo} />
              <Chips rotulo="New view" opcoes={VISTAS} valor={vista} aoMudar={setVista} />
            </div>
          )}
          {f.id === 'anygles' && (<>
            <div className="hf-linha-controles">
              <label className="hf-campo"><span>Engine</span>
                <select className="hf-select" value={motorOrbita} aria-label="Engine" onChange={(e) => { setMotorOrbita(e.target.value); setPrevia(null) }}>
                  {MOTORES_ORBITA.map((m) => <option key={m.id} value={m.id}>{m.rotulo}</option>)}
                </select></label>
            </div>
            {comFrase || com3d ? (
              <div className="hf-orbita">
                <svg className="hf-orbita-mapa" viewBox="-60 -60 120 120" role="img" aria-label={`Camera ${Math.abs(giro)} degrees ${giro >= 0 ? 'right' : 'left'}`}>
                  {/* Visto de cima: a pessoa no centro; o ponto cinza e a camera da foto, o amarelo a nova. */}
                  <circle r="44" className="hf-orbita-trilho" />
                  <circle cx="0" cy={44} r="4" className="hf-orbita-original" />
                  <ellipse rx="9" ry="6" className="hf-orbita-pessoa" />
                  <path d="M0 6 L0 14" className="hf-orbita-frente" />
                  {(() => {
                    const a = (giro * Math.PI) / 180, x = Math.sin(a) * 44, y = Math.cos(a) * 44
                    return <g><line x1={x} y1={y} x2="0" y2="0" className="hf-orbita-mira" /><circle cx={x} cy={y} r={6} className="hf-orbita-camera" /></g>
                  })()}
                </svg>
                <div className="hf-orbita-controles">
                  <div className="hf-campo"><span>Turn</span>
                    <label className="hf-duracao"><span className="hf-valor">{giro > 0 ? `${giro}° right` : giro < 0 ? `${-giro}° left` : 'no turn'}</span>
                      <input type="range" min={-180} max={180} step={5} value={giro} onChange={(e) => setGiro(Number(e.target.value))} aria-label="Turn" /></label>
                  </div>
                  <Chips rotulo="Height" opcoes={[{ id: 'baixo', rotulo: 'Low' }, { id: 'olho', rotulo: 'Eye level' }, { id: 'alto', rotulo: 'High' }]}
                    valor={alturaFrase} aoMudar={setAlturaFrase} />
                  <Chips rotulo="Resolution" valor={resOk} aoMudar={setResolucao}
                    opcoes={['1K', '2K', '4K'].map((r) => ({ id: r, rotulo: r, desligado: !resDoMotor.includes(r),
                      dica: resDoMotor.includes(r) ? undefined : motorApi ? 'This model does not make this size' : '4K is only on the API models (it does not fit a 16 GB card)' }))} />
                </div>
              </div>
            ) : (
            <div className="hf-orbita">
              <svg className="hf-orbita-mapa" viewBox="-60 -60 120 120" role="img"
                aria-label={`Camera ${Math.abs(yaw)} degrees ${yaw >= 0 ? 'right' : 'left'}, ${altura} degrees up, distance ${distancia.toFixed(2)}`}>
                {/* Visto de cima: a pessoa no centro olhando para baixo (para a camera original). */}
                <circle r="44" className="hf-orbita-trilho" />
                <circle cx="0" cy={44} r="4" className="hf-orbita-original" />
                <ellipse rx="9" ry="6" className="hf-orbita-pessoa" />
                <path d="M0 6 L0 14" className="hf-orbita-frente" />
                {(() => {
                  const r = 30 + 14 * distancia, a = (yaw * Math.PI) / 180
                  const x = Math.sin(a) * r, y = Math.cos(a) * r
                  return <g>
                    <line x1={x} y1={y} x2="0" y2="0" className="hf-orbita-mira" />
                    <circle cx={x} cy={y} r={5 + altura / 20} className="hf-orbita-camera" />
                  </g>
                })()}
              </svg>
              <div className="hf-orbita-controles">
                <div className="hf-campo"><span>Turn</span>
                  <label className="hf-duracao"><span className="hf-valor">{yaw > 0 ? `${yaw}° right` : yaw < 0 ? `${-yaw}° left` : 'front'}</span>
                    <input type="range" min={-12} max={12} step={1} value={Math.round((yaw - base) / 15)} onChange={(e) => setYaw(Math.max(-180, Math.min(180, base + Number(e.target.value) * 15)))} aria-label="Turn" /></label>
                </div>
                {<>
                <div className="hf-campo"><span>Camera height</span>
                  <label className="hf-duracao"><span className="hf-valor">{altura > 0 ? `${altura}° above` : altura < 0 ? `${-altura}° below` : 'eye level'}</span>
                    <input type="range" min={-45} max={60} step={5} value={altura} onChange={(e) => setAltura(Number(e.target.value))} aria-label="Camera height" /></label>
                </div>
                <div className="hf-campo"><span>Distance</span>
                  <label className="hf-duracao"><span className="hf-valor">{distancia.toFixed(2)}×</span>
                    <input type="range" min={0.8} max={1.8} step={0.05} value={distancia} onChange={(e) => setDistancia(Number(e.target.value))} aria-label="Distance" /></label>
                </div>
                </>}
                {rotacao !== null && Math.abs(rotacao) >= 1 && (
                  <button type="button" className="hf-botao-sec hf-orbita-frente-btn" onClick={() => { setBase(Math.round(rotacao)); setYaw(Math.round(rotacao)) }}
                    title={`In the photo the body is already turned about ${Math.abs(Math.round(rotacao))}°. This sets Turn so the person faces the camera.`}>
                    ⟲ Face the camera ({Math.round(rotacao) > 0 ? `${Math.round(rotacao)}° right` : `${-Math.round(rotacao)}° left`})
                  </button>
                )}
              </div>
            </div>
            )}
          </>)}
          {f.id === 'personagem' && (
            <div className="hf-linha-controles">
              <Chips rotulo="Priority" opcoes={[{ id: 'rapido', rotulo: 'Fast · 4 steps' }, { id: 'fiel', rotulo: 'Faithful · 20 steps' }]}
                valor={prioridade} aoMudar={setPrioridade} />
            </div>
          )}
          {f.id === 'rosto' && (
            <div className="hf-rosto">
              {ROSTO.map((g) => (
                <div key={g.grupo} className="hf-campo"><span>{g.grupo}</span>
                  {g.itens.map((c) => (
                    <label key={c.id} className="hf-rosto-item">{c.rotulo}
                      <input type="range" min={c.min} max={c.max} step={c.passo} value={rosto[c.id] ?? 0} aria-label={c.rotulo}
                        onChange={(e) => setRosto((r) => ({ ...r, [c.id]: Number(e.target.value) }))}
                        onDoubleClick={() => setRosto((r) => ({ ...r, [c.id]: 0 }))} />
                      <small>{(rosto[c.id] ?? 0).toFixed(c.passo < 0.5 ? 2 : 1)}</small>
                    </label>
                  ))}
                </div>
              ))}
              {Object.values(rosto).some(Boolean) && <button type="button" className="hf-ajustes-limpar" onClick={() => setRosto({})}>Reset all</button>}
            </div>
          )}
          {f.id === 'ampliar' && (<>
            <div className="hf-linha-controles">
              <Chips rotulo="Method" opcoes={METODOS_AMPLIAR} valor={metodoAmpliar} aoMudar={setMetodoAmpliar} />
              <Chips rotulo="Scale" opcoes={escalasOk.map((e) => ({ id: e, rotulo: `${e}×` }))} valor={escalaOk} aoMudar={setEscalaAmpliar} />
            </div>
            {metodoAmpliar === 'criativo' && (
              <div className="hf-linha-controles"><Chips rotulo="Made for" opcoes={OTIMIZACOES} valor={otimizacao} aoMudar={setOtimizacao} /></div>
            )}
            {!ampliarApi && (
              <div className="hf-linha-controles">
                {([['detalhe', 'Restore detail'], ['microcontraste', 'Micro-contrast'], ['granulacao', 'Film grain']] as const).map(([id, nome]) => (
                  <div key={id} className="hf-campo"><span>{nome}</span>
                    <label className="hf-duracao"><span className="hf-valor">{Math.round(acabamento[id] * 100)}%</span>
                      <input type="range" min={0} max={1} step={0.05} value={acabamento[id]} aria-label={nome}
                        onChange={(e) => setAcabamento((a) => ({ ...a, [id]: Number(e.target.value) }))} /></label>
                  </div>
                ))}
              </div>
            )}
            {metodoAmpliar === 'magnific' && (
              <div className="hf-linha-controles">
                <div className="hf-campo"><span>Creativity</span>
                  <label className="hf-duracao"><span className="hf-valor">{criatividadeMag > 0 ? `+${criatividadeMag}` : criatividadeMag}</span>
                    <input type="range" min={-10} max={10} step={1} value={criatividadeMag} aria-label="Creativity"
                      onChange={(e) => setCriatividadeMag(Number(e.target.value))} /></label>
                </div>
              </div>
            )}
          </>)}
          {f.id === 'area' && (
            <div className="hf-linha-controles">
              <div className="hf-campo hf-campo-largo"><span>What to change</span>
                <input className="hf-entrada" value={alvoArea} maxLength={80} onChange={(e) => setAlvoArea(e.target.value)}
                  placeholder='e.g. "the jacket", "the sky", "the car"' aria-label="What to change" />
              </div>
              <Chips rotulo="Edge" opcoes={[{ id: 4, rotulo: 'Tight' }, { id: 12, rotulo: 'Normal' }, { id: 32, rotulo: 'Loose' }]}
                valor={bordaArea} aoMudar={setBordaArea} />
            </div>
          )}
          {f.id === 'controle' && (
            <div className="hf-linha-controles"><Chips rotulo="Follow" opcoes={CONTROLES} valor={tipoControle} aoMudar={setTipoControle} /></div>
          )}

          {com3d && <p className="hf-orbita-frase"><b>How it works:</b> the photo becomes a 3D model (about 40 s the first time), the preview shows it at the exact angle, and Apply turns that view into a photo with Qwen Image Edit, using your photo for the face, clothes and place. About 3 minutes.</p>}
          {comFrase && <p className="hf-orbita-frase"><b>Prompt (written for you):</b> {fraseOrbita(giro, alturaFrase, texto)}</p>}
          {f.texto && (f.id !== 'ampliar' || metodoAmpliar === 'magnific') && <div className="hf-campo hf-edt-texto"><span>{luzApi ? 'Light' : f.id === 'area' ? 'New look' : f.texto === 'obrigatorio' ? 'Prompt' : 'Optional'}</span><textarea aria-label="Prompt" maxLength={MAX_PROMPT} value={texto} onChange={(e) => setTexto(e.target.value)} rows={1}
            placeholder={luzApi ? 'Describe the light, e.g. "warm sunset light from the left, soft shadows"' : f.id === 'area' ? 'What it should become, e.g. "a red leather jacket"' : f.texto === 'obrigatorio' ? 'Describe what to draw on this structure…' : 'An extra touch, e.g. "keep the background dark"'} /></div>}
            <BotaoGerar rotulo="✦ Apply" est={custo} desligado={faltaImagem || faltaTexto || naoInstalado || soLocal} aoClicar={gerar} />
            {naoInstalado && <span className="hf-dica">Needs {pacoteAtual}.</span>}
            {soLocal && <span className="hf-dica">This tool runs on your GPU. Switch to Local to use it.</span>}
            {naoInstalado && <AvisoInstalar rotulo={pacoteAtual!} semMenu />}
            {erro && <p className="hf-erro">{erro}</p>}
          </>) : <p className="hf-dica">Pick a tool on the left.</p>}
        </aside>
      </div>

      <section className="hf-img-recentes" aria-label="Recent edits">
        <span className="hf-img-titulo">Recent edits</span>
        <div className="hf-img-faixa">
          {emCurso.map((t) => <div key={t.id} className="hf-img-faixa-item hf-img-faixa-curso"><CartaoTarefa t={t} /></div>)}
          {recentes.map((a) => (
            <button key={a.subpasta + a.nome} type="button" className="hf-img-faixa-item" data-ativo={depois?.nome === a.nome}
              onClick={() => setVerResultado(a)} title="Show it in the big view">
              <img src={urlImagem(a)} alt="" loading="lazy" />
            </button>
          ))}
          {!recentes.length && !emCurso.length && <p className="hf-vazio">Your edits will appear here.</p>}
        </div>
      </section>
    </div>
  )
}
