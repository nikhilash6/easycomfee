import { useEffect, useRef, useState } from 'react'
import AbaNodes from './AbaNodes'
import PainelAndamento from '../PainelAndamento'
import { ProtegeAba, useSoltarNaCaixa, useTarefas } from './comum'
import { api, type GeradorVideo, type Modelo, type ModeloNuvem } from '../api'
import TelaModelos from '../TelaModelos'
import AbaApps from './AbaApps'
import AbaAssets from './AbaAssets'
import BotaoAtualizar from './BotaoAtualizar'
import MedidorRecursos from './MedidorRecursos'
import AvisoComfy from './AvisoComfy'
import MenuEstudios, { ESTUDIOS } from './MenuEstudios'
import IconeMenu from './IconesMenu'
import AbaCinema from './AbaCinema'
import AbaGenjutsu from './AbaGenjutsu'
import AbaImagem from './AbaImagem'
import AbaEditar from './AbaEditar'
import AbaLipSync, { type ModeloLipSync } from './AbaLipSync'
import AbaLTX from './AbaLTX'
import { AbaFlux3, AbaH3, AbaWan } from './EstudiosModelo'
import AbaMusica from './AbaMusica'
import AbaVideo from './AbaVideo'
import AbaVoz from './AbaVoz'
import { CHAVE_OCULTAR, EVENTO_AVISO_MOTOR, MotorCtx } from './motor'
import ContaApi from './ContaApi'
import PainelConta from './PainelConta'
import Visualizador from './Visualizador'
import './estudio.css'

// The new front door, Higgsfield-style: a top bar of modes, the Comfy Cloud
// balance and Models. Where each generation runs is picked in the model menus. "Advanced" is ComfyUI itself,
// with its node editor.

type Aba = 'image' | 'video' | 'ltx' | 'h3' | 'wan' | 'flux3' | 'lipsync' | 'music' | 'voice' | 'cinema' | 'genjutsu' | 'apps' | 'edit' | 'assets' | 'advanced'

const ABAS: { id: Aba; rotulo: string; breve?: boolean }[] = [
  { id: 'image', rotulo: 'Image' },
  { id: 'edit', rotulo: 'Edit' },
  { id: 'video', rotulo: 'Video' },
  { id: 'ltx', rotulo: 'LTX Studio' },
  { id: 'h3', rotulo: 'MiniMax H3 Studio' },
  { id: 'wan', rotulo: 'Wan Studio' },
  { id: 'flux3', rotulo: 'FLUX 3 Studio' },
  { id: 'apps', rotulo: 'VFX Studio' },
  { id: 'lipsync', rotulo: 'Lip Sync' },
  { id: 'music', rotulo: 'Music' },
  { id: 'voice', rotulo: 'Voice' },
  { id: 'cinema', rotulo: 'Cinema Studio' },
  { id: 'genjutsu', rotulo: 'Genjutsu' },
  { id: 'assets', rotulo: 'Assets' },
  { id: 'advanced', rotulo: 'Advanced' },
]

function lerAba(): Aba {
  const h = location.hash.replace('#', '').split('/')[0] as Aba
  if (ABAS.some((a) => a.id === h)) return h
  // Endereco que nao existe (ex.: #voz): a tela mostra a Image e o endereco passa a
  // dizer isso. Antes ficava o endereco errado na barra (varredura de 29/10/2026).
  if (location.hash) history.replaceState(history.state, '', '#image')
  return 'image'
}

/** Barra de abas que rola de lado: esmaece a borda onde ha mais abas e traz
 *  a aba ativa para a vista (antes "Advanced" ficava cortado sem nenhum sinal,
 *  e a aba ativa podia ficar fora da tela). */
function useBarraRolavel(ativa: string) {
  const ref = useRef<HTMLElement>(null)
  const marcar = () => {
    const nav = ref.current
    if (!nav) return
    nav.dataset.maisEsquerda = String(nav.scrollLeft > 1)
    nav.dataset.maisDireita = String(nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 1)
  }
  const trazerAtiva = () => {
    const nav = ref.current
    const botao = nav?.querySelector<HTMLElement>('button[data-ativo="true"]')
    if (!nav || !botao) { marcar(); return }
    // 40 px: a faixa esmaecida da borda tambem conta como fora da vista.
    const n = nav.getBoundingClientRect(), b = botao.getBoundingClientRect()
    const esq = nav.scrollLeft > 1 ? 40 : 0, dir = nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 1 ? 40 : 0
    if (b.left < n.left + esq) nav.scrollLeft -= n.left + esq - b.left + 8
    else if (b.right > n.right - dir) nav.scrollLeft += b.right - (n.right - dir) + 8
    marcar()
  }
  useEffect(() => {
    const nav = ref.current
    if (!nav) return
    marcar()
    nav.addEventListener('scroll', marcar, { passive: true })
    // Mudou de tamanho (janela, fontes carregando): a ativa volta para a vista.
    const obs = new ResizeObserver(trazerAtiva)
    obs.observe(nav)
    document.fonts?.ready.then(trazerAtiva)
    return () => { nav.removeEventListener('scroll', marcar); obs.disconnect() }
  }, [])
  useEffect(trazerAtiva, [ativa])
  return ref
}

