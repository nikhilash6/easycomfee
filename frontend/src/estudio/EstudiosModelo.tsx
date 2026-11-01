// Estudios por modelo (LTX, MiniMax H3, Wan, FLUX 3), no desenho de 31/10/2026: capa
// com o botao Create, secoes de cartoes com imagem e selos (modelo, GPU, Cloud, API)
// e, a direita, um "Quick start" e as criacoes recentes desse modelo. Cada cartao abre
// a aba certa ja com o modo e o modelo escolhidos ("#video/imagem/minimax"; ver parteDoHash).
import { useEffect, useState } from 'react'
import { api, urlImagem, type ItemGaleria } from '../api'
import { abrirVisualizador } from './Visualizador'

export type Fluxo = { nome: string; descricao: string; destino: string; etiqueta: string; capa?: string }
type Secao = { titulo: string; texto: string; icone: string; fluxos: Fluxo[]; verTudo?: string
  /** bento: um grande + menores; compacto: fileira de cartoes pequenos; largo: cartoes deitados. */
  estilo?: 'bento' | 'compacto' | 'largo'
  /** Fileira compacta com cartoes mais largos (7 viram 4 + 3). */
  largos?: boolean }
export type Estudio = {
  nome: string; titulo: string; texto: string
  destaque: { rotulo: string; destino: string }
  capa: string  // .mp4 toca em loop; o resto e imagem
  secoes: Secao[]
  /** Quais criacoes da galeria sao deste estudio (pelo modelo do pedido). */
  meu: (i: ItemGaleria) => boolean
}

const eVideo = (s: string) => /\.mp4($|\?)/.test(s)

/** Selos a partir da etiqueta: "Comfy Cloud · API" -> Cloud + API; "Local GPU" -> GPU;
 *  um nome de modelo (roda na placa e, quase sempre, na nuvem) -> o nome + GPU. */
function selos(etiqueta: string) {
  const nuvem = /cloud/i.test(etiqueta), apiPaga = /\bapi\b/i.test(etiqueta)
  const gpu = /gpu|local|8 gb|steps/i.test(etiqueta) || (!nuvem && !apiPaga)
  const modelo = etiqueta.replace(/comfy cloud|·|\bapi\b|local gpu|local|\bgpu\b/gi, '').replace(/\s+/g, ' ').trim()
  return { modelo, gpu, nuvem, apiPaga }
}

function Capa({ src, classe }: { src: string; classe?: string }) {
  return eVideo(src)
    ? <video className={classe} src={src} muted loop playsInline preload="metadata"
        onMouseEnter={(e) => { e.currentTarget.play().catch(() => {}) }} onMouseLeave={(e) => e.currentTarget.pause()} />
    : <img className={classe} src={src} alt="" loading="lazy" />
}

/** Mosaico ("bento"): tamanho de cada cartao numa grade de 12 colunas, pela quantidade
 *  da secao. 5 ou mais: um grande + quatro pequenos (2x2), e o resto continua. */
function tamanhos(n: number): [number, number][] {
  const t: [number, number][] = []
  let resto = n
  while (resto > 0) {
    if (resto >= 5) { t.push([6, 6], [3, 3], [3, 3], [3, 3], [3, 3]); resto -= 5 }
    else if (resto === 4) { t.push([6, 6], [6, 3], [3, 3], [3, 3]); resto = 0 }
    else if (resto === 3) { t.push([6, 6], [6, 3], [6, 3]); resto = 0 }
    else if (resto === 2) { t.push([7, 4], [5, 4]); resto = 0 }
    else { t.push([12, 3]); resto = 0 }
  }
  return t
}

function Cartao({ fluxo, capaPadrao, tam }: { fluxo: Fluxo; capaPadrao: string; tam?: [number, number] }) {
  const s = selos(fluxo.etiqueta)
  return (
    <a className="hf-est2-cartao" href={fluxo.destino} data-grande={!!tam && tam[0] * tam[1] >= 30}
      style={tam ? { gridColumn: `span ${tam[0]}`, gridRow: `span ${tam[1]}` } : undefined}>
      <div className="hf-est2-cartao-img">
        <Capa src={fluxo.capa ?? capaPadrao} />
        {/* O 3D render -> Video ainda e experimental (o mesmo selo do VFX Studio). */}
        {fluxo.destino === '#apps/maquete' && <small className="hf-selo-neon hf-est2-experimental">Experimental</small>}
        <div className="hf-est2-selos">
          {s.modelo && <span className="hf-est2-selo hf-est2-selo-modelo">{s.modelo}</span>}
          {s.gpu && <span className="hf-est2-selo">⚙ GPU</span>}
          {s.nuvem && <span className="hf-est2-selo">☁ Cloud</span>}
          {s.apiPaga && <span className="hf-est2-selo">⚡ API</span>}
        </div>
      </div>
      <div className="hf-est2-cartao-texto">
        <strong>{fluxo.nome}</strong>
        <span>{fluxo.descricao}</span>
      </div>
      <b className="hf-est2-seta" aria-hidden="true">→</b>
    </a>
  )
}

