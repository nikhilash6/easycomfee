import { useEffect, useState } from 'react'
import { api } from '../api'
import { GruposAbertos, useEscolha } from './motor'
import { BotaoGerar, CartaoTarefa, mensagem, teclasRadio, useCusto, useTarefas, Galeria, useLembrado, textoDoDetalhe, TituloPagina } from './comum'

// Voice: text to speech with open weights. Locally it is OmniVoice (voz.grafo);
// on Comfy Cloud, where OmniVoice is missing, Qwen3-TTS (voz.grafo_nuvem),
// which also brings a set of ready speakers.

const MODOS = [
  { id: 'narrar', rotulo: 'Narrate', icone: '🗣', frase: 'Read your text with a ready voice.' },
  { id: 'criar', rotulo: 'Design a voice', icone: '✨', frase: 'Describe a voice and hear it say your text.' },
  { id: 'clonar', rotulo: 'Clone a voice', icone: '🎙', frase: 'Copy a voice from a short recording.' },
]
// Exemplos de voz para o modo "Design a voice": um clique preenche a descricao.
const VOZES_PRONTAS = [
  { rotulo: 'Warm narrator', texto: 'Warm middle-aged male narrator, deep and calm, documentary style' },
  { rotulo: 'Movie trailer', texto: 'Powerful deep male voice, dramatic movie trailer delivery, slow and intense' },
  { rotulo: 'Bright host', texto: 'Young energetic female host, bright and friendly, fast pace' },
  { rotulo: 'Soft whisper', texto: 'Soft gentle female voice, close whisper, calm and intimate' },
  { rotulo: 'Old storyteller', texto: 'Elderly man with a raspy voice, slow storyteller, slight British accent' },
]
// Vozes prontas do Narrate local: o OmniVoice nao tem lista de falantes, entao cada
// uma e um Voice Design com as tags que ele entende (genero, idade, tom, whisper)
// e seed fixa, para soar igual de um texto para outro. Medidas em 27/10/2026:
// homens 100-180 Hz, mulheres 240-350 Hz, em ingles e em portugues.
const VOZES_LOCAIS = [
  { id: '', rotulo: 'Auto', tags: '', seed: 0 },
  { id: 'warm', rotulo: 'Warm narrator', tags: 'male, middle-aged, low pitch', seed: 1101 },
  { id: 'bright', rotulo: 'Bright host', tags: 'female, young adult, high pitch', seed: 1102 },
  { id: 'trailer', rotulo: 'Movie trailer', tags: 'male, middle-aged, very low pitch', seed: 1103 },
  { id: 'storyteller', rotulo: 'Storyteller', tags: 'male, elderly, low pitch', seed: 1104 },
  { id: 'grandma', rotulo: 'Grandma', tags: 'female, elderly, moderate pitch', seed: 1105 },
  { id: 'whisper', rotulo: 'Soft whisper', tags: 'female, young adult, moderate pitch, whisper', seed: 1106 },
  { id: 'casual', rotulo: 'Young casual', tags: 'male, young adult, moderate pitch', seed: 1107 },
  { id: 'calm', rotulo: 'Calm presenter', tags: 'female, middle-aged, moderate pitch', seed: 1108 },
]
// Fala comum: ~15 caracteres por segundo. Serve para avisar do limite do Lip Sync.
const segundosDe = (texto: string) => Math.round(texto.trim().length / 15)
// O mesmo teto do servidor (12.000 caracteres, uns 13 min de fala): antes a caixa
// aceitava qualquer tamanho e so o Generate falhava.
const MAX_TEXTO = 12000
const IDIOMAS = ['English', 'Portuguese', 'Spanish', 'French', 'German', 'Italian', 'Japanese', 'Chinese', 'Korean']
const FALANTES = ['Ryan', 'Aiden', 'Dylan', 'Eric', 'Serena', 'Vivian', 'Ono_anna', 'Sohee', 'Uncle_fu']

