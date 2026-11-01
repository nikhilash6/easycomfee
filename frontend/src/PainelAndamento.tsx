import { useContext, useEffect, useRef, useState } from 'react'
import { api, type Andamento, type Tarefa } from './api'
import { MotorCtx } from './estudio/motor'

function tempo(segundos: number) {
  const s = Math.max(0, Math.floor(segundos))
  return s >= 3600
    ? `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}min`
    : `${Math.floor(s / 60)}min ${String(s % 60).padStart(2, '0')}s`
}

// O backend descreve a etapa em portugues (o editor antigo tambem le); aqui vira ingles.
const ETAPAS: [RegExp, string][] = [
  [/^(gerando|executando)$/, 'Generating'], [/^gerando a base do vídeo$/, 'Generating the base video'],
  [/^gerando o vídeo$/, 'Generating the video'], [/^gerando a música$/, 'Generating the music'], [/^gerando a fala$/, 'Generating the speech'],
  [/^revelando a imagem$/, 'Decoding the image'], [/^compondo o resultado$/, 'Compositing'],
  [/^encontrando a região$/, 'Finding the region'], [/^ajustando a máscara$/, 'Refining the mask'], [/^salvando$/, 'Saving'], [/^ampliando$/, 'Upscaling'],
  [/^carregando o modelo$/, 'Loading the model'], [/^carregando o modelo de (voz|transcrição|música)$/, 'Loading the model'],
  [/^carregando o (modelo auxiliar|interpretador de texto|controle|ampliador de vídeo)$/, 'Loading the models'],
  [/^carregando o decodificador de (áudio|vídeo)$/, 'Loading the decoder'],
  [/^decodificando o vídeo$/, 'Decoding the video'], [/^decodificando o áudio$/, 'Decoding the audio'],
  [/^montando o vídeo$/, 'Building the video'], [/^refinando o vídeo$/, 'Refining the video'],
  [/^extraindo os quadros$/, 'Reading the frames'], [/^extraindo afinação e timbre$/, 'Reading pitch and timbre'],
  [/^preparando o motor.*/, 'Starting the engine'], [/^preparando a geração.*/, 'Preparing the generation'], [/^preparando.*/, 'Preparing'],
  [/^(lendo|analisando)/, 'Reading the inputs'], [/^enriquecendo o prompt$/, 'Improving the prompt'],
  [/^escrevendo o layout$/, 'Writing the layout'], [/^aplicando o estilo$/, 'Applying the style'],
  [/^separando/, 'Separating the tracks'], [/^juntando/, 'Mixing'], [/^transcrevendo/, 'Transcribing'],
  [/^treinando \((\d+) de (\d+) épocas\)$/, 'Training ($1 of $2 epochs)'], [/^variação (\d+)$/, 'Variation $1'],
  [/^retomad/, 'Resumed after a restart'], [/refazendo$/, 'Retrying'],
]
// So o trecho reconhecido, ja traduzido: com s.replace o resto da frase ficava em portugues
// ("Reading the inputs o prompt…", 30/10/2026).
/** Interromper (o botao do topo e o do cartao): pergunta antes; devolve se parou. */
export async function pararGeracao(naNuvem: boolean): Promise<boolean> {
  if (!window.confirm(naNuvem
    ? 'Stop this generation? Anything waiting in line is cancelled too. Comfy Cloud may still charge for the work already done.'
    : 'Stop this generation? Anything waiting in line is cancelled too.')) return false
  try { await api.cancelar(); return true } catch { return false /* o estado da tarefa avisa se nao parou */ }
}

export const emIngles = (s: string) => {
  for (const [re, t] of ETAPAS) { const m = s.match(re); if (m) return m[0].replace(re, t) }
  return s
}

const MODELOS: Record<string, string> = {
  ltx: 'LTX 2.5', fasth3: 'FastH3', minimax: 'MiniMax H3', planos: 'Multi-shot video',
}