// Nome legivel da criacao (a galeria guarda o id do modo: "flux3ref", "video"...).
const NOMES: Record<string, string> = {
  flux3: 'FLUX 3 Klein', flux3ref: 'FLUX 3 Klein · edit', flux3api: 'FLUX 3', klein: 'FLUX 2 Klein', flux2dev: 'FLUX.2 dev',
  flux1krea: 'FLUX.1 Krea dev', flux1s: 'FLUX.1 schnell', ltx: 'LTX 2.5', minimax: 'MiniMax H3', fasth3: 'FastH3',
  transformar_video: 'LTX VFX', avatar: 'Lip Sync', genjutsu: 'Genjutsu', wan22_14b: 'Wan 2.2 14B', wan22_5b: 'Wan 2.2 5B',
  wan21_13b: 'Wan 2.1 1.3B', wan3: 'Wan 3.0', wan27: 'Wan 2.7', flux3video: 'FLUX 3 Video', flux3max: 'FLUX 3 Max Video',
}
const nomeDe = (r: ItemGaleria) => {
  const id = r.modelo === 'video' ? String(r.parametros?.modelo_video ?? 'video') : r.modelo
  return r.rotulo || NOMES[id] || (r.modelo === 'video' ? 'Video' : id)
}

const tempo = (s: number) => {
  const m = Math.max(1, Math.round((Date.now() / 1000 - s) / 60))
  return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`
}

function SecaoEstudio({ s, numero, capa }: { s: Secao; numero: number; capa: string }) {
  // Sem estilo escolhido: cartoes deitados nas secoes curtas, fileira compacta nas outras.
  const estilo = s.estilo ?? (s.fluxos.length <= 2 ? 'largo' : 'compacto')
  const t = estilo === 'bento' ? tamanhos(s.fluxos.length) : []
  // Fileira compacta: ate 7 por linha, sem sobrar um cartao sozinho (7 -> 4 + 3 com 7 itens largos).
  const colunas = estilo === 'compacto' ? (s.fluxos.length <= 7 ? (s.fluxos.length === 7 && s.largos ? 4 : s.fluxos.length) : 7) : undefined
  return (
    <section className="hf-est2-secao">
      <span className="hf-est2-numero">{String(numero).padStart(2, '0')} / {s.titulo.toUpperCase()}</span>
      <div className="hf-est2-cabecalho">
        <div><h3>{s.titulo}</h3><p>{s.texto}</p></div>
        {s.verTudo && <a className="hf-est2-ver" href={s.verTudo}>View all →</a>}
      </div>
      <div className="hf-est2-grade" data-estilo={estilo} style={colunas ? { gridTemplateColumns: `repeat(${colunas}, minmax(0, 1fr))` } : undefined}>
        {s.fluxos.map((f, i) => <Cartao key={f.nome + f.destino} fluxo={f} capaPadrao={capa} tam={t[i]} />)}
      </div>
    </section>
  )
}

export function PaginaEstudio({ e }: { e: Estudio }) {
  const [recentes, setRecentes] = useState<ItemGaleria[]>([])
  useEffect(() => {
    api.galeria(300).then((itens) => setRecentes(itens.filter(e.meu).slice(0, 4))).catch(() => {})
  }, [e])
  const passos = [
    ['Choose a workflow', 'Pick a card: image, video or a model.'],
    ['Add your input', 'A prompt, images or a video.'],
    ['Adjust settings', 'Model, aspect ratio, length…'],
    ['Generate', 'Create and iterate.'],
  ]
  return (
    <div className="hf-aba hf-est2">
      <div className="hf-est2-principal">
        <div className="hf-est2-capa">
          <div className="hf-est2-capa-texto">
            <span className="hf-est2-sobre">{e.nome}</span>
            <h1>{e.titulo}</h1>
            <p>{e.texto}</p>
            <a className="hf-est2-criar" href={e.destaque.destino}>Start creating <span aria-hidden="true">→</span></a>
            <div className="hf-est2-onde">
              <span><b>⚙ GPU</b><small>Local</small></span>
              <span><b>☁ Cloud</b><small>Comfy Cloud</small></span>
              <span><b>⚡ API</b><small>Partner models</small></span>
            </div>
          </div>
          <div className="hf-est2-capa-quadro"><Capa src={e.capa} classe="hf-est2-capa-midia" /></div>
        </div>
        {/* Secoes curtas (ate 2 cartoes) dividem a linha, como no layout aprovado. */}
        {(() => {
          const blocos: Secao[][] = []
          e.secoes.forEach((sec) => {
            const ult = blocos.at(-1)
            const curta = sec.fluxos.length <= 2
            if (curta && ult && ult.length === 1 && ult[0].fluxos.length <= 2) ult.push(sec)
            else blocos.push([sec])
          })
          let n = 0
          return blocos.map((bloco) => (
            <div key={bloco[0].titulo} className="hf-est2-bloco" data-lado-a-lado={bloco.length > 1}>
              {bloco.map((sec) => { n += 1; return <SecaoEstudio key={sec.titulo} s={sec} numero={n} capa={e.capa} /> })}
            </div>
          ))
        })()}
      </div>

      <aside className="hf-est2-lado">
        <h3>Quick start</h3>
        <p className="hf-dica">Create with {e.nome.replace(' Studio', '')} in a few steps.</p>
        <ol className="hf-est2-passos">
          {passos.map(([t, d], i) => (
            <li key={t} data-ativo={i === 0}><span>{i + 1}</span><div><b>{t}</b><small>{d}</small></div></li>
          ))}
        </ol>
        <div className="hf-est2-recentes-topo"><h3>Recent creations</h3><a href="#assets">View all</a></div>
        {recentes.length ? recentes.map((r) => (
          <button key={r.id} type="button" className="hf-est2-recente" onClick={() => abrirVisualizador({ nome: r.arquivo, subpasta: r.subpasta })}>
            {r.duracao_video ? <video src={urlImagem({ nome: r.arquivo, subpasta: r.subpasta }) + '#t=0.5'} muted preload="metadata" />
              : <img src={urlImagem({ nome: r.arquivo, subpasta: r.subpasta })} alt="" loading="lazy" />}
            <div><b>{nomeDe(r)}</b><small>{tempo(r.criada_em)}</small></div>
          </button>
        )) : <p className="hf-dica">What you make here shows up in this list.</p>}
      </aside>
    </div>
  )
}

const H3: Estudio = {
  nome: 'MiniMax H3 Studio',
  titulo: 'Video with sound, characters and music.',
  texto: 'MiniMax H3 makes video and its soundtrack together. Run the open model on a big GPU, the fast distilled FastH3, or Comfy Cloud.',
  destaque: { rotulo: 'Create', destino: '#video/imagem/minimax' },
  capa: '/exemplos/capa_h3.mp4',
  meu: (i) => (i.modelo === 'video' && /minimax|fasth3/i.test(String(i.parametros?.modelo_video ?? ''))) || (i.modelo === 'genjutsu' && /h3/i.test(String(i.parametros?.modelo_genjutsu ?? ''))),
  secoes: [
    { titulo: 'Create', icone: 'video', texto: 'Text, a first frame, or how the shot begins and ends.', verTudo: '#video/texto/minimax', fluxos: [
      { nome: 'Text → Video', descricao: 'A scene from a line of text, with sound.', destino: '#video/texto/minimax', etiqueta: 'MiniMax H3', capa: '/studios/cartoes/h3_texto.gif' },
      { nome: 'Image → Video', descricao: 'Animate a still, keeping its subject and look.', destino: '#video/imagem/minimax', etiqueta: 'MiniMax H3', capa: '/studios/cartoes/h3_imagem.gif' },
      { nome: 'First & last frame', descricao: 'Choose how the shot begins and ends.', destino: '#video/primeiro_ultimo/minimax', etiqueta: 'MiniMax H3', capa: '/studios/cartoes/h3_pu.gif' },
      { nome: 'FastH3', descricao: 'MiniMax H3 distilled to 8 steps: the same model, about twice as fast, up to 15 s.', destino: '#video/texto/fasth3', etiqueta: 'FastH3 · Local GPU', capa: '/studios/cartoes/h3_fast.gif' },
      { nome: 'References → Video', descricao: 'Put up to 9 people or objects from your images into one shot.', destino: '#video/referencia/minimax-ref-nuvem', etiqueta: 'MiniMax H3 · Comfy Cloud · API', capa: '/studios/cartoes/nuvem_h3_ref.gif' },
    ] },
    { titulo: 'Recast', estilo: 'largo', icone: 'genjutsu', texto: 'Keep the motion, camera, light and sound of a video; change who is in it.', verTudo: '#genjutsu', fluxos: [
      { nome: 'H3 Character Swap', descricao: 'SAM 3 finds who to replace; MiniMax H3 puts your character in, with the original motion and sound.', destino: '#genjutsu/h3_swap', etiqueta: 'MiniMax H3 Ref2VA', capa: '/exemplos/trocar.mp4' },
    ] },
    { titulo: 'Sound', estilo: 'largo', icone: 'music', texto: 'The same family writes the music.', verTudo: '#music', fluxos: [
      { nome: 'MiniMax Music 3', descricao: 'Full songs with vocals and lyrics, up to 5 minutes.', destino: '#music/minimax-music3', etiqueta: 'Music 3 · Comfy Cloud · API', capa: '/studios/cartoes/h3_music.webp' },
    ] },
  ],
}

const WAN: Estudio = {
  nome: 'Wan Studio',
  titulo: 'From a tiny GPU to a full studio.',
  texto: 'Alibaba’s Wan family, from the 1.3B model that runs on 8 GB to Wan 2.2 14B, plus character animation that copies the motion of any video.',
  destaque: { rotulo: 'Create', destino: '#video/texto/wan22_14b' },
  capa: '/exemplos/capa_wan.mp4',
  meu: (i) => /^wan/i.test(i.modelo) || (i.modelo === 'video' && /wan/i.test(String(i.parametros?.modelo_video ?? ''))) || (i.modelo === 'genjutsu' && /wan/i.test(String(i.parametros?.modelo_genjutsu ?? ''))),
  secoes: [
    { titulo: 'Make the shot', largos: true, icone: 'video', texto: 'Pick the size that fits your graphics card, or run it on Comfy Cloud.', verTudo: '#video/texto/wan22_14b', fluxos: [
      { nome: 'Text → Video', descricao: 'Wan 2.2 14B in 4 steps (lightx2v), from the official ComfyUI template.', destino: '#video/texto/wan22_14b', etiqueta: 'Wan 2.2 14B', capa: '/studios/cartoes/wan_texto.gif' },
      { nome: 'Image → Video', descricao: 'Animate a still with Wan 2.2 14B.', destino: '#video/imagem/wan22_14b', etiqueta: 'Wan 2.2 14B', capa: '/studios/cartoes/wan_imagem.gif' },
      { nome: 'First & last frame', descricao: 'Wan 2.2 14B moves from one image to another.', destino: '#video/primeiro_ultimo/wan22_14b', etiqueta: 'Wan 2.2 14B', capa: '/studios/cartoes/wan_pu.gif' },
      { nome: 'Wan 2.2 5B', descricao: 'Text or image to 720p video on an 8 GB card.', destino: '#video/texto/wan22_5b', etiqueta: 'Wan 2.2 5B · GPU', capa: '/studios/cartoes/wan_5b.gif' },
      { nome: 'Wan 2.1 1.3B', descricao: 'The lightest Wan: text to 480p video.', destino: '#video/texto/wan21_13b', etiqueta: 'Wan 2.1 · GPU', capa: '/studios/cartoes/wan_13b.gif' },
      { nome: 'Wan 3.0', descricao: 'Image, first & last frame and references, hosted by Comfy.', destino: '#video/imagem/wan3', etiqueta: 'Wan 3.0 · Comfy Cloud · API', capa: '/studios/cartoes/nuvem_wan3.gif' },
      { nome: 'Wan 2.7', descricao: 'Text, image and first & last frame, hosted by Comfy.', destino: '#video/texto/wan27', etiqueta: 'Wan 2.7 · Comfy Cloud · API', capa: '/studios/cartoes/nuvem_wan27.gif' },
    ] },
    { titulo: 'Animate', estilo: 'largo', icone: 'genjutsu', texto: 'Copy the exact motion of a video: face, body and hands.', verTudo: '#genjutsu', fluxos: [
      { nome: 'Wan Animate 2', descricao: 'The person in your photo performs the video’s motion, in the photo’s own setting.', destino: '#genjutsu/wan_animate2', etiqueta: 'Wan Animate 2 · Comfy Cloud', capa: '/exemplos/trocar.mp4' },
      { nome: 'Wan 2.2 Animate · Replace', descricao: 'Your character replaces the person inside the video; the light is matched to the scene.', destino: '#genjutsu/wan22_replace', etiqueta: 'Wan 2.2 Animate', capa: '/studios/cartoes/wan_replace.webp' },
    ] },
    { titulo: 'Image', estilo: 'largo', icone: 'image', texto: 'A first frame for any of the above.', verTudo: '#image', fluxos: [
      { nome: 'Wan 2.5 Image', descricao: 'Text to image with Wan 2.5.', destino: '#image/wan25img', etiqueta: 'Wan 2.5 · Comfy Cloud · API', capa: '/studios/cartoes/nuvem_wan25img.webp' },
    ] },
  ],
}

const FLUX3: Estudio = {
  nome: 'FLUX 3 Studio',
  titulo: 'Photoreal images, edits and video.',
  texto: 'FLUX 3 Klein runs on your own GPU; the full FLUX 3 and FLUX 3 Video run on Comfy Cloud. Edit with reference images, direct a shot, then animate it.',
  destaque: { rotulo: 'Create', destino: '#image/flux3' },
  capa: '/exemplos/capa_flux3.webp?v=2',
  meu: (i) => /flux|klein/i.test(i.modelo) || (i.modelo === 'video' && /flux/i.test(String(i.parametros?.modelo_video ?? ''))),
  secoes: [
    { titulo: 'Image', estilo: 'bento', icone: 'image', texto: 'Photoreal images and well-written text, or edit with references.', verTudo: '#image/flux3', fluxos: [
      { nome: 'Flux 3 Klein', descricao: 'Photorealism and well-written text, on your GPU or on Comfy Cloud.', destino: '#image/flux3', etiqueta: 'FLUX 3 Klein · GPU', capa: '/studios/cartoes/flux_klein.webp' },
      { nome: 'Edit with references', descricao: 'Drop images into the box and describe the change: @image1, @image2…', destino: '#image/flux3', etiqueta: 'FLUX 3 Klein · GPU · Comfy Cloud', capa: '/studios/cartoes/flux_refs.webp' },
      { nome: 'FLUX 3', descricao: 'The full FLUX 3 model, hosted by Comfy.', destino: '#image/flux3api', etiqueta: 'FLUX 3 · Comfy Cloud · API', capa: '/cinema/genero/epoca.webp' },
      { nome: 'Cinema Studio', descricao: 'Direct the shot: camera, lens, light, film and grade, with Flux 3 Klein.', destino: '#cinema', etiqueta: 'Cinema Studio · Comfy Cloud', capa: '/studios/cartoes/cinema.gif' },
    ] },
    { titulo: 'Video', estilo: 'largo', icone: 'video', texto: 'Animate a FLUX 3 picture, or go straight to video.', verTudo: '#video', fluxos: [
      { nome: 'FLUX 3 Video', descricao: 'Text or image to video.', destino: '#video/texto/flux3video', etiqueta: 'FLUX 3 Video · Comfy Cloud · API', capa: '/studios/cartoes/nuvem_flux3video.gif' },
      { nome: 'FLUX 3 Max Video', descricao: 'The highest-quality FLUX video.', destino: '#video/texto/flux3max', etiqueta: 'FLUX 3 Max Video · Comfy Cloud · API', capa: '/cinema/genero/scifi.webp' },
      { nome: 'Animate a FLUX 3 picture', descricao: 'Hover any image in the gallery and press ▶ Animate: LTX moves it, with sound.', destino: '#video/imagem', etiqueta: 'FLUX 3 + LTX · Comfy Cloud', capa: '/studios/cartoes/flux_animar.gif' },
    ] },
    { titulo: 'FLUX family', estilo: 'compacto', icone: 'assets', texto: 'Other FLUX models you can install from Config Models.', verTudo: '#image', fluxos: [
      { nome: 'FLUX 2 Klein 9B', descricao: 'Maximum micro-detail and texture.', destino: '#image/klein', etiqueta: 'FLUX 2', capa: '/studios/cartoes/flux_klein9b.webp' },
      { nome: 'FLUX.2 dev', descricao: 'The big FLUX.2 (32B). Best on Comfy Cloud.', destino: '#image/flux2dev', etiqueta: 'FLUX 2 · GPU · Comfy Cloud', capa: '/cinema/genero/noir.webp' },
      { nome: 'FLUX.1 Krea dev', descricao: 'Natural photos that look less like AI.', destino: '#image/flux1krea', etiqueta: 'FLUX.1', capa: '/studios/cartoes/flux_krea.webp' },
      { nome: 'FLUX.1 schnell', descricao: 'Fast and light: 4 steps, 8–12 GB cards.', destino: '#image/flux1s', etiqueta: 'FLUX.1', capa: '/studios/cartoes/flux_schnell.webp' },
    ] },
  ],
}

export const AbaH3 = () => <PaginaEstudio e={H3} />
export const AbaWan = () => <PaginaEstudio e={WAN} />
export const AbaFlux3 = () => <PaginaEstudio e={FLUX3} />