export default function AbaVoz({ naNuvem }: { naNuvem: boolean }) {
  const tarefas = useTarefas()
  const [modo, setModo] = useState('narrar')
  const [texto, setTexto] = useLembrado('voice.texto', '')
  const [idioma, setIdioma] = useState('English')
  const [falante, setFalante] = useState('Ryan')
  const [vozLocal, setVozLocal] = useState('')
  const [busca, setBusca] = useState('')
  const [instrucao, setInstrucao] = useLembrado('voice.instrucao', '')
  // Narrate na nuvem: "como dizer" (excited, whispering...). Era o mesmo campo da
  // descricao do Design a voice, que ia escondida no pedido do Narrate.
  const [comoDizer, setComoDizer] = useLembrado('voice.como', '')
  const [ref, setRef] = useState<{ nome: string; url: string } | null>(null)
  const [transcricao, setTranscricao] = useLembrado('voice.transcricao', '')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  // The model follows the engine: OmniVoice on your GPU, Qwen3-TTS on Comfy Cloud.
  // Picking the other one in the menu switches the engine.
  const escolher = useEscolha(() => {})

  // Narrate local com voz pronta = Voice Design com as tags e a seed dela.
  const pronta = modo === 'narrar' && !naNuvem ? VOZES_LOCAIS.find((v) => v.id === vozLocal && v.tags) : undefined
  const pedido = {
    modelo: 'voz', modo_voz: pronta ? 'criar' : modo, prompt: texto.trim() || 'x', proporcao: '1:1', idioma_voz: idioma,
    falante_voz: falante,
    instrucao_voz: pronta ? pronta.tags : modo === 'criar' ? instrucao.trim() : modo === 'narrar' && naNuvem ? comoDizer.trim() : '', ...(pronta ? { seed: pronta.seed } : {}),
    referencia_voz: modo === 'clonar' ? ref?.nome ?? '' : '', transcricao_voz: modo === 'clonar' ? transcricao.trim() : '',
  }
  const custo = useCusto(pedido)
  // O que o motor tem: sem os nos do OmniVoice (TTS Audio Suite) a voz local nao
  // gera. Antes a aba nao perguntava e o Generate ficava ligado.
  const [caps, setCaps] = useState<{ disponivel: boolean; motivo: string; design?: boolean } | null>(null)
  useEffect(() => {
    setCaps(null)
    fetch('/api/voz').then((r) => r.json()).then(setCaps).catch(() => setCaps(null))
  }, [naNuvem])
  const semMotor = !!caps && (!caps.disponivel || (modo === 'criar' && caps.design === false))
  const pronto = !semMotor && !!texto.trim() && (modo !== 'criar' || !!instrucao.trim())
    && (modo !== 'clonar' || (!!ref && (naNuvem || !!transcricao.trim())))
  // O que falta para o Generate ligar (antes ficava desligado sem dizer por que).
  const falta = semMotor ? null
    : modo === 'criar' && !instrucao.trim() ? 'Describe the voice (or pick an example) to design it.'
    : modo === 'clonar' && !ref ? 'Add a voice sample to clone.'
    : modo === 'clonar' && !naNuvem && !transcricao.trim() ? 'Type what the sample says, word for word (needed on your GPU).'
    : !texto.trim() ? 'Write what to say.' : null

  const enviar = async (f: File) => {
    setEnviando(true); setErro(null)
    try { setRef({ nome: (await api.enviarAudio(f)).nome, url: URL.createObjectURL(f) }) }
    catch (e) { setErro(mensagem(e)) } finally { setEnviando(false) }
  }

  const gerar = async () => {
    setErro(null)
    try {
      const r = await fetch('/api/gerar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...pedido, prompt: texto.trim() }) })
      if (!r.ok) throw new Error(textoDoDetalhe((await r.json().catch(() => ({}))).detail, 'Could not start the voice.'))
    } catch (e) { setErro(mensagem(e)) }
  }

  const minhas = tarefas.filter((t) => t.modelo === 'voz')

  return (
    <div className="hf-aba hf-img hf-vzn">
      <TituloPagina antes="Give it a" destaque="voice" sub="Narration, a voice made from a description, or a clone of a recording. Use it in Lip Sync next." />

      <div className="hf-vz-modos" role="radiogroup" aria-label="Mode" onKeyDown={teclasRadio}>
        {MODOS.map((m) => (
          <button key={m.id} type="button" role="radio" aria-checked={modo === m.id} tabIndex={modo === m.id ? 0 : -1} className="hf-vz-modo"
            data-ativo={modo === m.id} onClick={() => setModo(m.id)}>
            <span aria-hidden>{m.icone}</span><b>{m.rotulo}</b><small>{m.frase}</small>
          </button>
        ))}
      </div>

      <div className="hf-barra-prompt">
        <div className="hf-vz-corpo">
          <section className="hf-vz-coluna">
            <div className="hf-vzn-cabeca">
              <span className="hf-grupo-rotulo">The voice</span>
              {modo === 'narrar' && <label className="hf-vfx-busca hf-vzn-busca"><span aria-hidden>⌕</span>
                <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Search voices…" aria-label="Search voices" /></label>}
            </div>
            {modo === 'narrar' && (naNuvem ? (
              <>
                <div className="hf-vzn-lista" role="radiogroup" aria-label="Speaker">
                  {FALANTES.filter((f) => f.toLowerCase().includes(busca.trim().toLowerCase())).map((f) => (
                    <button key={f} type="button" role="radio" aria-checked={falante === f} data-ativo={falante === f} onClick={() => setFalante(f)}>
                      <i aria-hidden>{f[0]}</i><b>{f.replace('_', ' ')}</b>
                    </button>
                  ))}
                </div>
                <input className="hf-campo" value={comoDizer} onChange={(e) => setComoDizer(e.target.value)} aria-label="How to say it"
                  placeholder="Optional: how to say it, e.g. excited, whispering, sad" />
              </>
            ) : (
              <>
                <div className="hf-vzn-lista" role="radiogroup" aria-label="Voice">
                  {VOZES_LOCAIS.filter((v) => `${v.rotulo} ${v.tags}`.toLowerCase().includes(busca.trim().toLowerCase())).map((v) => (
                    <button key={v.id} type="button" role="radio" aria-checked={vozLocal === v.id} data-ativo={vozLocal === v.id} onClick={() => setVozLocal(v.id)}>
                      <i aria-hidden>{v.rotulo[0]}</i><b>{v.rotulo}</b>
                      {v.tags && <span>{v.tags.split(', ').map((t) => <small key={t}>{t}</small>)}</span>}
                    </button>
                  ))}
                </div>
                <p className="hf-dica">{vozLocal ? 'The same voice in any language.' : 'Auto: OmniVoice picks a natural voice for the language.'} Want your own? Use <b>Design a voice</b> or <b>Clone a voice</b>.</p>
              </>
            ))}
            {modo === 'criar' && (
              <>
                <textarea aria-label="Voice description" className="hf-vz-caixa" value={instrucao} onChange={(e) => setInstrucao(e.target.value)} rows={4}
                  placeholder="Describe the voice: age, tone, pace, accent… e.g. warm elderly man, deep and slow, slight British accent" />
                <div className="hf-vz-exemplos">
                  {VOZES_PRONTAS.map((v) => (
                    <button key={v.rotulo} type="button" className="hf-botao-sec" onClick={() => setInstrucao(v.texto)}>{v.rotulo}</button>
                  ))}
                </div>
              </>
            )}
            {modo === 'clonar' && (
              <>
                <label className="hf-slot hf-vz-amostra" data-cheio={!!ref}>
                  {ref
                    ? <span className="hf-fala"><audio src={ref.url} controls onClick={(e) => e.preventDefault()} /></span>
                    : <span>{enviando ? 'Uploading…' : '+ Voice sample'}<small>5–20 s, one speaker, no music</small></span>}
                  <input type="file" accept=".wav,.mp3,.flac,.m4a,.ogg,audio/*" className="hf-arquivo"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) enviar(f) }} />
                </label>
                {ref && <button type="button" className="hf-botao-sec" onClick={() => setRef(null)}>Remove sample</button>}
                <textarea aria-label="What the sample says" className="hf-vz-caixa" value={transcricao} onChange={(e) => setTranscricao(e.target.value)} rows={3}
                  placeholder={naNuvem ? 'Optional: what is said in the sample, word for word (better clone)' : 'What is said in the sample, word for word'} />
              </>
            )}
          </section>

          <section className="hf-vz-coluna hf-vz-texto">
            <span className="hf-grupo-rotulo">What to say</span>
            <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={7} maxLength={MAX_TEXTO}
              placeholder="The text to speak…" aria-label="The text to speak" />
            <span className="hf-dica">
              {texto.length.toLocaleString('en-US')} / {MAX_TEXTO.toLocaleString('en-US')} characters · about {segundosDe(texto)} s of speech
              {/* Narracao longa e valida; so o Lip Sync aceita ate 30 s de fala. */}
              {segundosDe(texto) > 30 && <b className="hf-vz-longo"> · fine for narration, but over the 30 s that Lip Sync takes</b>}
              {texto.length >= MAX_TEXTO && <b className="hf-vz-longo"> · limit reached</b>}
            </span>
          </section>

          <aside className="hf-vz-coluna hf-vzn-dir" aria-label="Settings">
            <span className="hf-grupo-rotulo">Settings</span>
          <label className="hf-campo"><span>Model</span><select className="hf-select" value={naNuvem ? 'nuvem:qwen3tts' : 'local:omnivoice'} onChange={(e) => escolher(e.target.value)} aria-label="Model">
            <GruposAbertos itens={[{ id: 'omnivoice', rotulo: 'OmniVoice', soLocal: true, naoInstalado: !naNuvem && !!caps && !caps.disponivel, falta: 'nodes missing' },
              { id: 'qwen3tts', rotulo: 'Qwen3-TTS', soNuvem: true }]} />
          </select></label>
          <label className="hf-campo"><span>Language</span><select className="hf-select" value={idioma} onChange={(e) => setIdioma(e.target.value)} aria-label="Language">
            {IDIOMAS.map((i) => <option key={i}>{i}</option>)}
          </select></label>
            <BotaoGerar rotulo="Generate ✦" est={custo} desligado={!pronto} aoClicar={gerar} />
          </aside>
        </div>
        {falta && <p className="hf-dica" role="status">{falta}</p>}
        {semMotor && <p className="hf-erro" role="alert">{naNuvem ? 'Voice design is not available here.' : 'OmniVoice is not installed in your ComfyUI'}{caps?.motivo ? ` (${caps.motivo})` : ''}. Install the TTS Audio Suite nodes, or pick Qwen3-TTS (Comfy Cloud) in the menu.</p>}
        {erro && <p className="hf-erro">{erro}</p>}
      </div>

      <section className="hf-img-recentes hf-lsn-recentes" aria-label="Recent voices">
      <span className="hf-img-titulo">Recent voices</span>
      <Galeria tipo="audio">
        {minhas.map((t) => <CartaoTarefa key={t.id} t={t} />)}
        {minhas.length === 0 && <p className="hf-vazio">Your voices will appear here.</p>}
      </Galeria>
      </section>
    </div>
  )
}
