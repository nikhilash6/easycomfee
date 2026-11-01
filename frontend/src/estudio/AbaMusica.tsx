import { useContext, useEffect, useState } from 'react'
import { CartaoModelo, LinhaOnde, MotorCtx, useEscolha } from './motor'
import { useReusarPrompt } from './Visualizador'
import { api } from '../api'
import BlocoYue from './BlocoYue'
import { BotaoGerar, CartaoTarefa, Chips, mensagem, useCusto, useTarefas, Galeria, parteDoHash, useLembrado, textoDoDetalhe, MAX_PROMPT, TituloPagina } from './comum'

// Music: the three open-weight song models of the backend (musica.py), on
// your GPU or on Comfy Cloud, plus YuE2 and YuE2 Cover through Plenio (this
// computer's second engine), with their lyrics and score review (BlocoYue).

type ModeloMusica = { id: string; rotulo: string; letra: boolean; maximo: number; disponivel: boolean; motivo: string; plenio?: boolean
  estilos?: string[]; cover?: boolean; ordem?: string[]
  /** Where it exists: this machine (installed) and Comfy Cloud. */
  local?: boolean; nuvem?: boolean }

const DESCRICOES: Record<string, string> = {
  'minimax-music3': 'Full songs with vocals and lyrics, radio quality. Up to 5 min.',
  'ace-step15': 'Fast songs with vocals and lyrics, many genres and languages. Up to 10 min.',
  'stable-audio3': 'Instrumentals, loops and sound design. No vocals.',
  yue2: 'YuE2 via Plenio: AI-written lyrics, review the lyrics and score, mastered song. Non-commercial.',
  'yue2-cover': 'A cover of a recording: same melody, your style, original or new lyrics. Non-commercial.',
}

// Etiquetas dos cartoes de modelo.
const ETIQUETAS: Record<string, string[]> = {
  'minimax-music3': ['Vocals', 'Lyrics'],
  'ace-step15': ['Vocals', 'Lyrics', 'Guide track'],
  'stable-audio3': ['Instrumental', 'Sound design'],
  yue2: ['Vocals', 'Lyrics review'],
  'yue2-cover': ['Cover'],
}
// Estilos prontos: um clique acrescenta ao texto do estilo.
const ESTILOS = ['Lo-fi hip hop, mellow, vinyl crackle', 'Synthwave, 80s, driving bass, neon night',
  'Bossa nova, nylon guitar, soft female vocals', 'Epic orchestral, cinematic, big drums',
  'Indie rock, energetic, live band', 'Ambient, slow, dreamy pads']

const NOTAS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
// Os mesmos limites do servidor (PedidoGeracao): acima deles o preco sumia e o
// Generate devolvia um erro.
const MAX_LETRA = 12000
const BPM_MIN = 40, BPM_MAX = 240
const IDIOMAS: Record<string, string> = { en: 'English', pt: 'Portuguese', es: 'Spanish', fr: 'French', de: 'German', it: 'Italian', ja: 'Japanese', zh: 'Chinese', ko: 'Korean' }

