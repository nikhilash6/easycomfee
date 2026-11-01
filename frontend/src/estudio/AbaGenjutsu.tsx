import { useContext, useEffect, useRef, useState } from 'react'
import { CartaoModelo, LinhaOnde, MotorCtx, useEscolha, useInstalado } from './motor'
import { api, referenciaDaGaleria, urlEntrada, urlImagem, type Referencia } from '../api'
import { ThenNow } from './Visualizador'
import { BotaoGerar, CartaoTarefa, Chips, SlotImagem, arquivos, mensagem, useCusto, useTarefas, type Estimativa, Galeria, parteDoHash, useLembrado, textoDoDetalhe, MAX_PROMPT, TituloPagina } from './comum'

// Genjutsu: recast a video with a new cast, place or style while its motion,
// camera and timing stay. Models (backend genjutsu.py):
// - Recast (open, default): Qwen Image Edit redraws the first frame with the
//   references, then LTX Union Control carries the whole video to that look.
//   This tab chains the two jobs: when the frame is done, the video job starts.
// - Wan Animate 2 (open): the character photo performs the video's motion.
// - Wan 2.2 Animate Replace (open): the official template, SAM 3 mask; the character goes INTO the video.
// - MiniMax H3 Character Swap (open, Comfy Cloud): MDMZ's workflow; SAM 3 mask + H3 Ref2VA.
// - Higgsfield Genjutsu, Kling Omni, Runway Aleph2: Comfy partner nodes.

type Modelo = { id: string; rotulo: string; aberto: boolean; refs: string[]; dica: string }

const MODELOS: Modelo[] = [
  { id: 'recast', rotulo: 'Recast', aberto: true, refs: ['Character', 'Location (optional)'],
    dica: 'Open weights. Redraws the first frame with your references, then carries the whole video to that look. Up to 14 s.' },
  { id: 'wan_animate2', rotulo: 'Wan Animate 2', aberto: true, refs: ['Character'],
    dica: 'Open weights. The person in your photo performs the exact motion of the video (face, body, hands), in the photo’s own setting. About 5 s.' },
  { id: 'wan22_replace', rotulo: 'Wan 2.2 Animate · Replace', aberto: true, refs: ['Character'],
    dica: 'Open weights. Replaces the person inside the video with your character, keeping the place; the light is matched to the scene. About 5 s. Comfy Cloud, or your GPU with its package from Config Models.' },
  { id: 'h3_swap', rotulo: 'MiniMax H3 Character Swap', aberto: true, refs: ['Character'],
    dica: 'Open weights. Comfy Cloud, or your GPU with its package from Config Models (24-32 GB card). SAM 3 finds who to replace; MiniMax H3 puts your character in, with the video’s motion, camera, light and sound. Up to 8 s. Workflow by MDMZ.' },
  { id: 'higgsfield', rotulo: 'Higgsfield Genjutsu', aberto: false, refs: ['Reference 1', 'Reference 2 (optional)', 'Reference 3 (optional)'],
    dica: 'The original Genjutsu. New cast, place and style from up to 8 references. 720p, up to 30 s.' },
  { id: 'kling_omni', rotulo: 'Kling 3.0 Omni', aberto: false, refs: ['Reference 1 (optional)', 'Reference 2 (optional)'],
    dica: 'Video to video guided by text and reference images. 720p, 3 to 10 s.' },
  { id: 'aleph2', rotulo: 'Runway Aleph2', aberto: false, refs: [],
    dica: 'Restyle, relight, add or remove things, described in text. Up to 30 s.' },
]

// Etiquetas dos cartoes: o essencial de cada modelo num relance.
// Foto de cada cartao de modelo (geradas para o app, em public/studios/cartoes).
const FOTOS: Record<string, string> = { recast: 'gj_recast', wan_animate2: 'gj_wan_animate', wan22_replace: 'gj_wan_replace',
  h3_swap: 'gj_h3_swap', higgsfield: 'gj_higgsfield', kling_omni: 'gj_kling', aleph2: 'gj_runway' }

const ETIQUETAS: Record<string, string[]> = {
  recast: ['New cast + place', 'Up to 14 s'],
  wan_animate2: ['Photo performs the video', '~5 s', 'Cloud'],
  wan22_replace: ['Into the video', '~5 s'],
  h3_swap: ['Into the video', 'With sound', 'Up to 8 s'],
  higgsfield: ['Up to 30 s', '8 references'],
  kling_omni: ['3–10 s'],
  aleph2: ['Text only', 'Up to 30 s'],
}

