// Icones da barra lateral (traco, herdam a cor do item: cinza, ou lima no item ativo).
const D: Record<string, string> = {
  image: 'M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15 9.5a1.5 1.5 0 1 0 0-.01',
  edit: 'M12 4H5v15h15v-7M18.4 3.6a2 2 0 0 1 2.9 2.9L12 15.8 8 17l1.2-4z',
  video: 'M4 6h12v12H4zM16 10l5-3v10l-5-3',
  estudios: 'M5 4v16M12 4v16M19 4v16M3 8h4M10 15h4M17 10h4',
  lipsync: 'M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM5 11a7 7 0 0 0 14 0M12 18v3',
  music: 'M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  voice: 'M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2',
  genjutsu: 'M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5zM12 9v4',
  assets: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  advanced: 'M6 4h4v4H6zM14 16h4v4h-4zM6 16h4v4H6zM8 8v8M10 18h4M16 16V10a2 2 0 0 0-2-2h-4',
}

export default function IconeMenu({ nome }: { nome: string }) {
  return (
    <svg className="hf-lat-icone" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
      strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={D[nome] ?? D.image} />
    </svg>
  )
}
