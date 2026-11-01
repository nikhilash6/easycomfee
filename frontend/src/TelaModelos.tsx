import { EVENTO_ESTADO, EVENTO_APLICAR } from './estudio/BotaoAtualizar'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useLembrado } from './estudio/comum'
import {
  apiPacotes, type Detectado, type Pacote, type PerfilMaquina, type ProgressoInstalacao,
} from './apiPacotes'

// Models screen. Two steps:
//  1. "Your machine": detected GPU/VRAM/RAM, confirmed (or corrected) by the
//     person. Without it the cards can't say whether a model is worth
//     downloading here.
//  2. One card per package: fit badge for this machine, tags, the required
//     components with Ready/size, and a single Download that installs the
//     ComfyUI nodes first and then the model files.

const gb = (b: number) => `${(b / 1e9).toFixed(1)} GB`

// Placas mais comuns e a VRAM de cada uma: escolher uma na lista ja preenche a VRAM.
const PLACAS: [string, number][] = [
  ['NVIDIA GeForce RTX 5090', 32], ['NVIDIA GeForce RTX 5080', 16], ['NVIDIA GeForce RTX 5070 Ti', 16],
  ['NVIDIA GeForce RTX 5070', 12], ['NVIDIA GeForce RTX 5060 Ti 16GB', 16], ['NVIDIA GeForce RTX 5060 Ti 8GB', 8],
  ['NVIDIA GeForce RTX 5060', 8],
  ['NVIDIA GeForce RTX 4090', 24], ['NVIDIA GeForce RTX 4080 SUPER', 16], ['NVIDIA GeForce RTX 4080', 16],
  ['NVIDIA GeForce RTX 4070 Ti SUPER', 16], ['NVIDIA GeForce RTX 4070 Ti', 12], ['NVIDIA GeForce RTX 4070 SUPER', 12],
  ['NVIDIA GeForce RTX 4070', 12], ['NVIDIA GeForce RTX 4060 Ti 16GB', 16], ['NVIDIA GeForce RTX 4060 Ti 8GB', 8],
  ['NVIDIA GeForce RTX 4060', 8],
  ['NVIDIA GeForce RTX 3090 Ti', 24], ['NVIDIA GeForce RTX 3090', 24], ['NVIDIA GeForce RTX 3080 Ti', 12],
  ['NVIDIA GeForce RTX 3080 12GB', 12], ['NVIDIA GeForce RTX 3080 10GB', 10], ['NVIDIA GeForce RTX 3070 Ti', 8],
  ['NVIDIA GeForce RTX 3070', 8], ['NVIDIA GeForce RTX 3060 Ti', 8], ['NVIDIA GeForce RTX 3060 12GB', 12],
  ['NVIDIA GeForce RTX 3060 8GB', 8], ['NVIDIA GeForce RTX 3050', 8],
  ['NVIDIA GeForce RTX 2080 Ti', 11], ['NVIDIA GeForce RTX 2080 SUPER', 8], ['NVIDIA GeForce RTX 2070', 8],
  ['NVIDIA GeForce RTX 2060 12GB', 12], ['NVIDIA GeForce RTX 2060', 6], ['NVIDIA GeForce GTX 1660 Ti', 6],
  ['NVIDIA GeForce GTX 1080 Ti', 11],
  ['NVIDIA RTX PRO 6000 Blackwell', 96], ['NVIDIA RTX 6000 Ada', 48], ['NVIDIA RTX A6000', 48],
  ['NVIDIA RTX A5000', 24], ['NVIDIA RTX A4000', 16], ['NVIDIA H100', 80], ['NVIDIA A100 80GB', 80],
  ['NVIDIA A100 40GB', 40], ['NVIDIA L40S', 48],
  ['AMD Radeon RX 9070 XT', 16], ['AMD Radeon RX 7900 XTX', 24], ['AMD Radeon RX 7900 XT', 20],
  ['AMD Radeon RX 7800 XT', 16], ['AMD Radeon RX 7600', 8],
]
// O catalogo usa tipos em portugues ("imagem"); a tela e em ingles.
const TIPOS: Record<string, string> = { imagem: 'image', musica: 'music', voz: 'voice', audio: 'audio' }
const OUTRA = '__outra__'
const OPCOES_VRAM = [4, 6, 8, 10, 11, 12, 16, 20, 24, 32, 40, 48, 80, 96]
const OPCOES_RAM = [8, 16, 24, 32, 48, 64, 96, 128, 192, 256]
// 15,9 GB detectados viram 16; 63,8 viram 64: o menu so tem numeros redondos.
const redondo = (v: number, opcoes: number[]) =>
  v ? opcoes.reduce((m, o) => (Math.abs(o - v) < Math.abs(m - v) ? o : m)) : 0

