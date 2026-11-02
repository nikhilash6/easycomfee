import { useEffect, useRef, useState } from 'react'
import { useReusarPrompt } from './Visualizador'
import { AvisoInstalar, GruposAbertos, useEscolha, useValor, useFaltaInstalar } from './motor'
import { api, urlImagem, type GeradorVideo, type Referencia } from '../api'
import { BotaoGerar, CartaoTarefa, Chips, SlotImagem, mensagem, useCusto, useTarefas, arquivos, parteDoHash, useLembrado, quadroChave, passoChave, MAX_PROMPT , AJUSTES_VAZIOS, Avancado, camposAjustes, type Ajustes, TituloPagina, Midia, EVENTO_REMOVIDO } from './comum'

// Video tab: LTX 2.5 or the open-weight MiniMax H3, plus the API generators.
// "References" puts the people and objects of your images into the shot:
// LTX 2.5 MSR on your GPU (up to 4, plus an optional background; its custom
// node is not on Comfy Cloud), and the API generators MiniMax H3 MultiRef (9),
// Kling Omni (7), Seedance 2.5 Reference (9) and Wan 3.0 (10).
// Ingredients and keyframes stay in Advanced.

type Modo = 'texto' | 'imagem' | 'primeiro_ultimo' | 'referencia' | 'chaves'

const MODOS: { id: Modo; rotulo: string }[] = [
  { id: 'texto', rotulo: 'Text → Video' },
  { id: 'imagem', rotulo: 'Image → Video' },
  { id: 'primeiro_ultimo', rotulo: 'First & last frame' },
  { id: 'referencia', rotulo: 'References → Video' },
  // LTX 2.5 only (local or Comfy Cloud): 2 to 8 images, each at its own moment of the clip.
  { id: 'chaves', rotulo: 'Keyframes → Video' },
]

// Outros geradores abertos (backend videos_leves.py e FastH3): modos,
// resolucoes, duracao maxima e se existem na Comfy Cloud (conferido no
// object_info da nuvem em 27/10/2026: LTX 2.3, os Wan, HunyuanVideo 1.5 e Kandinsky 5 sim; LTX-Video 2B e FastH3 nao).
const LEVES: Record<string, { rotulo: string; modos: Modo[]; resolucoes: string[]; max: number; nuvem: boolean }> = {
  ltx23: { rotulo: 'LTX 2.3', modos: ['imagem', 'primeiro_ultimo'], resolucoes: ['480p', '720p'], max: 30, nuvem: true },
  fasth3: { rotulo: 'FastH3 (MiniMax H3 distilled)', modos: ['texto', 'imagem', 'primeiro_ultimo'], resolucoes: ['480p', '720p'], max: 15, nuvem: false },
  wan22_14b: { rotulo: 'Wan 2.2 14B', modos: ['texto', 'imagem', 'primeiro_ultimo'], resolucoes: ['480p', '720p'], max: 5, nuvem: true },
  hunyuan15: { rotulo: 'HunyuanVideo 1.5', modos: ['texto', 'imagem'], resolucoes: ['480p', '720p'], max: 5, nuvem: true },
  kandinsky5: { rotulo: 'Kandinsky 5 Lite', modos: ['texto'], resolucoes: ['480p'], max: 5, nuvem: true },
  ltxv2b: { rotulo: 'LTX-Video 2B (light)', modos: ['texto', 'imagem'], resolucoes: ['480p', '720p'], max: 10, nuvem: false },
  wan22_5b: { rotulo: 'Wan 2.2 5B (light)', modos: ['texto', 'imagem'], resolucoes: ['720p'], max: 5, nuvem: true },
  wan21_13b: { rotulo: 'Wan 2.1 1.3B (light)', modos: ['texto'], resolucoes: ['480p'], max: 5, nuvem: true },
}

type Chave = { id: number; img: Referencia | null; seg: number }
let proximaChave = 3

/** 1280x720 -> "16:9" (o selo do player). */
function proporcaoDe([w, h]: [number, number]) {
  const r = w / h
  return [['16:9', 16 / 9], ['9:16', 9 / 16], ['1:1', 1], ['4:3', 4 / 3], ['3:4', 3 / 4], ['21:9', 21 / 9]]
    .reduce((m, o) => (Math.abs((o[1] as number) - r) < Math.abs((m[1] as number) - r) ? o : m))[0] as string
}

