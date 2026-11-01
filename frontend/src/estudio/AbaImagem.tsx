import { useCallback, useEffect, useState } from 'react'
import { abrirVisualizador, recriar, useRecriar, useReusarPrompt, type Receita } from './Visualizador'
import { api, urlEntrada, urlImagem, type Elemento, type Modelo, type ModeloNuvem, type Referencia } from '../api'
import LayoutIdeogram from './LayoutIdeogram'
import { AvisoInstalar, GruposAbertos, useEscolha, useFaltaInstalar, useInstalado, useValor, valorAberto } from './motor'
import { LOOKS, aplicarLook } from './looks'
import { AJUSTES_VAZIOS, Avancado, camposAjustes, type Ajustes, BotaoGerar, CartaoTarefa, Chips, SlotImagem, Midia, arquivos, mensagem, useCusto, useTarefas, parteDoHash, teclasRadio, useLembrado, MAX_PROMPT, TituloPagina } from './comum'

// Image tab: one prompt bar, the model, aspect ratio and how many images.
// Everything else (steps, cfg, styles) keeps its defaults; the full controls
// live in the Advanced tab.

const PROPORCOES = ['1:1', '4:5', '2:3', '9:16', '3:2', '16:9']

// English blurbs for the new studio (the backend presets keep the Portuguese ones).
const DESCRICOES: Record<string, string> = {
  krea: 'Photorealism. Fast. The default for most images.',
  kroma: 'Illustration and anime, a fine-tune of Krea 2.',
  qwen21: 'Text inside the scene, very accurate. The only local model with native 2K.',
  klein: 'Maximum micro-detail and texture. Slower.',
  flux3: 'The new BFL model. Photorealism and well-written text.',
  zimage: 'Fast drafts. Supports ControlNet.',
  mage: 'Lightweight. The base of instruction editing.',
  ideogram: 'Typography and layout controlled with boxes.',
  flux1dev: 'The classic FLUX.1, 20 steps. Non-commercial license.',
  flux1krea: 'FLUX.1 tuned by Krea: natural photos that look less like AI.',
  flux2dev: 'FLUX.2 (32B): very detailed and very heavy. Best on Comfy Cloud.',
  hidream: 'HiDream I1 Fast: follows long prompts closely. 16 steps.',
  chroma: 'Chroma1 HD: open FLUX-based model (Apache 2.0) for any style.',
  sd35l: 'Stable Diffusion 3.5 Large (8B): good with text and composition.',
  kandinsky5i: 'Kandinsky 5 for images (Apache 2.0).',
  // Light models, for smaller graphics cards.
  flux1s: 'Light FLUX: good images in 4 steps. For 8-12 GB cards.',
  sd35m: 'Stable Diffusion 3.5 Medium. Handles text in images. For 8 GB cards.',
  sdxl: 'The classic SDXL (RealVisXL 5), photoreal. For 6-8 GB cards.',
  sd15: 'The lightest: runs on 4 GB cards. 512 px images.',
}