type Nos = { ativo: boolean; atual: string | null; feitos: string[]; erros: string[]; reiniciar: boolean; religado?: boolean }

const SELOS: Record<string, { texto: string; classe: string }> = {
  bem: { texto: 'Runs well here', classe: 'bem' },
  limitado: { texto: 'Runs limited here', classe: 'limitado' },
  nao_testado: { texto: 'Not tested on AMD', classe: 'limitado' },
  nao_roda: { texto: "Won't run here — use Comfy Cloud", classe: 'nao' },
  nuvem: { texto: 'Cloud only (no downloads)', classe: 'nuvem' },
}

/** Botao seletor: ligar o ComfyUI junto com o Windows (atalho na pasta Inicializar,
 *  backend/inicializacao.py). Com ele ligado, o motor ja esta pronto ao abrir o app. */
function InicioComWindows() {
  const [est, setEst] = useState<{ disponivel: boolean; ativo: boolean; motivo: string } | null>(null)
  const [mudando, setMudando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  useEffect(() => {
    fetch('/api/inicializacao').then((r) => r.json()).then(setEst).catch(() => setEst(null))
  }, [])
  if (!est) return null
  const alternar = async () => {
    setMudando(true); setErro(null)
    try {
      const r = await fetch('/api/inicializacao', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ativo: !est.ativo }) })
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Could not change it.')
      setEst(d)
    } catch (e) { setErro(e instanceof Error ? e.message : String(e)) } finally { setMudando(false) }
  }
  return (
    <section className="mq-cartao mq-interruptor">
      <div>
        <span className="mq-rotulo" id="mq-inicio-rotulo">Start ComfyUI with Windows</span>
        <p className="mq-sub">{est.disponivel
          ? 'ComfyUI loads while the PC starts, so it is ready when you open EasyComfee. It uses some memory even on days you do not open the app.'
          : est.motivo}</p>
        {erro && <p className="mq-aviso erro">{erro}</p>}
      </div>
      <button type="button" role="switch" aria-checked={est.ativo} aria-labelledby="mq-inicio-rotulo"
        className="mq-seletor" data-ligado={est.ativo} disabled={!est.disponivel || mudando} onClick={alternar}>
        <span className="mq-seletor-bola" aria-hidden />
        <span className="mq-seletor-texto">{est.ativo ? 'On' : 'Off'}</span>
      </button>
    </section>
  )
}

