// Line icons for the camera rig (body, lens, focal length, aperture). Drawn
// here instead of photos: the gear is a tool, the photos are for the looks.

const P = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

function Corpo({ id }: { id: string }) {
  switch (id) {
    case 'alexa': // big digital cinema body, top handle, side monitor
      return <g {...P}><rect x="14" y="12" width="26" height="16" rx="2" /><path d="M20 12v-4h14v4" /><rect x="40" y="15" width="10" height="10" rx="1.5" />
        <circle cx="45" cy="20" r="3" /><rect x="6" y="14" width="8" height="8" rx="1" /><path d="M24 28v4M32 28v4" /></g>
    case 'venice': // compact full-frame body, flat sides
      return <g {...P}><rect x="16" y="11" width="22" height="18" rx="3" /><path d="M20 15h8M20 19h5" /><rect x="38" y="14" width="11" height="12" rx="2" />
        <circle cx="43.5" cy="20" r="3.5" /></g>
    case 'imax': // huge body with two large reels on top
      return <g {...P}><circle cx="22" cy="10" r="7" /><circle cx="38" cy="10" r="7" /><rect x="12" y="17" width="34" height="14" rx="2" />
        <rect x="46" y="20" width="8" height="8" rx="1" /><circle cx="22" cy="10" r="1.5" /><circle cx="38" cy="10" r="1.5" /></g>
    case 'film35': // classic film camera, magazine on top
      return <g {...P}><path d="M18 14a8 6 0 0 1 16 0" /><path d="M26 14a8 6 0 0 1 16 0" /><rect x="16" y="14" width="26" height="14" rx="2" />
        <path d="M42 17l8-3v12l-8-3" /></g>
    case 'bolex': // small 16mm body with a 3-lens turret and a crank
      return <g {...P}><rect x="18" y="10" width="18" height="20" rx="3" /><circle cx="42" cy="13" r="3" /><circle cx="44" cy="20" r="3.5" />
        <circle cx="42" cy="27" r="3" /><path d="M18 20h-5l-2 4" /><circle cx="11" cy="24" r="1.5" /></g>
    case 'iphone': // phone back with a three-lens camera island
      return <g {...P}><rect x="20" y="4" width="20" height="32" rx="4" /><rect x="23" y="7" width="11" height="11" rx="3" /><circle cx="26" cy="10.5" r="1.8" />
        <circle cx="31" cy="10.5" r="1.8" /><circle cx="26" cy="15" r="1.8" /><circle cx="31.5" cy="15" r="0.8" /></g>
    case 'canon5d': // dslr: grip, prism hump, round lens
      return <g {...P}><path d="M12 14h8l3-4h10l3 4h8v16H12z" /><path d="M12 14v16h6V14" /><circle cx="32" cy="22" r="6" /><circle cx="32" cy="22" r="3" /></g>
    case 'a7s': // mirrorless: flat top, small hump, grip
      return <g {...P}><path d="M12 15h10l2-3h8l2 3h10v14H12z" /><path d="M12 15v14h5V15" /><circle cx="32" cy="22" r="5.5" /><circle cx="32" cy="22" r="2.5" /><circle cx="40" cy="12.5" r="1.2" /></g>
    case 'super8': // home movie camera: slanted body, pistol grip
      return <g {...P}><path d="M14 12h22l4 4v8H14z" /><path d="M40 16l8-2v12l-8-2" /><path d="M20 24l-2 10h6l2-10" /><rect x="10" y="14" width="4" height="5" rx="1" /></g>
    default: // vhs camcorder: cassette door, handle strap, viewfinder
      return <g {...P}><rect x="10" y="13" width="30" height="15" rx="4" /><rect x="15" y="17" width="14" height="7" rx="1" /><circle cx="19" cy="20.5" r="1.3" />
        <circle cx="25" cy="20.5" r="1.3" /><path d="M40 16h8v9h-8" /><path d="M14 13c3-5 18-5 22 0" /><rect x="6" y="9" width="8" height="5" rx="1" /></g>
  }
}