export default function Estudio() {
  const [aba, setAba] = useState<Aba>(lerAba)
  // Titulo da janela/aba do navegador por rota ("Video · EasyComfee"): o historico,
  // as abas do navegador e os leitores de tela distinguem as paginas.
  useEffect(() => {
    const rotulo = ABAS.find((a) => a.id === aba)?.rotulo
    document.title = rotulo ? `${rotulo} · EasyComfee` : 'EasyComfee'
  }, [aba])
  const [modelos, setModelos] = useState<Modelo[]>([])
  const [apiImagem, setApiImagem] = useState<ModeloNuvem[]>([])
  const [geradores, setGeradores] = useState<GeradorVideo[]>([])
  const [lipsyncApi, setLipsyncApi] = useState<ModeloLipSync[]>([])
  const [soAbertos, setSoAbertos] = useState(true)
  const [naNuvem, setNaNuvem] = useState(false)
  const [verModelos, setVerModelos] = useState<false | 'api' | 'locais'>(false)
  const [versao, setVersao] = useState(0)
  // Reloads the catalog WITHOUT remounting the tabs (switching engine keeps the prompt).
  const [recarga, setRecarga] = useState(0)
  const [temChave, setTemChave] = useState(false)
  // Installed packages: the "Local" group of each model menu lists only these.
  const [instalados, setInstalados] = useState<Set<string> | undefined>()
  const [ocultar, setOcultar] = useState(() => { try { return localStorage.getItem(CHAVE_OCULTAR) === '1' } catch { return false } })
  const mudarOcultar = (v: boolean) => { setOcultar(v); try { localStorage.setItem(CHAVE_OCULTAR, v ? '1' : '0') } catch { /* private window */ } }
  const [linkRecarga, setLinkRecarga] = useState<string | undefined>()

  // As abas so leem o modelo e o modo do endereco ao montar. Na MESMA aba, ela
  // monta de novo quando chega uma rota profunda nova ("#video/imagem/wan22_14b")
  // ou quando se volta de uma rota profunda para a simples (Voltar ate "#video":
  // antes a tela seguia com o modelo do link). O texto escrito fica (useLembrado).
  const [rota, setRota] = useState(0)
  // A ultima rota de cada aba: o botao da aba volta para ela (modelo e modo
  // inclusos), em vez de abrir a aba do zero. Video e Image mantem o endereco em dia.
  const rotas = useRef<Record<string, string>>({})
  useEffect(() => {
    const ao = (e: HashChangeEvent) => {
      const antes = new URL(e.oldURL).hash, agora = location.hash
      const abaDe = (h: string) => h.replace('#', '').split('/')[0]
      if (antes) rotas.current[abaDe(antes)] = antes
      setAba(lerAba())
      const profunda = (h: string) => h.replace('#', '').includes('/')
      if (agora !== antes && abaDe(agora) === abaDe(antes) && (profunda(agora) || profunda(antes))) setRota((r) => r + 1)
      else if (agora !== antes && profunda(agora)) setRota((r) => r + 1)
    }
    window.addEventListener('hashchange', ao)
    return () => window.removeEventListener('hashchange', ao)
  }, [])
  const chave = `${versao}.${rota}`

  // Troca de motor que nao aconteceu (sem chave, geracao na fila...): aviso na tela.
  const [avisoMotor, setAvisoMotor] = useState<{ texto: string; chave: boolean } | null>(null)
  useEffect(() => {
    let timer: number | undefined
    const ao = (e: Event) => {
      setAvisoMotor((e as CustomEvent).detail)
      clearTimeout(timer)
      timer = window.setTimeout(() => setAvisoMotor(null), 12000)
    }
    window.addEventListener(EVENTO_AVISO_MOTOR, ao)
    return () => { window.removeEventListener(EVENTO_AVISO_MOTOR, ao); clearTimeout(timer) }
  }, [])

  useEffect(() => {
    const ao = (e: Event) => { setNaNuvem((e as CustomEvent).detail === 'nuvem'); setRecarga((r) => r + 1) }
    window.addEventListener('motor-trocado', ao)
    return () => window.removeEventListener('motor-trocado', ao)
  }, [])

  // O catalogo de modelos. Logo depois de ligar o PC o ComfyUI ainda esta subindo e
  // o pedido pode falhar ou vir vazio; antes a pagina nao pedia de novo e o menu de
  // modelos ficava vazio ate recarregar. Agora tenta de novo a cada 5 s ate vir.
  const [tentativaCatalogo, setTentativaCatalogo] = useState(0)
  useEffect(() => {
    let vivo = true, timer: number | undefined
    const deNovo = () => { if (vivo) timer = window.setTimeout(() => setTentativaCatalogo((n) => n + 1), 5000) }
    api.modelos().then((d) => {
      if (!d?.modelos?.length) { deNovo(); return }
      setModelos(d.modelos); setApiImagem(d.nuvem ?? [])
      // Os de API da interface antiga (MiniMax API, Wan 3.0) + os da lista nova (Kling, Veo, Seedance, Runway, Luma).
      const extras = ((d as unknown as { video_api?: GeradorVideo[] }).video_api ?? [])
      setGeradores([...(d.video?.geradores ?? []), ...extras])
      setLipsyncApi((d as unknown as { lipsync_api?: ModeloLipSync[] }).lipsync_api ?? [])
    }).catch(deNovo)
    fetch('/api/motor').then((r) => r.json()).then((m) => {
      setNaNuvem(m.modo === 'nuvem'); setSoAbertos(m.so_abertos !== false)
      setTemChave(!!m.chave_nuvem); setLinkRecarga(m.link_recarga)
    }).catch(() => {})
    return () => { vivo = false; clearTimeout(timer) }
  }, [versao, recarga, tentativaCatalogo])

  // Pacotes instalados. Com o ComfyUI ainda subindo (ou fora), o servidor nao sabe
  // (pronto: null): antes isso virava "nao instalado" em tudo e o Generate desligava.
  // Agora "nao sei" nao bloqueia nada, o topo avisa e a pergunta se repete ate saber.
  const [motorSubindo, setMotorSubindo] = useState(false)
  useEffect(() => {
    let vivo = true, timer: number | undefined
    const ler = () => fetch('/api/pacotes').then((r) => r.json()).then((d) => {
      if (!vivo) return
      const lista: { id: string; pronto: boolean | null }[] = d.pacotes ?? d
      const semSaber = lista.some((p) => p.pronto === null)
      setMotorSubindo((antes) => {
        // O ComfyUI acabou de responder: rele o catalogo (pedido durante a subida).
        if (antes && !semSaber) setTentativaCatalogo((n) => n + 1)
        return semSaber
      })
      setInstalados(semSaber ? undefined : new Set(lista.filter((p) => p.pronto).map((p) => p.id)))
      if (semSaber) timer = window.setTimeout(ler, 8000)
    }).catch(() => { if (vivo) timer = window.setTimeout(ler, 8000) })
    ler()
    return () => { vivo = false; clearTimeout(timer) }
  }, [versao, recarga])

  // A geracao em curso (local ou na nuvem) aparece no topo, com etapa e passos.
  const tarefas = useTarefas(true)
  // Arrastar da galeria (ou do computador) para qualquer caixa de prompt.
  useSoltarNaCaixa()
  const ATIVOS = ['preparando', 'submetendo', 'executando']
  const ativa = tarefas.find((t) => ATIVOS.includes(t.estado)) ?? tarefas.find((t) => t.estado === 'na_fila')
  const ir = (a: Aba) => {
    if (a !== aba) location.hash = rotas.current[a] ?? a
    setAba(a)
  }
  const barra = useBarraRolavel(aba)

  return (
    <MotorCtx.Provider value={{ naNuvem, temChave, instalados, ocultarNaoInstalados: ocultar }}>
    <div className="hf hf-com-lateral">
      {/* Barra lateral (layout de 31/10/2026): marca, as abas com icone (a ativa em destaque,
          icone lima) e, embaixo, o medidor de RAM/VRAM. Os estudios abrem pelo item Studios. */}
      <aside className="hf-lateral">
        <a className="hf-marca" href="#image" onClick={() => ir('image')} aria-label="EasyComfee home">
          <img className="hf-marca-completa" src="/brand/easycomfee-logo-horizontal.svg?v=5" alt="" />
          <img className="hf-marca-simbolo" src="/brand/easycomfee-symbol.svg" alt="" />
        </a>
        <nav className="hf-lat-nav" ref={barra} aria-label="Tabs">
          {ABAS.filter((a) => !ESTUDIOS.some((e) => e.id === a.id)).map((a) => (
            <span key={a.id} style={{ display: 'contents' }}>
              <button data-ativo={aba === a.id} aria-current={aba === a.id ? 'page' : undefined} onClick={() => ir(a.id)} title={a.rotulo}>
                <IconeMenu nome={a.id} /><span className="hf-lat-rotulo">{a.rotulo}</span>{a.breve && <sup>soon</sup>}
              </button>
              {a.id === 'video' && <MenuEstudios aba={aba} ir={(id) => ir(id as Aba)} lateral icone={<IconeMenu nome="estudios" />} />}
            </span>
          ))}
        </nav>
        <MedidorRecursos />
      </aside>
      <div className="hf-principal">
      <header className="hf-topo hf-topo-direita">
        <div className="hf-direita">
          {ativa && <PainelAndamento key={ativa.id} tarefa={ativa}
            naFila={tarefas.filter((t) => t.estado === 'na_fila' && t.id !== ativa.id).length} />}
<BotaoAtualizar />
          <PainelConta temChave={temChave} linkRecarga={linkRecarga} abrirConfig={() => setVerModelos('api')} />
          <button className="hf-botao-modelos" onClick={() => setVerModelos('locais')}>Config Models</button>
        </div>
      </header>
      <AvisoComfy />

      {motorSubindo && !naNuvem && (
        <p className="hf-aviso-partida" role="status">ComfyUI is starting (or not running yet). It usually takes a minute or two after the PC starts; this message goes away by itself.</p>
      )}
      <main className={aba === 'advanced' ? 'hf-avancado' : 'hf-corpo'}>
        <ProtegeAba key={aba}>
        {aba === 'image' && <AbaImagem key={chave} modelos={modelos} apiModelos={soAbertos ? [] : apiImagem} apiOcultos={soAbertos ? apiImagem : []} naNuvem={naNuvem} />}
        {aba === 'video' && <AbaVideo key={chave} apiGeradores={soAbertos ? [] : geradores.filter((g) => g.nuvem)} apiOcultos={soAbertos ? geradores.filter((g) => g.nuvem) : []} naNuvem={naNuvem} pronto={modelos.length > 0} />}
        {aba === 'ltx' && <AbaLTX />}
        {aba === 'h3' && <AbaH3 />}
        {aba === 'wan' && <AbaWan />}
        {aba === 'flux3' && <AbaFlux3 />}
        {aba === 'cinema' && <AbaCinema key={chave} modelos={modelos} apiModelos={soAbertos ? [] : apiImagem}
          apiGeradores={soAbertos ? [] : geradores.filter((g) => g.nuvem)} naNuvem={naNuvem} />}
        {aba === 'genjutsu' && <AbaGenjutsu key={chave} apiLiberado={!soAbertos} />}
        {aba === 'apps' && <AbaApps key={chave} naNuvem={naNuvem} />}
        {aba === 'edit' && <AbaEditar key={chave} />}
        {aba === 'lipsync' && <AbaLipSync key={chave} apiModelos={soAbertos ? [] : lipsyncApi} />}
        {aba === 'music' && <AbaMusica key={chave} />}
        {aba === 'voice' && <AbaVoz key={chave} naNuvem={naNuvem} />}
        {aba === 'assets' && <AbaAssets />}
        {aba === 'advanced' && <AbaNodes />}
        </ProtegeAba>
      </main>
      </div>

      <Visualizador />
      {avisoMotor && (
        <div className="hf-aviso-motor" role="alert">
          <span>{avisoMotor.texto}</span>
          {avisoMotor.chave && <button type="button" className="hf-botao-sec" onClick={() => { setVerModelos('api'); setAvisoMotor(null) }}>Add key</button>}
          <button type="button" className="hf-link" onClick={() => setAvisoMotor(null)} aria-label="Close">✕</button>
        </div>
      )}
      {verModelos && <TelaModelos abaInicial={verModelos}
        topoLocais={<label className="mq-check"><input type="checkbox" checked={ocultar} onChange={(e) => mudarOcultar(e.target.checked)} />
          <span>Hide the models that are not installed from the model menus (otherwise they show greyed out).</span></label>} fechar={() => { setVerModelos(false); setVersao((v) => v + 1) }}
        conta={<ContaApi temChave={temChave} soAbertos={soAbertos} linkRecarga={linkRecarga} aoMudar={() => setRecarga((r) => r + 1)} />} />}
    </div>
    </MotorCtx.Provider>
  )
}
