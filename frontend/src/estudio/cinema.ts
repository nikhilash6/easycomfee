// Cinema Studio presets. Each choice turns into plain words the image and video
// models understand: what the camera, lens, focal length and aperture LOOK like
// on screen (grain, flares, depth of field), not brand names alone.

export type Opcao = { id: string; rotulo: string; texto: string }

export const CAMERAS: Opcao[] = [
  { id: 'alexa', rotulo: 'ARRI Alexa 65', texto: 'the look of large-format digital cinema footage, soft natural highlight roll-off, rich skin tones' },
  { id: 'venice', rotulo: 'Sony Venice 2', texto: 'the look of clean full-frame digital cinema footage, deep shadows, neutral color' },
  { id: 'imax', rotulo: 'IMAX 70mm film', texto: 'the look of 70mm large-format film, extreme detail, very fine grain, epic scale' },
  { id: 'film35', rotulo: '35mm film', texto: 'the look of 35mm motion picture film, visible film grain, warm halation around highlights' },
  { id: 'bolex', rotulo: '16mm Bolex', texto: 'the look of 16mm film, heavy grain, slightly soft, vintage indie feel' },
  { id: 'iphone', rotulo: 'iPhone 16 Pro Max', texto: 'the look of a modern flagship smartphone video: crisp computational HDR, deep focus, punchy clean colors, natural handheld feel' },
  { id: 'canon5d', rotulo: 'Canon 5D', texto: 'the look of a full-frame DSLR: shallow depth of field, warm pleasing skin tones, slightly soft creamy highlights' },
  { id: 'a7s', rotulo: 'Sony A7S III', texto: 'the look of a full-frame mirrorless low-light camera: clean shadows at night, smooth gradation, modern indie film feel' },
  { id: 'super8', rotulo: 'Super 8 film', texto: 'the look of Super 8 home movie film: strong grain, faded warm colors, light leaks, gate weave, rounded frame edges' },
  { id: 'vhs', rotulo: 'VHS camcorder', texto: 'the look of a worn 1990s VHS tape recording: low resolution, smeared colors bleeding past edges, horizontal scan lines, tracking noise, washed-out blacks' },
]

export const LENTES: Opcao[] = [
  { id: 'esferica', rotulo: 'Spherical prime', texto: 'sharp spherical prime lens, clean round bokeh' },
  { id: 'anamorfica', rotulo: 'Anamorphic', texto: 'anamorphic lens, oval bokeh, faint horizontal streaks only on bright street lights, widescreen cinematic feel' },
  { id: 'vintage', rotulo: 'Vintage', texto: 'vintage lens, swirly bokeh, soft glow, lower contrast' },
  { id: 'macro', rotulo: 'Macro', texto: 'macro lens, extreme close detail, razor-thin focus plane' },
  { id: 'tilt_shift', rotulo: 'Tilt-shift', texto: 'tilt-shift lens, a thin diagonal band of sharp focus with strong blur above and below, miniature model effect' },
  { id: 'split', rotulo: 'Split diopter', texto: 'split diopter lens, a near subject and a far subject both sharp at the same time, a faint soft line between them' },
  { id: 'sonda', rotulo: 'Probe lens', texto: 'probe lens, tiny lens tip very close to the subject, bug-eye perspective, deep focus, wide distorted background' },
  { id: 'soft', rotulo: 'Soft focus', texto: 'soft focus diffusion filter, dreamy glow blooming around highlights, gentle low-contrast haze' },
  { id: 'olho_peixe', rotulo: 'Fisheye', texto: 'fisheye lens, strong barrel distortion, ultra-wide curved horizon' },
]

export const FOCAIS: Opcao[] = [
  { id: '14', rotulo: '14mm', texto: '14mm ultra-wide focal length, exaggerated perspective, vast environment' },
  { id: '24', rotulo: '24mm', texto: '24mm wide focal length, subject in their environment' },
  { id: '35', rotulo: '35mm', texto: '35mm focal length, natural documentary framing' },
  { id: '50', rotulo: '50mm', texto: '50mm focal length, natural human-eye perspective' },
  { id: '85', rotulo: '85mm', texto: '85mm portrait focal length, compressed background, flattering face' },
  { id: '135', rotulo: '135mm', texto: '135mm telephoto focal length, strongly compressed background, isolated subject' },
]