function Maquina({ aoSalvar }: { aoSalvar: (p: PerfilMaquina) => void }) {
  const [det, setDet] = useState<Detectado | null>(null)
  const [salvo, setSalvo] = useState<PerfilMaquina | null>(null)
  const [editando, setEditando] = useState(false)
  const [outra, setOutra] = useState(false)
  const [form, setForm] = useState<PerfilMaquina>({ gpu: '', vram_gb: 0, ram_gb: 0, so_nuvem: false })

  useEffect(() => {
    apiPacotes.maquina().then((m) => {
      setDet(m.detectado)
      setSalvo(m.salvo)
      const f = m.salvo ?? { gpu: m.detectado.gpu ?? '', vram_gb: m.detectado.vram_gb ?? 0,
                             ram_gb: m.detectado.ram_gb ?? 0, so_nuvem: false }
      setForm({ ...f, vram_gb: redondo(f.vram_gb, OPCOES_VRAM), ram_gb: redondo(f.ram_gb, OPCOES_RAM) })
    }).catch(() => {})
  }, [])

  const salvar = async (p: PerfilMaquina) => {
    const r = await apiPacotes.salvarMaquina(p)
    setSalvo(r); setEditando(false); aoSalvar(r)
  }

  if (!det) return <section className="mq-cartao"><p className="mq-sub">Detecting your machine…</p></section>

  if (salvo && !editando) {
    return (
      <section className="mq-cartao mq-resumo">
        <div>
          <span className="mq-rotulo">Your machine</span>
          <p className="mq-linha">
            {salvo.so_nuvem ? 'Comfy Cloud only' : `${salvo.gpu || 'GPU'} · ${salvo.vram_gb} GB VRAM · ${salvo.ram_gb} GB RAM`}
            {det.disco_livre_gb != null && !salvo.so_nuvem && ` · ${det.disco_livre_gb} GB free for models`}
          </p>
        </div>
        <button className="mq-botao-sec" onClick={() => setEditando(true)}>Change</button>
      </section>
    )
  }

  return (
    <section className="mq-cartao">
      <span className="mq-rotulo">Step 1 · Your machine</span>
      <p className="mq-sub">
        We check this before showing downloads, so you only install models that are worth running here.
        {det.fonte ? ` Detected via ${det.fonte}.` : ' No NVIDIA GPU detected — fill it in or use Comfy Cloud.'}
      </p>
      <div className="mq-campos">
        <label>GPU
          {/* Menu comum (o datalist do Chrome mostrava so o tamanho, sem o nome). "Other" abre um campo. */}
          <select value={outra ? OUTRA : form.gpu}
            onChange={(e) => {
              if (e.target.value === OUTRA) { setOutra(true); setForm({ ...form, gpu: '' }); return }
              const placa = PLACAS.find(([nome]) => nome === e.target.value)
              setOutra(false)
              setForm({ ...form, gpu: e.target.value, ...(placa ? { vram_gb: placa[1] } : {}) })
            }}>
            {!form.gpu && !outra && <option value="">Choose your graphics card</option>}
            {form.gpu && !outra && !PLACAS.some(([nome]) => nome === form.gpu) && <option value={form.gpu}>{form.gpu}</option>}
            {PLACAS.map(([nome, vram]) => <option key={nome} value={nome}>{nome} · {vram} GB</option>)}
            <option value={OUTRA}>Other (type it)</option>
          </select>
          {outra && <input autoFocus value={form.gpu} placeholder="Type your graphics card" onChange={(e) => setForm({ ...form, gpu: e.target.value })} />}
        </label>
        <label>VRAM (GB)<select value={form.vram_gb} onChange={(e) => setForm({ ...form, vram_gb: Number(e.target.value) })}>
          {!form.vram_gb && <option value={0}>Choose</option>}
          {OPCOES_VRAM.map((o) => <option key={o} value={o}>{o} GB</option>)}
        </select></label>
        <label>RAM (GB)<select value={form.ram_gb} onChange={(e) => setForm({ ...form, ram_gb: Number(e.target.value) })}>
          {!form.ram_gb && <option value={0}>Choose</option>}
          {OPCOES_RAM.map((o) => <option key={o} value={o}>{o} GB</option>)}
        </select></label>
      </div>
      {/(amd|radeon)/i.test(form.gpu) && (
        <p className="mq-aviso-amd">Local models were tested on NVIDIA cards only. On AMD some may not run; Comfy Cloud is the safe option.</p>
      )}
      <div className="mq-acoes">
        <button className="mq-botao" disabled={!form.vram_gb} onClick={() => salvar({ ...form, so_nuvem: false })}>Confirm</button>
        <button className="mq-botao-sec" onClick={() => salvar({ ...form, so_nuvem: true })}>I'll only use Comfy Cloud</button>
      </div>
    </section>
  )
}