const ROTULO_CUSTO = (a: Estimativa | null, b: Estimativa | null): Estimativa | null =>
  a && b && a.tipo === b.tipo && a.tipo === 'gpu' ? { tipo: 'gpu', usd: (a.usd ?? 0) + (b.usd ?? 0) }
    : a && b && a.tipo === 'gratis' && b.tipo === 'gratis' ? a : b

export default function AbaGenjutsu({ apiLiberado }: { apiLiberado: boolean }) {
  const tarefas = useTarefas()
  const [modelo, setModelo] = useState(() => MODELOS.some((m) => m.id === parteDoHash(1)) ? parteDoHash(1) : 'recast')
  const escolher = useEscolha(setModelo)
  const { naNuvem } = useContext(MotorCtx)
  const instalado = useInstalado()
  const [video, setVideo] = useState<Referencia | null>(null)
  const [refs, setRefs] = useState<(Referencia | null)[]>([])
  const [texto, setTexto] = useLembrado('genjutsu.texto', '')
  const [controle, setControle] = useState('pose')
  // MiniMax H3 Character Swap
  const [alvo, setAlvo] = useState('person')
  const [gemini, setGemini] = useState(true)
  const [turbo, setTurbo] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  // Recast in flight: the frame job, and what the video job needs once it is done.
  const pendente = useRef<{ id: string; video: string; texto: string; controle: string } | null>(null)
  const [etapa, setEtapa] = useState('')
  // Jobs started here (the Recast steps are ordinary image and video jobs).
  const [meus, setMeus] = useState<string[]>([])
  const anotar = (id: string) => setMeus((m) => [id, ...m])

  const cfg = MODELOS.find((m) => m.id === modelo)!
  // Cartao: modelo aberto no motor atual (Wan Animate 2 so existe na nuvem); de API, pelo id.
  const escolherModelo = (m: Modelo) => {
    if (!m.aberto) { escolher(m.id); return }
    escolher(`${m.id === 'wan_animate2' || naNuvem ? 'nuvem' : 'local'}:${m.id}`)
  }
  const cartao = (m: Modelo) => (
    <CartaoModelo key={m.id} ativo={modelo === m.id} aoEscolher={() => escolherModelo(m)} title={m.dica}
      rodape={m.aberto && <LinhaOnde escolher={escolher} id={m.id} cartaoAtivo={modelo === m.id} local={m.id !== 'wan_animate2'} nuvem faltaLocal={!instalado(m.id)} />}>
      {FOTOS[m.id] && <img className="hf-gj-foto" src={`/studios/cartoes/${FOTOS[m.id]}.webp`} alt="" loading="lazy" />}
      <b>{m.rotulo}</b>
      <span className="hf-mu-tags">
        <i data-onde={m.aberto ? 'local' : 'falta'}>{m.aberto ? 'Open weights' : 'API'}</i>
        {(ETIQUETAS[m.id] ?? []).filter((t) => t !== 'Cloud').map((t) => <i key={t}>{t}</i>)}
      </span>
    </CartaoModelo>
  )
  const imagens = refs.slice(0, cfg.refs.length).filter(Boolean) as Referencia[]
  const precisaRef = cfg.refs.length > 0 && !cfg.refs[0].includes('optional')
  const pronto = !!video && (!cfg.aberto || naNuvem || instalado(modelo)) && (!precisaRef || imagens.length > 0)
    && (modelo === 'wan_animate2' || modelo === 'wan22_replace' || modelo === 'h3_swap' || !!texto.trim()) && !etapa

  const custoQuadro = useCusto(modelo === 'recast' ? { modelo: 'qwen', prompt: 'x', proporcao: '16:9', lote: 1, referencias: ['a.png'] } : null)
  const custoVideo = useCusto(!video ? null : modelo === 'recast'
    ? { modelo: 'transformar_video', efeito_video: 'trocar', prompt: 'x', proporcao: '1:1', referencias: [`entrada:${video.nome}`] }
    : { modelo: 'genjutsu', modelo_genjutsu: modelo, prompt: 'x', proporcao: '1:1',
        referencias: [`entrada:${video.nome}`, ...imagens.map((r) => r.nome)],
        ...(modelo === 'h3_swap' ? { alvo_genjutsu: alvo, gemini_genjutsu: gemini, turbo_genjutsu: turbo } : modelo === 'wan22_replace' ? { alvo_genjutsu: alvo } : {}) })
  const custo = modelo === 'recast' ? ROTULO_CUSTO(custoQuadro, custoVideo) : custoVideo

  // Step 2 of Recast: when the new first frame is ready, start the video job.
  useEffect(() => {
    const p = pendente.current
    if (!p) return
    const t = tarefas.find((x) => x.id === p.id)
    if (!t || (t.estado !== 'pronto' && t.estado !== 'erro')) return
    pendente.current = null
    if (t.estado === 'erro') { setEtapa(''); setErro(t.erro || 'The first frame failed.'); return }
    const quadro = arquivos(t)[0]
    setEtapa('Animating the video…')
    referenciaDaGaleria({ arquivo: quadro.nome, subpasta: quadro.subpasta })
      .then((r) => api.gerar({
        modelo: 'transformar_video', efeito_video: 'trocar', controle_troca: p.controle, prompt: p.texto,
        proporcao: '1:1', referencias: [`entrada:${p.video}`, r.nome],
      } as Parameters<typeof api.gerar>[0]))
      .then((v) => anotar(v.id))
      .catch((e) => setErro(mensagem(e)))
      .finally(() => setEtapa(''))
  }, [tarefas])

  const gerar = async () => {
    if (!video) return
    setErro(null)
    try {
      if (modelo === 'recast') {
        setEtapa('Redrawing the first frame…')
        const r = await fetch('/api/genjutsu/quadro', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ video: `entrada:${video.nome}` }) })
        if (!r.ok) throw new Error(textoDoDetalhe((await r.json().catch(() => ({}))).detail, 'Could not read the video.'))
        const { nome } = await r.json()
        const quem = imagens.length > 1
          ? 'the main character from image 2, placed in the setting of image 3'
          : 'the main character from image 2'
        const instrucao = `Redraw image 1 keeping its exact composition, camera angle, framing and the pose of every person. Replace the person with ${quem}. ${texto.trim()}`
        const t = await api.gerar({ modelo: 'qwen', prompt: instrucao, proporcao: '16:9', lote: 1,
          resolucao_edicao: 'baixa', referencias: [nome, ...imagens.map((i) => i.nome)] } as Parameters<typeof api.gerar>[0])
        anotar(t.id)
        pendente.current = { id: t.id, video: video.nome, texto: texto.trim(), controle }
      } else {
        // The server refuses an empty prompt; for Wan the text is optional.
        // The server refuses an empty prompt; these models need none, so a neutral line goes.
        const frase = texto.trim() || (modelo === 'h3_swap'
          ? 'Replace the performer in the video with the character in the image, copying the motion, timing and camera movement exactly.'
          : modelo === 'wan22_replace' ? 'The person moves naturally' : 'The person from the photo, moving naturally')
        anotar((await api.gerar({ modelo: 'genjutsu', modelo_genjutsu: modelo, prompt: frase, proporcao: '1:1',
          referencias: [`entrada:${video.nome}`, ...imagens.map((i) => i.nome)],
          ...(modelo === 'h3_swap' ? { alvo_genjutsu: alvo, gemini_genjutsu: gemini, turbo_genjutsu: turbo } : modelo === 'wan22_replace' ? { alvo_genjutsu: alvo } : {}),
        } as unknown as Parameters<typeof api.gerar>[0])).id)
      }
    } catch (e) { setEtapa(''); setErro(mensagem(e)) }
  }

  const minhas = tarefas.filter((t) => t.modelo === 'genjutsu' || meus.includes(t.id))
  // O ultimo video pronto desta sessao vai para o comparador Original | Result.
  const feita = minhas.find((t) => t.estado === 'pronto' && arquivos(t).some((a) => /\.(mp4|webm|mov)$/i.test(a.nome)))
  const resultado = feita ? arquivos(feita).find((a) => /\.(mp4|webm|mov)$/i.test(a.nome)) : undefined

  return (
    <div className="hf-aba hf-img hf-gj">
      <TituloPagina antes="Recast" destaque="any video" sub="Same motion, camera and timing. New cast, place or style." />

      <div className="hf-mu-modelos hf-gj-modelos">{MODELOS.filter((m) => m.aberto).map(cartao)}</div>
      {apiLiberado && <>
        <span className="hf-grupo-rotulo hf-gj-api">Partner models · Comfy credits</span>
        <div className="hf-mu-modelos hf-gj-modelos">{MODELOS.filter((m) => !m.aberto).map(cartao)}</div>
      </>}

      <div className="hf-barra-prompt hf-ls hf-gj-passos">
        <div className="hf-ls-passos">
          <section className="hf-ls-cartao" data-pronto={!!video}>
            <header><b>1</b> Video <small>{cfg.dica}</small></header>
            <label className="hf-slot hf-gj-video" data-cheio={!!video}>
              {video ? <video src={urlEntrada(video.nome)} muted loop autoPlay playsInline />
                : <span>{enviando ? 'Uploading…' : '+ Your video'}<small>The motion, camera and timing come from here</small></span>}
              <input type="file" accept="video/*" className="hf-arquivo" onChange={async (e) => {
                const f = e.target.files?.[0]
                if (!f) return
                setEnviando(true); setErro(null)
                try { setVideo(await api.enviarReferencia(f)) } catch (x) { setErro(mensagem(x)) } finally { setEnviando(false) }
              }} />
            </label>
            {video && <button type="button" className="hf-botao-sec" onClick={() => setVideo(null)}>Remove video</button>}
          </section>

          <section className="hf-ls-cartao" data-pronto={!precisaRef || imagens.length > 0}>
            <header><b>2</b> New cast {cfg.refs.length === 0 && <small>not used by this model</small>}</header>
            {cfg.refs.length > 0 ? (
              <div className="hf-gj-refs" data-n={cfg.refs.length}>
                {cfg.refs.map((rotulo, i) => (
                  <SlotImagem key={modelo + i} rotulo={rotulo} valor={refs[i] ?? null}
                    aoMudar={(r) => setRefs((atual) => { const c = atual.slice(); c[i] = r; return c })} />
                ))}
              </div>
            ) : <p className="hf-dica">{cfg.rotulo} works from the text alone.</p>}
            <p className="hf-dica">A clear photo of the character, full body if the video shows the body. Drag one from the gallery or press ↑ Use.</p>
          </section>

          <section className="hf-ls-cartao hf-ls-cena">
            <header><b>3</b> Direction {(modelo === 'wan_animate2' || modelo === 'wan22_replace' || modelo === 'h3_swap') && <small>optional</small>}</header>
            <textarea aria-label="Direction" maxLength={MAX_PROMPT} value={texto} onChange={(e) => setTexto(e.target.value)} rows={4}
              placeholder={modelo === 'wan_animate2'
                ? 'Describe the character and the background'
                : modelo === 'h3_swap' ? 'e.g. the performer is singing; keep the original voice'
                : 'What changes, e.g. the dancer becomes a snow queen in an ice palace'} />
            {modelo === 'recast' && (
              <label className="hf-ctrl"><small>The new video follows</small>
                <Chips rotulo="Follow" opcoes={[{ id: 'pose', rotulo: 'Body pose' }, { id: 'profundidade', rotulo: 'Depth' }]}
                  valor={controle} aoMudar={setControle} /></label>
            )}
            {(modelo === 'wan22_replace' || modelo === 'h3_swap') && (
              <label className="hf-ctrl" title="Who leaves the video. 'person' for one person; 'woman in red:1' to pick one of several.">
                <small>Who to replace</small>
                <input className="hf-campo" value={alvo} onChange={(e) => setAlvo(e.target.value)} placeholder="person" />
              </label>
            )}
            {modelo === 'h3_swap' && <>
              <Chips rotulo="Prompt" opcoes={[{ id: 'g', rotulo: 'Gemini writes it (API)' }, { id: 'p', rotulo: 'Standard' }]}
                valor={gemini ? 'g' : 'p'} aoMudar={(v) => setGemini(v === 'g')} />
              <Chips rotulo="Speed" opcoes={[{ id: 'n', rotulo: 'Quality · 20 steps' }, { id: 't', rotulo: 'Turbo · 8 steps' }]}
                valor={turbo ? 't' : 'n'} aoMudar={(v) => setTurbo(v === 't')} />
            </>}
            <div className="hf-gj-gerar">
              {etapa && <span className="hf-dica">{etapa}</span>}
              {cfg.aberto && !naNuvem && !instalado(modelo) && (
                <span className="hf-erro">{cfg.rotulo} is not installed on this computer. Install it in Config Models, or choose Cloud on its card.</span>
              )}
              <BotaoGerar rotulo="Generate →" est={custo} desligado={!pronto} aoClicar={gerar} />
            </div>
          </section>
        </div>
        {erro && <p className="hf-erro">{erro}</p>}
      </div>

      {video && resultado && (
        <section className="hf-gj-comparar" aria-label="Original and result">
          <ThenNow antes={urlEntrada(video.nome)} depois={urlImagem(resultado)} modo="cortina" rotulos={['Original', 'Result']} />
        </section>
      )}

      <section className="hf-img-recentes hf-lsn-recentes" aria-label="Recent recasts">
      <span className="hf-img-titulo">Recent recasts</span>
      <Galeria tipo="video">
        {minhas.map((t) => <CartaoTarefa key={t.id} t={t} />)}
        {minhas.length === 0 && <p className="hf-vazio">Your recast videos will appear here.</p>}
      </Galeria>
      </section>
    </div>
  )
}
