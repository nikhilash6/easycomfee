import { useCallback, useState } from 'react'
import { useReusarPrompt } from './Visualizador'
import { AvisoInstalar, GruposAbertos, useEscolha, useFaltaInstalar, useValor } from './motor'
import { api, type Referencia } from '../api'
import { BotaoGerar, CartaoTarefa, Chips, SlotImagem, mensagem, useCusto, useTarefas, Galeria, useFalaPendente, useLembrado, textoDoDetalhe, MAX_PROMPT, TituloPagina } from './comum'

// Lip Sync: a portrait and a voice track become a talking video. LTX 2.3 is the
// open-weights default (up to 30 s); with "Open weights only" off, the Comfy
// partner nodes (avatar.API in the backend) join the model dropdown. The server
// crops the photo to head and shoulders first: with the whole photo the mouth
// had too few pixels.

export type ModeloLipSync = { id: string; rotulo: string; limite: number }

// LongCat 1.5 so roda na placa (nao existe no Comfy Cloud); o pacote e o "avatar" do Config Models.
const ABERTOS: (ModeloLipSync & { soLocal?: boolean })[] = [{ id: 'ltx23', rotulo: 'LTX 2.3', limite: 30 }, { id: 'longcat', rotulo: 'LongCat 1.5', limite: 15, soLocal: true }]

const DESCRICOES: Record<string, string> = {
  ltx23: 'Open weights. Natural lips and head motion, up to 30 s.',
  longcat: 'Open weights, your GPU only. Long talking portraits at 832×480, up to 15 s; slower than LTX.',
  kling: 'Broadcast-style presenter from one photo.',
  heygen: 'HeyGen Avatar IV: expressive face and gestures, 1080p.',
  sync: 'sync.so sync-3: precise lip sync, keeps the photo intact.',
  veed: 'Works with photos, illustrations and mascots. 720p.',
}

// A foto e a voz ficam guardadas enquanto a pessoa anda pelas abas (useLembrado):
// mandar a voz pelo menu de um audio e depois o rosto pelo de uma imagem nao pode perder a voz.

