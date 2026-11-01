import { useEffect, useState } from 'react'
import { api, urlImagem, urlMiniatura, type ItemGaleria } from '../api'
import { eAudio, eVideo, TituloPagina } from './comum'
import { abrirVisualizador, recriar } from './Visualizador'

// Assets (layout de 31/10/2026): filtros por tipo, busca e ordem no topo, a grade de
// tudo o que foi gerado e, a direita, os detalhes do item escolhido.

type Filtro = 'tudo' | 'imagem' | 'video' | 'musica' | 'voz' | 'lipsync' | 'genjutsu'
const FILTROS: [Filtro, string][] = [['tudo', 'All'], ['imagem', 'Images'], ['video', 'Videos'], ['musica', 'Music'],
  ['voz', 'Voice'], ['lipsync', 'Lip Sync'], ['genjutsu', 'Genjutsu']]

/** O tipo de cada arquivo da galeria, pelo modelo que o gerou e pela extensao. */
function tipoDe(i: ItemGaleria): Filtro {
  if (i.modelo === 'musica') return 'musica'
  if (i.modelo === 'voz') return 'voz'
  if (i.modelo === 'avatar') return 'lipsync'
  if (i.modelo === 'genjutsu') return 'genjutsu'
  if (eAudio(i.arquivo)) return 'musica'
  return eVideo(i.arquivo) || (i.duracao_video ?? 0) > 0 ? 'video' : 'imagem'
}
const SELO: Record<Filtro, string> = { tudo: '', imagem: 'IMG', video: 'VID', musica: 'MUSIC', voz: 'VOICE', lipsync: 'LIP SYNC', genjutsu: 'GENJUTSU' }

/** Mosaico (masonry): cada item na proporcao da propria imagem. */
const proporcao = (i: ItemGaleria) => ({ aspectRatio: i.largura > 0 && i.altura > 0 ? `${i.largura} / ${i.altura}` : '3 / 2' })
const tempo = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.round(s % 60)).padStart(2, '0')}`
const tamanho = (b: number) => b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`
const data = (s: number) => new Date(s * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })

export default function AbaAssets() {
  const [itens, setItens] = useState<ItemGaleria[] | null>(null)
  const [filtro, setFiltro] = useState<Filtro>('tudo')
  const [busca, setBusca] = useState('')
  const [antigos, setAntigos] = useState(false)
  const [sel, setSel] = useState<ItemGaleria | null>(null)
  const [falhou, setFalhou] = useState(false)

  useEffect(() => { api.galeria(2000).then(setItens).catch(() => { setFalhou(true); setItens([]) }) }, [])

  const termo = busca.trim().toLowerCase()
  const visiveis = (itens ?? [])
    .filter((i) => filtro === 'tudo' || tipoDe(i) === filtro)
    .filter((i) => !termo || `${i.prompt} ${i.arquivo} ${i.modelo}`.toLowerCase().includes(termo))
    .sort((a, b) => (antigos ? a.criada_em - b.criada_em : b.criada_em - a.criada_em))
  const atual = sel && visiveis.some((i) => i.id === sel.id) ? sel : visiveis[0] ?? null

  return (
    <div className="hf-aba hf-img hf-ast">
      <div className="hf-ast-grade">
        <section className="hf-ast-centro">
          <div className="hf-ast-topo">
            <div>
              <TituloPagina antes="Everything" destaque="you made" sub="Images, videos, songs and voices, newest first." />
              <div className="hf-ast-filtros" role="group" aria-label="Filter">
                {FILTROS.map(([f, r]) => (
                  <button key={f} type="button" data-ativo={filtro === f} aria-pressed={filtro === f} onClick={() => setFiltro(f)}>{r}</button>
                ))}
              </div>
            </div>
            <div className="hf-ast-ferramentas">
              <label className="hf-vfx-busca"><span aria-hidden>⌕</span>
                <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Search" aria-label="Search" /></label>
              <select className="hf-select" value={antigos ? 'a' : 'n'} onChange={(e) => setAntigos(e.target.value === 'a')} aria-label="Order">
                <option value="n">Latest</option><option value="a">Oldest</option>
              </select>
            </div>
          </div>

          {itens === null && <p className="hf-vazio">Loading…</p>}
          <div className="hf-ast-mosaico">
            {visiveis.map((i) => {
              const t = tipoDe(i), url = urlImagem({ nome: i.arquivo, subpasta: i.subpasta })
              return (
                <button key={i.id} type="button" className="hf-ast-item" style={proporcao(i)} data-ativo={atual?.id === i.id} data-midia
                  data-nome={i.arquivo} data-subpasta={i.subpasta}
                  onClick={() => setSel(i)} onDoubleClick={() => abrirVisualizador({ nome: i.arquivo, subpasta: i.subpasta })}>
                  {eAudio(i.arquivo) ? <span className="hf-ast-audio">♪<small>{i.prompt.slice(0, 60)}</small></span>
                    : eVideo(i.arquivo) ? <video src={url + '#t=0.5'} muted preload="metadata" playsInline />
                    : <img src={urlMiniatura({ nome: i.arquivo, subpasta: i.subpasta })} alt="" loading="lazy" />}
                  <span className="hf-ast-rodape">
                    <i>{SELO[t]}</i>
                    {(i.duracao_video ?? 0) > 0 && <span>{tempo(i.duracao_video!)}</span>}
                    {i.largura > 0 && <span>{i.largura} × {i.altura}</span>}
                  </span>
                </button>
              )
            })}
          </div>
          {itens && visiveis.length === 0 && <Vazio filtro={filtro} nada={itens.length === 0} falhou={falhou} />}
        </section>

        <aside className="hf-img-col hf-ast-dir" aria-label="Details">
          {atual ? <Detalhes i={atual} /> : <p className="hf-dica">Pick a file to see its details.</p>}
        </aside>
      </div>
    </div>
  )
}