export default function AbaMusica() {
  const tarefas = useTarefas()
  const [modelos, setModelos] = useState<ModeloMusica[]>([])
  const [modelo, setModelo] = useState(() => parteDoHash(1) || 'minimax-music3')
  const escolher = useEscolha(setModelo)
  const { naNuvem } = useContext(MotorCtx)
  const [prompt, setPrompt] = useLembrado('music.prompt', '')
  // "Reuse prompt" in the viewer fills this tab's text.
  useReusarPrompt(setPrompt)
  const [vocal, setVocal] = useState(true)
  const [letra, setLetra] = useLembrado('music.letra', '')
  const [duracao, setDuracao] = useState(60)
  const [genero, setGenero] = useState('livre')
  // As in the editor's music panel: ending, BPM, key and lyrics language.
  const [final, setFinal] = useState('natural')
  const [bpm, setBpm] = useState(120)
  const [tom, setTom] = useState('C major')
  const [idioma, setIdioma] = useState('en')
  // ACE-Step only: a recording the new song follows (its length and part of its structure).
  const [guia, setGuia] = useState<{ nome: string; url: string } | null>(null)
  const [transformacao, setTransformacao] = useState(0.75)
  const [subindo, setSubindo] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  // Carregar os cartoes: num PC lento o ComfyUI leva ate um minuto para listar
  // os modelos. Depois de 15 s avisa que segue conferindo; em 150 s desiste
  // (o backend espera ate 120 s) e mostra o erro com "Try again".
  const [tentativa, setTentativa] = useState(0)
  const [demorando, setDemorando] = useState(false)
  const [falhaCarga, setFalhaCarga] = useState<string | null>(null)
  useEffect(() => {
    const parar = new AbortController()
    let esgotou = false
    setFalhaCarga(null); setDemorando(false)
    const aviso = setTimeout(() => setDemorando(true), 15000)
    const limite = setTimeout(() => { esgotou = true; parar.abort() }, 150000)
    fetch('/api/musica', { signal: parar.signal })
      .then((r) => { if (!r.ok) throw new Error(); return r.json() })
      .then((l: ModeloMusica[]) => setModelos(l))
      .catch(() => {
        if (parar.signal.aborted && !esgotou) return  // tab closed or engine switched
        setFalhaCarga(esgotou ? 'ComfyUI took too long to list the music models.' : 'Could not load the music models.')
      })
      .finally(() => { clearTimeout(aviso); clearTimeout(limite) })
    return () => { parar.abort(); clearTimeout(aviso); clearTimeout(limite) }
  }, [naNuvem, tentativa])  // availability depends on the engine: reread when it switches

  const cfg = modelos.find((m) => m.id === modelo)
  // Link com um modelo que nao existe (#music/xyz): nenhum cartao escolhido e o
  // Generate desligado sem motivo. Agora a aba diz o que fazer.
  const modeloDesconhecido = modelos.length > 0 && !cfg
  // Cartao clicado: usa o motor atual se o modelo existe nele; senao troca de motor.
  const escolherModelo = (m: ModeloMusica) => {
    const aqui = naNuvem ? m.nuvem !== false : m.local !== false
    // So troca de motor se o modelo existe no outro e NAO pode existir neste
    // (nao instalado localmente ainda pode ser instalado: fica, e o aviso explica).
    if (aqui || !naNuvem) setModelo(m.id)
    else escolher(`local:${m.id}`)
  }
  const inserir = (marca: string) => setLetra((l) => (l && !l.endsWith('\n') ? l + '\n' : l) + marca + '\n')
  const comVoz = !!cfg?.letra && vocal
  const durOk = Math.min(duracao, cfg?.maximo ?? duracao)

  const pedido = {
    modelo: 'musica', modelo_musica: modelo, prompt: prompt.trim() || 'x', proporcao: '1:1',
    vocal_musica: comVoz, letra_musica: comVoz ? letra : '', duracao_musica: durOk,
    genero_vocal_musica: genero, encerramento_musica: final, margem_musica: 10,
    ...(modelo === 'ace-step15' ? { bpm_musica: Math.min(BPM_MAX, Math.max(BPM_MIN, Math.round(bpm) || 120)), tonalidade_musica: tom, idioma_musica: idioma,
      ...(guia ? { referencia_musica: guia.nome, transformacao_musica: transformacao } : {}) } : {}),
  }
  const custo = useCusto(cfg?.disponivel ? pedido : null)
  const pronto = !!cfg?.disponivel && !!prompt.trim() && (!comVoz || !!letra.trim())

  const gerar = async () => {
    setErro(null)
    try {
      const r = await fetch('/api/gerar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...pedido, prompt: prompt.trim() }) })
      if (!r.ok) throw new Error(textoDoDetalhe((await r.json().catch(() => ({}))).detail, 'Could not start the song.'))
    } catch (e) { setErro(mensagem(e)) }
  }

  // As etapas de revisao do YuE2 (letra, partitura) terminam "prontas" mas so com
  // texto, que o painel de revisao usa; na galeria ficariam cartoes vazios.
  const minhas = tarefas.filter((t) => t.modelo === 'musica' && !(t.estado === 'pronto' && t.imagens.length === 0))

  return (
    <div className="hf-aba hf-img hf-mun">
      <TituloPagina antes="Make a" destaque="song" sub="Describe the style, write the lyrics, get a full track." />
      <div className="hf-mun-grade">
      <div className="hf-mun-esq">
      <div className="hf-mu-modelos">
        {modelos.length === 0 && !falhaCarga && [0, 1, 2, 3, 4].map((k) => (
          <div key={k} className="hf-mu-modelo" data-carregando="true"><b>Checking models…</b>
            <small>{demorando ? 'Still checking: ComfyUI can take a minute the first time.' : 'On this computer and on Comfy Cloud'}</small></div>
        ))}
        {modelos.length === 0 && falhaCarga && (
          <p className="hf-erro" role="alert" style={{ gridColumn: "1 / -1" }}>{falhaCarga} Check that ComfyUI is running.{' '}
            <button type="button" className="hf-link" onClick={() => setTentativa((t) => t + 1)}>Try again</button></p>
        )}
        {modelos.map((m) => {
          const ok = m.local !== false || m.nuvem !== false
          return (
            <CartaoModelo key={m.id} ativo={modelo === m.id} aoEscolher={() => escolherModelo(m)}
              title={ok ? DESCRICOES[m.id] : 'Install it in Config Models'}
              // A placa aparece mesmo sem o modelo instalado: escolher leva ao aviso junto do Generate.
              rodape={<LinhaOnde escolher={escolher} id={m.id} cartaoAtivo={modelo === m.id} local nuvem={m.nuvem !== false} faltaLocal={m.local === false} />}>
              <b>{m.rotulo}</b>
              <small>{DESCRICOES[m.id]}</small>
              <span className="hf-mu-tags">
                {(ETIQUETAS[m.id] ?? []).map((t) => <i key={t}>{t}</i>)}
              </span>
            </CartaoModelo>
          )
        })}
      </div>

      <div className="hf-barra-prompt">
        <div className="hf-mu-corpo" data-letra={!cfg?.plenio && !!cfg?.letra}>
          <section className="hf-vz-coluna">
            <span className="hf-grupo-rotulo">Style</span>
            <textarea aria-label="Style and mood" maxLength={MAX_PROMPT} className="hf-vz-caixa" value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={5}
              placeholder="Genre, mood, instruments, tempo… e.g. upbeat synth-pop, female vocals, 120 bpm, summer night drive" />
            <div className="hf-vz-exemplos">
              {ESTILOS.map((e) => (
                <button key={e} type="button" className="hf-botao-sec" onClick={() => setPrompt(e)}>{e.split(',')[0]}</button>
              ))}
            </div>
          </section>
          {!cfg?.plenio && cfg?.letra && (
            <section className="hf-vz-coluna">
              <div className="hf-mu-cabeca">
                <span className="hf-grupo-rotulo">Lyrics</span>
                <Chips rotulo="Type" opcoes={[{ id: 'v', rotulo: 'With vocals' }, { id: 'i', rotulo: 'Instrumental' }]}
                  valor={vocal ? 'v' : 'i'} aoMudar={(v) => setVocal(v === 'v')} />
              </div>
              {comVoz ? <>
                <textarea aria-label="Lyrics" className="hf-vz-caixa hf-mu-letra" value={letra} onChange={(e) => setLetra(e.target.value)} rows={7}
                  maxLength={MAX_LETRA}
                  placeholder={'[Verse]\nCity lights are calling me…\n[Chorus]\n…'} />
                <div className="hf-vz-exemplos">
                  {['[Intro]', '[Verse]', '[Pre-Chorus]', '[Chorus]', '[Bridge]', '[Outro]'].map((m) => (
                    <button key={m} type="button" className="hf-botao-sec" onClick={() => inserir(m)}>{m}</button>
                  ))}
                </div>
              </> : <p className="hf-dica">No vocals: the style text alone drives the track.</p>}
            </section>
          )}
        </div>

        {modeloDesconhecido && <p className="hf-dica" role="status">{`"${modelo}" is not a music model here. Pick one of the cards above.`}</p>}
        {cfg?.plenio && <BlocoYue key={cfg.id} cfg={cfg} prompt={prompt} />}
      </div>
      </div>
      <aside className="hf-img-col hf-mun-dir" aria-label="Song settings">
        <b className="hf-mun-dir-titulo">Song Settings</b>
        {cfg?.plenio ? <p className="hf-dica">{cfg.rotulo} has its own steps on the left: lyrics, score review, then the song.</p> : <>
        <div className="hf-mu-ajustes">
          {/* O teto vem do modelo: enquanto o catalogo carrega nao ha teto para mostrar
              (antes aparecia um "max 3 min" inventado que depois virava 5 ou 10 min). */}
          {/* Duracao e final na mesma caixa: o final fica logo abaixo do controle deslizante. */}
          <div className="hf-ctrl hf-mun-duracao">
          {!(modelo === 'ace-step15' && guia) && <label className="hf-ctrl-largo"><small>Length · {Math.floor(durOk / 60)}:{String(durOk % 60).padStart(2, '0')}
            {cfg ? ` (max ${Math.round(cfg.maximo / 60)} min)` : ' (checking the limit…)'}</small>
            <input type="range" min={10} max={cfg?.maximo ?? duracao} step={5} value={durOk} disabled={!cfg}
              onChange={(e) => setDuracao(Number(e.target.value))} aria-label="Length in seconds" />
            {cfg && duracao > cfg.maximo && <small className="hf-ctrl-nota">{cfg.rotulo} goes up to {Math.round(cfg.maximo / 60)} min, so the song is {Math.round(cfg.maximo / 60)} min.</small>}</label>}
          <label className="hf-mun-final" title="Natural looks for a pause near the length; fade out fades the last seconds."><small>Ending</small>
            <select value={final} onChange={(e) => setFinal(e.target.value)}>
              <option value="natural">Natural ending</option><option value="fade">Fade out</option><option value="original">Keep as generated</option>
            </select></label>
          </div>
          {modelo === 'ace-step15' && <>
            <label className="hf-ctrl"><small>Tempo</small><span><input className="hf-campo" type="number" min={BPM_MIN} max={BPM_MAX} value={bpm} style={{ width: 64 }}
              onChange={(e) => setBpm(Number(e.target.value))}
              // Ao sair do campo o valor volta para a faixa (digitar "9" a caminho de "90" nao e cortado).
              onBlur={() => setBpm((b) => Math.min(BPM_MAX, Math.max(BPM_MIN, Math.round(b) || 120)))} /> BPM</span></label>
            <label className="hf-ctrl"><small>Key</small><select value={tom} onChange={(e) => setTom(e.target.value)}>
              {(['major', 'minor'] as const).flatMap((m) => NOTAS.map((n) => <option key={n + m} value={`${n} ${m}`}>{n} {m}</option>))}</select></label>
          </>}
          {comVoz && modelo === 'ace-step15' && <>
            <label className="hf-ctrl"><small>Voice</small><select value={genero} onChange={(e) => setGenero(e.target.value)}>
              <option value="livre">Any</option><option value="feminino">Female</option><option value="masculino">Male</option></select></label>
            <label className="hf-ctrl"><small>Lyrics language</small><select value={idioma} onChange={(e) => setIdioma(e.target.value)}>
              {Object.entries(IDIOMAS).map(([v, r]) => <option key={v} value={v}>{r}</option>)}</select></label>
          </>}
        </div>
        {modelo === 'ace-step15' && (
          <div className="hf-linha-controles">
            <label className="hf-slot hf-slot-audio" data-cheio={!!guia} title="Optional. A 10 to 600 s recording (WAV, MP3, FLAC, OGG, up to 40 MB). The new song keeps its length and part of its structure.">
              {guia ? <audio src={guia.url} controls /> : <span>{subindo ? 'Uploading…' : '+ Guide track (optional)'}</span>}
              <input type="file" accept="audio/*" className="hf-arquivo" onChange={async (e) => {
                const f = e.target.files?.[0]
                if (!f) return
                setSubindo(true); setErro(null)
                try { setGuia({ nome: (await api.enviarAudio(f)).nome, url: URL.createObjectURL(f) }) }
                catch (x) { setErro(mensagem(x)) } finally { setSubindo(false) }
              }} />
            </label>
            {guia && <>
              <label className="hf-ctrl hf-ctrl-largo" title="Lower keeps more of the guide; higher lets the arrangement change more.">
                <small>Change from the guide · {Math.round(transformacao * 100)}%</small>
                <input type="range" min={0.3} max={1} step={0.05} value={transformacao} onChange={(e) => setTransformacao(Number(e.target.value))} />
              </label>
              <button type="button" className="hf-botao-sec" onClick={() => setGuia(null)}>Remove guide</button>
              <span className="hf-dica">The length follows the guide.</span>
            </>}
          </div>
        )}
        <div className="hf-linha-controles">
          {cfg && !naNuvem && cfg.local === false
            ? <span className="hf-erro">{cfg.rotulo} is not installed on this computer. Install it in Config Models, or choose Cloud on its card.</span>
            : cfg && !cfg.disponivel && <span className="hf-erro">{cfg.motivo}</span>}
          <span className="hf-espaco" />
          <BotaoGerar rotulo="Generate ✦" est={custo} desligado={!pronto} aoClicar={gerar} />
        </div>
        </>}
        {erro && <p className="hf-erro">{erro}</p>}
      </aside>
      </div>

      <h3 className="hf-lsn-sub">Recent songs</h3>

      <Galeria tipo="audio">
        {minhas.map((t) => <CartaoTarefa key={t.id} t={t} />)}
        {minhas.length === 0 && <p className="hf-vazio">Your songs will appear here.</p>}
      </Galeria>
    </div>
  )
}
