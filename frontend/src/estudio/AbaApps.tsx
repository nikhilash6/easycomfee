import { useContext, useEffect, useRef, useState } from 'react'
import { MotorCtx } from './motor'
import { api, referenciaDaGaleria, urlEntrada, urlImagem, type Referencia } from '../api'
import { ThenNow, abrirVisualizador } from './Visualizador'
import { Popup } from './AbaCinema'
import { BotaoGerar, CartaoTarefa, Chips, SlotImagem, arquivos, mensagem, rotuloCusto, useCusto, useTarefas, Galeria, MAX_PROMPT, TituloPagina } from './comum'

// VFX Apps: one card per effect, all open-weight LTX IC-LoRAs. Pick a card,
// drop a video, press Apply. Each card id is an effect of VIDEO_TRANSFORMAR
// in the backend (presets.py); "slowmo" is the LTX slow-motion LoRA instead.

export type App = {
  id: string; nome: string; frase: string; texto?: string
  imagem?: string; imagemOpcional?: boolean; formatos?: boolean; video?: boolean; chaves?: boolean
}

type Chave = { id: number; img: Referencia | null; quadro: number; vista?: Vista }
// Que lado do objeto a camera mostra naquele quadro. Uma maquete de blocos nao tem
// farol nem lanterna: no teste de 29/10/2026 o FLUX desenhou a FRENTE do carro onde a
// camera estava atras dele, e o video saiu com o carro virado ao contrario.
type Vista = 'auto' | 'front' | 'rear' | 'side'
const VISTAS: Record<Exclude<Vista, 'auto'>, string> = {
  front: 'seen from the front', rear: 'seen from the rear', side: 'seen from the side, in profile',
}

// 3D render → Video com referencias (character sheets): quando a camera gira e mostra
// um lado que o quadro 1 nao tinha, o LTX inventava. O app redesenha os quadros cinza
// da maquete com o FLUX 3 + as referencias e usa o resultado como quadros-chave.
// Experimento de 29/10/2026 (sheet de um carro numa maquete do Blender): o FLUX 3
// manteve o enquadramento; o Qwen mudou a camera e, com a placa cheia, levou 21 min.
const MAX_REFS_MAQUETE = 3
const MAX_CENARIOS = 2
// Quadro 1 + ate 3 momentos, por enquanto (30/10/2026).
const MAX_MOMENTOS = 4
// O video sai com no maximo 353 quadros (14,7 s a 24 fps); de render mais longo a pessoa
// escolhe o trecho (inicio e duracao). Minimo de 9 quadros, como no backend.
const MAX_QUADROS_MAQUETE = 353
const MIN_QUADROS_MAQUETE = 9
const segundos = (q: number) => `${(q / 24).toFixed(1)} s`
// Modelos que redesenham os quadros no passo 2. Os locais sao gratis; os da Comfy Cloud cobram
// creditos por versao (ids de presets.NUVEM).
type ModeloQuadro = 'flux3' | 'qwen' | 'sunburst' | 'nano-2' | 'seedream5'
const MODELOS_QUADRO_API = new Set<ModeloQuadro>(['sunburst', 'nano-2', 'seedream5'])
const MODELOS_QUADRO: { id: ModeloQuadro; rotulo: string }[] = [
  { id: 'flux3', rotulo: 'FLUX 3 · your GPU · recommended' },
  { id: 'qwen', rotulo: 'Qwen Image Edit · your GPU · slower' },
  { id: 'sunburst', rotulo: 'GPT Image 2.5 · Cloud' },
  { id: 'nano-2', rotulo: 'Nano Banana 2 · Cloud' },
  { id: 'seedream5', rotulo: 'Seedream 5 Pro · Cloud' },
]
// Resolucao do 3D render -> Video pela VRAM (igual a presets.limite_maquete do servidor,
// que tem a palavra final): abaixo de 16 GB nao roda, 16 GB vai ate 720p, mais que isso 1080p.
function tetoMaquete(vram: number | null | undefined): number | null {
  if (vram == null) return 576
  return vram < 15 ? null : vram < 18 ? 720 : 1088
}
const LADOS_MAQUETE = [{ id: '576', rotulo: '576p · fastest' }, { id: '720', rotulo: '720p' }, { id: '1088', rotulo: '1080p' }]
// Quantas versoes de cada quadro o FLUX 3 desenha para a pessoa escolher. O video bom do
// teste de 29/10/2026 saiu juntando o melhor quadro de cada rodada: um so por quadro errava.
const VISTA_OPCOES = [{ id: 'auto', rotulo: 'Auto' }, { id: 'front', rotulo: 'Front' }, { id: 'rear', rotulo: 'Rear' }, { id: 'side', rotulo: 'Side' }]
function instrucaoMaquete(cena: string, nomes: string[], vista: Vista = 'auto', nota = '', cenarios = 0) {
  // No formato do guia da BFL para editar com referencias (docs.bfl.ml): imagens pelo
  // nome (<ref_image_N>), um papel para cada uma, o que muda dito numa frase, texto curto.
  // A versao longa, cheia de "nao", confundia o FLUX (carro virado, copia do bloco, carro
  // a mais). E o objeto vai pelo NOME ("green Lamborghini Huracan"): com "the matching
  // object" o quadro de lado voltou a sair hatch. Testes de 29/10/2026.
  // Cada Cast e um character sheet: UM elemento (objeto ou pessoa) visto de varios lados. Sem
  // dizer isso o FLUX copiava o sheet inteiro, as 4 vistas do aviao espalhadas pela cena
  // (30/10/2026); com "one single ... drawn only once" saiu um aviao so, no lugar do bloco.
  const elementos = nomes.map((n) => n.trim() || 'element')
  const um = elementos.length === 1
  const folhas = elementos.map((n, i) => `<ref_image_${i + 1}> is a reference sheet of one single ${n} seen from several angles.`).join(' ')
  // Sem character sheet (modo guiado, quem so tem o render): a cena descrita da a aparencia.
  return 'Modify <ref_image_0>, a grey 3D blockout of a film shot, into a photorealistic frame with exactly the '
    + 'same camera, framing and layout. '
    + (folhas ? folhas + ' ' : '')
    + (!elementos.length ? 'The grey and colored blocks are placeholders: each one becomes the real object the scene describes, with real materials, color and details'
      : um ? `The colored block is a placeholder: it becomes that one ${elementos[0]}, drawn only once, with its real shape, color and details`
      : `The colored blocks are placeholders: they become ${elementos.map((n) => `the ${n}`).join('; ')}, each drawn only once, with its real shape, color and details`)
    + (vista === 'auto' ? '' : `, ${VISTAS[vista]}`)
    + (um ? ", at the block's position and size." : ", at its block's position and size.")
    // As referencias de cenario vem depois dos objetos: <ref_image_N+1>, <ref_image_N+2>.
    + (cenarios ? ` The setting (ground, background, sky, buildings) looks like ${Array.from({ length: cenarios },
      (_, i) => `<ref_image_${nomes.length + 1 + i}>`).join(' and ')}.` : '')
    + (nota.trim() ? ` ${nota.trim().replace(/\.?$/, '.')}` : '')
    + (cena.trim() ? ` ${cena.trim()}` : '')
    + (!elementos.length ? ' Keep the same number of objects.'
      : um ? ` Keep the same number of objects: exactly one ${elementos[0]}.`
      : ' Keep the same number of objects: each element appears only once.')
}

/** Render x take lado a lado com cortina: arrastar (ou as setas) mostra mais de um ou do outro.
 *  Uma imagem solta aqui substitui o take (correcao feita fora do app). */
function Comparador({ antes, depois, rotuloDepois, proporcao, gerando, aoSoltar }: {
  antes: string | null; depois: string | null; rotuloDepois: string; proporcao: string; gerando: boolean; aoSoltar: (f: File) => void
}) {
  const [pos, setPos] = useState(50)
  const caixa = useRef<HTMLDivElement>(null)
  const [l, a] = proporcao.split(':').map(Number)
  const mover = (x: number) => {
    const r = caixa.current?.getBoundingClientRect()
    if (r) setPos(Math.max(0, Math.min(100, ((x - r.left) / r.width) * 100)))
  }
  const cortina = !!(antes && depois)
  return (
    <div ref={caixa} className="hf-comparar" style={{ aspectRatio: `${l || 16} / ${a || 9}` }}
      role={cortina ? 'slider' : undefined} tabIndex={cortina ? 0 : undefined} aria-label="Compare the render and the take"
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={cortina ? Math.round(pos) : undefined}
      onKeyDown={(e) => { if (e.key === 'ArrowLeft') setPos((x) => Math.max(0, x - 5)); if (e.key === 'ArrowRight') setPos((x) => Math.min(100, x + 5)) }}
      onPointerDown={(e) => { if (!cortina) return; e.currentTarget.setPointerCapture(e.pointerId); mover(e.clientX) }}
      onPointerMove={(e) => { if (cortina && e.buttons) mover(e.clientX) }}
      onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) e.preventDefault() }}
      onDrop={(e) => {
        const f = Array.from(e.dataTransfer.files).find((x) => x.type.startsWith('image/'))
        if (f) { e.preventDefault(); e.stopPropagation(); aoSoltar(f) }
      }}>
      {depois ? <img src={depois} alt={rotuloDepois} draggable={false} />
        : antes ? <img src={antes} alt="Render" draggable={false} /> : <span className="hf-comparar-vazio">Taking the screenshot…</span>}
      {cortina && <div className="hf-comparar-antes" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}><img src={antes!} alt="Render" draggable={false} /></div>}
      {cortina && <div className="hf-comparar-linha" style={{ left: `${pos}%` }}><i aria-hidden>⟷</i></div>}
      {antes && <small className="hf-comparar-rotulo" data-lado="esq">Render</small>}
      {depois && <small className="hf-comparar-rotulo" data-lado="dir">{rotuloDepois}</small>}
      {gerando && <div className="hf-comparar-gerando" role="status">Drawing…</div>}
    </div>
  )
}