function Detalhes({ i }: { i: ItemGaleria }) {
  const arq = { nome: i.arquivo, subpasta: i.subpasta }
  const url = urlImagem(arq), t = tipoDe(i)
  const [copiado, setCopiado] = useState(false)
  return (<>
    <div className="hf-ast-previa" onClick={() => !eAudio(i.arquivo) && abrirVisualizador(arq)}>
      {eAudio(i.arquivo) ? <audio src={url} controls /> : eVideo(i.arquivo) ? <video key={url} src={url} controls playsInline /> : <img src={url} alt="" />}
    </div>
    <b className="hf-ast-nome" title={i.arquivo}>{i.arquivo}</b>
    <div className="hf-ast-chips">
      <i>{{ tudo: '', imagem: 'Image', video: 'Video', musica: 'Music', voz: 'Voice', lipsync: 'Lip Sync', genjutsu: 'Genjutsu' }[t]}</i>
      {i.largura > 0 && <i>{i.largura} × {i.altura}</i>}
      {i.bytes > 0 && <i>{tamanho(i.bytes)}</i>}
    </div>
    <small className="hf-ast-data">{data(i.criada_em)}</small>
    {i.prompt && <>
      <span className="hf-img-titulo">Prompt</span>
      <div className="hf-ast-prompt">{i.prompt}
        <button type="button" title="Copy prompt" aria-label="Copy prompt"
          onClick={() => navigator.clipboard.writeText(i.prompt).then(() => { setCopiado(true); setTimeout(() => setCopiado(false), 1500) })}>{copiado ? '✓' : '⧉'}</button>
      </div>
    </>}
    <span className="hf-img-titulo">Model</span>
    <div className="hf-ast-modelo">{i.rotulo || i.modelo}</div>
    <span className="hf-img-titulo">Other info</span>
    <dl className="hf-ast-info">
      {i.largura > 0 && <><dt>Dimensions</dt><dd>{i.largura} × {i.altura}</dd></>}
      {(i.duracao_video ?? 0) > 0 && <><dt>Length</dt><dd>{tempo(i.duracao_video!)}</dd></>}
      {i.bytes > 0 && <><dt>File size</dt><dd>{tamanho(i.bytes)}</dd></>}
      <dt>Type</dt><dd>{{ tudo: '', imagem: 'Image', video: 'Video', musica: 'Music', voz: 'Voice', lipsync: 'Lip Sync', genjutsu: 'Genjutsu' }[t]}</dd>
      <dt>Created</dt><dd>{data(i.criada_em)}</dd>
    </dl>
    <a className="hf-gerar hf-ast-baixar" href={url} download={i.arquivo}>⤓ Download</a>
    {t === 'imagem' && i.prompt && (
      <button type="button" className="hf-botao-sec hf-ast-reusar" onClick={() => recriar({ modelo: i.modelo, prompt: i.prompt, parametros: i.parametros })}>↻ Reuse prompt</button>
    )}
  </>)
}

/** Galeria vazia: diz o que falta e leva a aba que cria. */
function Vazio({ filtro, nada, falhou }: { filtro: Filtro; nada: boolean; falhou: boolean }) {
  if (falhou) return <p className="hf-vazio">Could not load your files. Check that the app is running and reload the page.</p>
  const destino: Record<Filtro, [string, string]> = { tudo: ['#image', 'Create an image'], imagem: ['#image', 'Create an image'], video: ['#video', 'Make a video'],
    musica: ['#music', 'Make a song'], voz: ['#voice', 'Make a voice'], lipsync: ['#lipsync', 'Make a portrait talk'], genjutsu: ['#genjutsu', 'Recast a video'] }
  return (
    <div className="hf-vazio">
      <p>{nada ? 'Nothing here yet. What you generate in any tab shows up here.' : 'Nothing of this kind yet.'}</p>
      <div className="hf-linha-controles" style={{ justifyContent: 'center' }}>
        <a className="hf-botao-sec" href={destino[filtro][0]}>{destino[filtro][1]}</a>
      </div>
    </div>
  )
}
