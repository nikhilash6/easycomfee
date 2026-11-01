import { createContext, useContext, type ReactNode } from 'react'

// Where generations run, shared by every model menu. There is no Local / Cloud
// switch in the top bar any more: each menu has a "Local" group (open models
// installed here) and a "Comfy Cloud" group (open models hosted there and the
// paid "(API)" ones); picking an open model of the other group switches the engine.

export type Motor = 'local' | 'nuvem'

export const MotorCtx = createContext<{ naNuvem: boolean; temChave: boolean; instalados?: Set<string>; ocultarNaoInstalados?: boolean }>({ naNuvem: false, temChave: false })

/** The user's choice (Config Models > Local models): hide, instead of greying out, the models not installed. */
export const CHAVE_OCULTAR = 'openfield.ocultarNaoInstalados'

export async function trocarMotor(modo: Motor) {
  const r = await fetch('/api/motor', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ modo }),
  })
  const corpo = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(corpo.detail ?? 'Could not switch the engine.')
  window.dispatchEvent(new CustomEvent('motor-trocado', { detail: corpo.modo }))
}

type Item = { id: string; rotulo: string; nuvem?: boolean; soLocal?: boolean; soNuvem?: boolean; desligado?: boolean
  /** The tab knows it is not installed here (the menus that do not go by package). */
  naoInstalado?: boolean
  /** O que falta, quando nao e um pacote do Config Models (ex.: nos do ComfyUI). */
  falta?: string }

// Which install package (Config Models > Local models) each menu id needs.
// A model whose package is not installed does not show under "Local".
const PACOTE: Record<string, string | string[]> = {
  krea: 'krea2', kroma: 'kroma', flux3: 'flux3', klein: 'flux2_klein', qwen21: 'qwen21', zimage: 'zimage', upscale: 'upscale', trellis: 'trellis', qwen_edit: 'qwen_edit',
  mage: 'mage', ideogram: 'ideogram4', ltx: 'ltx25', minimax: 'minimax_h3', ltx23: 'avatar_ltx', longcat: 'avatar', h3_swap: 'h3_swap', wan22_replace: 'wan22_animate',
  // Recast: Qwen edits the first frame, then LTX 2.5 with the LTX 2.3 Union Control moves it.
  recast: ['ltx25', 'ltx23', 'qwen_edit'],
  // Modelos leves, para placas pequenas.
  flux1dev: 'flux1dev', flux1krea: 'flux1krea', flux2dev: 'flux2dev', hidream: 'hidream', chroma: 'chroma', sd35l: 'sd35l', kandinsky5i: 'kandinsky5i',
  flux1s: 'flux1s', sd35m: 'sd35m', sdxl: 'sdxl', sd15: 'sd15',
  ltxv2b: 'ltxv2b', fasth3: 'fasth3', wan22_14b: 'wan22_14b', hunyuan15: 'hunyuan15', kandinsky5: 'kandinsky5', wan22_5b: 'wan22_5b', wan21_13b: 'wan21_13b',
}

/** The value of a select option: "local:flux3", "nuvem:flux3". */
export function valorAberto(id: string, naNuvem: boolean) {
  return `${naNuvem ? 'nuvem' : 'local'}:${id}`
}

/** Two groups: "Local" (open models installed here) and "Comfy Cloud" (open
 *  models that exist there, plus the paid API ones marked "(API)"). */
export function GruposAbertos({ itens, api = [] }: { itens: Item[]; api?: { id: string; rotulo: string }[] }) {
  const { temChave, instalados, ocultarNaoInstalados } = useContext(MotorCtx)
  const precisa = (id: string) => ([] as string[]).concat(PACOTE[id] ?? [])
  const instalado = (m: Item) => !m.naoInstalado && (!instalados || precisa(m.id).every((p) => instalados.has(p)))
  // Not installed: greyed out with a hint, or hidden if the user asked for that.
  const local = itens.filter((m) => !m.soNuvem && (instalado(m) || !ocultarNaoInstalados))
  const nuvem = itens.filter((m) => !m.soLocal && m.nuvem !== false)
  return (
    <>
      {local.length > 0 && (
        <optgroup label="Local · your GPU">
          {local.map((m) => (
            <option key={'l' + m.id} value={`local:${m.id}`} disabled={m.desligado || !instalado(m)}>
              {m.rotulo}{instalado(m) ? '' : ` (${m.falta ?? 'install it in Config Models'})`}
            </option>
          ))}
        </optgroup>
      )}
      {(temChave || api.length > 0) && (
        <optgroup label="Comfy Cloud · credits">
          {temChave && nuvem.map((m) => <option key={'n' + m.id} value={`nuvem:${m.id}`} disabled={m.desligado}>{m.rotulo}</option>)}
          {api.map((m) => <option key={m.id} value={m.id}>{m.rotulo.replace(/ \((API|nuvem)\)$/, '')} (API)</option>)}
        </optgroup>
      )}
    </>
  )
}