// Reference images per open model. With images attached, the request goes to
// the model's reference/edit mode in the backend (presets.EDICAO), or, for
// Krea and Kroma, to the generator's own character slots. "@image1" in the
// prompt is translated by the server to the label each model expects.
// Tested 23/10/2026: the edit models treat image 1 as the BASE (its size and
// scene). With the person first and the scene second, Qwen 2.1 and Flux 3
// kept the scene's original person; scene first, person second worked.
// "base" marks those models, so slot 1 is labelled "Base image".
const REFERENCIAS: Record<string, { modo: string; max: number; uso: string; base?: boolean }> = {
  krea: { modo: 'krea', max: 3, uso: 'Puts up to 3 people or characters from your images into a new scene.' },
  kroma: { modo: 'kroma', max: 3, uso: 'Puts up to 3 characters from your images into a new illustrated scene.' },
  qwen21: { modo: 'qwen21edit', max: 8, base: true, uso: 'Image 1 is the base you edit; add people or objects as image 2, 3… e.g. "put the woman from @image2 in @image1".' },
  klein: { modo: 'trocar', max: 4, base: true, uso: 'Image 1 is the scene; the others replace who or what is in it.' },
  flux3: { modo: 'flux3ref', max: 10, base: true, uso: 'Image 1 is the base you edit; add people, outfits or places as image 2, 3… (up to 10).' },
  mage: { modo: 'instrucao', max: 3, base: true, uso: 'Quick edit of image 1 from an instruction, keeping the rest intact.' },
  sd15: { modo: 'sd15', max: 1, base: true, uso: 'Starting image: the new picture keeps its layout and colors. Strength says how much it changes.' },
  sdxl: { modo: 'sdxl', max: 1, base: true, uso: 'Starting image: the new picture keeps its layout and colors. Strength says how much it changes.' },
  sd35m: { modo: 'sd35m', max: 1, base: true, uso: 'Starting image: the new picture keeps its layout and colors. Strength says how much it changes.' },
  sd35l: { modo: 'sd35l', max: 1, base: true, uso: 'Starting image: the new picture keeps its layout and colors. Strength says how much it changes.' },
}

// On Comfy Cloud the Krea character, Qwen 2.1 edit and Flux 3 reference modes
// are not hosted; images go through Qwen Image Edit 2511 there (open, 3 images).
const NUVEM_SEM_REF = new Set(['krea', 'kroma', 'qwen21', 'flux3'])
// Modelos de checkpoint unico: a imagem vira o ponto de partida (img2img), com uma forca.
const IMG2IMG = new Set(['sd15', 'sdxl', 'sd35m', 'sd35l'])
const REF_NUVEM = { modo: 'qwen', max: 3, base: true, uso: 'On Comfy Cloud, images go through Qwen Image Edit. Image 1 is the base; add people or objects as image 2, 3.' }