export const ABERTURAS: Opcao[] = [
  { id: '1.4', rotulo: 'f/1.4', texto: 'aperture f/1.4, very shallow depth of field, background fully melted into bokeh' },
  { id: '2.8', rotulo: 'f/2.8', texto: 'aperture f/2.8, shallow depth of field, soft background' },
  { id: '5.6', rotulo: 'f/5.6', texto: 'aperture f/5.6, moderate depth of field' },
  { id: '11', rotulo: 'f/11', texto: 'aperture f/11, deep focus, foreground and background both sharp' },
]

// LTX follows camera directions written in the prompt; these are the phrasings
// that move the camera reliably.
export const MOVIMENTOS: Opcao[] = [
  // Sem "tripod": o LTX desenhava um tripe na cena (27/10/2026).
  { id: 'estatica', rotulo: 'Static', texto: 'Static shot with fixed framing: the view does not move, pan or zoom.' },
  { id: 'dolly_in', rotulo: 'Dolly in', texto: 'The camera slowly dollies in toward the subject.' },
  { id: 'dolly_out', rotulo: 'Dolly out', texto: 'The camera slowly dollies back, revealing more of the scene.' },
  { id: 'pan_esq', rotulo: 'Pan left', texto: 'The camera pans smoothly to the left.' },
  { id: 'pan_dir', rotulo: 'Pan right', texto: 'The camera pans smoothly to the right.' },
  { id: 'orbita', rotulo: 'Orbit', texto: 'The camera orbits around the subject in a smooth arc.' },
  { id: 'grua', rotulo: 'Crane up', texto: 'The camera cranes up and rises above the scene.' },
  { id: 'mao', rotulo: 'Handheld', texto: 'Handheld camera, subtle natural shake, following the action.' },
  { id: 'drone', rotulo: 'FPV drone', texto: 'Fast FPV drone shot flying forward through the scene.' },
  { id: 'zoom', rotulo: 'Crash zoom', texto: 'A sudden fast crash zoom into the subject.' },
]

// The rest of the shot, as in a call sheet. Each card shows a picture from
// public/cinema/<grupo>/<id>.webp, all made once with Flux 3 from the same scene.
export type Cor = Opcao & { cores?: string[] }

export const ENQUADRAMENTOS: Opcao[] = [
  { id: 'extremo_aberto', rotulo: 'Extreme wide', texto: 'Extreme wide shot, the figure small in a vast environment' },
  { id: 'aberto', rotulo: 'Wide', texto: 'Wide shot, full body with the surroundings around them' },
  { id: 'medio', rotulo: 'Medium', texto: 'Medium shot, framed from the waist up' },
  { id: 'close', rotulo: 'Close-up', texto: 'Close-up of one single person: the camera is close, only their head and shoulders are in frame, the place is a soft blur behind them' },
  { id: 'extremo_close', rotulo: 'Extreme close-up', texto: 'Extreme close-up of one single person: only their eyes and part of their face fill the whole frame, nothing else visible' },
  { id: 'ombro', rotulo: 'Over the shoulder', texto: 'Over-the-shoulder shot, a blurred shoulder in the foreground' },
  { id: 'baixo', rotulo: 'Low angle', texto: 'Low-angle shot from near the ground, looking steeply up at the person, who towers against the sky' },
  { id: 'alto', rotulo: 'High angle', texto: 'High-angle shot looking down on the subject from above' },
]

export const LUZES: Opcao[] = [
  { id: 'auto', rotulo: 'Auto', texto: '' },
  { id: 'dourada', rotulo: 'Golden hour', texto: 'warm low golden-hour sunlight, long soft shadows' },
  { id: 'nublado', rotulo: 'Overcast', texto: 'soft diffused overcast daylight, no hard shadows' },
  { id: 'azul', rotulo: 'Blue hour', texto: 'deep blue twilight, the last light in the sky, first lamps turning on' },
  { id: 'pratica', rotulo: 'Practical night', texto: 'night lit only by practical lamps in the scene, pools of warm light in darkness' },
  { id: 'neon', rotulo: 'Neon', texto: 'night lit by magenta and cyan neon signs, colored reflections on wet surfaces' },
  { id: 'chiaroscuro', rotulo: 'Low key', texto: 'low-key lighting, a single hard light, deep black shadows' },
  { id: 'silhueta', rotulo: 'Silhouette', texto: 'strong backlight, the subject a dark silhouette against a bright sky' },
]