export default function PainelAndamento({ tarefa, naFila }: { tarefa: Tarefa; naFila: number }) {
  const [agora, setAgora] = useState(() => Date.now() / 1000)
  const [medidas, setMedidas] = useState<Andamento | null>(null)
  const [conexao, setConexao] = useState(true)
  const [aberto, setAberto] = useState(false)
  const raiz = useRef<HTMLDivElement>(null)
  const falhou = tarefa.estado === 'erro'

  useEffect(() => {
    if (!aberto) return
    const fechar = (e: PointerEvent) => {
      if (!raiz.current?.contains(e.target as Node)) setAberto(false)
    }
    const teclado = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setAberto(false)
        raiz.current?.querySelector('button')?.focus()
      }
    }
    document.addEventListener('pointerdown', fechar)
    document.addEventListener('keydown', teclado)
    return () => {
      document.removeEventListener('pointerdown', fechar)
      document.removeEventListener('keydown', teclado)
    }
  }, [aberto])

  useEffect(() => {
    if (falhou) return
    const relogio = window.setInterval(() => setAgora(Date.now() / 1000), 1000)
    let ativo = true
    let proxima: number | undefined
    const atualizar = async () => {
      try {
        const retrato = await api.andamento()
        if (ativo) { setMedidas(retrato); setConexao(true) }
      } catch {
        if (ativo) setConexao(false)
      } finally {
        if (ativo) proxima = window.setTimeout(atualizar, 5000)
      }
    }
    atualizar()
    return () => { ativo = false; clearInterval(relogio); clearTimeout(proxima) }
  }, [tarefa.id, falhou])

  const naEspera = tarefa.estado === 'na_fila'
  const inicio = tarefa.iniciada_em || tarefa.criada_em
  const ultimoAvanco = tarefa.ultimo_avanco_em || inicio
  const semAvanco = !falhou && !naEspera && agora - ultimoAvanco >= 120
  const recente = !!medidas?.coletado_em && agora - medidas.coletado_em < 20
  const respondendo = conexao && recente && medidas?.motor_respondendo
  const gpu = recente ? medidas?.gpu : null
  const ram = recente ? medidas?.ram : null
  const total = tarefa.passos_total || 0
  const passo = tarefa.passo_atual || 0
  const amostrando = tarefa.etapa_no?.startsWith('passo') || tarefa.etapa_no === 'amostra'
  const conhecido = !naEspera && !falhou && total > 0 && passo > 0
  const pct = conhecido ? Math.min(100, passo / total * 100) : 0
  const modelo = MODELOS[tarefa.modelo_video || ''] || (tarefa.modelo === 'video' ? 'Video' : 'Generation')
  const etapa = falhou ? 'Generation stopped' : naEspera ? 'In queue' : emIngles(tarefa.detalhe) || 'Preparing'
  // Parar (30/10/2026): o servidor ja sabia (/api/cancelar), faltava o botao. Na Comfy Cloud
  // o pedido de interromper tambem vai, mas o que ja rodou la pode ser cobrado (o aviso diz).
  const { naNuvem } = useContext(MotorCtx)
  const [parando, setParando] = useState(false)
  const parar = async () => {
    setParando(true)
    await pararGeracao(naNuvem)
    setParando(false)
  }

  return (
    <div className="andamento-topo" ref={raiz}>
      <button type="button" className="andamento-indicador" data-alerta={falhou || semAvanco}
        aria-expanded={aberto} aria-controls="andamento-detalhes"
        title="Generation details" onClick={() => setAberto(v => !v)}>
        <i className="andamento-ponto" aria-hidden="true" />
        <span className="andamento-etapa">{etapa}</span>
        {!falhou && total > 0 && <span className="andamento-passos">{passo}/{total}</span>}
        <span className="andamento-tempo">{falhou ? tempo(tarefa.duracao) : tempo(agora - inicio)}</span>
        <span aria-hidden="true">{aberto ? '⌃' : '⌄'}</span>
      </button>
      {!falhou && <button type="button" className="andamento-parar" onClick={parar} disabled={parando}
        title="Stop the generation (and anything waiting in line)">{parando ? 'Stopping…' : '■ Stop'}</button>}
      {!falhou && <div className="andamento-barra andamento-barra-topo" data-indeterminado={!conhecido}
        {...(conhecido ? { role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': total, 'aria-valuenow': passo,
          'aria-label': 'Steps done in the current stage' } : { 'aria-label': 'Generating, progress unknown' })}>
        <div style={conhecido ? { width: `${pct}%` } : undefined} />
      </div>}
    <section id="andamento-detalhes" className="painel-andamento" aria-label="Generation details" hidden={!aberto}>
      <div className="andamento-cabecalho">
        <div><span className="andamento-sobre">{tarefa.teste ? 'DIAGNOSTIC TEST' : 'IN PROGRESS'} · {modelo}</span>
          <h2>{etapa}</h2></div>
        <div className="andamento-acoes">
        {!falhou && <>
        <span className="andamento-conexao" data-ok={!!respondendo}>
          <i className="ponto" data-vivo={!!respondendo} />
          {respondendo ? 'Engine responding' : !conexao || !recente ? 'Checking connection' : 'Engine not responding'}
        </span>
        </>}
        </div>
      </div>
      {falhou ? <p className="andamento-alerta" role="alert">{/interrompida|cancelada/i.test(tarefa.erro) ? 'Stopped by you.'
        : tarefa.erro || 'The generation stopped. Check the engine before trying again.'}</p> : <>
      <div className="andamento-metricas">
        <div><span>{tarefa.iniciada_em ? 'Generating for' : 'Since sent'}</span><strong>{tempo(agora - inicio)}</strong></div>
        <div><span>Stage steps</span><strong>{total ? `${passo} / ${total}` : 'Waiting'}</strong></div>
        <div><span>GPU</span><strong>{gpu ? `${Math.round(gpu.uso_pct)}% busy` : 'No reading'}</strong></div>
        <div><span>GPU memory</span><strong>{gpu ? `${gpu.vram_usada_gib.toFixed(1)} / ${gpu.vram_total_gib.toFixed(1)} GB` : 'No reading'}</strong></div>
        <div><span>System RAM</span><strong>{ram ? `${ram.usada_gib.toFixed(1)} / ${ram.total_gib.toFixed(1)} GB` : 'No reading'}</strong></div>
      </div>
      <div className="andamento-rodape">
        <span>{naEspera ? 'Your request starts when the engine is free.'
          : amostrando && !passo ? 'Preparing the first step. The engine has not confirmed a finished step yet.'
          : tarefa.ultimo_avanco_em ? `Last confirmed progress ${tempo(agora - ultimoAvanco)} ago.`
          : 'Waiting for the engine to confirm the first progress.'}</span>
        <span>{naFila > 0 ? `${naFila} waiting in queue` : 'Nothing else in the queue'}</span>
      </div>
      {semAvanco && <p className="andamento-alerta" role="status">
        No confirmed progress for {tempo(agora - ultimoAvanco)}.
        {gpu && gpu.uso_pct > 5 ? ' The GPU is busy, but that does not prove this request is moving.'
          : ' Check the connection and the engine before trying again.'}
      </p>}
      <small className="andamento-nota">Steps are for the current stage; preparing, decoding and saving take time too. Memory and GPU use include other programs.</small>
      </>}
    </section>
    </div>
  )
}