function Lente({ id }: { id: string }) {
  switch (id) {
    case 'esferica':
      return <g {...P}><rect x="14" y="12" width="24" height="16" rx="2" /><path d="M20 12v16M26 12v16" /><circle cx="44" cy="20" r="7" /><circle cx="44" cy="20" r="3" /></g>
    case 'anamorfica':
      return <g {...P}><rect x="12" y="12" width="26" height="16" rx="2" /><path d="M18 12v16" /><ellipse cx="44" cy="20" rx="5" ry="8" />
        <path d="M30 20h26" strokeDasharray="2 2" /></g>
    case 'vintage':
      return <g {...P}><path d="M14 14h20l6 3v6l-6 3H14z" /><path d="M18 14v12M22 14v12M26 14v12" /><circle cx="44" cy="20" r="4" /></g>
    case 'macro':
      return <g {...P}><rect x="10" y="13" width="32" height="14" rx="2" /><path d="M16 13v14M36 13v14" /><path d="M44 20h4" />
        <circle cx="52" cy="20" r="3" /><path d="M50 17l-2-3M54 17l2-3" /></g>
    case 'tilt_shift': // lens body bent at an angle
      return <g {...P}><rect x="10" y="13" width="14" height="14" rx="2" /><path d="M24 15l4-2v14l-4-2" /><path d="M28 13l14 3v10l-14 3" transform="rotate(-10 28 20)" />
        <ellipse cx="45" cy="18" rx="3" ry="7" transform="rotate(-10 45 18)" /></g>
    case 'split': // round glass split in half: one half thicker
      return <g {...P}><rect x="10" y="13" width="18" height="14" rx="2" /><circle cx="40" cy="20" r="9" /><path d="M40 11v18" /><path d="M42 13a7 7 0 0 1 0 14" /></g>
    case 'sonda': // long thin probe ending in a tiny lens
      return <g {...P}><rect x="6" y="13" width="14" height="14" rx="2" /><path d="M20 18h28M20 22h28" /><path d="M48 17l4 1v4l-4 1z" /><circle cx="54" cy="20" r="1.2" /></g>
    case 'soft': // lens with glow rays
      return <g {...P}><rect x="10" y="13" width="20" height="14" rx="2" /><circle cx="40" cy="20" r="5" /><path d="M40 10v3M40 27v3M48 20h3M47 13l2-2M47 27l2 2" /></g>
    default: // fisheye: a bulging dome
      return <g {...P}><rect x="14" y="13" width="18" height="14" rx="2" /><path d="M32 10c14 0 14 20 0 20" /><path d="M36 14c6 2 6 10 0 12" /></g>
  }
}

/** Field of view: the wider the focal length, the wider the cone. */
function Focal({ id }: { id: string }) {
  const mm = Number(id)
  const meio = Math.max(2, Math.min(15, 220 / mm))
  return <g {...P}><circle cx="8" cy="20" r="2.2" /><path d={`M10 20L52 ${20 - meio}M10 20L52 ${20 + meio}`} />
    <path d={`M52 ${20 - meio}v${meio * 2}`} strokeDasharray="2 2" /></g>
}

/** The iris: the opening shrinks as the f-number grows. */
function Abertura({ id }: { id: string }) {
  const f = Number(id)
  const r = Math.max(2, 11 - f * 0.8)
  const laminas = Array.from({ length: 6 }, (_, i) => {
    const a = (i * Math.PI) / 3
    return `M${32 + 13 * Math.cos(a)} ${20 + 13 * Math.sin(a)}L${32 + r * Math.cos(a + 1.2)} ${20 + r * Math.sin(a + 1.2)}`
  })
  return <g {...P}><circle cx="32" cy="20" r="13" /><circle cx="32" cy="20" r={r} />{laminas.map((d) => <path key={d} d={d} />)}</g>
}

export function IconeCamera({ grupo, id }: { grupo: string; id: string }) {
  return (
    <svg viewBox="0 0 64 40" className="hf-icone-cam" aria-hidden>
      {grupo === 'camera' ? <Corpo id={id} /> : grupo === 'lente' ? <Lente id={id} />
        : grupo === 'focal' ? <Focal id={id} /> : <Abertura id={id} />}
    </svg>
  )
}