/** As versoes de um quadro redesenhado: clicar escolhe a que vai para o video. */
function EscolhaVersao({ versoes, atual, aoEscolher }: {
  versoes: Referencia[]; atual: Referencia | null; aoEscolher: (r: Referencia) => void
}) {
  if (versoes.length < 2) return null
  return (
    <div className="hf-versoes" role="group" aria-label="Pick a version">
      {versoes.map((v, i) => (
        <button key={v.nome} type="button" className="hf-versao" aria-pressed={atual?.nome === v.nome}
          title={`Use version ${i + 1}`} onClick={() => aoEscolher(v)}>
          <img src={urlEntrada(v.nome)} alt={`Version ${i + 1}`} />
        </button>
      ))}
    </div>
  )
}

// Aviso antes da tela do 3D render -> Video: o que foi testado, o que a placa precisa e
// como o modo Advanced funciona. "Nao mostrar de novo" fica so neste navegador.
const CHAVE_AVISO_MAQUETE = 'easycomfee.aviso-maquete'
function avisoMaqueteVisto() {
  try { return localStorage.getItem(CHAVE_AVISO_MAQUETE) === '1' } catch { return false }
}

function AvisoMaquete({ aoFechar }: { aoFechar: () => void }) {
  const [naoMostrar, setNaoMostrar] = useState(false)
  const botao = useRef<HTMLButtonElement>(null)
  useEffect(() => { botao.current?.focus() }, [])
  const fechar = () => {
    if (naoMostrar) { try { localStorage.setItem(CHAVE_AVISO_MAQUETE, '1') } catch { /* sem armazenamento: so nao lembra */ } }
    aoFechar()
  }
  return (
    <div className="hf-aviso-fundo" onClick={fechar}>
      <div className="hf-aviso-janela" role="dialog" aria-modal="true" aria-labelledby="aviso-maquete-titulo"
        onClick={(e) => e.stopPropagation()} onKeyDown={(e) => { if (e.key === 'Escape') fechar() }}>
        <span className="hf-selo-neon hf-selo-solto">Experimental</span>
        <h2 id="aviso-maquete-titulo">3D render → Video: before you start</h2>
        <ul>
          <li><b>Still in development:</b> it needs more testing, results change from shot to shot and some renders will not work yet.</li>
          <li><b>Tested only on NVIDIA</b> cards (RTX 5070 Ti, 16 GB). Other GPUs may not work.</li>
          <li><b>Needs 16 GB of VRAM or more.</b> On 16 GB keep 720p videos to 10 s or less (576p handles the full 14.7 s); with more VRAM, up to 1080p.</li>
          <li><b>Go easy on PCs with little memory:</b> close heavy apps (Premiere, After Effects, games) and run one generation at a time.</li>
          <li><b>The video runs on your GPU only.</b> The realistic frames can also use paid Comfy Cloud models, with your credits.</li>
        </ul>
        <h3>Two modes</h3>
        <ul>
          <li><b>Advanced · 3 steps</b> (default): <b>1</b> take screenshots of your gray render where the camera shows something new;{' '}
            <b>2</b> in Cinema Studio, describe the scene, add a character sheet of each element (with its name) and shoot each frame until it looks right;{' '}
            <b>3</b> generate the video. About 1 to 1.5 min per frame and 5 to 8 min per video on 16 GB.</li>
          <li><b>Simple:</b> your gray render plus your own image of frame 1. LTX keeps the camera and motion of the render
            and paints the scene like that image.</li>
        </ul>
        <p className="hf-dica">Best results when the blocks have the rough shape of the real object (a low sports car, a person), not just a cube.
          More tips in “Experimental · Tips”, next to the page title.</p>
        <div className="hf-linha-controles">
          <label className="hf-toggle"><input type="checkbox" checked={naoMostrar} onChange={(e) => setNaoMostrar(e.target.checked)} /> Don't show this again</label>
          <button ref={botao} type="button" className="hf-gerar" onClick={fechar}>Got it</button>
        </div>
      </div>
    </div>
  )
}

/** Espera uma tarefa terminar e devolve os arquivos dela. */
async function esperarTarefa(id: string) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000))
    const t = (await api.tarefas()).find((x) => x.id === id)
    if (t?.estado === 'erro') throw new Error(t.erro || 'A step failed.')
    if (t?.estado === 'pronto') return arquivos(t)
  }
}

// Ajustes do recorte do Tirar o fundo: aplicados na montagem do video transparente
// (/api/alpha), sem gerar de novo.
const RECORTE_NEUTRO = { borda: 0, suavizar: 0, preto: 0, branco: 1, tempo: 0, inverter: false }
type Recorte = typeof RECORTE_NEUTRO
const paramsRecorte = (r: Recorte) => new URLSearchParams(Object.entries(r).map(([k, v]) => [k, String(v)])).toString()

function AjustesRecorte({ valor, aoMudar, webm, mov }: { valor: Recorte; aoMudar: (r: Recorte) => void; webm: string; mov: string }) {
  const barra = (chave: 'borda' | 'suavizar' | 'preto' | 'branco' | 'tempo', rotulo: string, min: number, max: number, passo: number, dica: string) => (
    <label className="hf-recorte-campo" title={dica}>
      <span>{rotulo} <b>{valor[chave]}</b></span>
      <input type="range" min={min} max={max} step={passo} value={valor[chave]}
        onChange={(e) => aoMudar({ ...valor, [chave]: Number(e.target.value) })} />
    </label>
  )
  return (
    <div className="hf-recorte">
      <div className="hf-recorte-campos">
        {barra('borda', 'Choke / Expand', -10, 10, 1, 'Pixels: negative pulls the edge in (removes background halo), positive pushes it out')}
        {barra('suavizar', 'Feather', 0, 10, 0.5, 'Softens the edge')}
        {barra('preto', 'Black point', 0, 0.9, 0.05, 'Faint grey below this becomes transparent')}
        {barra('branco', 'White point', 0.1, 1, 0.05, 'Grey above this becomes solid')}
        {barra('tempo', 'Smooth', 0, 3, 1, 'Averages neighbouring frames so the edge does not flicker')}
        <label className="hf-toggle"><input type="checkbox" checked={valor.inverter} onChange={(e) => aoMudar({ ...valor, inverter: e.target.checked })} /> Invert</label>
        <button type="button" className="hf-botao-sec" onClick={() => aoMudar(RECORTE_NEUTRO)}>Reset</button>
      </div>
      <div className="hf-recorte-baixar">
        <a className="hf-botao-sec" href={webm} download>Transparent video (.webm)</a>
        <a className="hf-botao-sec" href={mov} download>ProRes 4444 with alpha (.mov)</a>
      </div>
    </div>
  )
}

export const APPS: App[] = [
  { id: 'noite', nome: 'Day → Night', frase: 'The same shot at night: dark sky, streetlights and windows on.' },
  { id: 'alpha', nome: 'Remove background', frase: 'Cuts out the subject with a clean alpha matte, no green screen: hair, smoke and glass included. Up to 6 s. Download it as a transparent video.' },
  { id: 'limpar', nome: 'Remove people', frase: 'Erases people and cars that move and rebuilds the background.' },
  { id: 'agua', nome: 'Add water', frase: 'Flood, rain, waves and splashes. Describe the water you want.', texto: 'The ground is flooded with shallow rushing water' },
  { id: 'trocar', nome: 'Swap character', frase: 'Keeps the motion of the video, takes the look from a new first frame.', imagem: 'New first frame' },
  { id: 'expandir', nome: 'Expand frame', frase: 'Turns vertical into widescreen (or back) by inventing the edges.', formatos: true },
  { id: 'cor', nome: 'Colorize', frase: 'Brings black-and-white footage to color. Name the colors you want: it needs them.', texto: 'A full color video with natural vivid colors: ' },
  { id: 'nitidez', nome: 'Unblur', frase: 'Recovers sharpness from blurry footage.' },
  { id: 'compressao', nome: 'Remove compression', frase: 'Clears blocky compression artifacts from footage.' },
  { id: 'detalhe', nome: 'Refine details', frase: 'Rebuilds texture in soft or upscaled footage.' },
  { id: 'restaurar', nome: 'Restore', frase: 'For very damaged footage. Creative: it may invent details.' },
  { id: 'profundidade', nome: 'Follow depth', frase: 'Keeps the video’s forms and camera motion while changing its appearance.', imagem: 'First frame (optional)', imagemOpcional: true },
  { id: 'maquete', nome: '3D render → Video', frase: 'A blockout from Blender or Unreal becomes the finished shot: camera and motion from the render, look from your image.', imagem: 'Look (frame 1)', chaves: true },
  { id: 'mapa_profundidade', nome: 'Video → Depth map', frase: 'Turns a video into a stable depth map: near is bright, far is dark. Optional EXR frames for Blender or After Effects.' },
  { id: 'slowmo', nome: 'Slow motion', frase: 'Animates a still in true slow motion (high-speed camera look).', imagem: 'Start image', video: false },
]

// Comfy Cloud has the LTX 2.3 version of most of these LoRAs (nuvem.SUBSTITUTOS);
// these two exist only in the 2.5 Creative Lab, so they need your own GPU.
// The layout-to-render LoRA (3D render → Video) is a 2.5 one too.
const SO_LOCAL = new Set(['restaurar', 'slowmo', 'maquete', 'mapa_profundidade', 'alpha'])