export default function AbaVideo({ apiGeradores = [], apiOcultos = [], naNuvem = false, pronto = true }: {
  apiGeradores?: GeradorVideo[]; apiOcultos?: GeradorVideo[]; naNuvem?: boolean
  /** O catalogo ja chegou: antes disso um gerador de API do link ainda nao esta na lista. */
  pronto?: boolean }) {
  const tarefas = useTarefas()
  const [escolhido, setMotor] = useState<string>(() => parteDoHash(2) || 'ltx')
  // O que aparece, o que o preco mostra e o que vai no pedido sao o MESMO modelo:
  // um id que o menu nao tem (API oculta, sem chave, link inventado) vira LTX 2.5.
  // Modelo leve so local (nuvem: false) com o motor na Comfy Cloud: nao esta no menu ali.
  const soLocal = naNuvem && LEVES[escolhido]?.nuvem === false
  const motor = apiGeradores.some((g) => g.id === escolhido) || (!!LEVES[escolhido] && !soLocal)
    || escolhido === 'ltx' || escolhido === 'minimax' ? escolhido : 'ltx'
  const apiOculta = pronto && motor !== escolhido ? apiOcultos.find((g) => g.id === escolhido) : undefined
  const indisponivel = pronto && motor !== escolhido && !apiOculta
  const escolher = useEscolha(setMotor)
  const faltaInstalar = useFaltaInstalar()
  const valorSelect = useValor(motor, apiGeradores.some((g) => g.id === motor))
  const [turbo, setTurbo] = useState(true)
  const [modo, setModo] = useState<Modo>(() => {
    const destino = parteDoHash(1)
    return MODOS.some((item) => item.id === destino) ? destino as Modo : 'texto'
  })
  // O modo que o link pediu (#video/chaves/minimax): se o modelo nao o tem, a aba
  // avisa em vez de abrir outro modo calada.
  const [modoDoLink] = useState(() => parteDoHash(1))
  const [prompt, setPrompt] = useLembrado('video.prompt', '')
  // "Reuse prompt" in the viewer fills this tab's text.
  useReusarPrompt(setPrompt)
  const [proporcao, setProporcao] = useState('16:9')
  const [resolucao, setResolucao] = useState('720p')
  const [duracao, setDuracao] = useState(5)
  const [audio, setAudio] = useState(true)
  const [inicio, setInicio] = useState<Referencia | null>(null)
  const [fim, setFim] = useState<Referencia | null>(null)
  const [refs, setRefs] = useState<Referencia[]>([])
  const [fundo, setFundo] = useState<Referencia | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  // Keyframes: each image and the second it appears (counted from 0).
  const [chaves, setChaves] = useState<Chave[]>([{ id: 1, img: null, seg: 0 }, { id: 2, img: null, seg: 5 }])
  const [forcaChaves, setForcaChaves] = useState(0.7)

  // Geradores de API (MiniMax H3 API, Wan 3.0): cada um traz os proprios limites.
  const gApi = apiGeradores.find((g) => g.id === motor)
  // Open models: only LTX 2.5 takes references, and only locally (MSR).
  // MiniMax H3 MultiRef is a paid API node, listed with the API generators.
  const leve = LEVES[motor]
  const naoInstalado = faltaInstalar(motor, !!gApi)
  // O rotulo do servidor marca " (nuvem)" (app.py usa a marca); a tela e em ingles.
  const rotuloMotor = gApi ? gApi.rotulo.replace(' (nuvem)', '') : leve ? leve.rotulo : motor === 'ltx' ? 'LTX 2.5' : 'MiniMax H3'
  const modos = gApi ? MODOS.filter((m) => gApi.modos.includes(m.id))
    : leve ? MODOS.filter((m) => leve.modos.includes(m.id))
    : motor === 'ltx' ? MODOS.filter((m) => !naNuvem || m.id !== 'referencia')
      : MODOS.filter((m) => m.id !== 'referencia' && m.id !== 'chaves')
  const maxRefs = gApi ? (gApi.max_referencias ?? 1) : 4
  const modoOk = modos.some((m) => m.id === modo) ? modo : modos[0]?.id ?? 'texto'
  // Some sozinho quando a pessoa troca o modo (ou o modelo passa a ter o modo).
  const rotuloModo = (id: string) => MODOS.find((m) => m.id === id)?.rotulo
  const avisoModo = !modoDoLink ? null
    : !rotuloModo(modoDoLink) ? (modo === 'texto' ? `This link asks for an unknown mode ("${modoDoLink}"); showing ${rotuloModo(modoOk)}.` : null)
    : modo === modoDoLink && modoOk !== modo ? `${rotuloModo(modo)} is not available with this model; showing ${rotuloModo(modoOk)}.`
    : null
  const proporcoes = gApi ? (gApi.proporcoes ?? []).filter((p) => p !== 'adaptive') : ['16:9', '9:16', '1:1']
  const resolucoes = gApi ? (gApi.resolucoes ?? ['720p']) : leve ? leve.resolucoes : motor === 'minimax' ? ['480p', '720p'] : ['480p', '720p', '1080p']
  const proporcaoOk = proporcoes.includes(proporcao) ? proporcao : proporcoes[0]
  const resolucaoOk = resolucoes.includes(resolucao) ? resolucao : resolucoes[Math.min(1, resolucoes.length - 1)]
  const dMin = gApi?.duracao_min ?? 2, dMax = gApi?.duracao_max ?? leve?.max ?? 15
  const duracaoOk = Math.max(dMin, Math.min(dMax, duracao))

  const refsOk = refs.slice(0, maxRefs)
  const ehChaves = modoOk === 'chaves'
  // Keyframes in time order, only the ones with an image, inside the clip length.
  const chavesOk = chaves.filter((c) => c.img).map((c) => ({ ...c, seg: Math.min(c.seg, duracaoOk) })).sort((x, y) => x.seg - y.seg)
  // Duas imagens no mesmo quadro: o backend fica com uma so (como em FerramentasLTX).
  const chavesRepetidas = ehChaves && chavesOk.some((c, i) => i > 0 && quadroChave(c.seg, duracaoOk) === quadroChave(chavesOk[i - 1].seg, duracaoOk))
  const ehRef = modoOk === 'referencia'
  const faltaImagem = ehChaves ? chavesOk.length < 2 : ehRef ? refsOk.length === 0
    : (modoOk !== 'texto' && !inicio) || (modoOk === 'primeiro_ultimo' && !fim)
  // O Generate cinza so por falta de imagem nao dizia nada: com LTX 2.3, Wan 3.0 ou Runway
  // (so Image → Video) a aba trocava de modo sozinha e ficava so o quadro vazio
  // (varredura de 29/10/2026).
  const soDeImagem = !modos.some((m) => m.id === 'texto')
  const faltaQual = !faltaImagem ? ''
    : ehChaves ? `Add at least 2 keyframe images (${chavesOk.length} added).`
    : ehRef ? 'Add at least one reference image.'
    : modoOk === 'primeiro_ultimo' ? (!inicio && !fim ? 'Add the first and the last frame.' : !inicio ? 'Add the first frame.' : 'Add the last frame.')
    : `Add a start image${soDeImagem ? `: ${rotuloMotor} only makes video from an image` : ''}.`
  const motorPedido = motor
  const nomesRefs = ehRef ? refsOk.map((r) => r.nome)
    : [inicio, fim].filter((r): r is Referencia => !!r && modoOk !== 'texto').map((r) => r.nome)
      .slice(0, modoOk === 'primeiro_ultimo' ? 2 : 1)

  // Para o preco, imagem que ainda falta vira um nome qualquer: so os campos contam.
  const custo = useCusto({
    modelo: 'video', modelo_video: motorPedido, turbo, modo_video: modoOk, prompt: prompt || 'x', proporcao: '1:1',
    proporcao_video: proporcaoOk, resolucao_video: resolucaoOk, duracao_video: duracaoOk, com_audio: audio,
    referencias: modoOk === 'texto' ? [] : ehRef ? (nomesRefs.length ? nomesRefs : ['a.png']) : [inicio?.nome ?? 'a.png', fim?.nome ?? 'b.png'],
  })

  const [ajustes, setAjustes] = useState<Ajustes>(AJUSTES_VAZIOS)
  const [selecionado, setSelecionado] = useState<{ nome: string; subpasta: string } | null>(null)
  const [tamanhoVideo, setTamanhoVideo] = useState<[number, number] | null>(null)
  const [salvos, setSalvos] = useState<{ nome: string; subpasta: string }[]>([])
  useEffect(() => {
    const tirar = (e: Event) => { const d = (e as CustomEvent<{ nome: string; subpasta: string }>).detail
      setSalvos((l) => l.filter((a) => !(a.nome === d.nome && a.subpasta === d.subpasta))); setSelecionado(null) }
    window.addEventListener(EVENTO_REMOVIDO, tirar)
    return () => window.removeEventListener(EVENTO_REMOVIDO, tirar)
  }, [])
  useEffect(() => {
    api.galeria(400).then((itens) => setSalvos(itens.filter((i) => !!i.duracao_video && /\.(mp4|webm|mov)$/i.test(i.arquivo))
      .slice(0, 30).map((i) => ({ nome: i.arquivo, subpasta: i.subpasta })))).catch(() => {})
  }, [])
  const gerar = async () => {
    setErro(null); setSelecionado(null)  // o video novo vai para o player quando sair
    try {
      await api.gerar({
        modelo: 'video', modelo_video: motorPedido, turbo, modo_video: modoOk, prompt, proporcao: '1:1',
        proporcao_video: proporcaoOk, resolucao_video: resolucaoOk, duracao_video: duracaoOk, com_audio: audio,
        referencias: ehChaves ? chavesOk.map((c) => c.img!.nome) : nomesRefs,
        ...(gApi ? {} : camposAjustes(ajustes, false)),
        ...(ehRef && motor === 'ltx' && fundo ? { fundo_referencia: fundo.nome } : {}),
        ...(ehChaves ? { quadros_referencias: chavesOk.map((c) => quadroChave(c.seg, duracaoOk) + 1), forca_chaves: forcaChaves } : {}),
      } as Parameters<typeof api.gerar>[0])
    } catch (e) { setErro(mensagem(e)) }
  }

  // O endereco acompanha o modo e o modelo (sem novo item no historico): voltar a
  // aba, recarregar ou copiar o link abre o que esta na tela.
  useEffect(() => {
    if (pronto && !indisponivel) history.replaceState(history.state, '', `#video/${modoOk}/${motor}`)
  }, [pronto, indisponivel, modoOk, motor])

  const minhas = tarefas.filter((t) => t.modelo === 'video')

  // Layout de 31/10/2026: o video grande a esquerda (o ultimo gerado, ou o escolhido na
  // faixa), o painel de criacao a direita e os videos recentes numa faixa embaixo.
  const daSessao = minhas.flatMap((t) => (t.estado === 'pronto' ? arquivos(t) : []))
  const recentes = [...daSessao, ...salvos.filter((a) => !daSessao.some((b) => b.nome === a.nome && b.subpasta === a.subpasta))]
  const emCurso = minhas.filter((t) => t.estado !== 'pronto' && t.estado !== 'erro')
  const palco = (selecionado && recentes.find((a) => a.nome === selecionado.nome && a.subpasta === selecionado.subpasta)) || recentes[0]
  const faixa = useRef<HTMLDivElement>(null)

  return (
    <div className="hf-aba hf-img hf-vid">
      <TituloPagina antes="Make a" destaque="video" sub="From text, an image, first and last frames, references or keyframes." />
      <div className="hf-vid-grade">
        <section className="hf-vid-palco">
          {palco ? (<>
            <div className="hf-vid-selo">{tamanhoVideo ? `${proporcaoDe(tamanhoVideo)}  ${tamanhoVideo[0]}×${tamanhoVideo[1]}` : ''}</div>
            {/* O mesmo Midia das imagens: Open, Download, Use, Remove... no canto do video. */}
            <Midia key={palco.subpasta + palco.nome} nome={palco.nome} subpasta={palco.subpasta} />
            <video src={urlImagem(palco)} preload="metadata" hidden
              onLoadedMetadata={(e) => setTamanhoVideo([e.currentTarget.videoWidth, e.currentTarget.videoHeight])} />
          </>) : emCurso[0] ? <CartaoTarefa t={emCurso[0]} />
            : <div className="hf-img-vazio"><b>Your video appears here</b><span>Describe the shot on the right, then press Generate.</span></div>}
        </section>

        <aside className="hf-img-col hf-img-dir hf-vid-dir" aria-label="Create video">
          <div className="hf-img-controles">
          <label className="hf-campo"><span>Model</span><select className="hf-select" value={valorSelect} onChange={(e) => escolher(e.target.value)} aria-label="Model">
            <GruposAbertos itens={[{ id: 'ltx', rotulo: 'LTX 2.5' }, { id: 'minimax', rotulo: 'MiniMax H3' },
              ...Object.entries(LEVES).map(([id, l]) => ({ id, rotulo: l.rotulo, soLocal: !l.nuvem }))]} api={apiGeradores} />
          </select></label>
          {motor === 'minimax' && (
            <Chips rotulo="Speed" opcoes={[{ id: 1, rotulo: 'Turbo · 8 steps' }, { id: 0, rotulo: 'Quality · 40 steps' }]}
              valor={turbo ? 1 : 0} aoMudar={(v) => setTurbo(v === 1)} />
          )}
          </div>
        {apiOculta && <p className="hf-erro">{apiOculta.rotulo.replace(/ \((API|nuvem)\)$/, '')} is a paid API model. To use it, turn on "Paid API models" in Comfy Cloud API (the balance at the top right). Showing LTX 2.5 instead.</p>}
        {indisponivel && soLocal && <p className="hf-erro" role="alert">{`${LEVES[escolhido].rotulo} runs only on your GPU: pick it under "Local" in the model menu to switch. Showing LTX 2.5 on Comfy Cloud instead.`}</p>}
        {indisponivel && !soLocal && <p className="hf-erro" role="alert">{`"${escolhido}" is not available here: an unknown name, or a paid API model (those need a Comfy Cloud key and "Paid API models" turned on in Config Models → Comfy Cloud API). Showing LTX 2.5 instead.`}</p>}
        {motor === 'minimax' && <p className="hf-dica">MiniMax H3 is heavy: on a 16 GB card it only fits at low resolution. Best on Comfy Cloud or a 32 GB+ GPU.</p>}
        <Chips rotulo="Mode" opcoes={modos} valor={modoOk} aoMudar={setModo} />
        {ehRef && (
          <>
            <div className="hf-slots">
              {refsOk.map((r, i) => (
                <SlotImagem key={r.nome + i} rotulo={`Image ${i + 1}`} valor={r}
                  aoMudar={(n) => setRefs((a) => n ? a.map((x, j) => (j === i ? n : x)) : a.filter((_, j) => j !== i))} />
              ))}
              {refsOk.length < maxRefs && (
                <SlotImagem key={`novo${refsOk.length}`} rotulo={refsOk.length ? `Image ${refsOk.length + 1}` : 'Person or object'}
                  valor={null} aoMudar={(n) => n && setRefs((a) => [...a.slice(0, maxRefs), n])} />
              )}
              {motor === 'ltx' && <SlotImagem rotulo="Background (optional)" valor={fundo} aoMudar={setFundo} />}
            </div>
            <p className="hf-dica">Up to {maxRefs} people or objects, each on its own image. Refer to them in the prompt as @image1, @image2…
              {motor === 'ltx' ? ' The place tends to come from the photos: add a background image to choose it.' : ''}</p>
          </>
        )}
        {ehChaves && (
          <div className="hf-chaves-video">
            {chaves.map((c, i) => (
              <div key={c.id} className="hf-chave">
                <SlotImagem rotulo={`Keyframe ${i + 1}`} valor={c.img}
                  aoMudar={(img) => setChaves((a) => a.map((x) => (x.id === c.id ? { ...x, img } : x)))} />
                <label className="hf-ctrl"><small>At second</small>
                  <input className="hf-campo" type="number" min={0} max={duracaoOk} step={0.33} value={c.seg} style={{ width: 80 }}
                    // Ao sair do campo, vai ao passo de 1/3 s em que o modelo poe a imagem.
                    onBlur={() => setChaves((a) => a.map((x) => (x.id === c.id ? { ...x, seg: Math.min(duracaoOk, passoChave(x.seg)) } : x)))}
                    onChange={(e) => {
                      // Dentro do video: o max do campo so vale para as setinhas, nao para o que se digita.
                      const v = Number(e.target.value)
                      const seg = Number.isFinite(v) ? Math.min(duracaoOk, Math.max(0, v)) : 0
                      setChaves((a) => a.map((x) => (x.id === c.id ? { ...x, seg } : x)))
                    }} />
                </label>
                {chaves.length > 2 && <button type="button" className="hf-botao-sec hf-x" onClick={() => setChaves((a) => a.filter((x) => x.id !== c.id))}>×</button>}
              </div>
            ))}
            <div className="hf-linha-controles">
              {chaves.length >= 8 && <span className="hf-dica">Up to 8 keyframes.</span>}
              {chaves.length < 8 && <button type="button" className="hf-botao-sec"
                onClick={() => setChaves((a) => [...a, { id: proximaChave++, img: null, seg: Math.min(duracaoOk, (a.at(-1)?.seg ?? 0) + 2) }])}>+ Add keyframe</button>}
              <label className="hf-ctrl hf-ctrl-largo" title="How strictly the video matches each image. Lower lets the motion flow more freely between them.">
                <small>Keyframe strength · {Math.round(forcaChaves * 100)}%</small>
                <input type="range" min={0.3} max={1} step={0.05} value={forcaChaves} onChange={(e) => setForcaChaves(Number(e.target.value))} />
              </label>
            </div>
            <p className="hf-dica">2 to 8 images, each at the second it should appear (the model places them on steps of 1/3 s). Up to 15 s. The text says what happens between them.</p>
          </div>
        )}
        {modoOk !== 'texto' && !ehRef && !ehChaves && (
          <div className="hf-slots">
            <SlotImagem rotulo={modoOk === 'primeiro_ultimo' ? 'First frame' : 'Start image'} valor={inicio} aoMudar={setInicio} />
            {modoOk === 'primeiro_ultimo' && <SlotImagem rotulo="Last frame" valor={fim} aoMudar={setFim} />}
          </div>
        )}
        <span className="hf-vid-rotulo">Prompt</span>
        <textarea aria-label="Prompt" maxLength={MAX_PROMPT} value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2}
          placeholder={ehRef ? 'e.g. @image1 and @image2 dance together on a rooftop at sunset' : 'Describe the shot: subject, action, camera, sound…'} />
          <div className="hf-vid-par">
          <Chips rotulo="Aspect ratio" opcoes={proporcoes.map((p) => ({ id: p, rotulo: p }))} valor={proporcaoOk} aoMudar={setProporcao} />
          <Chips rotulo="Resolution" opcoes={resolucoes.map((r) => ({ id: r, rotulo: r }))} valor={resolucaoOk} aoMudar={setResolucao} />
          </div>
          <div className="hf-vid-par hf-vid-par-duracao">
          <div className="hf-campo"><span>Length</span>
            <label className="hf-duracao">
              {duracaoOk}s
              <input type="range" min={dMin} max={dMax} value={duracaoOk} onChange={(e) => setDuracao(Number(e.target.value))} aria-label="Length" />
            </label>
          </div>
          <div className="hf-campo" style={(gApi as { sem_audio?: boolean } | undefined)?.sem_audio ? { display: 'none' } : undefined}><span>Sound</span>
            <label className="hf-toggle"><input type="checkbox" checked={audio} onChange={(e) => setAudio(e.target.checked)} /> Audio</label>
          </div>
          </div>
        {avisoModo && <p className="hf-dica" role="note">{avisoModo}</p>}
        {chavesRepetidas && <p className="hf-erro">Two keyframes are at the same second: move one of them.</p>}
        {naoInstalado && <AvisoInstalar rotulo={rotuloMotor} />}
        {!naoInstalado && faltaQual && <p className="hf-dica" role="note">{faltaQual}</p>}
        {erro && <p className="hf-erro">{erro}</p>}
          {!gApi && <Avancado valor={ajustes} aoMudar={setAjustes} comPassos={false} />}
          <BotaoGerar rotulo="✦ Generate" est={custo} desligado={naoInstalado || !prompt.trim() || faltaImagem || chavesRepetidas} aoClicar={gerar} />
        </aside>
      </div>

      <section className="hf-img-recentes" aria-label="Recent videos">
        <div className="hf-vid-recentes-topo">
          <span className="hf-img-titulo">Recent videos</span>
          <div>
            <button type="button" className="hf-vid-seta" aria-label="Scroll left" onClick={() => faixa.current?.scrollBy({ left: -600, behavior: 'smooth' })}>‹</button>
            <button type="button" className="hf-vid-seta" aria-label="Scroll right" onClick={() => faixa.current?.scrollBy({ left: 600, behavior: 'smooth' })}>›</button>
          </div>
        </div>
        <div className="hf-img-faixa" ref={faixa}>
          {emCurso.map((t) => <div key={t.id} className="hf-img-faixa-item hf-img-faixa-curso"><CartaoTarefa t={t} /></div>)}
          {recentes.map((a) => (
            <button key={a.subpasta + a.nome} type="button" className="hf-img-faixa-item hf-vid-item" data-ativo={palco?.nome === a.nome}
              onClick={() => setSelecionado(a)} title="Play it in the big player">
              <video src={urlImagem(a) + '#t=0.5'} muted preload="metadata" playsInline
                onLoadedMetadata={(e) => { const d = e.currentTarget.duration; const el = e.currentTarget.nextElementSibling; if (el && isFinite(d)) el.textContent = `00:${String(Math.round(d)).padStart(2, '0')}` }} />
              <span className="hf-vid-dur" />
            </button>
          ))}
          {!recentes.length && !emCurso.length && <p className="hf-vazio">Your videos will appear here.</p>}
        </div>
      </section>
    </div>
  )
}