// `conta` (the new studio) adds a first tab, "Comfy Cloud API", next to the local models.
export default function TelaModelos({ fechar, conta, abaInicial = 'locais', topoLocais }: {
  fechar: () => void; conta?: ReactNode; abaInicial?: 'api' | 'locais'
  /** Shown at the top of the Local models tab (the new studio's menu option). */
  topoLocais?: ReactNode
}) {
  const [aba, setAba] = useState<'api' | 'locais'>(conta ? abaInicial : 'locais')
  // Ligado: some da lista o que nao roda nesta placa (o que ja esta instalado fica).
  const [soQueRodam, setSoQueRodam] = useLembrado('modelos.so_que_rodam', false)
  const [pacotes, setPacotes] = useState<Pacote[] | null>(null)
  const [perfil, setPerfil] = useState<PerfilMaquina | null>(null)
  const [motor, setMotor] = useState(true)
  const [prog, setProg] = useState<ProgressoInstalacao | null>(null)
  const [nos, setNos] = useState<Nos | null>(null)
  const [opcionais, setOpcionais] = useState<Record<string, boolean>>({})
  const [erro, setErro] = useState<string | null>(null)
  // Recado sem erro (antes um alert() do navegador): mostrado como o erro, sem o vermelho.
  const [aviso, setAviso] = useState<string | null>(null)
  const [token, setToken] = useState<{ configurado: boolean } | null>(null)
  const [novoToken, setNovoToken] = useState('')

  const recarregar = () =>
    apiPacotes.listar()
      .then((r) => { setPacotes(r.pacotes); setMotor(r.motor_respondendo); setPerfil(r.maquina) })
      .catch((e) => setErro(e instanceof Error ? e.message : String(e)))

  useEffect(() => { recarregar(); apiPacotes.token().then(setToken).catch(() => {}) }, [])

  // Download and node progress: once a second while something installs, every
  // 10 s when idle (each poll is a line in the server window). When something
  // finishes, re-check. Installing calls lerAgora so the bar shows at once.
  const lerAgora = useRef<() => void>(() => {})
  useEffect(() => {
    let vivo = true
    let estavaAtivo = false
    let t: ReturnType<typeof setTimeout>
    const ler = async () => {
      clearTimeout(t)
      let ativo = false
      try {
        const p = await apiPacotes.progresso().catch(() => null)
        const n = await apiPacotes.progressoNos().catch(() => null)
        if (!vivo) return
        if (p) setProg(p)
        if (n?.progresso) setNos(n.progresso)
        ativo = !!(p?.ativo || n?.progresso?.ativo)
        if (estavaAtivo && !ativo) recarregar()
        estavaAtivo = ativo
      } finally {
        // Agenda a proxima leitura mesmo se uma resposta vier fora do esperado.
        if (vivo) t = setTimeout(ler, ativo ? 1000 : 10000)
      }
    }
    lerAgora.current = () => { ler() }
    ler()
    return () => { vivo = false; clearTimeout(t) }
  }, [])

  // Remove: mostra o plano (o que sai, o que fica por ser de outro pacote) e so
  // entao manda os arquivos para a Lixeira.
  const remover = async (p: Pacote) => {
    setErro(null); setAviso(null)
    try {
      const plano = await apiPacotes.planoRemocao(p.id)
      if (!plano.sai.length) {
        setAviso(`Nothing to remove: every file of ${p.nome} is also used by another installed package.`)
        return
      }
      const sai = plano.sai.map((f) => `• ${f.rotulo} (${gb(f.tamanho)})`).join('\n')
      const fica = plano.fica.length
        ? '\n\nKept (used by another installed package):\n'
          + plano.fica.map((f) => `• ${f.rotulo} (${f.usado_por.join(', ')})`).join('\n')
        : ''
      if (!confirm(`Remove ${p.nome}? Frees ${gb(plano.libera)}.\n\nGoes to the Recycle Bin:\n${sai}${fica}`)) return
      await apiPacotes.remover(p.id)
      recarregar()
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e))
    }
  }

  const instalar = async (p: Pacote) => {
    setErro(null)
    try {
      if (p.nos.some((n) => n.instalado === false)) await apiPacotes.instalarNos(p.id).catch(() => {})
      await apiPacotes.instalar(p.id, !!opcionais[p.id])
      lerAgora.current()
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e))
    }
  }

  const precisaToken = pacotes?.some((p) => p.arquivos.some((a) => a.requer_aceite && a.instalado !== true))

  // Janela modal de verdade: o foco entra nela ao abrir, Tab fica dentro dela,
  // Esc fecha e o foco volta para o botao que a abriu.
  const janela = useRef<HTMLDivElement>(null)
  const fecharAgora = useRef(fechar)
  useEffect(() => { fecharAgora.current = fechar })
  useEffect(() => {
    const antes = document.activeElement as HTMLElement | null
    janela.current?.focus()
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); fecharAgora.current(); return }
      if (e.key !== 'Tab' || !janela.current) return
      const focaveis = [...janela.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
      if (!focaveis.length) return
      const primeiro = focaveis[0], ultimo = focaveis[focaveis.length - 1]
      if (e.shiftKey && (document.activeElement === primeiro || document.activeElement === janela.current)) { e.preventDefault(); ultimo.focus() }
      else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus() }
    }
    document.addEventListener('keydown', tecla)
    return () => { document.removeEventListener('keydown', tecla); antes?.focus?.() }
  }, [])

  return (
    <div className="modelos-fundo" onClick={fechar}>
      <div className="modelos-janela mq" role="dialog" aria-modal="true" aria-labelledby="mq-titulo" tabIndex={-1} ref={janela}
        onClick={(e) => e.stopPropagation()}>
        <div className="mq-topo">
          <div>
            <h2 id="mq-titulo">{conta ? 'Config Models' : 'Local models'}</h2>
            <p className="mq-sub">{aba === 'api' ? 'Comfy Cloud GPUs and paid API models, with your Comfy credits.'
              : 'Stored in your ComfyUI models folder. Everything here is open weights.'}</p>
          </div>
          <button className="mq-botao-sec" onClick={fechar}>Close</button>
        </div>
        {conta && (
          <div className="mq-abas" role="tablist">
            <button role="tab" id="mq-aba-api" aria-controls="mq-painel" aria-selected={aba === 'api'} data-ativo={aba === 'api'} onClick={() => setAba('api')}>Comfy Cloud API</button>
            <button role="tab" id="mq-aba-locais" aria-controls="mq-painel" aria-selected={aba === 'locais'} data-ativo={aba === 'locais'} onClick={() => setAba('locais')}>Local models</button>
          </div>
        )}
        {/* O conteudo da aba escolhida: as abas acima apontam para ele (aria-controls). */}
        <div role={conta ? 'tabpanel' : undefined} id="mq-painel" aria-labelledby={conta ? `mq-aba-${aba}` : undefined}>
        {aba === 'api' ? conta : <>
        <InicioComWindows />

        <Maquina aoSalvar={(p) => { setPerfil(p); recarregar() }} />

        {!motor && <p className="mq-aviso">ComfyUI is not responding, so installed files can't be checked.</p>}
        {erro && <p className="mq-aviso erro">{erro}</p>}
        {aviso && <p className="mq-aviso" role="status">{aviso}</p>}
        {nos?.ativo && <p className="mq-aviso">Installing ComfyUI nodes: {nos.atual}…</p>}
        {nos && !nos.ativo && nos.erros.length > 0 && <p className="mq-aviso erro">Node errors: {nos.erros.join('; ')}</p>}
        {nos && !nos.ativo && nos.religado && <p className="mq-aviso" role="status">New nodes installed ({nos.feitos.join(', ')}). ComfyUI was restarted to load them; it takes a minute or two to come back.</p>}
        {nos && !nos.ativo && nos.reiniciar && <p className="mq-aviso">New nodes installed ({nos.feitos.join(', ')}). Restart ComfyUI to load them.</p>}

        {perfil && !perfil.so_nuvem && precisaToken && (
          <section className="mq-cartao">
            <span className="mq-rotulo">Hugging Face access</span>
            <p className="mq-sub">
              Lightricks and Black Forest Labs models are free but gated: sign in, open each “accept license” link
              below once, then paste a read token from{' '}
              <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noreferrer">huggingface.co/settings/tokens</a>.
              It stays on this computer.
            </p>
            <div className="mq-acoes">
              <input className="mq-token" type="password" autoComplete="off" value={novoToken} aria-label="Hugging Face token"
                placeholder={token?.configurado ? 'token saved' : 'hf_…'}
                onChange={(e) => setNovoToken(e.target.value)} />
              <button className="mq-botao" disabled={!novoToken.trim()}
                onClick={async () => { setToken(await apiPacotes.salvarToken(novoToken)); setNovoToken('') }}>Save</button>
            </div>
          </section>
        )}

        <Atualizacoes />

        {/* As duas opcoes de filtro juntas, sem caixa, uma em cima da outra. */}
        <div className="mq-filtros">
        {topoLocais}
        {perfil && !perfil.so_nuvem && pacotes && (
          <label className="mq-filtro">
            <input type="checkbox" checked={soQueRodam} onChange={(e) => setSoQueRodam(e.target.checked)} />
            Only show models that run on my computer
            {soQueRodam && <small> ({pacotes.filter((p) => p.nesta_maquina.selo === 'nao_roda' && p.pronto !== true).length} hidden)</small>}
          </label>
        )}
        </div>

        {perfil && pacotes?.filter((p) => !soQueRodam || p.nesta_maquina.selo !== 'nao_roda' || p.pronto === true).map((p) => {
          const baixando = !!prog?.ativo && prog.pacote === p.id
          const avaliacao = p.nesta_maquina
          const selo = SELOS[avaliacao.selo]
          const faltaNo = p.nos.some((n) => n.instalado === false)
          const aBaixar = p.arquivos
            .filter((a) => a.instalado !== true && !a.sem_origem && (opcionais[p.id] || !a.opcional))
            .reduce((s, a) => s + a.tamanho, 0)
          const temOpcional = p.arquivos.some((a) => a.opcional && a.instalado === false && !a.sem_origem)
          const pronto = p.pronto === true && !faltaNo
          const bloqueado = avaliacao.selo === 'nao_roda' || avaliacao.selo === 'nuvem' || !!avaliacao.sem_espaco
          const essencial = p.arquivos.filter((a) => !a.opcional).reduce((s, a) => s + a.tamanho, 0)
          return (
            <section key={p.id} className="mq-pacote" data-selo={avaliacao.selo}>
              <div className="mq-cabeca">
                <div>
                  <h3>
                    {p.nome}
                    {p.id === 'ltx25' && <span className="mq-destaque">⚡ Featured</span>}
                  </h3>
                  <p className="mq-sub">{p.descricao}</p>
                </div>
              </div>

              <div className="mq-etiquetas">
                <span className="mq-tag forte">{(TIPOS[p.tipo] ?? p.tipo).toUpperCase()}</span>
                <span className="mq-tag">{gb(essencial)}</span>
                <span className="mq-tag">{p.requisitos.vram_min}+ GB VRAM</span>
                <span className="mq-tag">local</span>
                <a className="mq-tag" href={p.licenca.url} target="_blank" rel="noreferrer">{p.licenca.nome}</a>
              </div>

              {selo && (
                <p className={`mq-selo ${selo.classe}`}>
                  {selo.texto}{avaliacao.motivo ? ` · ${avaliacao.motivo}` : ''}
                  {avaliacao.sem_espaco && ' · Not enough free disk space'}
                </p>
              )}
              {avaliacao.medido && <p className="mq-medido">{avaliacao.medido}</p>}

              {baixando && prog && (
                <div className="mq-progresso">
                  <progress value={prog.baixado} max={prog.total || 1} />
                  <span>{Math.min(prog.feitos + 1, prog.quantos)}/{prog.quantos} · {prog.arquivo} · {gb(prog.baixado)} of {gb(prog.total)} · {(prog.velocidade / 1e6).toFixed(0)} MB/s</span>
                </div>
              )}
              {!prog?.ativo && prog?.pacote === p.id && prog.erro && (
                <p className="mq-aviso erro">
                  {prog.erro}
                  {prog.repo_recusado && <> <a href={`https://huggingface.co/${prog.repo_recusado}`} target="_blank" rel="noreferrer">Open license page</a></>}
                </p>
              )}

              {/* Mesma linha em todo cartao: componentes a esquerda, acao a direita. */}
              <div className="mq-rodape">
                <details className="mq-componentes">
                  <summary>Required components ({p.arquivos.filter((a) => !a.opcional).length + p.nos.length})</summary>
                  <ul>
                    {p.arquivos.map((a) => (
                      <li key={a.pasta + a.subpasta + a.arquivo} data-ok={a.instalado === true}>
                        <span className="mq-marca">{a.instalado === true ? '✓' : '○'}</span>
                        <span className="mq-nome">{a.rotulo}{a.opcional ? ' · optional' : ''}</span>
                        <span className="mq-estado">
                          {a.encontrado ? <span title={`${a.pasta}/${a.encontrado}`}>Found in your ComfyUI: {a.pasta}/{a.encontrado}</span>
                            : a.instalado === true ? 'Ready'
                            : a.sem_origem ? `manual: ${a.pasta}/${a.subpasta ? a.subpasta + '/' : ''}${a.arquivo}`
                            : <>{gb(a.tamanho)}{a.requer_aceite && <> · <a href={`https://huggingface.co/${a.repo}`} target="_blank" rel="noreferrer">accept license</a></>}</>}
                        </span>
                      </li>
                    ))}
                    {p.nos.map((n) => (
                      <li key={'no' + n.nome} data-ok={n.instalado === true}>
                        <span className="mq-marca">{n.instalado ? '✓' : '○'}</span>
                        <span className="mq-nome">{n.nome} · ComfyUI node</span>
                        <span className="mq-estado">{n.instalado ? 'Ready' : 'to install'}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              <div className="mq-acao">
                {baixando ? (
                  <button className="mq-botao-sec" onClick={() => apiPacotes.cancelar()}>Cancel</button>
                ) : pronto && aBaixar === 0 ? (
                  <span className="mq-pronto">✓ Installed</span>
                ) : (
                  <button className="mq-botao" disabled={!!prog?.ativo || !!nos?.ativo || bloqueado}
                    title={bloqueado ? avaliacao.motivo : undefined} onClick={() => instalar(p)}>
                    ⤓ Download {aBaixar > 0 ? `(${gb(aBaixar)})` : 'nodes'}
                  </button>
                )}
                {!baixando && pronto && (
                  <button className="mq-remover" disabled={!!prog?.ativo || !!nos?.ativo} onClick={() => remover(p)}>Remove</button>
                )}
                {temOpcional && !baixando && (
                  <label className="mq-opc">
                    <input type="checkbox" checked={!!opcionais[p.id]}
                      onChange={(e) => setOpcionais({ ...opcionais, [p.id]: e.target.checked })} />
                    include optional
                  </label>
                )}
              </div>
              </div>
            </section>
          )
        })}
        </>}
        </div>
      </div>
    </div>
  )
}

/** "Check for updates": pergunta ao GitHub agora (sem esperar os 30 min do cache) e, se houver
 *  versao nova, oferece atualizar ali mesmo; o botao do topo tambem aparece. */
function Atualizacoes() {
  const [fase, setFase] = useState<'' | 'olhando' | 'feito'>('')
  const [dados, setDados] = useState<{ disponivel: boolean; novos: number; versao: string; motivo: string; sem_internet?: boolean } | null>(null)
  const conferir = async () => {
    setFase('olhando')
    try {
      const d = await fetch('/api/atualizacao?forcar=true').then((r) => r.json())
      setDados(d); window.dispatchEvent(new CustomEvent(EVENTO_ESTADO, { detail: d }))
    } catch { setDados({ disponivel: false, novos: 0, versao: '', motivo: 'Could not reach the studio.' }) }
    setFase('feito')
  }
  const texto = !dados ? 'See if a newer version of EasyComfee is on GitHub.'
    : dados.disponivel ? `A new version is available (${dados.novos} change${dados.novos === 1 ? '' : 's'}).`
    : dados.sem_internet ? 'No internet connection right now. Try again later.'
    : dados.motivo ? `Updates are not available on this install (${dados.motivo}).`
    : `You have the latest version${dados.versao ? ` (${dados.versao})` : ''}.`
  return (
    <section className="mq-cartao mq-atualizar">
      <div>
        <span className="mq-rotulo">Updates</span>
        <p className="mq-sub">{texto}</p>
      </div>
      {dados?.disponivel
        ? <button className="mq-botao mq-botao-forte" onClick={() => window.dispatchEvent(new Event(EVENTO_APLICAR))}>Update now</button>
        : <button className="mq-botao" disabled={fase === 'olhando'} onClick={conferir}>{fase === 'olhando' ? 'Checking…' : 'Check for updates'}</button>}
    </section>
  )
}