export default function AbaLipSync({ apiModelos }: { apiModelos: ModeloLipSync[] }) {
  const tarefas = useTarefas()
  const [foto, setFoto] = useLembrado<{ nome: string; url: string } | null>('lipsync.foto', null)
  const [fala, setFala] = useLembrado<{ nome: string; url: string; segundos: number } | null>('lipsync.fala', null)
  const [vertical, setVertical] = useLembrado('lipsync.vertical', false)
  const [cena, setCena] = useLembrado('lipsync.cena', '')
  // "Reuse prompt" in the viewer fills this tab's text.
  useReusarPrompt(setCena)
  const [ocupado, setOcupado] = useState('')
  const [modelo, setModelo] = useState('ltx23')
  const escolher = useEscolha(setModelo)
  const valorSelect = useValor(modelo, apiModelos.some((m) => m.id === modelo))
  const cfg = [...ABERTOS, ...apiModelos].find((m) => m.id === modelo) ?? ABERTOS[0]
  // LTX 2.3 local sem o pacote: Generate desligado e aviso (como Image e Video).
  const naoInstalado = useFaltaInstalar()(cfg.id, apiModelos.some((m) => m.id === cfg.id))
  const LIMITE = cfg.limite
  const [erro, setErro] = useState<string | null>(null)

  const comErro = async (rotulo: string, f: () => Promise<void>) => {
    setOcupado(rotulo); setErro(null)
    try { await f() } catch (e) { setErro(mensagem(e)) } finally { setOcupado('') }
  }

  const recortar = (nome: string, url: string, emPe: boolean) => comErro('Framing the face…', async () => {
    const r = await fetch('/api/avatar/recorte', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ foto: nome, vertical: emPe }) })
    const d = await r.json()
    if (!r.ok) throw new Error(textoDoDetalhe(d.detail, 'Could not prepare the photo.'))
    setFoto({ nome: d.nome, url })
  })

  const [original, setOriginal] = useLembrado<{ nome: string; url: string } | null>('lipsync.original', null)

  // A foto chega pelo slot (computador, galeria arrastada ou botao "Use") ja enviada;
  // aqui so se enquadra o rosto no formato escolhido.
  const receberFoto = (r: Referencia | null) => {
    if (!r) { setOriginal(null); setFoto(null); return }
    setOriginal(r)
    void recortar(r.nome, r.url, vertical)
  }

  const enviarFala = (f: File) => comErro('Uploading…', async () => {
    const url = URL.createObjectURL(f)
    const segundos = await new Promise<number>((ok, falha) => {
      const a = new Audio(); a.preload = 'metadata'
      a.onloadedmetadata = () => ok(a.duration); a.onerror = () => falha(new Error('The browser could not read this audio.'))
      a.src = url
    })
    const { nome } = await api.enviarAudio(f)
    setFala({ nome, url, segundos })
  })

  // Audio mandado da galeria pelo menu "Send to Lip Sync (as the voice)".
  useFalaPendente(useCallback((f: File) => { void enviarFala(f) }, []))  // eslint-disable-line react-hooks/exhaustive-deps

  const trocarFormato = (emPe: boolean) => {
    setVertical(emPe)
    if (original) recortar(original.nome, original.url, emPe)
  }

  const longa = !!fala && fala.segundos > LIMITE + 0.05
  const pronto = !naoInstalado && !!foto && !!fala && !longa && !ocupado

  const custo = useCusto(foto && fala ? { modelo: 'avatar', prompt: cena, referencias: [foto.nome],
    referencia_avatar: fala.nome, modelo_avatar: cfg.id, vertical_avatar: vertical } : null)

  const gerar = () => comErro('', async () => {
    const r = await fetch('/api/gerar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modelo: 'avatar', prompt: cena, referencias: [foto!.nome],
        referencia_avatar: fala!.nome, modelo_avatar: cfg.id, vertical_avatar: vertical }) })
    if (!r.ok) throw new Error(await r.text())
  })

  const minhas = tarefas.filter((t) => t.modelo === 'avatar')

  return (
    <div className="hf-aba hf-img hf-lsn">
      <TituloPagina antes="Make any portrait" destaque="talk" selo={cfg.rotulo}
        sub={`A photo plus a voice track becomes a talking video, up to ${LIMITE} seconds, on your GPU or on Comfy Cloud.`} />
      <ol className="hf-lsn-etapas" aria-label="Steps">
        <li data-feito={!!foto}><i>1</i>Portrait</li>
        <li data-feito={!!fala && !longa}><i>2</i>Voice</li>
        <li data-feito={!!cena.trim()}><i>3</i>Scene</li>
      </ol>

      <div className="hf-barra-prompt hf-ls">
        <div className="hf-ls-passos">
          <section className="hf-ls-cartao" data-pronto={!!foto}>
            <header><b>1</b> Portrait</header>
            <SlotImagem rotulo="Portrait photo" valor={original} aoMudar={receberFoto} />
            <Chips rotulo="Format" opcoes={[{ id: 'h', rotulo: '▭ 16:9' }, { id: 'v', rotulo: '▯ 9:16' }]}
              valor={vertical ? 'v' : 'h'} aoMudar={(v) => trocarFormato(v === 'v')} />
            <p className="hf-dica">One face, looking at the camera. The app frames head and shoulders for you. Drag one from the gallery or press ↑ Use.</p>
          </section>

          <section className="hf-ls-cartao" data-pronto={!!fala && !longa}>
            <header><b>2</b> Voice</header>
            <label className="hf-slot hf-ls-voz" data-cheio={!!fala}>
              {fala ? (
                <span className="hf-fala">
                  <audio src={fala.url} controls onClick={(e) => e.preventDefault()} />
                  <span className="hf-ls-medidor" data-longa={longa}>
                    <i style={{ width: `${Math.min(100, (fala.segundos / LIMITE) * 100)}%` }} />
                  </span>
                  <small>{fala.segundos.toFixed(1)} s of {LIMITE} s</small>
                </span>
              ) : <span>+ Voice track<small>WAV, MP3, FLAC, M4A or OGG</small></span>}
              <input type="file" accept=".wav,.mp3,.flac,.m4a,.ogg,audio/*" className="hf-arquivo" onChange={(e) => { const f = e.target.files?.[0]; if (f) enviarFala(f) }} />
            </label>
            {fala && <button type="button" className="hf-botao-sec" onClick={() => setFala(null)}>Remove voice</button>}
            <p className="hf-dica">Up to {LIMITE} s with this model. No recording? <a href="#voice">Create one in the Voice tab</a>.</p>
          </section>

          <section className="hf-ls-cartao hf-ls-cena">
            <header><b>3</b> Describe the scene <small>optional</small></header>
            <textarea aria-label="Scene description" maxLength={MAX_PROMPT} value={cena} onChange={(e) => setCena(e.target.value)} rows={4}
              placeholder="e.g. a news anchor in a bright studio, speaking with confidence" />
            <p className="hf-dica">How the person behaves while talking: mood, setting, gestures.</p>
          </section>
        </div>

        <div className="hf-linha-controles hf-lsn-barra">
          <label className="hf-campo"><span>Model</span><select className="hf-select" value={valorSelect} onChange={(e) => escolher(e.target.value)} aria-label="Model">
            <GruposAbertos itens={ABERTOS.map((m) => ({ id: m.id, rotulo: m.rotulo, soLocal: m.soLocal }))} api={apiModelos} />
          </select></label>
          <span className="hf-dica">{DESCRICOES[cfg.id]}</span>
          {ocupado && <span className="hf-dica">{ocupado}</span>}
          {longa && <span className="hf-erro">The voice is {fala!.segundos.toFixed(1)} s; the limit is {LIMITE} s.</span>}
          <span className="hf-espaco" />
          <BotaoGerar rotulo="Generate ✦" est={custo} desligado={!pronto} aoClicar={gerar} />
        </div>
        {naoInstalado && <AvisoInstalar rotulo={cfg.rotulo} />}
        {erro && <p className="hf-erro">{erro}</p>}
      </div>

      <section className="hf-img-recentes hf-lsn-recentes" aria-label="Your talking videos">
      <span className="hf-img-titulo">Your talking videos</span>
      <Galeria tipo="video">
        {minhas.map((t) => <CartaoTarefa key={t.id} t={t} />)}
        {minhas.length === 0 && <p className="hf-vazio">Your talking videos will appear here.</p>}
      </Galeria>
      </section>
    </div>
  )
}