export default function AbaApps({ naNuvem }: { naNuvem: boolean }) {
  const tarefas = useTarefas()
  // Abre no efeito do endereco; sem ele, no 3D render -> Video (o primeiro da lista, como no layout).
  const [app, setApp] = useState<App | null>(() => APPS.find((a) => location.hash === `#apps/${a.id}`) ?? APPS.find((a) => a.id === 'maquete') ?? null)
  const [busca, setBusca] = useState('')
  const [comparar, setComparar] = useState<'cortina' | 'lado'>('cortina')
  const [aplicadoEm, setAplicadoEm] = useState(0)
  const [dicasMaquete, setDicasMaquete] = useState(false)
  const [video, setVideo] = useState<Referencia | null>(null)
  const [imagem, setImagem] = useState<Referencia | null>(null)
  const [texto, setTexto] = useState('')
  const [formato, setFormato] = useState('16:9')
  // Video -> Depth map: cinza ou colorido, e quadros EXR opcionais.
  const [corMapa, setCorMapa] = useState<'gray' | 'inferno'>('gray')
  const [exr, setExr] = useState(false)
  const ehMapa = app?.id === 'mapa_profundidade'
  // Pacote "profundidade" do Config Models (modelo + extensao no motor de video).
  const { instalados } = useContext(MotorCtx)
  const semPacote = ehMapa && !!instalados && !instalados.has('profundidade')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  // 3D render → Video: keyframes, each at a frame number (from 1, 24 fps, as in Blender).
  const [chaves, setChaves] = useState<Chave[]>([])
  const proximo = useRef(1)
  const player = useRef<HTMLVideoElement>(null)
  const [duracao, setDuracao] = useState(0)
  // Formato da maquete: os quadros redesenhados saem no mesmo formato.
  const [formatoMaquete, setFormatoMaquete] = useState('16:9')
  const quadroAtual = () => Math.round((player.current?.currentTime ?? 0) * 24) + 1
  // Trecho do render que vira video: inicio (quadro, contado de 0) e duracao em quadros.
  const totalQ = Math.max(0, Math.round(duracao * 24))
  const [inicioQ, setInicioQ] = useState(0)
  const [duracaoQ, setDuracaoQ] = useState(MAX_QUADROS_MAQUETE)
  const maxDuracaoQ = Math.max(MIN_QUADROS_MAQUETE, Math.min(MAX_QUADROS_MAQUETE, totalQ - inicioQ))
  const durQ = Math.min(duracaoQ, maxDuracaoQ)
  const dentro = (q: number) => q >= inicioQ + 1 && q <= inicioQ + durQ
  const chavesUsadas = chaves.filter((c) => dentro(c.quadro))
  const mudarInicio = (q: number) => {
    const n = Math.max(0, Math.min(q, Math.max(0, totalQ - MIN_QUADROS_MAQUETE)))
    setInicioQ(n)
    if (player.current) player.current.currentTime = n / 24
  }
  const addChave = () => {
    const n = quadroAtual()
    if (!dentro(n)) { setErro('This point is outside the part of the render that becomes video: move the player inside the highlighted part.'); return }
    setErro(null)
    setChaves((a) => a.some((c) => c.quadro === n) || a.filter((c) => dentro(c.quadro)).length >= MAX_MOMENTOS - 1 ? a
      : [...a, { id: proximo.current++, img: null, quadro: n }].sort((x, y) => x.quadro - y.quadro))
  }
  const mudarChave = (id: number, c: Partial<Chave>) => {
    setChaves((a) => a.map((x) => (x.id === id ? { ...x, ...c } : x)))
    if (c.quadro !== undefined) setCinzas((x) => { const n = { ...x }; delete n[id]; return n })
  }
  // Referencias (character sheets) e o preenchimento automatico dos quadros.
  const [refsMaquete, setRefsMaquete] = useState<(Referencia | null)[]>([null])
  const [preenchendo, setPreenchendo] = useState('')
  const [vistaLook, setVistaLook] = useState<Vista>('auto')
  // Simple: o 3D render -> Video de sempre. Advanced: as referencias (character sheets) que o
  // FLUX 3 usa para redesenhar os quadros antes do video.
  // 'avancado' = Make it here (guiado, o padrao): o leigo so tem o render e faz tudo nesta tela.
  const [modoMaquete, setModoMaquete] = useState<'simples' | 'avancado'>('avancado')
  // Advanced em 3 passos: 1 marcar os quadros no render, 2 deixar cada um realista, 3 gerar o video.
  const [passo, setPasso] = useState<1 | 2 | 3>(1)
  // Aviso de um passo nao fica aparecendo nos outros.
  useEffect(() => { setErro(null) }, [passo])
  // Passo 2: referencia do cenario (alem dos character sheets) e o modelo que redesenha os quadros.
  // Cenario: ate MAX_CENARIOS imagens do lugar; sempre ha um espaco vazio no fim.
  const [cenarios, setCenarios] = useState<(Referencia | null)[]>([null])
  const cenariosOk = cenarios.filter((r): r is Referencia => !!r)
  // FLUX 3 e o padrao: nos testes manteve a camera e levou ~1,5 min por versao. O Qwen Image
  // Edit (resolucao baixa, como no Recast) e a segunda opcao; mudou o enquadramento as vezes.
  const [modeloQuadro, setModeloQuadro] = useState<ModeloQuadro>('flux3')
  // Os modelos pagos da Comfy Cloud precisam da chave e de "Paid API models" ligado no Config
  // Models. Rodam com o motor local mesmo (a chave vai junto do pedido), entao o video segue local.
  const { temChave } = useContext(MotorCtx)
  const [soAbertos, setSoAbertos] = useState(true)
  useEffect(() => {
    if (app?.id !== 'maquete') return
    fetch('/api/motor').then((r) => r.json()).then((m) => setSoAbertos(!!m?.so_abertos)).catch(() => {})
  }, [app?.id])
  const pagosOk = temChave && !soAbertos
  const ehApi = MODELOS_QUADRO_API.has(modeloQuadro)
  // Preco de UMA versao no modelo pago escolhido (a maquete + ate 2 referencias).
  const custoVersao = useCusto(ehApi ? { modelo: modeloQuadro, prompt: 'x', proporcao: formatoMaquete, lote: 1,
    referencias: ['a.png', 'b.png'] } : null)
  // VRAM da placa (Config Models > Your machine): limita a resolucao.
  const [vramGb, setVramGb] = useState<number | null | undefined>(undefined)
  const [ladoEscolhido, setLadoEscolhido] = useState<string | null>(null)
  useEffect(() => {
    if (app?.id !== 'maquete' || vramGb !== undefined) return
    fetch('/api/maquina').then((r) => r.json())
      .then((m) => setVramGb(m?.detectado?.vram_gb ?? m?.salvo?.vram_gb ?? null)).catch(() => setVramGb(null))
  }, [app?.id, vramGb])
  const teto = tetoMaquete(vramGb)
  const ladosOk = LADOS_MAQUETE.filter((l) => teto !== null && Number(l.id) <= teto)
  // As tres aparecem; as acima do teto da placa ficam desligadas, com o motivo no title.
  const ladosTela = teto === null ? [] : LADOS_MAQUETE.map((l) => Number(l.id) <= teto ? l
    : { ...l, desligado: true, dica: 'Needs a graphics card with more than 16 GB of VRAM' })
  // Em 16 GB (teto 720), 720p passou de 10 s e o driver da placa reiniciou num teste (30/10/2026):
  // acima de 10 s o padrao e 576p, e escolher 720p mostra o aviso.
  const longoPara720 = teto === 720 && durQ > 240
  const lado = ladoEscolhido && ladosOk.some((l) => l.id === ladoEscolhido) ? ladoEscolhido
    : longoPara720 ? '576' : String(teto ?? 576)
  const avisoLado = longoPara720 && lado === '720'
    ? 'On a 16 GB card, 720p is safe up to 10 s: use 576p or shorten the video in step 1.' : ''
  // Versoes desenhadas de cada quadro (0 = Look / quadro 1; os outros, pelo id do quadro-chave).
  const [versoes, setVersoes] = useState<Record<number, Referencia[]>>({})
  // Nome de cada referencia, na mesma posicao do slot (vai para a instrucao do FLUX).
  const [nomesRefs, setNomesRefs] = useState<string[]>([])
  const refsOk = refsMaquete.filter((r): r is Referencia => !!r)
  const nomesOk = refsMaquete.map((r, i) => (r ? nomesRefs[i] ?? '' : null)).filter((n): n is string => n !== null)
  // Para desenhar um quadro basta a descricao da cena; o character sheet e opcional.
  // Sem a cena e o nome de cada elemento o FLUX so copia o character sheet (30/10/2026):
  // so deixa gerar com os dois.
  const semNome = nomesOk.some((n) => !n.trim())
  const podeDesenhar = !!texto.trim() && !semNome
  const faltaParaDesenhar = !texto.trim() ? 'Describe the scene first (or a few words and “Write with AI”).'
    : 'Name each cast picture (the field under it), e.g. “white stunt plane”: without a name the model just copies the sheet.'
  /** Tres quadros-chave espalhados pelo video (a 1/4, 2/4 e 3/4), se ainda nao houver. */
  const cheio = chavesUsadas.length >= MAX_MOMENTOS - 1
  const espalharChaves = () => {
    setChaves((a) => {
      // Dentro do trecho, ja na posicao que o modelo aceita (multiplo de 8 a partir do inicio).
      const usadas = a.filter((c) => dentro(c.quadro)).length
      const novos = [0.25, 0.5, 0.92].map((f) => inicioQ + Math.min(durQ, Math.max(9, Math.round((durQ * f) / 8) * 8 + 1)))
        .filter((n) => !a.some((c) => Math.abs(c.quadro - n) < 8))
        .slice(0, Math.max(0, MAX_MOMENTOS - 1 - usadas))
        .map((n) => ({ id: proximo.current++, img: null, quadro: n }))
      return [...a, ...novos].sort((x, y) => x.quadro - y.quadro)
    })
  }
  // Quadro de direcao (modo Advanced): cada momento (0 = quadro 1 / Look; os outros pelo id
  // do quadro-chave) tem o print cinza do render, as versoes desenhadas, uma observacao e o
  // lado do objeto. A pessoa gera versoes de um quadro ate acertar, escolhe e so entao aplica:
  // nos testes de 29/10/2026 o carro saiu virado, duplicado ou fora do lugar em varias
  // tentativas, e o video bom veio de juntar a melhor versao de cada quadro.
  const [cinzas, setCinzas] = useState<Record<number, Referencia>>({})
  const [notas] = useState<Record<number, string>>({})
  // Prompt editado a mao num quadro (vale so para ele; "Reset" volta ao montado pelo app).
  const [promptsEditados, setPromptsEditados] = useState<Record<number, string>>({})
  const [gerando, setGerando] = useState<number | null>(null)
  const alvoDe = (id: number) => id === 0 ? { id: 0, quadro: inicioQ + 1, vista: vistaLook }
    : (() => { const c = chaves.find((x) => x.id === id)!; return { id, quadro: c.quadro, vista: c.vista ?? 'auto' as Vista } })()
  /** Tira o quadro cinza de cada momento que ainda nao tem, no tamanho do modelo. */
  const capturando = useRef(false)
  const garantirCinzas = async (ids: number[]) => {
    const faltam = ids.filter((id) => !cinzas[id])
    if (!video || !faltam.length) return { ...cinzas }
    const quadros = faltam.map((id) => alvoDe(id).quadro)
    const arqs = await esperarTarefa((await api.gerar({ modelo: 'quadros_maquete', prompt: '', proporcao: '1:1',
      quadros_extrair: quadros, inicio_maquete: inicioQ, quadros_maquete: durQ,
      referencias: [`entrada:${video.nome}`] } as Parameters<typeof api.gerar>[0])).id)
    const novos: Record<number, Referencia> = {}
    for (let i = 0; i < faltam.length; i++) novos[faltam[i]] = await referenciaDaGaleria({ arquivo: arqs[i].nome, subpasta: arqs[i].subpasta })
    setCinzas((x) => ({ ...x, ...novos }))
    return { ...cinzas, ...novos }
  }
  // No modo Advanced os prints cinza aparecem sozinhos: a pessoa ve o que cada quadro mostra antes de gerar.
  const trechoDosCinzas = useRef('')
  useEffect(() => {
    const chave = `${inicioQ}|${durQ}`
    if (trechoDosCinzas.current && trechoDosCinzas.current !== chave) setCinzas({})
    trechoDosCinzas.current = chave
  }, [inicioQ, durQ])
  useEffect(() => {
    if (modoMaquete !== 'avancado' || !video || capturando.current) return
    const ids = [0, ...chavesUsadas.map((c) => c.id)].filter((id) => !cinzas[id])
    if (!ids.length) return
    const espera = setTimeout(() => {
      capturando.current = true
      garantirCinzas(ids).catch((e) => setErro(mensagem(e))).finally(() => { capturando.current = false; setCinzas((x) => ({ ...x })) })
    }, 600)
    return () => clearTimeout(espera)
  }, [modoMaquete, video, chaves, cinzas, inicioQ, durQ])
  /** O texto que vai para o modelo neste quadro (e o que "See the prompt" mostra). So o FLUX 3
   *  entende <ref_image_N>; os outros recebem "image 1, image 2..." na ordem das referencias. */
  const promptDoQuadro = (id: number) => {
    const alvo = alvoDe(id)
    const instrucao = promptsEditados[id] ?? instrucaoMaquete(texto, nomesOk, alvo.vista, notas[id] ?? '', cenariosOk.length)
    return modeloQuadro === 'flux3' ? instrucao : instrucao.replace(/<ref_image_(\d+)>/g, (_, n) => `image ${Number(n) + 1}`)
  }
  // "Write it for me": o modelo de texto local escreve o nome do elemento ou a cena a partir de
  // poucas palavras (ate em portugues). Mesmo caminho do modo Director do Cinema Studio.
  const [escrevendo, setEscrevendo] = useState<string | null>(null)
  const escrever = async (campo: 'nome' | 'cena', i = 0) => {
    const ideia = (campo === 'nome' ? nomesRefs[i] ?? '' : texto).trim()
    if (!ideia) { setErro(campo === 'nome' ? 'Type a few words about the element first, e.g. “green Lamborghini”.' : 'Type a few words about the scene first, e.g. “desert road, sunset”.'); return }
    setEscrevendo(campo === 'nome' ? `nome-${i}` : 'cena'); setErro(null)
    try {
      const r = await fetch('/api/maquete/escrever', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ideia, campo, objeto: nomesOk[0] ?? '', seed: Math.floor(Math.random() * 1e6) }) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d.detail ?? 'The text model did not answer.')
      if (campo === 'nome') setNomesRefs((a) => { const n = [...a]; n[i] = d.texto; return n })
      else setTexto(d.texto)
    } catch (e) { setErro(mensagem(e)) } finally { setEscrevendo(null) }
  }
  /** Imagem da pessoa (um take corrigido fora do app) entra como mais um take do quadro, ja escolhida. */
  const substituir = async (id: number, f: File) => {
    setErro(null)
    try {
      const ref = await api.enviarReferencia(f)
      setVersoes((x) => ({ ...x, [id]: [...(x[id] ?? []), ref] }))
      if (id === 0) setImagem(ref)
      else mudarChave(id, { img: ref })
    } catch (e) { setErro(mensagem(e)) }
  }
  const [copiado, setCopiado] = useState<number | null>(null)
  const copiar = async (id: number) => {
    try { await navigator.clipboard.writeText(promptDoQuadro(id)); setCopiado(id); setTimeout(() => setCopiado(null), 1500) } catch { /* sem area de transferencia */ }
  }

  /** Uma versao nova de um quadro (sem seed: cada uma sai diferente). A primeira ja e escolhida. */
  const gerarVersao = async (id: number) => {
    if (!video || !podeDesenhar) return
    setGerando(id); setErro(null)
    try {
      const cinza = (await garantirCinzas([id]))[id]
      const refs = [cinza.nome, ...refsOk.map((r) => r.nome), ...cenariosOk.map((r) => r.nome)]
      const prompt = promptDoQuadro(id)
      const pedido = modeloQuadro === 'flux3' ? { modelo: 'flux3ref', prompt }
        : modeloQuadro === 'qwen' ? { modelo: 'qwen', resolucao_edicao: 'baixa', prompt }
        : { modelo: modeloQuadro, prompt }
      const [pronto] = await esperarTarefa((await api.gerar({ ...pedido, proporcao: formatoMaquete, lote: 1,
        referencias: refs } as Parameters<typeof api.gerar>[0])).id)
      const ref = await referenciaDaGaleria({ arquivo: pronto.nome, subpasta: pronto.subpasta })
      setVersoes((x) => ({ ...x, [id]: [...(x[id] ?? []), ref] }))
      if (id === 0) setImagem((atual) => atual ?? ref)
      else setChaves((a) => a.map((c) => (c.id === id && !c.img ? { ...c, img: ref } : c)))
    } catch (e) { setErro(mensagem(e)) } finally { setGerando(null) }
  }
  /** Um take para cada momento ainda sem imagem (atalho para comecar; "Reshoot" em cada quadro faz mais). */
  const vazios = [...(imagem ? [] : [0]), ...chavesUsadas.filter((c) => !c.img).map((c) => c.id)]
  const preencherQuadros = async () => {
    const ids = vazios
    if (!ids.length) { setErro('Every frame already has an image. Use “Reshoot” on a frame to try again.'); return }
    for (let i = 0; i < ids.length; i++) {
      setPreenchendo(`Shooting frame ${i + 1} of ${ids.length}…`)
      await gerarVersao(ids[i])
    }
    setPreenchendo('')
  }
  // Saves the gray frame to Assets, in the size the model uses, to restyle in the Image tab.
  const capturar = async (n: number) => {
    setErro(null)
    try {
      await api.gerar({ modelo: 'quadros_maquete', prompt: '', proporcao: '1:1', quadros_extrair: [n],
        referencias: [`entrada:${video!.nome}`] })
    } catch (e) { setErro(mensagem(e)) }
  }

  // Tambem quando a pagina ja abre no 3D render -> Video (link #apps/maquete).
  const [avisoMaquete, setAvisoMaquete] = useState(() => app?.id === 'maquete' && !avisoMaqueteVisto())
  const abrir = (a: App) => {
    setApp(a); setTexto(a.texto ?? ''); setErro(null); setAplicadoEm(0)
    if (a.id === 'maquete' && !avisoMaqueteVisto()) setAvisoMaquete(true)
  }
  const precisaVideo = app?.video !== false
  /** Sobe o video do computador (escolhido ou arrastado para a caixa). */
  const enviarVideo = async (f: File) => {
    setEnviando(true); setErro(null)
    try { setVideo(await api.enviarReferencia(f)) } catch (x) { setErro(mensagem(x)) } finally { setEnviando(false) }
  }
  const videoArrastado = (dt: DataTransfer) => Array.from(dt.files).find((f) => f.type.startsWith('video/'))
  const bloqueado = naNuvem && !!app && SO_LOCAL.has(app.id)
  const semPlaca = app?.id === 'maquete' && !naNuvem && teto === null
  const pronto = app && !bloqueado && !semPacote && !semPlaca && (!precisaVideo || video) && (!app.imagem || app.imagemOpcional || imagem)

  const custo = useCusto(!app || bloqueado ? null : ehMapa
    ? { modelo: 'profundidade_video', prompt: '', proporcao: '1:1', referencias: video ? [`entrada:${video.nome}`] : [] }
    : app.id === 'slowmo'
    ? { modelo: 'video', modelo_video: 'ltx', modo_video: 'imagem', prompt: 'x', proporcao: '1:1',
        proporcao_video: '16:9', resolucao_video: '720p', duracao_video: 5, com_audio: false, referencias: ['a.png'] }
    : { modelo: 'transformar_video', efeito_video: app.id, prompt: 'x', proporcao: '1:1',
        referencias: video ? [`entrada:${video.nome}`] : [] })

  const aplicar = async () => {
    if (!app) return
    setErro(null); setAplicadoEm(Date.now() / 1000 - 2)  // o resultado deste Apply vai para o comparador
    try {
      if (ehMapa) {
        await api.gerar({ modelo: 'profundidade_video', prompt: '', proporcao: '1:1', mapa_cor: corMapa, exr,
          referencias: [`entrada:${video!.nome}`] } as Parameters<typeof api.gerar>[0])
      } else if (app.id === 'slowmo') {
        await api.gerar({
          modelo: 'video', modelo_video: 'ltx', modo_video: 'imagem', proporcao: '1:1',
          prompt: texto.trim() || 'Slow motion shot, high-speed camera, every movement stretched and graceful',
          proporcao_video: '16:9', resolucao_video: '720p', duracao_video: 5, com_audio: false,
          velocidade_video: 0.2, referencias: [imagem!.nome],
        })
      } else {
        await api.gerar({
          modelo: 'transformar_video', efeito_video: app.id, prompt: texto.trim(), proporcao: '1:1',
          formato_saida: formato, referencias: [`entrada:${video!.nome}`, ...(imagem ? [imagem.nome] : [])],
          ...(app.id === 'maquete' ? { lado_maquete: Number(lado), inicio_maquete: inicioQ, quadros_maquete: durQ } : {}),
          ...(app.chaves ? { chaves_video: chavesUsadas.filter((c) => c.img).map((c) => ({ imagem: c.img!.nome, quadro: c.quadro })) } : {}),
        })
      }
    } catch (e) { setErro(mensagem(e)) }
  }

  // Os quadros realistas do 3D render -> Video (FLUX 3, Qwen ou API) tambem aparecem aqui, para reaproveitar.
  const quadroMaquete = (prompt: string) => prompt.includes('a grey 3D blockout of a film shot')
  // Os prints cinza do render (quadros_maquete) ficam nos passos e em Assets, nao aqui: enchiam a galeria.
  const minhas = tarefas.filter((t) => t.modelo === 'transformar_video' || t.modelo === 'profundidade_video'
    || (t.modelo === 'video' && t.prompt.includes('Slow motion')) || quadroMaquete(t.prompt))

  const tarefaFeita = aplicadoEm ? minhas.find((t) => t.estado === 'pronto' && t.criada_em >= aplicadoEm) : undefined
  const resultado = tarefaFeita ? arquivos(tarefaFeita)[0] : undefined
  // Tirar o fundo: o resultado e a mascara; o palco mostra o video transparente sobre xadrez.
  const [recorte, setRecorte] = useState(RECORTE_NEUTRO)
  const [recorteAplicado, setRecorteAplicado] = useState(RECORTE_NEUTRO)
  useEffect(() => { const t = window.setTimeout(() => setRecorteAplicado(recorte), 450); return () => window.clearTimeout(t) }, [recorte])
  const urlRecorte = (formato: 'webm' | 'mov') => tarefaFeita ? `/api/alpha/${tarefaFeita.id}?formato=${formato}&${paramsRecorte(recorteAplicado)}` : ''
  const transparente = tarefaFeita?.alpha ? urlRecorte('webm') : ''

  return (
    <div className="hf-aba hf-img hf-vfx">
      <TituloPagina antes="Transform your" destaque="footage" sub="One-click LTX effects for videos you already have.">
        {/* As dicas do 3D render ficam ao lado do titulo, como o How it works do Cinema, e so nesse efeito. */}
        {app?.id === 'maquete' && (
          <button type="button" className="hf-cin-dicas-botao" onClick={() => setDicasMaquete(true)}><b>Experimental</b> · Tips <i aria-hidden>›</i></button>
        )}
        {dicasMaquete && app?.id === 'maquete' && (
          <Popup titulo="3D render → Video · Tips for better results" aoFechar={() => setDicasMaquete(false)}>
            <div className="hf-dicas hf-cin-dicas">
              <ul>
                <li><b>Shape the blocks roughly like the real thing</b> (a low box for a car, a simple figure for a person), on a visible ground, with smooth camera moves at 24 fps.</li>
                <li><b>Take a screenshot wherever a new side of the object shows</b> (it turns, the camera goes around it): the model only invents what it never saw.</li>
                <li><b>Name each cast picture</b> and pick the side the object is seen from in every frame.</li>
                <li><b>Describe the scene</b> (“a green sports car on a desert road at sunset”), not the camera: the camera comes from your render.</li>
                <li><b>Shoot 2 or 3 takes of a frame</b> and keep the best one, using the slider to compare it with the render.</li>
                <li>Simple mode: make the Look from frame 1 of the render, with the same framing and aspect ratio.</li>
              </ul>
              <b className="hf-dicas-sub">Good to know</b>
              <ul>
                <li><b>Still in development.</b> This mode needs more testing: results change from shot to shot, and some renders will not work yet.</li>
                <li><b>Tested only on NVIDIA</b> (RTX 5070 Ti, 16 GB). It needs at least 16 GB of VRAM.</li>
                <li><b>On a 16 GB card, keep 720p videos to 10 s or less.</b> 576p handles the full 14.7 s. 1080p needs more than 16 GB.</li>
                <li><b>Go easy on PCs with little memory.</b> Close Premiere, After Effects, games and other heavy apps, and do not run other generations at the same time.
                  In our tests a long 720p video on a busy card made the graphics driver reset and stopped everything.</li>
                <li><b>Typical times on 16 GB:</b> about 1 to 1.5 min per frame with FLUX 3, about 5 min for a 14.7 s video at 576p, about 8 min at 720p.</li>
                <li><b>Screenshots wait in line:</b> while a video is generating, new screenshots show “Taking the screenshot…” until it ends.</li>
              </ul>
                        </div>
          </Popup>
        )}
      </TituloPagina>
      {avisoMaquete && <AvisoMaquete aoFechar={() => setAvisoMaquete(false)} />}
      <div className="hf-vfx-grade">
        <aside className="hf-img-col hf-vfx-esq" aria-label="Effects">
          <label className="hf-vfx-busca"><span aria-hidden>⌕</span>
            <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Search effects…" aria-label="Search effects" /></label>
          <span className="hf-img-titulo">Effects</span>
          <div className="hf-vfx-lista">
            {[...APPS.filter((x) => x.id === 'maquete'), ...APPS.filter((x) => x.id !== 'maquete')]
              .filter((a) => !busca.trim() || (a.nome + ' ' + a.frase).toLowerCase().includes(busca.trim().toLowerCase()))
              .map((a) => (
              <button key={a.id} className="hf-app hf-vfx-cartao" data-ativo={app?.id === a.id} aria-pressed={app?.id === a.id} onClick={() => abrir(a)}>
                <video src={`/exemplos/${a.id}.mp4?v=10#t=1.5`} muted loop playsInline preload="metadata"
                  onMouseEnter={(e) => { e.currentTarget.play().catch(() => {}) }} onMouseLeave={(e) => e.currentTarget.pause()}
                  onError={(e) => { (e.currentTarget as HTMLVideoElement).style.visibility = 'hidden' }} />
                {a.id === 'maquete' && <small className="hf-selo-neon">Experimental</small>}
                <b>{a.nome}{naNuvem && SO_LOCAL.has(a.id) && <small> · local GPU</small>}</b>
                <span>{a.frase}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="hf-vfx-centro">
          <div className="hf-vfx-topo">
            <h2>{app?.nome ?? 'Pick an effect'}</h2>
            <div className="hf-vfx-modos" role="group" aria-label="Compare">
              <button type="button" data-ativo={comparar === 'cortina'} aria-pressed={comparar === 'cortina'} onClick={() => setComparar('cortina')}>Before / After</button>
              <button type="button" data-ativo={comparar === 'lado'} aria-pressed={comparar === 'lado'} onClick={() => setComparar('lado')}>Side by side</button>
              {resultado && <button type="button" onClick={() => abrirVisualizador(resultado)} aria-label="Full screen" title="Full screen with details">⛶</button>}
            </div>
          </div>
          <div className="hf-vfx-palco" data-xadrez={!!transparente || undefined}>
            {video && resultado ? <ThenNow antes={urlEntrada(video.nome)} depois={transparente || urlImagem(resultado)} ehVideo={transparente ? true : undefined} modo={comparar} rotulos={['Before', 'After']} />
              : resultado ? <video src={transparente || urlImagem(resultado)} controls autoPlay loop muted playsInline />
              : video ? <video src={urlEntrada(video.nome)} controls muted playsInline />
              : app ? <><video src={`/exemplos/${app.id}.mp4?v=10`} autoPlay loop muted playsInline /><span className="hf-vfx-exemplo">Example · drop your video on the right</span></>
              : <div className="hf-img-vazio"><b>Pick an effect</b><span>Choose one on the left.</span></div>}
          </div>
          {transparente && <AjustesRecorte valor={recorte} aoMudar={setRecorte} webm={urlRecorte('webm')} mov={urlRecorte('mov')} />}
        </section>

        <aside className="hf-img-col hf-img-dir hf-vfx-dir" aria-label="Effect settings">
          {app ? (<>
            <div className="hf-vfx-cabeca">
              <video src={`/exemplos/${app.id}.mp4?v=10`} autoPlay loop muted playsInline />
              {app.id === 'maquete' && <small className="hf-selo-neon">Experimental</small>}
              <b>{app.nome}</b>
              <span>{app.frase}</span>
            </div>
      {app && (<>
        <div className="hf-barra-prompt" style={{ marginTop: app.id === 'maquete' ? 12 : 20 }}
          onDragOver={(e) => { if (precisaVideo && e.dataTransfer.types.includes('Files')) e.preventDefault() }}
          onDrop={(e) => {
            const f = precisaVideo ? videoArrastado(e.dataTransfer) : undefined
            if (f) { e.preventDefault(); void enviarVideo(f) }
          }}>
          <div className="hf-cabeca-caixa">
            <span className="hf-passo">{app.nome}</span>
            {app.chaves && (
              <div className="hf-chave-modo" title="Simple: use your own Look image. Advanced: make the look here, step by step.">
                <span data-ativo={modoMaquete === 'simples'}>Simple</span>
                <button type="button" role="switch" aria-checked={modoMaquete === 'avancado'} aria-label="Advanced mode"
                  className="hf-chave-trilho" data-ligado={modoMaquete === 'avancado'}
                  onClick={() => setModoMaquete((m) => (m === 'avancado' ? 'simples' : 'avancado'))}>
                  <span className="hf-chave-bola" />
                </button>
                <span data-ativo={modoMaquete === 'avancado'}>Advanced</span>
              </div>
            )}
          </div>
          {app.chaves && <p className="hf-dica">{modoMaquete === 'avancado'
            ? 'Advanced · drop your gray render (Blender, Unreal…), then: 1 take screenshots, 2 make them realistic in Cinema Studio, 3 generate the video.'
            : 'Simple: drop your render and your own Look image of frame 1.'}</p>}
          <div className="hf-slots">
            {precisaVideo && (
              <label className="hf-slot" data-cheio={!!video}
                onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) e.preventDefault() }}>
                {video ? <video src={urlEntrada(video.nome)} muted /> : <span>{enviando ? 'Uploading…' : '+ Video'}</span>}
                <input type="file" accept="video/*" className="hf-arquivo" onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) void enviarVideo(f)
                }} />
              </label>
            )}
            {app.imagem && !(app.id === 'maquete' && modoMaquete === 'avancado') && <SlotImagem rotulo={app.imagem} valor={imagem} aoMudar={setImagem} />}
          </div>
          {/* Sem o render ainda, o modo Advanced nao mostrava nada e parecia nao ter mudado. */}
          {app.chaves && video && modoMaquete === 'simples' && (
            <div className="hf-chaves">
              <video ref={player} src={urlEntrada(video.nome)} controls muted
                onLoadedMetadata={(e) => {
                  const v = e.currentTarget, r = v.videoWidth / Math.max(1, v.videoHeight)
                  setDuracao(v.duration); setInicioQ(0); setFormatoMaquete(r > 1.2 ? '16:9' : r < 0.83 ? '9:16' : '1:1')
                }} />
              {duracao > 0 && (
                <div className="hf-linha-tempo" title="Keyframes on the timeline">
                  <b className="hf-trecho-janela" style={{ left: `${(inicioQ / Math.max(1, totalQ)) * 100}%`, width: `${(durQ / Math.max(1, totalQ)) * 100}%` }} />
                  {chaves.map((c) => (
                    <i key={c.id} data-cheio={!!c.img} style={{ left: `${Math.min(100, ((c.quadro - 1) / 24 / duracao) * 100)}%` }}
                      onClick={() => { if (player.current) player.current.currentTime = (c.quadro - 1) / 24 }} />
                  ))}
                </div>
              )}
              {duracao > 0 && (
                <div className="hf-trecho">
                  {totalQ > MAX_QUADROS_MAQUETE && <p className="hf-dica">Your render is {segundos(totalQ)}. A video uses up to {segundos(MAX_QUADROS_MAQUETE)}:
                    choose where it starts and how long it is (the highlighted part).</p>}
                  <label className="hf-trecho-ctrl">
                    <span>Starts at <b>{segundos(inicioQ)}</b></span>
                    <input type="range" min={0} max={Math.max(0, totalQ - MIN_QUADROS_MAQUETE)} step={1} value={inicioQ}
                      disabled={totalQ <= MIN_QUADROS_MAQUETE} aria-label="Start of the part used" onChange={(e) => mudarInicio(Number(e.target.value))} />
                  </label>
                  <label className="hf-trecho-ctrl">
                    <span>Length <b>{segundos(durQ)}</b></span>
                    <input type="range" min={MIN_QUADROS_MAQUETE} max={maxDuracaoQ} step={8} value={durQ}
                      aria-label="Length of the video" onChange={(e) => setDuracaoQ(Number(e.target.value))} />
                  </label>
                  <button type="button" className="hf-botao-sec" onClick={() => mudarInicio(quadroAtual() - 1)}
                    title="The video starts where the player is paused">Start here</button>
                  <span className="hf-dica">Video: {segundos(inicioQ)} → {segundos(inicioQ + durQ)}</span>
                </div>
              )}
              <div className="hf-linha-controles">
                <button type="button" className="hf-botao-sec" onClick={addChave}>+ Keyframe at this frame</button>
                <button type="button" className="hf-botao-sec" onClick={() => capturar(quadroAtual())}>Capture this frame to Assets</button>
              </div>
              {chaves.map((c) => {
                const q = Math.round((c.quadro - 1) / 8) * 8 + 1
                return (
                  <div key={c.id} className="hf-chave">
                    <SlotImagem rotulo={`Frame ${c.quadro}`} valor={c.img} aoMudar={(img) => mudarChave(c.id, { img })} />
                    <EscolhaVersao versoes={versoes[c.id] ?? []} atual={c.img} aoEscolher={(img) => mudarChave(c.id, { img })} />
                    <label className="hf-equip">
                      <span className="hf-grupo-rotulo">Frame nº</span>
                      <input className="hf-campo" type="number" min={1} value={c.quadro}
                        onChange={(e) => mudarChave(c.id, { quadro: Math.max(1, Math.round(Number(e.target.value))) })} />
                      {q !== c.quadro && <small className="hf-dica">enters at frame {q} (multiples of 8)</small>}
                    </label>
                    <button type="button" className="hf-botao-sec" onClick={() => capturar(c.quadro)}>Capture</button>
                    <button type="button" className="hf-botao-sec" onClick={() => setChaves((a) => a.filter((x) => x.id !== c.id))}>Remove</button>
                  </div>
                )
              })}
              <p className="hf-dica">Frame 1 comes from the Look image. For later moments, add a keyframe, capture the gray frame,
                restyle it in the Image tab (Flux 3 with the captured frame as the base) and drop it here. 24 frames = 1 s, counted from 1 as in Blender.</p>
            </div>
          )}
          {!ehMapa && !(app.id === 'maquete' && modoMaquete === 'avancado') && <textarea aria-label="Prompt" maxLength={MAX_PROMPT} value={texto} onChange={(e) => setTexto(e.target.value)} rows={1}
            placeholder="Optional: describe what you want to see…" />}
          {ehMapa && <p className="hf-dica">Up to the first 20 seconds of the video. EXR keeps the real depth values (32-bit, Z channel), one file per frame.</p>}
          {!(app.id === 'maquete' && modoMaquete === 'avancado') && <div className="hf-linha-controles">
            {ehMapa && <Chips rotulo="Look" opcoes={[{ id: 'gray', rotulo: 'Gray' }, { id: 'inferno', rotulo: 'Color' }]} valor={corMapa} aoMudar={setCorMapa} />}
            {ehMapa && <label className="hf-toggle"><input type="checkbox" checked={exr} onChange={(e) => setExr(e.target.checked)} /> EXR too</label>}
            {app.id === 'maquete' && ladosTela.length > 0 && (
              <Chips rotulo="Resolution" opcoes={ladosTela} valor={lado} aoMudar={setLadoEscolhido} />
            )}
            {app.id === 'maquete' && avisoLado && <span className="hf-erro hf-aviso-lado">{avisoLado}</span>}
            {semPlaca && <span className="hf-erro">3D render → Video needs a graphics card with at least 16 GB of VRAM (this one has {vramGb} GB).</span>}
            {app.formatos && <Chips rotulo="Output format" opcoes={['16:9', '9:16', '1:1'].map((f) => ({ id: f, rotulo: f }))} valor={formato} aoMudar={setFormato} />}
            {semPacote && <span className="hf-dica">Install “Video depth map” in Config Models to use this app.</span>}
            {bloqueado && <span className="hf-dica">This effect is not on Comfy Cloud yet. Switch to Local to use it.</span>}
            <BotaoGerar rotulo={app.id === 'maquete' && modoMaquete === 'avancado' ? 'Generate video ✦' : '✦ Apply effect'} est={custo} desligado={!pronto} aoClicar={aplicar} />
          </div>}
          {erro && !(app.chaves && video && modoMaquete === 'avancado') && <p className="hf-erro">{erro}</p>}
        </div>
        </>)}
          </>) : <p className="hf-dica">Pick an effect on the left.</p>}
        </aside>
      </div>
      {app && (<>
        {app.chaves && video && modoMaquete === 'avancado' && (
          // Caixa separada do envio do render: os 3 passos (30/10/2026).
          <div className="hf-barra-prompt hf-caixa-passos">
            <div className="hf-passos-maquete">
              <div className="hf-passos-barra" role="tablist" aria-label="Steps">
                {([[1, 'Frames', !!cinzas[0]], [2, 'Cinema Studio', !!imagem], [3, 'Video', false]] as const).map(([n, nome, feito]) => (
                  <button key={n} type="button" role="tab" aria-selected={passo === n} data-ativo={passo === n}
                    data-feito={feito && passo !== n} data-futuro={n > passo && !feito} onClick={() => setPasso(n)}>
                    <i className="hf-passo-num" aria-hidden>{feito && passo !== n ? '✓' : n}</i>
                    <span><b>Step {n}</b> · {nome}</span>
                  </button>
                ))}
              </div>

              {passo === 1 && (
                <div className="hf-chaves">
                  <div className="hf-momentos-intro">
                    <h3>Play the render and mark the moments to redraw</h3>
                    <p className="hf-dica">Frame 1 is always used. Pause where the camera shows something new (it turns, gets close, goes around
                      an object) and take a screenshot, or let the app pick them. Up to {MAX_MOMENTOS} frames.</p>
                  </div>
                  <video ref={player} src={urlEntrada(video.nome)} controls muted
                    onLoadedMetadata={(e) => {
                      const v = e.currentTarget, r = v.videoWidth / Math.max(1, v.videoHeight)
                      setDuracao(v.duration); setInicioQ(0); setFormatoMaquete(r > 1.2 ? '16:9' : r < 0.83 ? '9:16' : '1:1')
                    }} />
                  {duracao > 0 && (
                    <div className="hf-linha-tempo" title="Keyframes on the timeline">
                      <b className="hf-trecho-janela" style={{ left: `${(inicioQ / Math.max(1, totalQ)) * 100}%`, width: `${(durQ / Math.max(1, totalQ)) * 100}%` }} />
                      {chaves.map((c) => (
                        <i key={c.id} data-cheio={!!c.img} style={{ left: `${Math.min(100, ((c.quadro - 1) / 24 / duracao) * 100)}%` }}
                          onClick={() => { if (player.current) player.current.currentTime = (c.quadro - 1) / 24 }} />
                      ))}
                    </div>
                  )}
                  {duracao > 0 && (
                    <div className="hf-trecho">
                      {totalQ > MAX_QUADROS_MAQUETE && <p className="hf-dica">Your render is {segundos(totalQ)}. A video uses up to {segundos(MAX_QUADROS_MAQUETE)}:
                        choose where it starts and how long it is (the highlighted part).</p>}
                      <label className="hf-trecho-ctrl">
                        <span>Starts at <b>{segundos(inicioQ)}</b></span>
                        <input type="range" min={0} max={Math.max(0, totalQ - MIN_QUADROS_MAQUETE)} step={1} value={inicioQ}
                          disabled={totalQ <= MIN_QUADROS_MAQUETE} aria-label="Start of the part used" onChange={(e) => mudarInicio(Number(e.target.value))} />
                      </label>
                      <label className="hf-trecho-ctrl">
                        <span>Length <b>{segundos(durQ)}</b></span>
                        <input type="range" min={MIN_QUADROS_MAQUETE} max={maxDuracaoQ} step={8} value={durQ}
                          aria-label="Length of the video" onChange={(e) => setDuracaoQ(Number(e.target.value))} />
                      </label>
                      <button type="button" className="hf-botao-sec" onClick={() => mudarInicio(quadroAtual() - 1)}
                        title="The video starts where the player is paused">Start here</button>
                      <span className="hf-dica">Video: {segundos(inicioQ)} → {segundos(inicioQ + durQ)}</span>
                    </div>
                  )}
                  <div className="hf-linha-controles hf-momentos-acoes">
                    <button type="button" className="hf-botao-sec" onClick={addChave} disabled={cheio}
                      title={cheio ? `Up to ${MAX_MOMENTOS} frames: remove one first` : 'Screenshot of the render where it is paused'}>Screenshot here</button>
                    <button type="button" className="hf-botao-sec" onClick={espalharChaves} disabled={cheio}
                      title={cheio ? `Up to ${MAX_MOMENTOS} frames: remove one first` : 'Screenshots spread evenly across the render'}>Auto screenshot</button>
                  </div>
                  <div className="hf-prints hf-momentos hf-prints-4">
                    {[0, ...chaves.map((c) => c.id)].map((id) => {
                      const alvo = alvoDe(id)
                      return (
                        <figure key={id} className="hf-print hf-momento" data-fora={!dentro(alvo.quadro)}
                          title={dentro(alvo.quadro) ? undefined : 'Outside the part that becomes video: not used'}>
                          <button type="button" className="hf-momento-ver" title="Show this moment in the player"
                            onClick={() => { if (player.current) player.current.currentTime = (alvo.quadro - 1) / 24 }}>
                            {cinzas[id] ? <img src={urlEntrada(cinzas[id].nome)} alt={`Render at frame ${alvo.quadro}`} /> : <span>Taking the screenshot…</span>}
                            <figcaption><b>Frame {alvo.quadro}</b> · {((alvo.quadro - 1) / 24).toFixed(1)} s</figcaption>
                          </button>
                          {id !== 0 && <button type="button" className="hf-momento-tirar" aria-label={`Remove frame ${alvo.quadro}`} title="Remove this moment"
                            onClick={() => setChaves((a) => a.filter((x) => x.id !== id))}>×</button>}
                        </figure>
                      )
                    })}
                  </div>
                  <div className="hf-linha-controles hf-passo-nav">
                    <button type="button" className="hf-gerar hf-nav-seguir" onClick={() => setPasso(2)}>Step 2 · Cinema Studio →</button>
                  </div>
                </div>
              )}

              {passo === 2 && (
                <div className="hf-cinema hf-cinema-maquete">
                  <div className="hf-momentos-intro">
                    <h3>Cinema Studio</h3>
                    <p className="hf-dica">Turn each screenshot into a realistic frame: describe the scene, add your cast and the place,
                      and shoot until each frame looks right. The camera angle comes from your render.</p>
                  </div>
                  <section className="hf-painel-passo" aria-label="Scene and cast">
                    <div className="hf-rotulo-cena">
                      <span className="hf-passo">Scene</span>
                      <span className="hf-dica">What the gray blocks become, the place, the time of day and the mood. No camera words.</span>
                      <button type="button" className="hf-escrever-neon" disabled={!!escrevendo} onClick={() => escrever('cena')}
                        title="Type a few words (any language) and the local text model writes the scene">
                        {escrevendo === 'cena' ? 'Writing…' : '✦ Write with AI'}</button>
                    </div>
                    <textarea aria-label="Scene description" maxLength={MAX_PROMPT} className="hf-cinema-texto" value={texto}
                      onChange={(e) => setTexto(e.target.value)} rows={3}
                      placeholder="What the gray blocks become, where, the time of day and the mood: a green Lamborghini Huracan drives down a lonely desert highway at golden hour…" />
                    <div className="hf-grupos-cast">
                      <div className="hf-grupo-cast">
                        <div className="hf-grupo-cabeca">
                          <span className="hf-passo">Cast</span>
                          <small>{refsOk.length}/{MAX_REFS_MAQUETE}</small>
                        </div>
                        <p className="hf-dica">A character sheet of each element, named under its picture.</p>
                        <div className="hf-cast">
                          {refsMaquete.map((r, i) => (
                            <div key={i} className="hf-cast-item">
                              <SlotImagem rotulo={`Cast ${i + 1}`} valor={r}
                                aoMudar={(v) => setRefsMaquete((a) => {
                                  const n = a.map((x, j) => (j === i ? v : x)).filter((x, j) => x || j === a.length - 1 || j === i)
                                  return n.length < MAX_REFS_MAQUETE && n[n.length - 1] ? [...n, null] : n
                                })} />
                              {r && <label className="hf-nome-cast" data-vazio={!(nomesRefs[i] ?? '').trim()}>
                                <small>Name</small>
                                <input className="hf-campo" aria-label={`Name of cast ${i + 1}`} maxLength={200}
                                  placeholder="e.g. airplane" value={nomesRefs[i] ?? ''}
                                  onChange={(e) => setNomesRefs((a) => { const n = [...a]; n[i] = e.target.value; return n })} />
                              </label>}
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className="hf-grupo-cast">
                        <div className="hf-grupo-cabeca">
                          <span className="hf-passo">Scenery</span>
                          <small>optional</small>
                        </div>
                        <p className="hf-dica">A picture of the place.</p>
                        <div className="hf-cast">
                          {cenarios.map((r, i) => (
                            <div key={i} className="hf-cast-item">
                              <SlotImagem rotulo={`Scenery ${i + 1}`} valor={r}
                                aoMudar={(v) => setCenarios((a) => {
                                  const n = a.map((x, j) => (j === i ? v : x)).filter((x, j) => x || j === a.length - 1 || j === i)
                                  return n.length < MAX_CENARIOS && n[n.length - 1] ? [...n, null] : n
                                })} />
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </section>
                  <section className="hf-painel-passo" aria-label="Model and frames">
                    <div className="hf-modelo-quadros">
                      <span className="hf-passo">Model</span>
                      <select className="hf-select" value={modeloQuadro} aria-label="Image model"
                        onChange={(e) => setModeloQuadro(e.target.value as ModeloQuadro)}>
                        <optgroup label="Local · your GPU">
                          {MODELOS_QUADRO.filter((m) => !MODELOS_QUADRO_API.has(m.id)).map((m) => <option key={m.id} value={m.id}>{m.rotulo}</option>)}
                        </optgroup>
                        <optgroup label="Comfy Cloud · credits">
                          {MODELOS_QUADRO.filter((m) => MODELOS_QUADRO_API.has(m.id)).map((m) => (
                            <option key={m.id} value={m.id} disabled={!pagosOk}>{m.rotulo}{pagosOk ? '' : temChave
                              ? ' (turn on Paid API models in Config Models)' : ' (add your Comfy key in Config Models)'}</option>
                          ))}
                        </optgroup>
                      </select>
                      {ehApi && (
                        <span className="hf-ajuda">
                          <button type="button" aria-label="About the cost" aria-describedby="ajuda-custo-quadro">?</button>
                          <span role="tooltip" id="ajuda-custo-quadro">Runs on Comfy Cloud with your credits: {rotuloCusto(custoVersao) || '…'} per take.
                            The video itself still runs on your GPU.</span>
                        </span>
                      )}
                      {vazios.length > 1 && (
                        <button type="button" className="hf-gerar hf-shoot-todos" onClick={() => void preencherQuadros()}
                          disabled={!podeDesenhar || !!preenchendo || gerando !== null}
                          title={podeDesenhar ? 'One take for each frame without an image, one after the other' : faltaParaDesenhar}>
                          ✦ Shoot all {vazios.length} frames{ehApi && rotuloCusto(custoVersao) ? ` · ${rotuloCusto(custoVersao)} each` : ''}</button>
                      )}
                    </div>
                    <div className="hf-quadros-dir">
                      {[0, ...chavesUsadas.map((c) => c.id)].map((id) => {
                        const alvo = alvoDe(id)
                        const escolhida = id === 0 ? imagem : chaves.find((c) => c.id === id)?.img ?? null
                        const escolher = (r: Referencia) => (id === 0 ? setImagem(r) : mudarChave(id, { img: r }))
                        const lista = versoes[id] ?? []
                        return (
                          <div key={id} className="hf-quadro-dir">
                            <div className="hf-quadro-topo">
                              <b>{id === 0 ? 'Frame 1' : `Frame ${alvo.quadro}`}</b>
                              <span className="hf-dica">{((alvo.quadro - 1) / 24).toFixed(1)} s</span>
                              {escolhida && <a className="hf-botao-sec hf-baixar" href={urlEntrada(escolhida.nome)} download
                                title="Download the take to fix it in another app, then bring it back with Replace">Download</a>}
                              <label className="hf-botao-sec hf-baixar" title="Use your own image for this frame (a fixed version of a take)">
                                Replace…
                                <input type="file" accept="image/*" className="hf-arquivo" onChange={(e) => {
                                  const f = e.target.files?.[0]
                                  if (f) void substituir(id, f)
                                  e.target.value = ''
                                }} />
                              </label>
                            </div>
                            <Comparador antes={cinzas[id] ? urlEntrada(cinzas[id].nome) : null}
                              depois={escolhida ? urlEntrada(escolhida.nome) : null} proporcao={formatoMaquete} gerando={gerando === id}
                              rotuloDepois={escolhida && lista.some((v) => v.nome === escolhida.nome) ? `Take ${lista.findIndex((v) => v.nome === escolhida.nome) + 1}` : 'Your image'}
                              aoSoltar={(f) => void substituir(id, f)} />
                            {lista.length > 1 && (
                              <div className="hf-quadro-faixa">
                                {lista.map((v, n) => (
                                  <button key={v.nome} type="button" className="hf-versao hf-versao-mini" aria-pressed={escolhida?.nome === v.nome}
                                    title={`Use take ${n + 1} in the video`} onClick={() => escolher(v)}>
                                    <img src={urlEntrada(v.nome)} alt={`Take ${n + 1}`} />
                                    <small>Take {n + 1}</small>
                                  </button>
                                ))}
                              </div>
                            )}
                            <div className="hf-lado-objeto">
                              <span className="hf-grupo-rotulo">Object seen from</span>
                              <div className="hf-segmentos" role="radiogroup" aria-label={`Object seen from, frame ${alvo.quadro}`}>
                                {VISTA_OPCOES.map((o) => (
                                  <button key={o.id} type="button" role="radio" aria-checked={(alvo.vista ?? 'auto') === o.id}
                                    data-ativo={(alvo.vista ?? 'auto') === o.id}
                                    onClick={() => (id === 0 ? setVistaLook(o.id as Vista) : mudarChave(id, { vista: o.id as Vista }))}>{o.rotulo}</button>
                                ))}
                              </div>
                            </div>
                            <details className="hf-ver-prompt">
                              <summary>{promptsEditados[id] !== undefined ? 'Prompt (edited)' : 'See and edit the prompt'}
                                {/* Dentro do summary: o clique so copia, sem abrir/fechar. */}
                                <button type="button" className="hf-botao-sec hf-copiar"
                                  onClick={(e) => { e.preventDefault(); void copiar(id) }}>{copiado === id ? 'Copied' : 'Copy'}</button>
                              </summary>
                              <textarea className="hf-prompt-quadro" aria-label={`Prompt of frame ${alvo.quadro}`} maxLength={MAX_PROMPT} rows={4}
                                value={promptsEditados[id] ?? promptDoQuadro(id)}
                                onChange={(e) => setPromptsEditados((x) => ({ ...x, [id]: e.target.value }))} />
                              {promptsEditados[id] !== undefined && (
                                <div className="hf-linha-controles">
                                  <span className="hf-dica">Edited by you: the scene, cast names and side no longer change it.</span>
                                  <button type="button" className="hf-botao-sec hf-copiar"
                                    onClick={() => setPromptsEditados((x) => { const n = { ...x }; delete n[id]; return n })}>Reset</button>
                                </div>
                              )}
                            </details>
                            <div className="hf-shoot-linha">
                              <button type="button" className="hf-gerar hf-shoot" disabled={!podeDesenhar || gerando !== null || !!preenchendo}
                                onClick={() => gerarVersao(id)}>
                                {gerando === id ? 'Shooting…' : lista.length ? '↻ Reshoot' : '✦ Shoot this frame'}
                                {ehApi && rotuloCusto(custoVersao) ? ` · ${rotuloCusto(custoVersao)}` : ''}</button>
                              {!podeDesenhar ? <span className="hf-erro">{faltaParaDesenhar}</span>
                                : escolhida && lista.some((v) => v.nome === escolhida.nome)
                                  ? <span className="hf-dica">Take {lista.findIndex((v) => v.nome === escolhida.nome) + 1} goes into the video. Drag the line to compare.</span>
                                  : gerando !== null && gerando !== id ? <span className="hf-dica">Another frame is being shot…</span> : null}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    {preenchendo && <p className="hf-dica" role="status">{preenchendo}</p>}
                  </section>

                  <div className="hf-nav-passos">
                    <button type="button" className="hf-nav-voltar" onClick={() => setPasso(1)}>← Step 1 · Frames</button>
                    {!imagem && <span className="hf-dica">Shoot frame 1 to go on.</span>}
                    <button type="button" className="hf-gerar hf-nav-seguir" onClick={() => setPasso(3)} disabled={!imagem}>Step 3 · Video →</button>
                  </div>
                </div>
              )}

              {passo === 3 && (
                <div className="hf-refs-maquete">
                  <div className="hf-momentos-intro">
                    <h3>Generate the video</h3>
                    <p className="hf-dica">LTX keeps the camera and motion of your render and passes through these frames at their moments.
                      Frames without an image are skipped.</p>
                  </div>
                  <div className="hf-prints hf-prints-4">
                    {[0, ...chavesUsadas.map((c) => c.id)].map((id) => {
                      const alvo = alvoDe(id)
                      const img = id === 0 ? imagem : chaves.find((c) => c.id === id)?.img ?? null
                      return (
                        <figure key={id} className="hf-print">
                          {img ? <img src={urlEntrada(img.nome)} alt={`Frame ${alvo.quadro}`} /> : <span>No image: skipped</span>}
                          <figcaption><b>{id === 0 ? 'Frame 1' : `Frame ${alvo.quadro}`}</b> · {((alvo.quadro - 1) / 24).toFixed(1)} s</figcaption>
                        </figure>
                      )
                    })}
                  </div>
                  {!imagem && <p className="hf-erro">Frame 1 needs an image: go back to step 2.</p>}
                </div>
              )}
            </div>
            {passo === 3 && <div className="hf-linha-controles">
              {ladosTela.length > 0 && <Chips rotulo="Resolution" opcoes={ladosTela} valor={lado} aoMudar={setLadoEscolhido} />}
              {avisoLado && <span className="hf-erro hf-aviso-lado">{avisoLado}</span>}
              {semPlaca && <span className="hf-erro">3D render → Video needs a graphics card with at least 16 GB of VRAM (this one has {vramGb} GB).</span>}
              <div className="hf-gerar-grupo">
                <button type="button" className="hf-nav-voltar" onClick={() => setPasso(2)}>← Step 2 · Cinema Studio</button>
                <BotaoGerar rotulo="Generate video ✦" est={custo} desligado={!pronto} aoClicar={aplicar} />
              </div>
            </div>}
            {erro && <p className="hf-erro">{erro}</p>}
          </div>
        )}
      </>)}

      <Galeria tipo="video">
        {minhas.map((t) => t.alpha && t.estado === 'pronto' ? (
          <div key={t.id} className="hf-com-exr">
            <CartaoTarefa t={t} />
            <a className="hf-botao-sec" href={`/api/alpha/${t.id}?formato=webm`} download>Transparent video (.webm)</a>
            <a className="hf-botao-sec" href={`/api/alpha/${t.id}?formato=mov`} download>ProRes 4444 with alpha (.mov)</a>
          </div>
        ) : t.exr && t.estado === 'pronto' ? (
          <div key={t.id} className="hf-com-exr">
            <CartaoTarefa t={t} />
            <a className="hf-botao-sec" href={`/api/profundidade/exr/${t.id}`} download>Download EXR frames (.zip)</a>
          </div>
        ) : <CartaoTarefa key={t.id} t={t} />)}
      </Galeria>
    </div>
  )
}
