import type React from 'react'
// Botao "Studios" da barra de cima: os seis estudios num so lugar, numa janela
// com cartoes (capa, nome, uma linha). A barra passou de 13 para 9 itens e cabe
// inteira em laptop e Full HD. A janela e "fixed", fora da fileira de abas, porque
// a fileira rola de lado e cortaria o que saisse dela. Vai num portal no <body>:
// dentro da barra, o backdrop-filter dela prendia a janela (cortada e transparente).
// Um veu escuro atras da janela da contraste com a pagina.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export const ESTUDIOS = [
  { id: 'ltx', rotulo: 'LTX Studio', frase: 'Video, keyframes and VFX on one open model.' },
  { id: 'apps', rotulo: 'VFX Studio', frase: 'One-click LTX effects for your footage.' },
  { id: 'h3', rotulo: 'MiniMax H3 Studio', frase: 'Video with sound, characters and music.' },
  { id: 'wan', rotulo: 'Wan Studio', frase: 'From an 8 GB card to a full studio.' },
  { id: 'flux3', rotulo: 'FLUX 3 Studio', frase: 'Photoreal images, edits and video.' },
  { id: 'cinema', rotulo: 'Cinema Studio', frase: 'Direct the shot: camera, lens, light.' },
] as const

export default function MenuEstudios({ aba, ir, lateral = false, icone }: { aba: string; ir: (id: string) => void; lateral?: boolean; icone?: React.ReactNode }) {
  const [aberto, setAberto] = useState(false)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const botao = useRef<HTMLButtonElement>(null)
  const janela = useRef<HTMLDivElement>(null)
  const atual = ESTUDIOS.find((e) => e.id === aba)

  const abrir = () => {
    const r = botao.current!.getBoundingClientRect()
    // Centraliza a janela no botao sem passar das bordas da tela.
    const largura = Math.min(560, innerWidth - 24)
    // Na barra lateral a janela abre a direita do item, alinhada ao topo dele.
    if (lateral) setPos({ x: Math.min(r.right + 12, innerWidth - largura - 12), y: Math.max(12, Math.min(r.top - 8, innerHeight - 420)) })
    else setPos({ x: Math.max(12, Math.min(r.left + r.width / 2 - largura / 2, innerWidth - largura - 12)), y: r.bottom + 10 })
    setAberto(true)
  }

  useEffect(() => {
    if (!aberto) return
    janela.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const fora = (e: MouseEvent) => {
      if (!janela.current?.contains(e.target as Node) && !botao.current?.contains(e.target as Node)) setAberto(false)
    }
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') { setAberto(false); botao.current?.focus() } }
    const fechar = () => setAberto(false)
    document.addEventListener('mousedown', fora)
    document.addEventListener('keydown', tecla)
    window.addEventListener('resize', fechar)
    return () => {
      document.removeEventListener('mousedown', fora)
      document.removeEventListener('keydown', tecla)
      window.removeEventListener('resize', fechar)
    }
  }, [aberto])

  return (
    <>
      {/* Com um estudio aberto (Cinema, LTX...), o botao e a "pagina atual" da barra. */}
      <button ref={botao} type="button" data-ativo={!!atual} aria-current={atual ? 'page' : undefined} aria-haspopup="dialog" aria-expanded={aberto}
        onClick={() => (aberto ? setAberto(false) : abrir())}>
        {icone}<span className="hf-lat-rotulo">{atual ? atual.rotulo : 'Studios'}</span> <span className="hf-est-seta" aria-hidden>{lateral ? '›' : '▾'}</span>
      </button>
      {aberto && createPortal(<>
        <div className="hf-est-veu" aria-hidden onClick={() => setAberto(false)} />
        <div ref={janela} className="hf-est-janela" role="dialog" aria-label="Studios" style={{ left: pos.x, top: pos.y }}>
          {ESTUDIOS.map((e) => (
            <button key={e.id} type="button" className="hf-est-cartao" data-ativo={e.id === aba} aria-current={e.id === aba ? 'page' : undefined}
              onClick={() => { setAberto(false); ir(e.id) }}>
              <img src={`/studios/${e.id}.webp?v=3`} alt="" />
              <span><b>{e.rotulo}</b><small>{e.frase}</small></span>
            </button>
          ))}
        </div>
      </>, document.body)}
    </>
  )
}