export default function AbaImagem({ modelos, apiModelos, apiOcultos = [], naNuvem }: { modelos: Modelo[]; apiModelos: ModeloNuvem[]; apiOcultos?: ModeloNuvem[]; naNuvem: boolean }) {
  const tarefas = useTarefas()
  const [prompt, setPrompt] = useLembrado('image.prompt', '')
  const [look, setLook] = useState('')
  // "Reuse prompt" in the viewer fills this tab's text.
  useReusarPrompt(setPrompt)
  // '' = sem escolha (nem no link): fica o padrao abaixo.
  const [escolhido, setModelo] = useState(() => parteDoHash(1))
  // O que aparece, o que o preco mostra e o que vai no pedido sao o MESMO modelo:
  // um id que o menu nao tem (API oculta, sem chave, link inventado) vira o padrao.
  // Enquanto o catalogo carrega (listas vazias) fica o escolhido, para nao perde-lo.
  const carregado = modelos.length > 0
  const instalado = useInstalado()
  // Padrao: o Krea se roda aqui; senao o primeiro modelo que roda (instalado, ou na
  // nuvem). Antes era sempre o Krea, mesmo nao instalado com o Qwen instalado.
  const roda = (m: Modelo) => (naNuvem ? m.nuvem !== false : instalado(m.id))
  const padrao = (modelos.find((m) => m.id === 'krea' && roda(m)) ?? modelos.find(roda) ?? modelos.find((m) => m.id === 'krea') ?? modelos[0])?.id ?? 'krea'
  // Modelo so local (nuvem: false) com o motor na Comfy Cloud: o menu nao o tem
  // ali, entao a tela mostraria outro e o pedido iria com este.
  const soLocal = naNuvem && modelos.find((m) => m.id === escolhido)?.nuvem === false
  const conhecido = (modelos.some((m) => m.id === escolhido) && !soLocal) || apiModelos.some((m) => m.id === escolhido)
  const modelo = escolhido && (!carregado || conhecido) ? escolhido : padrao
  const apiOculta = carregado && escolhido && !conhecido ? apiOcultos.find((m) => m.id === escolhido) : undefined
  const indisponivel = carregado && !!escolhido && !conhecido && !apiOculta
  const escolher = useEscolha(setModelo)
  const faltaInstalar = useFaltaInstalar()
  const valorSelect = useValor(modelo, apiModelos.some((m) => m.id === modelo))
  const [proporcao, setProporcao] = useState('1:1')
  const [lote, setLote] = useState(1)
  const [refs, setRefs] = useState<Referencia[]>([])
  const [selecionada, setSelecionada] = useState<{ nome: string; subpasta: string } | null>(null)
  const [salvas, setSalvas] = useState<{ nome: string; subpasta: string }[]>([])
  useEffect(() => {
    api.galeria(40).then((itens) => setSalvas(itens.filter((i) => !i.duracao_video && /\.(png|jpe?g|webp)$/i.test(i.arquivo))
      .map((i) => ({ nome: i.arquivo, subpasta: i.subpasta })))).catch(() => {})
  }, [])
  const [ajustes, setAjustes] = useState<Ajustes>(AJUSTES_VAZIOS)
  // "Recreate" (galeria/visualizador): volta prompt, imagens, proporcao e modelo.
  // Com imagens o pedido foi no modo de referencia (flux3ref...): volta ao modelo do menu.
  // Trocar de modelo muda o endereco e remonta a aba: entao primeiro vai ao modelo
  // certo, e a aba nova (ja nele) preenche o resto.
  useRecriar(useCallback((r: Receita) => {
    const doMenu = Object.entries(REFERENCIAS).find(([, u]) => u.modo === r.modelo)?.[0] ?? r.modelo
    if (doMenu && doMenu !== parteDoHash(1)) { recriar(r, `#image/${doMenu}`); return }
    const q = r.parametros
    setPrompt(r.prompt.replace(/\bimage (\d)/g, '@image$1'))
    setLook('')
    const nomes = ([q.referencias_usadas, q.referencias].find((x) => Array.isArray(x) && x.length) ?? []) as string[]
    setRefs(nomes.map((n) => ({ nome: n, url: urlEntrada(n) })))
    if (typeof q.proporcao === 'string') setProporcao(q.proporcao)
    const txt = (v: unknown) => (typeof v === 'number' ? String(v) : '')
    setAjustes({ seed: txt(q.seed), steps: txt(q.steps), cfg: txt(q.cfg) })
  }, [setPrompt]))
  // Ideogram 4: optional hand-drawn layout (boxes) sent as its caption.
  const [comLayout, setComLayout] = useState(false)
  const [elementos, setElementos] = useState<Elemento[]>([])
  const [fundoLayout, setFundoLayout] = useState('')
  const [pensando, setPensando] = useState(false)
  const ehIdeogram = modelo === 'ideogram'
  const usarLayout = ehIdeogram && comLayout && elementos.length > 0
  const [erro, setErro] = useState<string | null>(null)
  const atual = modelos.find((m) => m.id === modelo)
  // Modelos de API (Nano Banana, GPT Image): rodam pelos creditos da conta Comfy.
  const apiAtual = apiModelos.find((m) => m.id === modelo)
  const naoInstalado = faltaInstalar(modelo, !!apiAtual)
  const niveis = apiAtual ? (apiAtual.resolucoes ?? apiAtual.niveis ?? ['1K']) : []
  const [nivel, setNivel] = useState('1K')
  const nivelOk = niveis.includes(nivel) ? nivel : niveis[0]
  const preco = (() => {
    if (!apiAtual) return null
    const v = apiAtual.preco_usd[nivelOk ?? '']
    const unit = typeof v === 'number' ? v : (v && typeof v === 'object' ? Object.values(v)[0] : undefined)
    return typeof unit === 'number' ? unit * lote : null
  })()

  const usoRefs = apiAtual
    ? { modo: modelo, max: apiAtual.max_referencias ?? 1, base: true, uso: `Image 1 is the base; edit it or combine up to ${apiAtual.max_referencias ?? 1} images.` }
    : naNuvem && NUVEM_SEM_REF.has(modelo) ? REF_NUVEM : REFERENCIAS[modelo]
  const maxRefs = usoRefs?.max ?? 0
  const refsOk = refs.slice(0, maxRefs)
  // With images, open models run in their reference/edit mode, one image per run.
  const comRefs = refsOk.length > 0
  // Flux 3 na placa: o tamanho padrao e ~1 MP (1344x768 no 16:9). "2 MP" usa a escala do servidor
  // (x1,4) e "4K" o modo nativo (~8,3 MP, uns 7,5 min em 16 GB), so sem imagens de referencia.
  const flux3Local = !apiAtual && !naNuvem && modelo === 'flux3'
  const [tamanho, setTamanho] = useState('padrao')
  const [forcaImagem, setForcaImagem] = useState(0.6)
  const tamanhoOk = tamanho === '4k' && comRefs ? 'padrao' : tamanho
  const pedido = {
    modelo: comRefs && usoRefs ? usoRefs.modo : modelo, prompt: prompt || 'x', proporcao,
    ...(flux3Local ? (tamanhoOk === 'alta' ? { escala: 1.4 } : tamanhoOk === '4k' ? { nativo_4k: true } : {}) : {}),
    lote: comRefs && !apiAtual ? 1 : lote, referencias: refsOk.map((r) => r.nome),
    ...(comRefs && IMG2IMG.has(modelo) ? { forca_imagem: forcaImagem } : {}),
    ...(apiAtual ? {} : camposAjustes(ajustes, true)),
    ...(apiAtual ? { resolucao_nuvem: nivelOk } : {}),
    ...(usarLayout ? { caption: {
      aspect_ratio: proporcao,
      high_level_description: prompt,
      compositional_deconstruction: {
        background: fundoLayout || 'A clean, uncluttered background.',
        elements: elementos.map((e) => ({ type: e.tipo, bbox: e.bbox.map(Math.round), desc: e.desc,
          ...(e.tipo === 'text' ? { text: e.texto ?? '' } : {}) })),
      },
    } } : {}),
  }
  const custo = useCusto(pedido)

  // The local language model drafts the layout from the prompt; the user then adjusts the boxes.
  const sugerir = async () => {
    setErro(null); setPensando(true)
    try {
      const { caption: c } = await api.caption(prompt, proporcao)
      setFundoLayout(c.compositional_deconstruction.background)
      setElementos((c.compositional_deconstruction.elements as Record<string, unknown>[])
        .filter((e) => Array.isArray(e.bbox))
        .map((e) => ({ tipo: e.type === 'text' ? 'text' : 'obj', bbox: e.bbox as Elemento['bbox'],
          texto: (e.text as string) ?? '', desc: (e.desc as string) ?? '' })))
    } catch (e) { setErro(mensagem(e)) } finally { setPensando(false) }
  }

  // Com foto na caixa, o look usa a versao "foto" (transforma a foto); sem foto, cria do zero.
  const lookAtual = LOOKS.find((l) => l.id === look)
  // Look que usa a foto: sem modelo que aceite imagem, passa para o Flux 3 Klein.
  const escolherLook = (l: typeof LOOKS[number]) => {
    if (look === l.id) { setLook(''); return }
    setLook(l.id)
    if (l.comImagem && !maxRefs) escolher(valorAberto('flux3', naNuvem))
  }
  const faltaFoto = !!lookAtual?.comImagem && !comRefs
  // A mesma regra vale para o botao e para o Ctrl+Enter (o atalho ignorava o
  // modelo nao instalado e mandava o pedido com o botao desligado).
  const desligado = naoInstalado || faltaFoto || (!prompt.trim() && !lookAtual)
  const gerar = async () => {
    setErro(null); setSelecionada(null)  // a imagem nova vai para o palco quando sair
    try {
      await api.gerar({ ...pedido, prompt: aplicarLook(lookAtual, prompt, comRefs) } as Parameters<typeof api.gerar>[0])
    } catch (e) { setErro(mensagem(e)) }
  }

  const modosRef = new Set([...Object.values(REFERENCIAS).map((r) => r.modo), REF_NUVEM.modo])
  // O endereco acompanha o modelo escolhido (sem novo item no historico): voltar a
  // aba, recarregar ou copiar o link abre o que esta na tela.
  useEffect(() => {
    if (carregado && escolhido && conhecido) history.replaceState(history.state, '', `#image/${escolhido}`)
  }, [carregado, escolhido, conhecido])

  const minhas = tarefas.filter((t) => modelos.some((m) => m.id === t.modelo) || apiModelos.some((m) => m.id === t.modelo)
    || modosRef.has(t.modelo))

  // Layout de 3 colunas (31/10/2026): looks a esquerda, a imagem grande no centro com o
  // prompt embaixo, o painel "Create image" a direita e as recentes numa faixa.
  // As desta sessao primeiro; depois as imagens ja salvas na galeria (ao abrir o app a
  // sessao esta vazia e o palco ficaria em branco).
  const daSessao = minhas.flatMap((t) => (t.estado === 'pronto' ? arquivos(t) : []))
  const recentes = [...daSessao, ...salvas.filter((a) => !daSessao.some((b) => b.nome === a.nome && b.subpasta === a.subpasta))]
  const emCurso = minhas.filter((t) => t.estado !== 'pronto' && t.estado !== 'erro')
  const palco = (selecionada && recentes.find((a) => a.nome === selecionada.nome && a.subpasta === selecionada.subpasta)) || recentes[0]

  return (
    <div className="hf-aba hf-img">
      <TituloPagina antes="Create an" destaque="image" sub="Pick a look or write a prompt, on your GPU or on Comfy Cloud." />
      <div className="hf-img-grade">
        <section className="hf-img-col hf-img-esq" aria-label="One-tap looks">
          <div className="hf-looks">
            <span className="hf-img-titulo">One-tap looks</span>
            {/* Cartoes com miniatura: cada uma e uma amostra real do look (Flux 3 Klein). */}
            <div className="hf-looks-grade" role="radiogroup" aria-label="One-tap looks" onKeyDown={teclasRadio}>
              <button type="button" role="radio" aria-checked={look === ''} tabIndex={look === '' || !lookAtual ? 0 : -1} className="hf-look" data-ativo={look === ''} onClick={() => setLook('')}>
                <span className="hf-look-nada" aria-hidden>⊘</span><span>None</span>
              </button>
              {/* Todos valem com ou sem foto: com foto, cada um transforma a foto (looks.ts, campo foto). */}
              {LOOKS.map((l) => (
                <button key={l.id} type="button" role="radio" aria-checked={look === l.id} tabIndex={look === l.id ? 0 : -1} className="hf-look" data-ativo={look === l.id}
                  onClick={() => escolherLook(l)}
                  title={l.comImagem ? `${l.rotulo}: uses the photo in the box below`
                    : comRefs ? `${l.rotulo}: restyles the photo in the box` : `${l.rotulo}: e.g. ${l.exemplo}`}>
                  <img src={`/looks/${l.id}.webp`} alt="" /><span>{l.rotulo}</span>
                </button>
              ))}
            </div>
            {comRefs && <small className="hf-looks-dica">With an image in the box, the look restyles your photo. Remove the image to make a new picture from text.</small>}
          </div>
        </section>

        <section className="hf-img-centro">
          <div className="hf-img-palco">
            {emCurso[0] && !palco ? <CartaoTarefa t={emCurso[0]} />
              : palco ? <Midia key={palco.subpasta + palco.nome} nome={palco.nome} subpasta={palco.subpasta} />
              : <div className="hf-img-vazio"><b>Your image appears here</b><span>Pick a look or write a prompt, then press Generate.</span></div>}
            {emCurso[0] && palco && <div className="hf-img-andamento"><CartaoTarefa t={emCurso[0]} /></div>}
          </div>
          {/* Navegacao entre as imagens recentes, logo abaixo da imagem grande. */}
          {(() => {
            const i = palco ? recentes.findIndex((a) => a.nome === palco.nome && a.subpasta === palco.subpasta) : -1
            const ir = (d: number) => { const n = recentes[i + d]; if (n) setSelecionada(n) }
            return (
              <div className="hf-edt-barra hf-img-nav">
                <button type="button" className="hf-botao-sec" disabled={i <= 0} onClick={() => ir(-1)} aria-label="Previous image" title="Newer">‹</button>
                <span className="hf-botao-sec">{recentes.length ? `${i + 1} / ${recentes.length}` : '0 / 0'}</span>
                <button type="button" className="hf-botao-sec" disabled={i < 0 || i >= recentes.length - 1} onClick={() => ir(1)} aria-label="Next image" title="Older">›</button>
                <button type="button" className="hf-botao-sec" disabled={!palco} onClick={() => palco && abrirVisualizador(palco)} aria-label="Full screen" title="Full screen with details">⤢</button>
              </div>
            )
          })()}
          <div className="hf-img-prompt">
            <span className="hf-img-titulo">Prompt</span>
            <div className="hf-img-prompt-linha">
        <textarea aria-label="Prompt" maxLength={MAX_PROMPT} value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={1}
          placeholder={comRefs && lookAtual ? `Optional: an extra touch for ${lookAtual.rotulo}, e.g. "smiling" or "blue background"`
            : comRefs ? 'Describe the result. Refer to the images as @image1, @image2…'
            : faltaFoto ? 'Add your photo under Character (right), then press Generate. Optional: extra direction here.'
            : lookAtual ? `What should it show? e.g. ${lookAtual.exemplo} (empty = this example)` : 'Describe the image you want…'}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !desligado) gerar() }} />
              <BotaoGerar est={custo} desligado={desligado} aoClicar={gerar} />
            </div>
          </div>
        </section>

        <aside className="hf-img-col hf-img-dir" aria-label="Create image">
          <span className="hf-img-titulo hf-img-titulo-forte">Create image</span>
        {maxRefs > 0 && (
          <div className="hf-campo"><span>{usoRefs?.base ? 'Images' : 'Character'}</span><div className="hf-slots">
            {refsOk.map((r, i) => (
              <SlotImagem key={r.nome + i} rotulo={i === 0 && usoRefs?.base ? 'Base image' : `Image ${i + 1}`} valor={r}
                aoMudar={(n) => setRefs((a) => n ? a.map((x, j) => (j === i ? n : x)) : a.filter((_, j) => j !== i))} />
            ))}
            {refsOk.length < maxRefs && (
              <SlotImagem key={`novo${refsOk.length}`} rotulo={refsOk.length ? `Image ${refsOk.length + 1}` : usoRefs?.base ? 'Base image' : 'Character'}
                valor={null} aoMudar={(n) => n && setRefs((a) => [...a.slice(0, maxRefs), n])} />
            )}
          </div></div>
        )}
        {comRefs && IMG2IMG.has(modelo) && (
          <div className="hf-campo"><span>Strength · {Math.round(forcaImagem * 100)}%</span>
            <input type="range" min={0.2} max={1} step={0.05} value={forcaImagem} aria-label="How much the image changes"
              onChange={(e) => setForcaImagem(Number(e.target.value))} />
            <small className="hf-dica">Low keeps the photo; high keeps only its layout.</small>
          </div>
        )}
        <div className="hf-img-controles">
          <label className="hf-campo"><span>Model</span><select className="hf-select" value={valorSelect} onChange={(e) => escolher(e.target.value)} aria-label="Model">
            <GruposAbertos itens={modelos.map((m) => ({ id: m.id, rotulo: m.rotulo, nuvem: m.nuvem }))} api={apiModelos} />
          </select></label>
          <Chips rotulo="Aspect ratio" opcoes={PROPORCOES.map((p) => ({ id: p, rotulo: p }))} valor={proporcao} aoMudar={setProporcao} />
          {!(comRefs && !apiAtual) && <Chips rotulo="Images" opcoes={[1, 2, 4].map((n) => ({ id: n, rotulo: `×${n}` }))} valor={lote} aoMudar={setLote} />}
          {flux3Local && (
            <Chips rotulo="Resolution" valor={tamanhoOk} aoMudar={setTamanho} opcoes={[
              { id: 'padrao', rotulo: '1 MP · fast' }, { id: 'alta', rotulo: '2 MP' },
              { id: '4k', rotulo: '4K · slow', ...(comRefs ? { desligado: true, dica: '4K works without reference images' } : { dica: 'About 8 MP; 7 to 17 min per image on a 16 GB card' }) }]} />
          )}
          {apiAtual && niveis.length > 1 && (
            <Chips rotulo="Resolution" opcoes={niveis.map((n) => ({ id: n, rotulo: n }))} valor={nivelOk} aoMudar={setNivel} />
          )}
        </div>
        {!apiAtual && <Avancado valor={ajustes} aoMudar={setAjustes} comPassos />}
        {ehIdeogram && (
          <div className="hf-linha-controles">
            <Chips rotulo="Layout" opcoes={[{ id: 'auto', rotulo: 'Automatic' }, { id: 'caixas', rotulo: 'Draw boxes' }]}
              valor={comLayout ? 'caixas' : 'auto'} aoMudar={(v) => setComLayout(v === 'caixas')} />
          </div>
        )}
        {ehIdeogram && comLayout && (
          <LayoutIdeogram proporcao={proporcao} elementos={elementos} aoMudar={setElementos}
            fundo={fundoLayout} aoMudarFundo={setFundoLayout} pensando={pensando}
            aoSugerir={sugerir} podeSugerir={!!prompt.trim()} />
        )}
        {atual && <p className="hf-dica">{DESCRICOES[atual.id] ?? atual.descricao}
          {usoRefs ? ` With images: ${usoRefs.uso}` : ''}</p>}
        {apiAtual && <p className="hf-dica">Paid API model, runs on your Comfy account credits{preco !== null ? ` · about $${preco.toFixed(2)} per run` : ''}.</p>}
        {apiOculta && <p className="hf-erro">{apiOculta.rotulo.replace(/ \((API|nuvem)\)$/, '')} is a paid API model. To use it, turn on "Paid API models" in Comfy Cloud API (the balance at the top right). Showing {atual?.rotulo ?? 'another model'} instead.</p>}
        {indisponivel && soLocal && <p className="hf-erro" role="alert">{`${modelos.find((m) => m.id === escolhido)?.rotulo} runs only on your GPU: pick it under "Local" in the model menu to switch. Showing ${atual?.rotulo ?? 'another model'} on Comfy Cloud instead.`}</p>}
        {indisponivel && !soLocal && <p className="hf-erro" role="alert">{`"${escolhido}" is not available here: an unknown name, or a paid API model (those need a Comfy Cloud key and "Paid API models" turned on in Config Models → Comfy Cloud API). Showing ${atual?.rotulo ?? 'another model'} instead.`}</p>}
        {naoInstalado && <AvisoInstalar rotulo={atual?.rotulo ?? modelo} />}
        {erro && <p className="hf-erro">{erro}</p>}
        </aside>
      </div>

      <section className="hf-img-recentes" aria-label="Recent generations">
        <span className="hf-img-titulo">Recent generations</span>
        <div className="hf-img-faixa">
          {emCurso.map((t) => <div key={t.id} className="hf-img-faixa-item hf-img-faixa-curso"><CartaoTarefa t={t} /></div>)}
          {recentes.map((a) => (
            <button key={a.subpasta + a.nome} type="button" className="hf-img-faixa-item" data-ativo={palco?.nome === a.nome}
              onClick={() => setSelecionada(a)} title="Show it in the big view">
              <img src={urlImagem(a)} alt="" loading="lazy" />
            </button>
          ))}
          {!recentes.length && !emCurso.length && <p className="hf-vazio">Your images will appear here.</p>}
        </div>
      </section>
    </div>
  )
}
