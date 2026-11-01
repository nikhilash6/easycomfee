import { useEffect, useState } from 'react'
import { APPS } from './AbaApps'
import FerramentaLTX, { FERRAMENTAS, type Ferramenta } from './FerramentasLTX'
import { PaginaEstudio, type Estudio } from './EstudiosModelo'

const LTX_CAPA = '/exemplos/noite.mp4?v=4'
const T = 'LTX 2.5 · GPU · Comfy Cloud'
const LTX: Estudio = {
  nome: 'LTX Studio',
  titulo: 'One model. An entire creative studio.',
  texto: 'Create a shot, reshape existing footage and finish it with LTX workflows running on your GPU or, where available, Comfy Cloud.',
  destaque: { rotulo: 'Create', destino: '#video/texto/ltx' },
  capa: LTX_CAPA,
  // So os videos LTX de fato: todo pedido traz modelo_video "ltx" por padrao, mesmo os de imagem.
  meu: (i) => (i.modelo === 'video' && /ltx/i.test(String(i.parametros?.modelo_video ?? ''))) || /^(transformar_video|avatar)$/.test(i.modelo),
  secoes: [
    { titulo: 'Create', estilo: 'compacto', icone: 'video', texto: 'Start from words, frames or visual references.', verTudo: '#video/texto/ltx', fluxos: [
      { nome: 'Text → Video', descricao: 'Turn a scene description into a video with sound.', destino: '#video/texto', etiqueta: T, capa: '/studios/cartoes/ltx_texto.gif' },
      { nome: 'Image → Video', descricao: 'Animate a still while keeping its subject and look.', destino: '#video/imagem', etiqueta: T, capa: '/studios/cartoes/ltx_imagem.gif' },
      { nome: 'First & last frame', descricao: 'Choose how the shot begins and ends.', destino: '#video/primeiro_ultimo', etiqueta: T, capa: '/studios/cartoes/ltx_pu.gif' },
      { nome: 'References → Video', descricao: 'Bring up to four people or objects into one shot.', destino: '#video/referencia', etiqueta: 'LTX 2.5 · Local GPU', capa: '/studios/cartoes/ltx_ref.gif' },
      { nome: 'Ingredients', descricao: 'Build a shot from several visual ingredients.', destino: '#ltx/ingredientes', etiqueta: 'LTX 2.5 · Local GPU', capa: '/studios/cartoes/ltx_ingredientes.gif' },
      { nome: 'Keyframes', descricao: 'Place 2 to 8 images at chosen seconds; LTX moves through them.', destino: '#ltx/chaves', etiqueta: T, capa: '/studios/cartoes/ltx_chaves.gif' },
      { nome: 'Cinema Studio', descricao: 'Direct LTX shots with framing, lighting and camera choices.', destino: '#cinema/ltx-video', etiqueta: T, capa: '/studios/cartoes/cinema.gif' },
    ] },
    { titulo: 'Transform', estilo: 'compacto', icone: 'estudios', texto: 'Apply an LTX video workflow to footage you already have.', verTudo: '#apps', fluxos:
      // O 3D render -> Video vai em segundo lugar na fileira.
      ((l) => { const m = l.find((x) => x.id === 'maquete'); const r = l.filter((x) => x.id !== 'maquete'); return m ? [r[0], m, ...r.slice(1)] : l })(
        APPS).map((app) => ({ nome: app.nome, descricao: app.frase, destino: `#apps/${app.id}`,
        etiqueta: app.id === 'slowmo' ? 'LTX Slow Motion · GPU' : app.id === 'mapa_profundidade' ? 'Depth map · GPU' : 'LTX VFX · GPU · Comfy Cloud', capa: `/exemplos/${app.id}.mp4?v=9` })) },
    { titulo: 'Finish & perform', estilo: 'largo', icone: 'lipsync', texto: 'Upscale, animate speech or carry a new character through the original motion.', fluxos: [
      { nome: 'Latent upscale', descricao: 'Enlarge an existing video with the LTX latent upscaler.', destino: '#ltx/ampliar', etiqueta: 'LTX 2.5 · Local GPU', capa: '/studios/cartoes/ltx_upscale.webp' },
      { nome: 'Lip Sync', descricao: 'Animate a portrait from a voice track with LTX 2.3.', destino: '#lipsync/ltx', etiqueta: 'LTX 2.3 · GPU · Comfy Cloud', capa: '/studios/cartoes/ltx_lipsync.webp' },
      { nome: 'Recast', descricao: 'Change the cast or setting while preserving the video’s motion.', destino: '#genjutsu/recast', etiqueta: 'LTX Union Control · GPU', capa: '/exemplos/trocar.mp4' },
    ] },
  ],
}

const lerFerramenta = () => {
  const id = location.hash.slice('#ltx/'.length)
  return location.hash.startsWith('#ltx/') && (FERRAMENTAS as readonly string[]).includes(id) ? id as Ferramenta : null
}

export default function AbaLTX() {
  // #ltx/<ferramenta> abre a tela propria; #ltx volta para a vitrine.
  const [ferramenta, setFerramenta] = useState(lerFerramenta)
  useEffect(() => {
    const ao = () => { setFerramenta(lerFerramenta()); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', ao)
    return () => window.removeEventListener('hashchange', ao)
  }, [])
  if (ferramenta) return <FerramentaLTX key={ferramenta} id={ferramenta} />
  return <PaginaEstudio e={LTX} />
}
