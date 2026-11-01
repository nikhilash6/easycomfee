import { useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api'
import { mensagem } from './comum'

/** Power: fecha o ComfyUI que o app liga e o proprio EasyComfee (como o parar.bat). */
export default function BotaoDesligar() {
  const [desligado, setDesligado] = useState(false)
  const desligar = async () => {
    if (!window.confirm('Turn off EasyComfee? ComfyUI closes too (if EasyComfee started it). To use it again, open EasyComfee from its shortcut.')) return
    try {
      await api.desligar()
      setDesligado(true)
    } catch (e) {
      window.alert(mensagem(e))
    }
  }
  // No body: dentro do topo o aviso ficava atras da barra lateral.
  if (desligado) return createPortal(
    <div className="hf-desligado" role="status">
      <div><h1>EasyComfee is off</h1><p>You can close this tab.</p></div>
    </div>, document.body)
  return (
    <button type="button" className="hf-botao-desligar" onClick={desligar} title="Turn off EasyComfee" aria-label="Turn off EasyComfee">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
        <path d="M12 3v9" /><path d="M6.3 6.8a8 8 0 1 0 11.4 0" />
      </svg>
    </button>
  )
}
