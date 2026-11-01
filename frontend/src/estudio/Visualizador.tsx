import { useEffect, useRef, useState } from 'react'
import { urlEntrada, urlImagem, type ItemGaleria } from '../api'
import { IconeX, eAudio, eVideo } from './comum'

// Full-size viewer for every generated file of the new studio, local or cloud.
// Any <Midia> opens it; the arrows walk through the files on the page, in the
// order they appear. On the side: what the file is, how it was made, and
// actions to download it or reuse its prompt.

type Arquivo = { nome: string; subpasta: string }

/** Opens the viewer on this file, with every file on the page as its neighbours. */
/** Imagem que comeca inteira na tela (fit); zoom pela roda ou botoes, arrasta para mover. */
function ImagemZoom({ src }: { src: string }) {
  const [z, setZ] = useState(1)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const arrasto = useRef<{ x: number; y: number } | null>(null)
  const mudar = (nz: number) => { const v = Math.min(8, Math.max(1, nz)); setZ(v); if (v === 1) setPos({ x: 0, y: 0 }) }
  return (
    <div className="hf-vis-zoom" data-zoom={z > 1 ? '1' : undefined}
      onWheel={(e) => mudar(z * (e.deltaY < 0 ? 1.15 : 1 / 1.15))}
      onDoubleClick={() => mudar(z > 1 ? 1 : 2)}
      onPointerDown={(e) => { if (z > 1) { arrasto.current = { x: e.clientX - pos.x, y: e.clientY - pos.y }; (e.target as Element).setPointerCapture(e.pointerId) } }}
      onPointerMove={(e) => { if (arrasto.current) setPos({ x: e.clientX - arrasto.current.x, y: e.clientY - arrasto.current.y }) }}
      onPointerUp={() => { arrasto.current = null }}>
      <img src={src} alt="" draggable={false} style={{ transform: `translate(${pos.x}px, ${pos.y}px) scale(${z})` }} />
      <div className="hf-vis-zoombar" onPointerDown={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
        <button onClick={() => mudar(z / 1.25)} aria-label="Zoom out">−</button>
        <button onClick={() => mudar(1)} aria-label="Fit">{Math.round(z * 100)}%</button>
        <button onClick={() => mudar(z * 1.25)} aria-label="Zoom in">+</button>
      </div>
    </div>
  )
}

export function abrirVisualizador(atual: Arquivo) {
  const lista: Arquivo[] = [...document.querySelectorAll<HTMLElement>('[data-midia]')]
    .map((e) => ({ nome: e.dataset.nome!, subpasta: e.dataset.subpasta! }))
    .filter((a, i, todos) => todos.findIndex((b) => b.nome === a.nome && b.subpasta === a.subpasta) === i)
  const indice = Math.max(0, lista.findIndex((a) => a.nome === atual.nome && a.subpasta === atual.subpasta))
  window.dispatchEvent(new CustomEvent('abrir-visualizador', { detail: { lista: lista.length ? lista : [atual], indice } }))
}

/** Sends a prompt back to the tab that is open (each tab listens with useReusarPrompt). */
export function reusarPrompt(prompt: string) {
  window.dispatchEvent(new CustomEvent('reusar-prompt', { detail: prompt }))
}

/** O que o "Recreate" devolve a aba Image: o registro da galeria (prompt e parametros). */
export type Receita = { modelo: string; prompt: string; parametros: Record<string, unknown> }
let recriarPendente: Receita | null = null

/** "Recreate": vai para a aba Image e preenche prompt, imagens, modelo e proporcao. */
export function recriar(r: Receita, destino = '#image') {
  recriarPendente = r
  if (location.hash !== destino && !location.hash.startsWith(destino + '/')) { location.hash = destino; return }  // a aba monta e pega
  window.dispatchEvent(new Event('recriar'))
}

/** A aba Image pega a receita ao montar e quando o evento chega com ela aberta. */
export function useRecriar(aoRecriar: (r: Receita) => void) {
  useEffect(() => {
    const pegar = () => { if (recriarPendente) { const r = recriarPendente; recriarPendente = null; aoRecriar(r) } }
    pegar()
    window.addEventListener('recriar', pegar)
    return () => window.removeEventListener('recriar', pegar)
  }, [aoRecriar])
}

export function useReusarPrompt(aoReusar: (prompt: string) => void) {
  useEffect(() => {
    const ao = (e: Event) => aoReusar((e as CustomEvent<string>).detail)
    window.addEventListener('reusar-prompt', ao)
    return () => window.removeEventListener('reusar-prompt', ao)
  }, [aoReusar])
}

const tamanho = (b?: number) => !b ? '—' : b < 1048576 ? `${Math.round(b / 1024)} KB` : `${(b / 1048576).toFixed(1)} MB`
const tempo = (s?: number) => !s ? '—' : s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`
const quando = (t?: number) => !t ? '—' : new Date(t * 1000).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

// Readable names for the ids saved with each file. Unknown ids show as saved.
const NOMES: Record<string, string> = {
  ltx: 'LTX 2.5', ltx23: 'LTX 2.3', minimax: 'MiniMax H3', krea: 'Krea 2 Turbo', kroma: 'Kroma', qwen21: 'Qwen Image 2.1',
  klein: 'Flux 2 Klein 9B', flux3: 'Flux 3 Klein', zimage: 'Z-Image Turbo', mage: 'Mage Flow', ideogram: 'Ideogram 4',
  transformar_video: 'LTX VFX app', video: 'Video', musica: 'Music', voz: 'Voice', avatar: 'Lip sync', genjutsu: 'Genjutsu',
  trocar: 'Flux 2 Klein · swap', flux3ref: 'Flux 3 · references', qwen21edit: 'Qwen 2.1 · edit', instrucao: 'Mage · edit', qwen: 'Qwen Image Edit',
}
const EFEITOS: Record<string, string> = { noite: 'Day → Night', limpar: 'Remove people', agua: 'Add water', trocar: 'Swap character',
  expandir: 'Expand frame', cor: 'Colorize', nitidez: 'Unblur', restaurar: 'Restore', maquete: '3D render → Video' }
const nome = (id?: unknown) => (id ? NOMES[String(id)] ?? String(id) : '')

const MODOS: Record<string, string> = { texto: 'Text to video', imagem: 'Image to video', primeiro_ultimo: 'First & last frame', referencia: 'References to video' }

// Then & Now: o arquivo de origem de um resultado (o video antes do efeito, a foto
// antes da edicao), lido de referencias_usadas. Tres formas: "editor/arquivo" (da
// galeria), "entrada:arquivo" (video enviado) e "ref_....png" (imagem enviada).
function origemDe(info: ItemGaleria | null, atual: string): string | null {
  const refs = (info?.parametros as Record<string, unknown> | undefined)?.referencias_usadas as string[] | undefined
  const r = refs?.[0]
  if (!r) return null
  const nomeR = r.startsWith('entrada:') ? r.slice(8) : r.includes('/') ? r.split('/').pop()! : r
  // So compara o que e do mesmo tipo (video com video, imagem com imagem).
  if (eVideo(nomeR) !== eVideo(atual) || eAudio(nomeR) || eAudio(atual)) return null
  if (r.startsWith('entrada:')) return urlEntrada(nomeR)
  if (r.includes('/')) { const [sub, ...resto] = r.split('/'); return urlImagem({ nome: resto.join('/'), subpasta: sub }) }
  return urlEntrada(r)
}

/** Antes e depois, lado a lado ou com cortina; videos andam juntos. */
export function ThenNow({ antes, depois, modo, rotulos = ['Then', 'Now'] }: { antes: string; depois: string; modo: 'lado' | 'cortina'; rotulos?: [string, string] }) {
  const [corte, setCorte] = useState(50)
  const vA = useRef<HTMLVideoElement>(null)
  const vD = useRef<HTMLVideoElement>(null)
  const video = eVideo(depois.split('nome=')[1]?.split('&')[0] ?? '')
  useEffect(() => {
    if (!video) return
    const t = setInterval(() => {
      const a = vA.current, d = vD.current
      if (a && d && Math.abs(a.currentTime - d.currentTime) > 0.12) a.currentTime = d.currentTime
    }, 400)
    return () => clearInterval(t)
  }, [video, antes, depois])
  const midia = (src: string, ref: React.RefObject<HTMLVideoElement | null>) => video
    ? <video ref={ref} src={src} autoPlay loop muted playsInline />
    : <img src={src} alt="" />
  if (modo === 'lado') return (
    <div className="hf-tn-lado">
      <figure>{midia(antes, vA)}<figcaption>{rotulos[0]}</figcaption></figure>
      <figure>{midia(depois, vD)}<figcaption>{rotulos[1]}</figcaption></figure>
    </div>
  )
  return (
    <div className="hf-tn-cortina">
      {midia(depois, vD)}
      <div className="hf-tn-antes" style={{ clipPath: `inset(0 ${100 - corte}% 0 0)` }}>{midia(antes, vA)}</div>
      <div className="hf-tn-linha" style={{ left: `${corte}%` }} />
      <span className="hf-tn-rotulo" data-lado="esq">{rotulos[0]}</span><span className="hf-tn-rotulo" data-lado="dir">{rotulos[1]}</span>
      <input type="range" min={0} max={100} value={corte} onChange={(e) => setCorte(Number(e.target.value))} aria-label="Slide between before and after" />
    </div>
  )
}

function Linha({ rotulo, valor }: { rotulo: string; valor?: string | number | null }) {
  if (valor === undefined || valor === null || valor === '') return null
  return <div className="hf-vis-linha"><span>{rotulo}</span><b>{valor}</b></div>
}

export default function Visualizador() {
  const [lista, setLista] = useState<Arquivo[]>([])
  const [i, setI] = useState(0)
  const [info, setInfo] = useState<ItemGaleria | null>(null)
  const [copiado, setCopiado] = useState('')
  const [comparar, setComparar] = useState<'' | 'lado' | 'cortina'>('')
  const [receita, setReceita] = useState(false)
  const atual = lista[i]

  useEffect(() => {
    const ao = (e: Event) => { const d = (e as CustomEvent).detail; setLista(d.lista); setI(d.indice) }
    window.addEventListener('abrir-visualizador', ao)
    return () => window.removeEventListener('abrir-visualizador', ao)
  }, [])

  useEffect(() => {
    if (!atual) return
    setInfo(null); setCopiado(''); setComparar(''); setReceita(false)
    fetch(`/api/galeria/receita?subpasta=${encodeURIComponent(atual.subpasta)}&nome=${encodeURIComponent(atual.nome)}`)
      .then((r) => setReceita(r.ok)).catch(() => setReceita(false))
    fetch(`/api/galeria/arquivo?subpasta=${encodeURIComponent(atual.subpasta)}&nome=${encodeURIComponent(atual.nome)}`)
      .then((r) => (r.ok ? r.json() : null)).then(setInfo).catch(() => setInfo(null))
  }, [atual?.nome, atual?.subpasta])

  useEffect(() => {
    if (!atual) return
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLista([])
      if (e.key === 'ArrowRight') setI((x) => Math.min(lista.length - 1, x + 1))
      if (e.key === 'ArrowLeft') setI((x) => Math.max(0, x - 1))
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [atual, lista.length])

  if (!atual) return null
  const url = urlImagem({ nome: atual.nome, subpasta: atual.subpasta })
  const p = (info?.parametros ?? {}) as Record<string, unknown>
  const prompt = info?.prompt || info?.prompt_final || ''
  const origem = origemDe(info, atual.nome)
  const copiar = async (texto: string, qual: string) => {
    try { await navigator.clipboard.writeText(texto); setCopiado(qual) } catch { setCopiado('') }
  }
  const resumo = [
    `File: ${atual.subpasta}/${atual.nome}`,
    info && `Model: ${info.rotulo || info.modelo}${p.modelo_video ? ` (${p.modelo_video})` : ''}`,
    info?.largura ? `Size: ${info.largura} × ${info.altura}` : '',
    p.seed !== undefined ? `Seed: ${p.seed}` : '',
    prompt && `Prompt: ${prompt}`,
  ].filter(Boolean).join('\n')

  return (
    <div className="hf-vis-fundo" onClick={() => setLista([])}>
      <div className="hf-vis" role="dialog" aria-label="Viewer" onClick={(e) => e.stopPropagation()}>
        <div className="hf-vis-palco">
          {i > 0 && <button className="hf-vis-seta" data-lado="esq" onClick={() => setI(i - 1)} aria-label="Previous">‹</button>}
          {comparar && origem ? <ThenNow key={url + comparar} antes={origem} depois={url} modo={comparar} />
            : eVideo(atual.nome) ? <video key={url} src={url} controls autoPlay loop playsInline />
            : eAudio(atual.nome) ? <audio key={url} src={url} controls autoPlay />
              : <ImagemZoom key={url} src={url} />}
          {i < lista.length - 1 && <button className="hf-vis-seta" data-lado="dir" onClick={() => setI(i + 1)} aria-label="Next">›</button>}
          {lista.length > 1 && <span className="hf-vis-conta">{i + 1} / {lista.length}</span>}
        </div>
        <aside className="hf-vis-lado">
          <button className="hf-vis-fechar" onClick={() => setLista([])} aria-label="Close"><IconeX tamanho={14} /></button>
          <span className="hf-vis-titulo">Details</span>
          {info ? <>
            <Linha rotulo="Resolution" valor={info.largura ? `${info.largura} × ${info.altura} · ${((info.largura * info.altura) / 1e6).toFixed(1)} MP` : null} />
            <Linha rotulo="Length" valor={info.duracao_video ? `${info.duracao_video.toFixed(2)} s${info.fps ? ` · ${info.fps} fps` : ''}` : null} />
            <Linha rotulo="Generation time" valor={tempo(info.duracao)} />
            <Linha rotulo="File" valor={tamanho(info.bytes)} />
            <Linha rotulo="Created" valor={quando(info.criada_em)} />
            <Linha rotulo="Cost" valor={info.custo_usd ? `$${info.custo_usd.toFixed(3)}` : atual.nome.startsWith('nuvem_') ? 'Comfy credits' : 'Free (your GPU)'} />
            <hr />
            <Linha rotulo="Model" valor={info.modelo === 'video' ? nome(p.modelo_video) : (!info.teste && info.rotulo) || nome(info.modelo)} />
            <Linha rotulo="Effect" valor={info.modelo === 'transformar_video' && p.efeito_video ? EFEITOS[String(p.efeito_video)] ?? String(p.efeito_video) : null} />
            <Linha rotulo="Mode" valor={info.modelo === 'video' && p.modo_video ? MODOS[String(p.modo_video)] ?? String(p.modo_video) : null} />
            <Linha rotulo="Seed" valor={p.seed !== undefined ? String(p.seed) : null} />
            <Linha rotulo="Aspect" valor={(p.proporcao_video ?? p.proporcao) as string} />
            <Linha rotulo="Sound" valor={p.com_audio === undefined || !eVideo(atual.nome) ? null : p.com_audio ? 'yes' : 'no'} />
            {prompt && <>
              <hr />
              <span className="hf-vis-titulo">Prompt</span>
              <p className="hf-vis-prompt">{prompt}</p>
            </>}
          </> : <p className="hf-dica">No details saved for this file.</p>}
          {origem && <>
            <span className="hf-vis-titulo">Then &amp; Now</span>
            <div className="hf-tn-botoes">
              <button className="hf-vis-botao" data-ativo={comparar === ''} aria-pressed={comparar === ''} onClick={() => setComparar('')}>Result</button>
              <button className="hf-vis-botao" data-ativo={comparar === 'lado'} aria-pressed={comparar === 'lado'} onClick={() => setComparar('lado')}>◧ Split</button>
              <button className="hf-vis-botao" data-ativo={comparar === 'cortina'} aria-pressed={comparar === 'cortina'} onClick={() => setComparar('cortina')}>⇹ Slide</button>
            </div>
          </>}
          <div className="hf-vis-acoes">
            <a className="hf-vis-botao" href={url} download={atual.nome}>⬇ Download</a>
            {receita && <a className="hf-vis-botao" href={`/api/galeria/receita?subpasta=${encodeURIComponent(atual.subpasta)}&nome=${encodeURIComponent(atual.nome)}`}
              download title="The exact ComfyUI graph that made this file. Drag it onto the ComfyUI canvas.">⬡ Node recipe</a>}
            {prompt && info && !eVideo(atual.nome) && !eAudio(atual.nome) && <button className="hf-vis-botao"
              title="Back to the Image tab with this prompt, its reference images, model and aspect ratio"
              onClick={() => { recriar({ modelo: info.modelo, prompt, parametros: p }); setLista([]) }}>⟲ Recreate</button>}
            {prompt && <button className="hf-vis-botao" onClick={() => { reusarPrompt(prompt); setLista([]) }}>↺ Reuse prompt</button>}
            {prompt && <button className="hf-vis-botao" onClick={() => copiar(prompt, 'prompt')}>{copiado === 'prompt' ? '✓ Copied' : '⧉ Copy prompt'}</button>}
            <button className="hf-vis-botao" onClick={() => copiar(resumo, 'resumo')}>{copiado === 'resumo' ? '✓ Copied' : '⧉ Copy summary'}</button>
            <a className="hf-vis-botao" href={url} target="_blank" rel="noreferrer">↗ Open in a new tab</a>
          </div>
          <small className="hf-vis-arquivo">{atual.subpasta}/{atual.nome}</small>
        </aside>
      </div>
    </div>
  )
}