export const FILMES: Opcao[] = [
  { id: 'auto', rotulo: 'Auto', texto: '' },
  { id: 'digital', rotulo: 'Digital clean', texto: 'clean noise-free digital image, crisp detail' },
  { id: 't500', rotulo: 'Tungsten 500T', texto: 'tungsten-balanced high-speed film emulsion, cool shadows, warm practicals, red halation, visible grain' },
  { id: 'd250', rotulo: 'Daylight 250D', texto: 'daylight film emulsion, natural warm colors, fine grain' },
  { id: 'pb', rotulo: 'Black & white', texto: 'black and white film, rich silver tones, grain' },
  { id: 'slide', rotulo: 'Slide film', texto: 'reversal slide film, punchy saturated colors, deep contrast' },
  { id: 'vencido', rotulo: 'Expired film', texto: 'expired film, faded colors, color shifts and light leaks' },
  { id: 'bleach', rotulo: 'Bleach bypass', texto: 'bleach bypass process, desaturated colors, high contrast, silvery highlights' },
]

export const GENEROS: Opcao[] = [
  { id: 'auto', rotulo: 'Auto', texto: '' },
  { id: 'noir', rotulo: 'Neo-noir', texto: 'neo-noir mood, moral tension, hard shadows, rain and reflections' },
  { id: 'western', rotulo: 'Western', texto: 'western mood, dust, heat, wide open land' },
  { id: 'scifi', rotulo: 'Science fiction', texto: 'science fiction mood, cold futuristic atmosphere, clean lines' },
  { id: 'epoca', rotulo: 'Period drama', texto: 'period drama mood, painterly composition, historical detail' },
  { id: 'suspense', rotulo: 'Thriller', texto: 'thriller mood, unease, something about to happen' },
  { id: 'documentario', rotulo: 'Documentary', texto: 'documentary realism, unposed, natural moment' },
  { id: 'estrada', rotulo: 'Road movie', texto: 'road movie mood, freedom, sun-bleached roadside Americana' },
]

export const GRADES: Cor[] = [
  { id: 'auto', rotulo: 'Auto', texto: '' },
  { id: 'teal', rotulo: 'Teal & orange', texto: 'teal and orange color grade, warm skin against cool shadows', cores: ['#0f4c5c', '#2a7f8a', '#e0a46b', '#d9772b'] },
  { id: 'aco', rotulo: 'Cold steel', texto: 'cold steel-blue color grade, muted colors', cores: ['#1c2733', '#3e5368', '#8aa0b4', '#c9d3dc'] },
  { id: 'ambar', rotulo: 'Warm amber', texto: 'warm amber color grade, golden highlights', cores: ['#3b1f0e', '#8c4a1c', '#d9902f', '#f2c879'] },
  { id: 'verde', rotulo: 'Sickly green', texto: 'greenish color grade, sickly fluorescent tint', cores: ['#142218', '#2f4a32', '#7a9a5e', '#c8d6a0'] },
  { id: 'pastel', rotulo: 'Pastel', texto: 'soft pastel color grade, lifted blacks, gentle colors', cores: ['#e8c6c0', '#f2dfc4', '#bcd7d2', '#c9c3e3'] },
  { id: 'mono', rotulo: 'Monochrome', texto: 'monochrome color grade, near black and white', cores: ['#111111', '#555555', '#aaaaaa', '#eeeeee'] },
]

export type Direcao = { camera: string; lente: string; focal: string; abertura: string;
  luz: string; filme: string; genero: string; grade: string }

/** The look as plain words, without the framing (that one changes per shot). */
export function visualDe(d: Direcao) {
  return [texto(CAMERAS, d.camera), texto(LENTES, d.lente), texto(FOCAIS, d.focal), texto(ABERTURAS, d.abertura),
    texto(LUZES, d.luz), texto(FILMES, d.filme), texto(GENEROS, d.genero), texto(GRADES, d.grade)].filter(Boolean).join(', ')
}

/** The still prompt: framing first, then the scene, then the look. */
export function montarPrompt(cena: string, d: Direcao, enquadramento: string) {
  return [texto(ENQUADRAMENTOS, enquadramento), cena.trim(), `Cinematic film still, ${visualDe(d)}`]
    .filter(Boolean).join('. ') + '.'
}

export function texto(lista: Opcao[], id: string) {
  return lista.find((o) => o.id === id)?.texto ?? ''
}
