// "Update" on the top bar: shows only when the GitHub repository has a newer
// version (backend/atualizacao.py). Pressing it closes the server, a window
// downloads and builds the new version, and this page reloads by itself when
// the studio is back.
import { useEffect, useRef, useState } from 'react'
import { textoDoDetalhe } from './comum'
import { avisarMotor } from './motor'

type Estado = { disponivel: boolean; novos: number }

/** O Config Models pede para conferir agora (forcar) e para atualizar: os dois avisos chegam aqui. */
export const EVENTO_ESTADO = 'easycomfee:atualizacao-estado'
export const EVENTO_APLICAR = 'easycomfee:atualizacao-aplicar'

export default function BotaoAtualizar() {
  const [estado, setEstado] = useState<Estado | null>(null)
  const [fase, setFase] = useState<'' | 'atualizando' | 'erro'>('')
  const [erro, setErro] = useState('')
  const atualizarRef = useRef<() => void>(() => {})

  // Pergunta ao abrir, de novo a cada 15 min e quando a pessoa volta para a aba:
  // antes so ao abrir, e uma versao publicada com a pagina aberta so aparecia com F5.
  useEffect(() => {
    let ultima = 0
    const ler = () => {
      if (Date.now() - ultima < 60_000) return
      ultima = Date.now()
      fetch('/api/atualizacao').then((r) => r.json()).then(setEstado).catch(() => {})
    }
    ler()
    const t = setInterval(ler, 15 * 60_000)
    const aoVoltar = () => { if (document.visibilityState === 'visible') ler() }
    document.addEventListener('visibilitychange', aoVoltar)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', aoVoltar) }
  }, [])

  useEffect(() => {
    const novo = (e: Event) => setEstado((e as CustomEvent<Estado>).detail)
    const aplicar = () => { atualizarRef.current() }
    window.addEventListener(EVENTO_ESTADO, novo); window.addEventListener(EVENTO_APLICAR, aplicar)
    return () => { window.removeEventListener(EVENTO_ESTADO, novo); window.removeEventListener(EVENTO_APLICAR, aplicar) }
  }, [])

  const atualizar = async () => {
    if (!confirm('Update EasyComfee now?\n\nThe studio closes for a few minutes while a window downloads the new version. '
      + 'Your key, gallery and models stay as they are.')) return
    setFase('atualizando')
    const r = await fetch('/api/atualizacao', { method: 'POST' }).catch(() => null)
    if (!r?.ok) {
      const texto = r ? textoDoDetalhe((await r.json().catch(() => ({}))).detail, 'Could not update.') : 'Could not reach the studio.'
      // Sem internet nada mudou: o botao continua "Update available" e o aviso explica.
      if (r?.status === 503) { setFase(''); avisarMotor(texto); return }
      setErro(texto); setFase('erro'); avisarMotor(texto)
      return
    }
    // Espera o servidor cair e voltar com a versao nova; ai recarrega.
    let caiu = false
    const vigia = setInterval(async () => {
      const ok = await fetch('/api/motor', { cache: 'no-store' }).then((x) => x.ok).catch(() => false)
      if (!ok) caiu = true
      else if (caiu) { clearInterval(vigia); location.reload() }
    }, 3000)
  }

  atualizarRef.current = atualizar
  if (!estado?.disponivel && !fase) return null

  if (fase === 'atualizando') return <span className="hf-atualizar" data-fase="atualizando">Updating… this page reloads by itself</span>
  return (
    <button type="button" className="hf-atualizar" onClick={atualizar} title={fase === 'erro' ? erro : `${estado?.novos ?? ''} new change(s) on GitHub`}>
      {fase === 'erro' ? 'Update failed' : 'Update available'}
    </button>
  )
}