/** The handler for a model select: switches the engine when an open model of the other group is picked. */
export function useEscolha(aoMudar: (id: string) => void) {
  const { naNuvem, temChave } = useContext(MotorCtx)
  return async (v: string) => {
    const [motor, id] = v.includes(':') ? (v.split(':', 2) as [Motor, string]) : [null, v]
    if (motor && (motor === 'nuvem') !== naNuvem) {
      // Sem chave a troca nem e tentada: o aviso leva direto a tela da chave.
      if (motor === 'nuvem' && !temChave) {
        avisarMotor('Add your Comfy Cloud API key to run models on the cloud.', true)
        return
      }
      // Troca primeiro: se o servidor recusar, o modelo escolhido continua o de antes.
      try { await trocarMotor(motor) } catch (e) {
        avisarMotor(String(e instanceof Error ? e.message : e))
        return
      }
    }
    aoMudar(id)
  }
}

/** Aviso na tela quando a troca de motor nao acontece (antes era um alert() do
 *  navegador, ou nada). O Estudio mostra; `chave` poe o botao da chave da nuvem. */
export const EVENTO_AVISO_MOTOR = 'easycomfee:aviso-motor'
export function avisarMotor(texto: string, chave = false) {
  window.dispatchEvent(new CustomEvent(EVENTO_AVISO_MOTOR, { detail: { texto, chave } }))
}

/** The select value: open models carry the engine, API models their own id. */
export function useValor(id: string, ehApi: boolean) {
  const { naNuvem } = useContext(MotorCtx)
  return ehApi ? id : valorAberto(id, naNuvem)
}

/** Se os pacotes de um modelo (PACOTE) estao instalados neste computador. */
export function useInstalado() {
  const { instalados } = useContext(MotorCtx)
  return (id: string) => !instalados || ([] as string[]).concat(PACOTE[id] ?? []).every((p) => instalados.has(p))
}

/** Modelo aberto escolhido para rodar NESTE computador sem o pacote instalado:
 *  o Generate fica desligado e a aba mostra <AvisoInstalar> (a Music ja fazia). */
export function useFaltaInstalar() {
  const { naNuvem } = useContext(MotorCtx)
  const instalado = useInstalado()
  return (id: string, ehApi = false) => !naNuvem && !ehApi && !instalado(id)
}

export function AvisoInstalar({ rotulo, semMenu = false }: { rotulo: string; semMenu?: boolean }) {
  // semMenu: telas sem menu de modelo (ferramentas LTX) nao mandam escolher outro.
  return <p className="hf-erro" role="alert">{rotulo} is not installed on this computer. Install it in Config Models{semMenu ? '.' : ', or pick a Comfy Cloud model in the menu.'}</p>
}

/** Etiqueta "Your GPU" / "Cloud" dentro de um cartao de modelo: escolhe o modelo
 *  JA no motor indicado. E um botao de verdade: o cartao (CartaoModelo) e um div
 *  com o seu proprio botao, porque botao dentro de botao e HTML invalido. */
export function Onde({ onde, ativo, falta, aoEscolher }: { onde: 'local' | 'nuvem'; ativo: boolean; falta?: boolean; aoEscolher: () => void }) {
  return (
    <button type="button" className="hf-onde" data-onde={onde} data-ativo={ativo} aria-pressed={ativo} data-falta={!!falta}
      title={onde === 'local' ? (falta ? 'Not installed: install it in Config Models' : 'Run it on your GPU (free)') : 'Run it on Comfy Cloud (credits)'}
      onClick={(e) => { e.stopPropagation(); aoEscolher() }}>
      {onde === 'local' ? (falta ? 'Your GPU · not installed' : 'Your GPU') : 'Cloud'}
    </button>
  )
}

/** Cartao de modelo (Music, Genjutsu): o cartao todo responde ao clique, mas o
 *  controle para teclado e leitor de tela e o botao com o nome; as etiquetas
 *  Your GPU / Cloud (LinhaOnde) ficam ao lado dele, nao dentro. */
export function CartaoModelo({ ativo, aoEscolher, title, children, rodape }: {
  ativo: boolean; aoEscolher: () => void; title?: string; children: ReactNode; rodape?: ReactNode
}) {
  return (
    <div className="hf-mu-modelo" data-ativo={ativo} onClick={aoEscolher} title={title}>
      <button type="button" className="hf-mu-escolher" aria-pressed={ativo} onClick={(e) => { e.stopPropagation(); aoEscolher() }}>
        {children}
      </button>
      {rodape}
    </div>
  )
}

/** A linha "Run on" de um cartao de modelo: sempre embaixo, a opcao nao escolhida apagada. */
export function LinhaOnde({ id, cartaoAtivo, local, nuvem, faltaLocal, escolher }: {
  id: string; cartaoAtivo: boolean; local: boolean; nuvem: boolean; faltaLocal?: boolean
  /** O useEscolha da aba: escolhe o modelo E o motor ("local:id" / "nuvem:id"). */
  escolher: (v: string) => void
}) {
  const { naNuvem } = useContext(MotorCtx)
  if (!local && !nuvem) return null
  return (
    <span className="hf-linha-onde" data-cartao-ativo={cartaoAtivo}>
      <small>Run on</small>
      {local && <Onde onde="local" ativo={cartaoAtivo && !naNuvem} falta={faltaLocal} aoEscolher={() => escolher(`local:${id}`)} />}
      {nuvem && <Onde onde="nuvem" ativo={cartaoAtivo && naNuvem} aoEscolher={() => escolher(`nuvem:${id}`)} />}
    </span>
  )
}
