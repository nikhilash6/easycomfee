import { Children, Component, useContext, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { api, ouvirTarefas, referenciaDaGaleria, urlImagem, type Referencia, type Tarefa } from '../api'
import { abrirVisualizador, recriar, reusarPrompt } from './Visualizador'
import { emIngles } from '../PainelAndamento'
import { MotorCtx } from './motor'

// Shared pieces of the new studio: live jobs, result tiles, upload slots.

/** Jobs of this session, kept current by the backend WebSocket. */
/** Parte n do endereco depois do #: "#video/imagem/minimax" -> 0 video, 1 imagem, 2 minimax.
 *  Os atalhos dos estudios (LTX, MiniMax H3, FLUX 3) abrem a aba ja com o modo e o modelo. */
/** Setas num role="radiogroup" (padrao ARIA): escolhem e focam a opcao vizinha;
 *  Home/End vao as pontas. Com tabIndex so na opcao marcada, o Tab entra e sai do
 *  grupo de uma vez em vez de parar em cada opcao. */
/** X desenhado (o caractere × fica baixo no circulo, conforme a fonte). */
export function IconeX({ tamanho = 12 }: { tamanho?: number }) {
  return (
    <svg width={tamanho} height={tamanho} viewBox="0 0 12 12" aria-hidden="true" style={{ display: 'block' }}>
      <path d="M2 2 L10 10 M10 2 L2 10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function teclasRadio(e: KeyboardEvent<HTMLElement>) {
  const radios = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="radio"]')]
  const i = radios.indexOf(document.activeElement as HTMLElement)
  const passo = ({ ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 } as Record<string, number>)[e.key]
  if (i < 0 || (!passo && e.key !== 'Home' && e.key !== 'End')) return
  const j = e.key === 'Home' ? 0 : e.key === 'End' ? radios.length - 1 : (i + passo + radios.length) % radios.length
  e.preventDefault()
  radios[j].focus()
  radios[j].click()
}

// O texto de cada aba sobrevive a troca de aba: a aba desmonta ao sair, mas o
// que a pessoa escreveu fica aqui ate a pagina recarregar.
const LEMBRADOS = new Map<string, unknown>()

/** useState que lembra o valor entre montagens da aba (chave unica por campo). */
export function useLembrado<T>(chave: string, inicial: T) {
  const [valor, setValor] = useState<T>(() => (LEMBRADOS.has(chave) ? LEMBRADOS.get(chave) as T : inicial))
  useEffect(() => { LEMBRADOS.set(chave, valor) }, [chave, valor])
  return [valor, setValor] as const
}

/** O quadro (contado de 0) onde o servidor poe uma imagem-chave do LTX, como em
 *  app.py _posicao_do_quadro: multiplo de 8 (passos de 1/3 s) e, passando do fim
 *  do clipe, o ultimo quadro. A tela confere repeticoes e envia por aqui, senao
 *  1,3 s e 1,4 s caiam no mesmo quadro e uma imagem sumia sem aviso. */
export function quadroChave(seg: number, duracao: number) {
  const pedidos = Math.floor(duracao * 24) + 1
  const quadros = Math.min(361, Math.floor((Math.max(pedidos, 9) - 1) / 8) * 8 + 1)
  const q = Math.round(Math.max(0, Math.round(seg * 24)) / 8) * 8
  return q >= quadros - 1 ? quadros - 1 : q
}

/** Segundos levados ao passo de 1/3 s dos quadros-chave (2 casas, para o campo). */
export const passoChave = (s: number) => Math.round(Math.round(s * 3) / 3 * 100) / 100

export function parteDoHash(n: number): string {
  return decodeURIComponent(location.hash.replace(/^#/, '').split('/')[n] ?? '')
}

export const EVENTO_REMOVIDO = 'openfield:removido'
const EVENTO_DISPENSADO = 'openfield:dispensado'

/** As tarefas para as galerias das abas. Os testes de diagnostico (teste: true) ficam
 *  de fora, como na galeria principal; so a barra de progresso os mostra. */
export function useTarefas(comTestes = false) {
  const [tarefas, setTarefas] = useState<Tarefa[]>([])
  useEffect(() => {
    api.tarefas().then(setTarefas).catch(() => {})
    // "Remove from view" na galeria: o arquivo sai de todas as abas abertas.
    const removido = (e: Event) => {
      const { nome, subpasta } = (e as CustomEvent<{ nome: string; subpasta: string }>).detail
      setTarefas((atuais) => atuais.map((t) => ({ ...t, imagens: t.imagens.filter((s) => {
        const d = JSON.parse(s); return !(d.nome === nome && (d.subpasta ?? '') === subpasta)
      }) })).filter((t) => t.estado !== 'pronto' || t.imagens.length > 0))
    }
    window.addEventListener(EVENTO_REMOVIDO, removido)
    // Cartao de erro dispensado (x): sai de todas as abas abertas.
    const dispensado = (e: Event) => {
      const id = (e as CustomEvent<string>).detail
      setTarefas((atuais) => atuais.filter((t) => t.id !== id))
    }
    window.addEventListener(EVENTO_DISPENSADO, dispensado)
    const parar = ouvirTarefas((t) => setTarefas((atuais) => {
      const i = atuais.findIndex((a) => a.id === t.id)
      if (i < 0) return [t, ...atuais]
      const copia = atuais.slice()
      copia[i] = t
      return copia
    }))
    return () => { parar(); window.removeEventListener(EVENTO_REMOVIDO, removido); window.removeEventListener(EVENTO_DISPENSADO, dispensado) }
  }, [])
  return comTestes ? tarefas : tarefas.filter((t) => !t.teste)
}

export function arquivos(t: Tarefa): { nome: string; subpasta: string }[] {
  return t.imagens.map((s) => JSON.parse(s))
}

export const eVideo = (nome: string) => /\.(mp4|webm|mov)$/i.test(nome)

export const eAudio = (nome: string) => /\.(mp3|flac|wav|ogg|opus|m4a)$/i.test(nome)

// ---- Usar uma imagem da galeria como referencia ----
// Arrastar uma imagem da galeria leva {nome, subpasta} neste tipo proprio. Soltar
// num slot o preenche; soltar em qualquer outro ponto da caixa de prompt (ou o
// botao "Use" da galeria) manda para o PRIMEIRO slot de imagem vazio da tela.
export const TIPO_GALERIA = 'application/x-openfield-midia'
type Entrega = { nome: string; subpasta: string } | File
const EVENTO_USAR = 'openfield:usar'

/** O que veio num arraste: uma imagem da galeria ou um arquivo de imagem do computador. */
export function entregaDoArraste(dt: DataTransfer): Entrega | null {
  const bruto = dt.getData(TIPO_GALERIA)
  if (bruto) { try { return JSON.parse(bruto) } catch { return null } }
  return Array.from(dt.files).find((f) => f.type.startsWith('image/')) ?? null
}

/** Sobe para a pasta de entrada do motor e devolve como referencia. */
export async function referenciaDe(e: Entrega): Promise<Referencia> {
  return e instanceof File ? api.enviarReferencia(e) : referenciaDaGaleria({ arquivo: e.nome, subpasta: e.subpasta })
}

/** O primeiro slot de imagem vazio visivel na tela, se houver. */
const primeiroSlotVazio = () => document.querySelector<HTMLElement>('.hf-slot[data-imagem][data-cheio="false"]')

/** Manda para o primeiro slot vazio; false quando a tela nao tem nenhum. */
export function usarNaCaixa(e: Entrega): boolean {
  const alvo = primeiroSlotVazio()
  if (!alvo) return false
  alvo.dispatchEvent(new CustomEvent(EVENTO_USAR, { detail: e }))
  return true
}

/** Soltar em qualquer ponto de uma caixa de prompt: vai para o primeiro slot vazio. */
export function useSoltarNaCaixa() {
  useEffect(() => {
    // Arquivo do computador solto fora de um espaco: o navegador abria o arquivo e a pessoa
    // saia do app (30/10/2026). Agora ele so e ignorado; dentro da caixa vai para um espaco.
    const comArquivo = (ev: DragEvent) => !!ev.dataTransfer?.types.includes('Files')
    const sobre = (ev: DragEvent) => {
      if (comArquivo(ev) || ((ev.target as HTMLElement)?.closest?.('.hf-barra-prompt') && ev.dataTransfer?.types.includes(TIPO_GALERIA)))
        ev.preventDefault()
    }
    const soltar = (ev: DragEvent) => {
      if (ev.defaultPrevented || !ev.dataTransfer) return
      if (comArquivo(ev)) ev.preventDefault()
      const caixa = (ev.target as HTMLElement)?.closest?.('.hf-barra-prompt')
      if (!caixa) return
      const e = entregaDoArraste(ev.dataTransfer)
      if (!e) return
      ev.preventDefault()
      usarNaCaixa(e)
    }
    document.addEventListener('dragover', sobre)
    document.addEventListener('drop', soltar)
    return () => { document.removeEventListener('dragover', sobre); document.removeEventListener('drop', soltar) }
  }, [])
}

// Icones da barra de acoes (traco, herdam a cor do botao). Os pontos do "mais" usam traco
// mais grosso: com 2 sumiam ao lado dos outros icones.
const ICONES: Record<string, string> = {
  mais: 'M12 5.5v.01M12 12v.01M12 18.5v.01',
  lixo: 'M4 7h16M9 7V4h6v3M6.5 7l1 13h9l1-13M10 11v6M14 11v6',
  baixar: 'M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 20h14',
  abrir: 'M14 4h6v6M10 14 20 4M20 14v6H4V4h6',
}
const Icone = ({ d }: { d: string }) => (
  <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth={d === 'mais' ? 3.2 : 2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={ICONES[d]} />
  </svg>
)

// "Edit this image": leva a imagem para a aba Edit, que a coloca na primeira caixa da
// ferramenta que a pessoa abrir (la ainda nao ha caixa antes de escolher a ferramenta).
let paraEditar: { nome: string; subpasta: string } | null = null
export function pegarParaEditar() { const e = paraEditar; paraEditar = null; return e }
function editarImagem(e: { nome: string; subpasta: string }) {
  paraEditar = e
  location.hash = '#edit'
  window.dispatchEvent(new Event('easycomfee:editar'))
}

/** Leva para outra aba e entrega o arquivo ao primeiro slot de imagem dela. */
function irComImagem(hash: string, e: { nome: string; subpasta: string }) {
  // Ja na aba com um modelo no endereco (#image/qwen21): ficar nele, e nao voltar a
  // rota simples, que remontaria a aba no modelo padrao.
  if (!location.hash.startsWith(hash + '/')) location.hash = hash
  // A aba nova monta no proximo quadro; tenta por ate ~1,5 s.
  let n = 0
  const tentar = () => { if (!usarNaCaixa(e) && n++ < 15) setTimeout(tentar, 100) }
  setTimeout(tentar, 100)
}

// "Send to Lip Sync" de um audio da galeria: guarda o arquivo ate a aba de Lip Sync
// montar e pegar (useFalaPendente), e avisa se ela ja estiver aberta.
let falaPendente: { nome: string; subpasta: string } | null = null
const EVENTO_FALA = 'easycomfee:fala-lipsync'

function mandarFalaParaLipSync(e: { nome: string; subpasta: string }) {
  falaPendente = e
  location.hash = '#lipsync'
  window.dispatchEvent(new Event(EVENTO_FALA))
}

/** Na aba Lip Sync: recebe o audio mandado pelo menu de um arquivo da galeria. */
export function useFalaPendente(receber: (f: File) => void) {
  useEffect(() => {
    const pegar = async () => {
      const e = falaPendente
      if (!e) return
      falaPendente = null
      const r = await fetch(urlImagem(e))
      if (r.ok) receber(new File([await r.blob()], e.nome, { type: r.headers.get('content-type') || 'audio/flac' }))
    }
    void pegar()
    window.addEventListener(EVENTO_FALA, pegar)
    return () => window.removeEventListener(EVENTO_FALA, pegar)
  }, [receber])
}

/** A generated file. Clicking it opens the full-size viewer; on hover, a bar of actions. */
export function Midia({ nome, subpasta, aoClicar }: { nome: string; subpasta: string; aoClicar?: () => void }) {
  const url = urlImagem({ nome, subpasta })
  const arq = { nome, subpasta }
  const abrir = () => abrirVisualizador(arq)
  // Nas faixas de recentes o clique na miniatura escolhe a imagem grande; o botao de abrir continua no topo.
  const clicar = aoClicar ?? abrir
  const imagem = !eAudio(nome) && !eVideo(nome)
  const video = eVideo(nome)
  const [aviso, setAviso] = useState('')
  const [menu, setMenu] = useState(false)
  const caixa = useRef<HTMLDivElement>(null)
  const avisar = (t: string) => { setAviso(t); setTimeout(() => setAviso(''), 2200) }

  useEffect(() => {
    if (!menu) return
    const fora = (e: PointerEvent) => { if (!caixa.current?.contains(e.target as Node)) setMenu(false) }
    document.addEventListener('pointerdown', fora)
    return () => document.removeEventListener('pointerdown', fora)
  }, [menu])

  // O prompt vem do registro da galeria, so quando pedem (copiar/reusar).
  const prompt = async () => {
    const r = await fetch(`/api/galeria/arquivo?subpasta=${encodeURIComponent(subpasta)}&nome=${encodeURIComponent(nome)}`)
    const d = r.ok ? await r.json() : null
    return (d?.prompt as string | undefined) || ''
  }
  const refazer = async () => {
    const r = await fetch(`/api/galeria/arquivo?subpasta=${encodeURIComponent(subpasta)}&nome=${encodeURIComponent(nome)}`)
    const d = r.ok ? await r.json() : null
    if (d?.prompt || d?.prompt_final) recriar({ modelo: d.modelo, prompt: d.prompt || d.prompt_final, parametros: d.parametros ?? {} })
    else avisar('No details saved')
  }
  const copiar = async (texto: string, ok: string) => {
    try { await navigator.clipboard.writeText(texto); avisar(ok) } catch { avisar('Could not copy') }
  }
  const remover = async () => {
    setMenu(false)
    try {
      const r = await fetch('/api/arquivo/remover', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(arq) })
      if (!r.ok) throw new Error()
      window.dispatchEvent(new CustomEvent(EVENTO_REMOVIDO, { detail: arq }))
    } catch { avisar('Could not remove') }
  }
  const usar = () => { if (!usarNaCaixa(arq)) avisar('No empty image slot here') }

  const itens: { rotulo: string; acao: () => void; perigo?: boolean }[] = [
    { rotulo: 'Open', acao: abrir },
    ...(imagem ? [{ rotulo: 'Recreate (prompt + images)', acao: refazer }] : []),
    ...(imagem ? [
      { rotulo: 'Use as reference here', acao: usar },
      { rotulo: 'Animate (Image → Video)', acao: () => irComImagem('#video/imagem', arq) },
      { rotulo: 'Use in the Image tab', acao: () => irComImagem('#image', arq) },
      { rotulo: 'Edit this image (Edit tab)', acao: () => editarImagem(arq) },
      { rotulo: 'Send to Lip Sync (as the face)', acao: () => irComImagem('#lipsync', arq) },
    ] : []),
    ...(eAudio(nome) ? [
      { rotulo: 'Send to Lip Sync (as the voice)', acao: () => mandarFalaParaLipSync(arq) },
    ] : []),
    ...(video ? [
      { rotulo: 'Upscale', acao: () => { location.hash = '#ltx/ampliar' } },
      { rotulo: 'Depth map', acao: () => { location.hash = '#apps/mapa_profundidade' } },
    ] : []),
    { rotulo: 'Reuse prompt', acao: async () => { const p = await prompt(); if (p) reusarPrompt(p); else avisar('No prompt saved') } },
    { rotulo: 'Copy prompt', acao: async () => { const p = await prompt(); if (p) copiar(p, 'Prompt copied'); else avisar('No prompt saved') } },
    { rotulo: 'Copy link', acao: () => copiar(new URL(url, location.href).href, 'Link copied') },
    { rotulo: 'Remove from view', acao: remover, perigo: true },
  ]

  return (
    <div ref={caixa} className="hf-midia-caixa" data-midia data-nome={nome} data-subpasta={subpasta} data-menu={menu} data-audio={eAudio(nome) || undefined}
      draggable={imagem} onDragStart={(e) => {
        e.dataTransfer.setData(TIPO_GALERIA, JSON.stringify(arq))
        e.dataTransfer.effectAllowed = 'copy'
      }}>
      {eAudio(nome) ? <audio src={url} controls className="hf-audio" />
        : video ? <>
            {/* The tile is a preview (plays muted on hover); a click opens the viewer with the full player. */}
            <video src={url} loop muted playsInline preload="metadata" className="hf-midia hf-midia-video" onClick={abrir}
              onMouseEnter={(e) => { e.currentTarget.play().catch(() => {}) }}
              onMouseLeave={(e) => { e.currentTarget.pause() }} />
            <span className="hf-play" aria-hidden>▶</span>
          </>
          : <img src={url} alt="" className="hf-midia" loading="lazy" onClick={clicar} onDoubleClick={abrir} />}

      <div className="hf-acoes-topo">
        <button type="button" className="hf-icone" data-ativo={menu} onClick={() => setMenu((m) => !m)} title="More" aria-label="More actions" aria-expanded={menu}><Icone d="mais" /></button>
        <button type="button" className="hf-icone" onClick={remover} title="Remove from view (the file stays on disk)" aria-label="Remove from view"><Icone d="lixo" /></button>
        <a className="hf-icone" href={url} download={nome} title="Download" aria-label="Download"><Icone d="baixar" /></a>
        <button type="button" className="hf-icone" onClick={abrir} title="Open the viewer" aria-label="Open the viewer"><Icone d="abrir" /></button>
      </div>
      {menu && (
        <div className="hf-menu-midia" role="menu">
          {itens.map((it, k) => (
            <button key={k} type="button" role="menuitem" data-perigo={!!it.perigo}
              onClick={() => { setMenu(false); void it.acao() }}>{it.rotulo}</button>
          ))}
        </div>
      )}
      {!eAudio(nome) && (
        <div className="hf-acoes-base">
          {imagem && <button type="button" className="hf-pilula" onClick={usar} title="Use as a reference in the box above (or drag the image there)">↑ Use</button>}
          {imagem && <button type="button" className="hf-pilula hf-pilula-forte" onClick={() => irComImagem('#video/imagem', arq)} title="Make a video from this image">▶ Animate</button>}
          {video && <button type="button" className="hf-pilula hf-pilula-forte" onClick={() => { location.hash = '#ltx/ampliar' }} title="Make it sharper and bigger">⤴ Upscale</button>}
        </div>
      )}
      {aviso && <span className="hf-aviso-midia">{aviso}</span>}
    </div>
  )
}

const ESTADOS: Record<string, string> = {
  na_fila: 'Queued', preparando: 'Preparing', submetendo: 'Sending', executando: 'Generating', pronto: 'Done', erro: 'Error',
}

/** The engine's raw error (JSON, Python traceback) is not for people: a short line instead.
 *  The full text stays in the tooltip for whoever needs it. */
export function erroCurto(erro: string): string {
  const e = erro.toLowerCase()
  if (e.includes('out of memory') || e.includes('allocation on device') || e.includes('outofmemory'))
    return 'This generation stopped: the GPU ran out of memory. Try a shorter clip or a lower resolution.'
  if (e.includes('interrompida') || e.includes('cancelada') || e.includes('interrupted'))
    return 'This generation was stopped before it finished.'
  if (e.includes('all connection attempts failed') || e.includes('connection refused'))
    return 'This generation stopped: the engine is not running. Try again in a minute.'
  if (/^\s*[[{]/.test(erro) || e.includes('traceback') || e.includes('exception_message') || erro.length > 240)
    return 'This generation stopped because of an engine error. Please try again.'
  return erro
}

/** One job: progress while it runs, the result when done. */
export function CartaoTarefa({ t }: { t: Tarefa }) {
  const prontos = arquivos(t)
  return (
    <div className="hf-tarefa" data-estado={t.estado}>
      {t.estado === 'pronto' && prontos.length > 0
        ? prontos.map((a) => <Midia key={a.subpasta + a.nome} {...a} />)
        : (
          <div className="hf-espera">
            <span className="hf-estado">{ESTADOS[t.estado] ?? t.estado}{t.detalhe && emIngles(t.detalhe) !== ESTADOS[t.estado] ? ` · ${emIngles(t.detalhe)}` : ''}</span>
            {t.estado !== 'erro' && <div className="hf-barra"><div style={{ width: `${Math.round((t.progresso || 0) * 100)}%` }} /></div>}
            {t.erro && <span className="hf-erro" title={t.erro}><ComLinks texto={erroCurto(t.erro)} /></span>}
          </div>
        )}
      {t.estado === 'erro' && (
        <button type="button" className="hf-dispensar" title="Dismiss this error" aria-label="Dismiss this error"
          onClick={async () => {
            const r = await fetch(`/api/tarefa/${t.id}/dispensar`, { method: 'POST' })
            if (r.ok) window.dispatchEvent(new CustomEvent(EVENTO_DISPENSADO, { detail: t.id }))
          }}>×</button>
      )}
      <p className="hf-legenda" title={t.prompt}>{t.prompt}</p>
    </div>
  )
}

/** Image slot: click to upload, shows the thumbnail, × to clear. */
export function SlotImagem({ rotulo, valor, aoMudar }: {
  rotulo: string; valor: Referencia | null; aoMudar: (r: Referencia | null) => void
}) {
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [alvo, setAlvo] = useState(false)
  const caixa = useRef<HTMLLabelElement>(null)
  // Recebe da galeria (arraste ou botao "Use") e do computador.
  const receber = async (e: Entrega) => {
    setEnviando(true); setErro(null)
    try { aoMudar(await referenciaDe(e)) } catch (x) { setErro(String(x)) } finally { setEnviando(false) }
  }
  const receberRef = useRef(receber)
  useEffect(() => { receberRef.current = receber })
  useEffect(() => {
    const el = caixa.current
    if (!el) return
    const ao = (ev: Event) => { void receberRef.current((ev as CustomEvent<Entrega>).detail) }
    el.addEventListener(EVENTO_USAR, ao)
    return () => el.removeEventListener(EVENTO_USAR, ao)
  }, [])
  return (
    <label ref={caixa} className="hf-slot" data-imagem data-cheio={!!valor} data-alvo={alvo}
      onDragOver={(e) => { e.preventDefault(); setAlvo(true) }}
      onDragLeave={() => setAlvo(false)}
      onDrop={(e) => {
        e.preventDefault(); setAlvo(false)
        const entrega = entregaDoArraste(e.dataTransfer)
        if (entrega) void receber(entrega)
      }}>
      {valor ? <img src={valor.url} alt="" /> : <span>{enviando ? 'Uploading…' : `+ ${rotulo}`}</span>}
      {valor && <button type="button" className="hf-slot-x" aria-label="Remove image" onClick={(e) => { e.preventDefault(); aoMudar(null) }}><IconeX tamanho={10} /></button>}
      <input type="file" accept="image/*" className="hf-arquivo" onChange={async (e) => {
        const f = e.target.files?.[0]
        if (!f) return
        setEnviando(true); setErro(null)
        try { aoMudar(await api.enviarReferencia(f)) } catch (x) { setErro(String(x)) } finally { setEnviando(false) }
      }} />
      {erro && <span className="hf-erro">{erro}</span>}
    </label>
  )
}

export function Chips<T extends string | number>({ opcoes, valor, aoMudar, rotulo }: {
  opcoes: { id: T; rotulo: string; desligado?: boolean; dica?: string }[]; valor: T; aoMudar: (v: T) => void; rotulo?: string
}) {
  const chips = (
    <div className="hf-chips" role="group" aria-label={rotulo}>
      {opcoes.map((o) => (
        <button key={String(o.id)} type="button" data-ativo={o.id === valor} aria-pressed={o.id === valor} disabled={o.desligado}
          title={o.dica} onClick={() => aoMudar(o.id)}>{o.rotulo}</button>
      ))}
    </div>
  )
  // O nome do grupo aparece em cima (Aspect ratio, Images...): cada controle diz o que e.
  return rotulo ? <div className="hf-campo"><span aria-hidden>{rotulo}</span>{chips}</div> : chips
}

/** Text with its URLs turned into links (the cloud top-up message carries one). */
export function ComLinks({ texto }: { texto: string }) {
  return <>{texto.split(/(https?:\/\/\S+)/).map((parte, i) =>
    /^https?:\/\//.test(parte)
      ? <a key={i} href={parte} target="_blank" rel="noreferrer">{parte}</a>
      : parte)}</>
}

// Nomes legiveis dos campos que o servidor recusa com 422.
const CAMPOS: Record<string, string> = {
  prompt: 'Prompt', letra_musica: 'Lyrics', bpm_musica: 'Tempo (BPM)', duracao_musica: 'Length',
  duracao_video: 'Length', lote: 'Images', referencias: 'Images',
}

/** O "detail" de um erro do servidor como texto. No 422 ele vem como lista de
 *  objetos {loc, msg}; antes isso virava "[object Object]" ou, posto na tela,
 *  quebrava a aba inteira (o React nao desenha objetos). */
export function textoDoDetalhe(detail: unknown, padrao: string): string {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => {
      const loc = Array.isArray(d?.loc) ? d.loc : []
      const campo = String(loc[loc.length - 1] ?? '')
      return `${CAMPOS[campo] ?? campo}${campo ? ': ' : ''}${d?.msg ?? 'invalid value'}`
    }).join('; ')
  }
  return padrao
}

export function mensagem(e: unknown): string {
  const bruto = e instanceof Error ? e.message : String(e)
  try { return textoDoDetalhe(JSON.parse(bruto).detail, bruto) } catch { return bruto }
}

// 'carregando' e so da tela: o preco do pedido atual ainda nao chegou.
/** Mesmo limite do servidor (PedidoGeracao.prompt). */
export const MAX_PROMPT = 12000

export type Estimativa = { tipo: 'gratis' | 'api' | 'gpu' | 'desconhecido' | 'carregando'; min?: number; max?: number; usd?: number }

/** Estimated cost of a request, asked to the backend (no generation happens).
 *  API models use Comfy's own price formula for each node; open models on
 *  Comfy Cloud are GPU time; local runs are free. */
export function useCusto(pedido: Record<string, unknown> | null) {
  // O preco guarda o pedido a que pertence. Antes o botao mostrava o preco do modelo
  // anterior ate a resposta chegar, e uma resposta antiga que chegasse depois da nova
  // ficava na tela (ex.: Flux 2 Klein local com "$0.03"; varredura de 29/10/2026).
  const [est, setEst] = useState<{ chave: string; est: Estimativa | null } | null>(null)
  // O motor entra na chave: "local:klein" e "nuvem:klein" mandam o mesmo pedido, e
  // sem isto o botao seguia dizendo "Free" com a nuvem escolhida (27/10/2026).
  const { naNuvem } = useContext(MotorCtx)
  const chave = pedido ? `${naNuvem}|${JSON.stringify(pedido)}` : ''
  useEffect(() => {
    if (!chave) return
    let atual = true
    const t = setTimeout(() => {
      fetch('/api/estimar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: chave.slice(chave.indexOf('|') + 1) })
        .then((r) => r.json()).then((e) => { if (atual) setEst({ chave, est: e }) })
        .catch(() => { if (atual) setEst({ chave, est: null }) })
    }, 350)
    return () => { atual = false; clearTimeout(t) }
  }, [chave])
  if (!chave) return null
  return est?.chave === chave ? est.est : { tipo: 'carregando' } as Estimativa
}

const usd = (v: number) => (v < 0.01 ? '<$0.01' : `$${v.toFixed(2)}`)

/** Text shown on the Generate button. */
/** O preco de N pedidos iguais (ex.: um por plano na Cinema). Modelo de API vem
 *  como faixa min/max e GPU da nuvem como usd: multiplica os tres. */
export function vezes(est: Estimativa | null, n: number): Estimativa | null {
  if (!est || n === 1) return est
  const m = (v?: number) => (v === undefined ? undefined : v * n)
  return { ...est, min: m(est.min), max: m(est.max), usd: m(est.usd) }
}

export function rotuloCusto(est: Estimativa | null): string {
  if (!est) return ''
  if (est.tipo === 'carregando') return '…'
  if (est.tipo === 'gratis') return 'Free'
  // Modelo de API sem tabela de preco na Comfy (ex.: Krea 3, Luma UNI-1): o botao ficava
  // so "Generate ✦" e parecia de graca.
  if (est.tipo === 'desconhecido') return 'Uses credits'
  if (est.tipo === 'gpu' && est.usd !== undefined) return `~${usd(est.usd)}`
  if (est.tipo === 'api' && est.min !== undefined) {
    return est.max !== undefined && est.max > est.min ? `${usd(est.min)}–${usd(est.max)}` : usd(est.min)
  }
  return ''
}

/** Generate button with the estimated cost underneath the label. */
export function BotaoGerar({ rotulo = 'Generate ✦', est, desligado, aoClicar }: {
  rotulo?: string; est: Estimativa | null; desligado?: boolean; aoClicar: () => void
}) {
  const custo = rotuloCusto(est)
  const dica = est?.tipo === 'gpu' ? 'Estimated Comfy Cloud GPU time for an open model'
    : est?.tipo === 'api' ? 'Price of the API model, from the Comfy pricing table'
    : est?.tipo === 'gratis' ? 'Runs on your own GPU'
    : est?.tipo === 'desconhecido' ? 'Comfy has not published a price for this model: it uses your Comfy credits, check your balance after'
    : undefined
  return (
    <button className="hf-gerar" disabled={desligado} onClick={aoClicar} title={dica}>
      {rotulo}
      {custo && <span className="hf-custo">{custo}</span>}
    </button>
  )
}


/** Masonry gallery: each result keeps its own height; items go left to right,
 *  column by column, so the newest stays at the top left. The number of
 *  columns follows the width (minimum column width per kind of media). */
export function Galeria({ tipo, children }: { tipo?: 'video' | 'audio'; children: ReactNode }) {
  const caixa = useRef<HTMLDivElement>(null)
  const minimo = tipo === 'video' || tipo === 'audio' ? 320 : 240
  const [colunas, setColunas] = useState(3)
  useEffect(() => {
    const el = caixa.current
    if (!el) return
    const medir = () => setColunas(Math.max(1, Math.floor((el.clientWidth + 14) / (minimo + 14))))
    medir()
    const ro = new ResizeObserver(medir)
    ro.observe(el)
    return () => ro.disconnect()
  }, [minimo])
  const itens = Children.toArray(children)
  const pilhas: ReactNode[][] = Array.from({ length: colunas }, () => [])
  itens.forEach((item, i) => pilhas[i % colunas].push(item))
  return (
    <div ref={caixa} className="hf-galeria">
      {pilhas.map((pilha, i) => <div key={i} className="hf-galeria-coluna">{pilha}</div>)}
    </div>
  )
}

/** Se uma aba quebrar ao desenhar, mostra o erro no lugar dela em vez de a tela
 *  ficar em branco (antes nao havia nenhum). Trocar de aba (key) recomeca. */
export class ProtegeAba extends Component<{ children: ReactNode }, { erro: Error | null }> {
  state = { erro: null as Error | null }
  static getDerivedStateFromError(erro: Error) { return { erro } }
  render() {
    if (!this.state.erro) return this.props.children
    return (
      <div className="hf-aba"><p className="hf-erro" role="alert">This tab hit an error: {this.state.erro.message}.{' '}
        <button type="button" className="hf-link" onClick={() => this.setState({ erro: null })}>Try again</button></p></div>
    )
  }
}

/** Ajustes finos de uma geracao. Vazio = o padrao do modelo (seed sorteada). */
export type Ajustes = { seed: string; steps: string; cfg: string }
export const AJUSTES_VAZIOS: Ajustes = { seed: '', steps: '', cfg: '' }

/** O que vai no pedido: so o que a pessoa preencheu. Passos e CFG so onde o modelo usa. */
export function camposAjustes(a: Ajustes, comPassos: boolean): { seed?: number; steps?: number; cfg?: number } {
  const n = (v: string) => (v.trim() === '' || !Number.isFinite(Number(v)) ? undefined : Number(v))
  return {
    ...(n(a.seed) !== undefined ? { seed: Math.floor(n(a.seed)!) } : {}),
    ...(comPassos && n(a.steps) !== undefined ? { steps: Math.floor(n(a.steps)!) } : {}),
    ...(comPassos && n(a.cfg) !== undefined ? { cfg: n(a.cfg) } : {}),
  }
}

/** "Advanced": um link discreto que abre seed, passos e CFG. Fechado, nada muda. */
export function Avancado({ valor, aoMudar, comPassos, nota }: { valor: Ajustes; aoMudar: (a: Ajustes) => void; comPassos: boolean; nota?: string }) {
  const [aberto, setAberto] = useState(false)
  const ativo = !!(valor.seed || (comPassos && (valor.steps || valor.cfg)))
  return (
    <div className="hf-ajustes" data-aberto={aberto}>
      <button type="button" className="hf-ajustes-botao" aria-expanded={aberto} onClick={() => setAberto(!aberto)}>
        {aberto ? '▾' : '▸'} Advanced{ativo && !aberto ? ' ·' : ''}
      </button>
      {aberto && (
        <div className="hf-ajustes-campos">
          <label title="Same seed + same settings = the same result. Empty = a new random seed each time.">
            Seed<input inputMode="numeric" placeholder="random" value={valor.seed}
              onChange={(e) => aoMudar({ ...valor, seed: e.target.value.replace(/\D/g, '') })} />
          </label>
          {comPassos && <>
            <label title="More steps: more detail and slower. Empty = the model's own default.">
              Steps<input inputMode="numeric" placeholder="default" value={valor.steps}
                onChange={(e) => aoMudar({ ...valor, steps: e.target.value.replace(/\D/g, '').slice(0, 3) })} />
            </label>
            <label title="How strictly the prompt is followed. Empty = the model's own default.">
              CFG<input inputMode="decimal" placeholder="default" value={valor.cfg}
                onChange={(e) => aoMudar({ ...valor, cfg: e.target.value.replace(/[^\d.]/g, '').slice(0, 4) })} />
            </label>
          </>}
          {nota && <small className="hf-ajustes-nota">{nota}</small>}
          {ativo && <button type="button" className="hf-ajustes-limpar" onClick={() => aoMudar(AJUSTES_VAZIOS)}>Reset</button>}
        </div>
      )}
    </div>
  )
}

/** Titulo de cada pagina, no mesmo padrao em todas: uma frase curta com a parte final na cor
 *  de destaque, um selo opcional (BETA, modelo) e, se precisar, um subtitulo pequeno. */
export function TituloPagina({ antes, destaque, sub, selo, children }: {
  antes: string; destaque: string; sub?: ReactNode; selo?: ReactNode; children?: ReactNode
}) {
  return (
    <div className="hf-titulo-pag">
      <div>
        <h1>{antes} <em>{destaque}</em>{selo && <small>{selo}</small>}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {children}
    </div>
  )
}
