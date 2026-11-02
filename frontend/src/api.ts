// Cliente da API do backend. Em dev o Vite faz proxy de /api e /ws.

export type Modelo = {
  id: string
  rotulo: string
  descricao: string
  steps?: number
  cfg?: number
  segundos_estimados: number
  motor?: string
  medido?: { mediana: number; amostras: number; minimo: number; maximo: number }
  qualidades?: string[]
  /** Falso nos modelos de CFG 1, onde o negativo é ignorado. */
  honra_negativo?: boolean
  /** So no modo Comfy Cloud: se este modelo roda la. */
  nuvem?: boolean
  referencia_personagem?: boolean
}

/** Modelo que roda no servidor do provedor, cobrado por imagem. */
export type ModeloNuvem = {
  id: string
  rotulo: string
  descricao: string
  /** "gemini" indexa o preco so por resolucao; "openai", por qualidade E tamanho. */
  familia: 'gemini' | 'openai'
  /** Familia gemini: 1K / 2K / 4K. */
  resolucoes?: string[]
  /** Familia openai: tamanhos em pixels, e os cinco niveis de qualidade. */
  tamanhos?: string[]
  /** Controles resumidos; a proporcao escolhe o tamanho real dentro do nivel. */
  niveis?: string[]
  tamanhos_por_nivel?: Record<string, Partial<Record<'quadrado' | 'retrato' | 'paisagem', string>>>
  qualidades?: string[]
  fundos?: { id: string; rotulo: string }[]
  /** gemini: {resolucao: preco}. openai: {qualidade: {tamanho: preco}}. */
  preco_usd: Record<string, number | Record<string, number>>
  max_referencias: number
  segundos_estimados: number
}

/** O gerador de video local (LTX 2.5). */
/** Um gerador local de video. Duracoes e tamanhos sao PROPRIOS de cada um:
    o MiniMax alinha os quadros de 17 em 17, o LTX nao. */
export type GeradorVideo = {
  id: string
  rotulo: string
  descricao: string
  fps: number
  /** Faixa continua; a interface mostra uma barra. */
  duracao_min: number
  duracao_max: number
  duracao_padrao: number
  /** So nos geradores locais. */
  tamanhos?: { id: string; largura: number; altura: number }[]
  tamanho_padrao?: string
  segundos_estimados: number
  /** Como o tempo cresce com a duracao: t = estimado * (d/5)^k. Ausente = 1
      (linear). So vem preenchido onde a curva foi MEDIDA. */
  expoente_duracao?: number
  /** So o MiniMax LOCAL tem: a chave liga a LoRA turbo E baixa os passos. */
  turbo?: { passos: number; passos_normal: number }

  /** Presente so no gerador por nuvem. Muda a forma dos controles: la o
      tamanho e proporcao + resolucao, nao pixels, e o custo e por TEMPO. */
  nuvem?: boolean
  tipo_tamanho?: 'pixels' | 'proporcao'
  proporcoes?: string[]
  proporcao_padrao?: string
  resolucoes?: string[]
  resolucao_padrao?: string
  usd_por_segundo_gpu?: number

  /** Quais modos ESTE gerador faz. O Wan nao faz texto puro; so ele faz
      referencias. Ate aqui todos faziam os mesmos tres. */
  modos: string[]
  /** So o Wan: variantes do modelo e preco por SEGUNDO de video gerado. */
  variantes?: { id: string; rotulo: string }[]
  variante_padrao?: string
  preco_por_segundo?: Record<string, Record<string, number>>
  /** So no Hailuo 03: as resolucoes MUDAM com a variante — a Padrao faz
      768P e 2K, a Max faz 480P e 768P. Nos outros geradores a lista e uma so. */
  resolucoes_por_variante?: Record<string, string[]>
  /** Formula do Hailuo MultiRef. A variante Padrao e exata; a Max retorna uma
      faixa porque a cobranca depende dos tokens das imagens. */
  preco_multiref?: Record<string, {
    usd_por_segundo?: Record<string, number>
    imagens_inclusas?: number
    usd_por_imagem_extra?: number
    usd_por_unidade?: number
    unidades_por_segundo?: Record<string, number>
    tokens_gratis?: number
    unidades_por_token_extra?: number
    tokens_min_por_imagem?: number
    tokens_max_por_imagem?: Record<string, number>
  }>
  max_referencias?: number
  /** Encadeamento de planos. A tela mostra a lista de planos porque o gerador
      DECLARA a capacidade, nao porque o id seja "planos": se outro gerador
      aprender a encadear, basta declara-la. */
  min_planos?: number
  max_planos?: number
  /** A estimativa deste gerador e POR PLANO; a tela multiplica. */
  segundos_por_plano?: number
  /** So o MiniMax ref2va aceita VIDEO como referencia; o teto vem do
      preset. Ausente nos demais, e a seção não aparece. */
  max_videos_referencia?: number
  /** So o MiniMax ref2va aceita arquivos de audio avulsos. */
  max_audios_referencia?: number
  /** LTXVReferenceAudio: uma amostra de voz, independente do modo visual. */
  max_audios_identidade?: number
  /** LTX 2.3: um arquivo que VIRA o som do video (fala ou musica). */
  max_audios_trilha?: number
  /** LoRA de camera lenta (so LTX 2.5): velocidades oferecidas, 1 = normal. */
  camera_lenta?: number[]
  modos_camera_lenta?: string[]
  forca_audio_referencia_padrao?: number
  /** MiniMax ref2va: qualidade/custo da codificacao das imagens de referencia. */
  tamanhos_referencia?: string[]
  tamanho_referencia_padrao?: string
  /** So o LTX MSR tem um quinto slot, separado, para o CENARIO. */
  tem_fundo_referencia?: boolean
  /** O que ESTE gerador aceita de verdade. Sem isto a tela mostrava os tres
      controles em todos, e dois nao chegavam ao grafo: a sugestao de prompt so
      existe no LTX, e o MiniMax por nuvem nao tem entrada de audio. */
  sugere_prompt?: boolean
  tem_audio?: boolean
  enriquece_prompt?: boolean
  /** So nos geradores LOCAIS: teto medido de pixels por quadro. */
  max_pixels?: number
  alinhamento?: number
}

export type ModeloVideo = {
  id: string
  fps: number
  /** `imagens` e o MINIMO exigido e `imagens_max` o teto. Nos modos de
      guia os dois coincidem (0, 1 ou 2); no de referencia nao — uma imagem
      basta, e o teto varia por gerador. Quando `imagens_max` falta, o teto
      e o proprio minimo. */
  modos: {
    id: string
    rotulo: string
    nota: string
    imagens: number
    imagens_max?: number
  }[]
  geradores: GeradorVideo[]
}

export type Imagem = { nome: string; subpasta: string; tipo: string }

export type ModoEdicao = {
  id: string
  rotulo: string
  descricao: string
  dica: string
  min_referencias: number
  max_referencias: number
  segundos_estimados: number
  /** Só o modo de controle traz os tipos de mapa (contorno, pose, …). */
  tipos?: { id: string; rotulo: string }[]
  /** Só o modo de ampliação. */
  metodos?: {
    id: string
    rotulo: string
    nota?: string
    segundos?: number
    /** Presente so nos metodos por nuvem: dolares por imagem. */
    custo_usd?: number
    /** Sobrepoe o limite do modo. O Magnific aceita a segunda imagem
        como referencia de luz; os outros metodos, nao. */
    max_referencias?: number
    estilos?: { id: string; rotulo: string }[]
  }[]
  escalas?: number[]
  vistas?: { id: string; rotulo: string; camera_documentada?: boolean }[]
  metodo_padrao?: string
  /** Grupo do menu a que este modo pertence. */
  grupo?: string
  /** Qual família de modelo este modo carrega na GPU. */
  motor?: string
  motor_por_metodo?: Record<string, string>
  /** Tempo real medido nesta máquina, quando há histórico bastante. */
  medido?: { mediana: number; amostras: number; minimo: number; maximo: number }
  /** Só o ajuste fino de rosto. */
  grupos?: {
    rotulo: string
    controles: { id: string; rotulo: string; min: number; max: number
                 passo: number; padrao: number; dica?: string }[]
  }[]
  /** Só "Girar a câmera" (Anygles): os três eixos, com faixa e passo vindos
      do preset. Ausente nas outras, e a seção não aparece. */
  camera?: { id: string; rotulo: string; min: number; max: number
             passo: number; padrao: number; unidade?: string; nota?: string }[]
  /** Só o modo de troca de personagem. */
  papeis?: string[]
  tem_destilado?: boolean
  /** Só a edição por instrução no Qwen. */
  resolucoes?: { id: string; rotulo: string; megapixels: number; nota: string; segundos: number }[]
  resolucao_padrao?: string
  prioridades?: { id: string; rotulo: string; nota: string; segundos: number }[]
  blocos?: { id: string; rotulo: string; padrao: boolean }[]
  temperaturas?: { id: string; rotulo: string }[]
  otimizacoes?: {
    id: string
    rotulo: string
    /** Ponto de partida dos controles. Só o criativo tem preset; o SeedVR2
        roda cru por escolha medida. */
    padroes: {
      criatividade: number
      semelhanca: number
      detalhe: number
      microcontraste: number
      granulacao: number
    }
  }[]
}

/** Uma referência já enviada ao motor, com a miniatura para mostrar na lista. */
export type Referencia = { nome: string; url: string }

/** Alturas da foto ja ocupadas, em unidades de bbox (0 a 1000). */
export type Zonas = { rostos: [number, number][]
                      letreiros: [number, number][] }

export type Tarefa = {
  id: string
  teste?: boolean
  rotulo_teste?: string | null
  estado: 'na_fila' | 'preparando' | 'executando' | 'pronto' | 'erro'
  progresso: number
  detalhe: string
  imagens: string[]
  erro: string
  // Nao bloqueia: a peca saiu, mas algo merece atencao — hoje,
  // contraste baixo do texto sobre a foto de fundo.
  aviso?: string
  modelo: string
  prompt: string
  prompt_final: string
  criada_em: number
  duracao: number
  iniciada_em?: number
  modelo_video?: string | null
  etapa_no?: string
  etapa_iniciada_em?: number
  ultimo_avanco_em?: number
  passo_atual?: number
  passos_total?: number
  largura: number
  altura: number
  /** Mapa de profundidade com quadros EXR (baixados em /api/profundidade/exr/<id>). */
  exr?: boolean
  /** Tirar o fundo: o arquivo e a mascara; /api/alpha/<id> devolve o video transparente. */
  alpha?: boolean
}

export type Andamento = {
  coletado_em: number | null
  motor_respondendo: boolean | null
  executando: number | null
  na_fila: number | null
  gpu: { vram_usada_gib: number; vram_total_gib: number; uso_pct: number } | null
  ram: { usada_gib: number; total_gib: number } | null
}

export type ItemGaleria = {
  teste?: number
  /** Rótulo legível, quando o id do modo não basta para identificar a imagem. */
  rotulo?: string | null
  id: number
  criada_em: number
  modelo: string
  prompt: string
  prompt_final: string
  arquivo: string
  subpasta: string
  parametros: Record<string, unknown>
  caption: Caption | null
  largura: number
  altura: number
  duracao: number
  bytes: number
  /** Segundos de video. 0 nas imagens — e o que distingue os dois. */
  duracao_video?: number
  fps?: number
  /** Dolares medidos pela diferenca de saldo. 0 nos modelos locais. */
  custo_usd?: number
}

export type Elemento = {
  tipo: 'text' | 'obj'
  bbox: [number, number, number, number]
  texto?: string
  desc: string
}

export type Caption = {
  aspect_ratio: string
  high_level_description: string
  compositional_deconstruction: { background: string; elements: unknown[] }
}

export type PedidoGeracao = {
  modelo: string
  prompt: string
  negativo?: string
  proporcao: string
  escala?: number
  /** So modelos que declaram `nativo_4k` (Flux 3): gera direto em ~8,3 MP. */
  nativo_4k?: boolean
  /** So o transformar_video: qual efeito do Creative Lab. */
  efeito_video?: string
  /** Trocar personagem: pose, profundidade ou contornos. */
  controle_troca?: string
  /** Seguir mapa de profundidade: o video ja e o mapa (passe Z). */
  mapa_pronto?: boolean
  formato_saida?: string
  /** Video, modo "chaves": numero do quadro de cada referencia, e a forca. */
  quadros_referencias?: number[]
  forca_chaves?: number
  /** Maquete: quadros-chave com o numero do quadro (de 1, a 24 fps). */
  chaves_video?: { imagem: string; quadro: number }[]
  /** Extracao de quadros da maquete nesses numeros de quadro. */
  quadros_extrair?: number[]
  /** < 1 liga a camera lenta no LTX 2.5. */
  velocidade_video?: number
  lote?: number
  seed?: number | null
  steps?: number | null
  cfg?: number | null
  qualidade?: string
  /** 1K/2K/4K nos do Google, ou o tamanho em pixels nos da OpenAI. */
  resolucao_nuvem?: string
  qualidade_nuvem?: string
  fundo_nuvem?: string
  // Video local.
  modo_video?: string
  duracao_video?: number
  com_audio?: boolean
  prompt_automatico?: boolean
  tamanho_video?: string
  /** 'ltx' ou 'minimax'. */
  modelo_video?: string
  /** Chave da LoRA turbo do MiniMax. */
  turbo?: boolean
  // So o gerador de nuvem usa estes dois.
  proporcao_video?: string
  resolucao_video?: string
  // So o Wan 3.0.
  variante_video?: string
  melhorar_prompt?: boolean
  // Ampliacao de video: 'ltx' (latente) ou 'seedvr' (pixels).
  metodo_video?: string
  resolucao_limpeza?: number
  // Especificos do metodo Magnific dentro do Reluz.
  estilo_luz?: string
  forca_luz?: number
  mudar_fundo_luz?: boolean
  caption?: Caption | null
  // Cor da tipografia quando ela e composta sobre uma foto enviada.
  tinta?: string | null
  // Quantas vezes repetir a MESMA edicao com seeds diferentes.
  variacoes?: number
  expandir_prompt?: boolean
  modo_expansao?: string
  estilo?: string
  estilo_manual?: string
  referencias?: string[]
  forca_referencia?: number
  posicoes_referencia?: string[]
  /** Videos de referencia, como "subpasta/arquivo" da GALERIA. Vem por
      caminho e nao por upload: o carregador le do disco. So o MiniMax
      ref2va aceita. */
  referencias_video?: string[]
  /** Audios avulsos enviados para a pasta input do motor. */
  referencias_audio?: string[]
  /** Um texto por plano, na ordem. So o gerador encadeado usa. */
  planos?: string[]
  forca_audio_referencia?: number
  tamanho_referencia?: string
  /** O quinto slot do MSR: uma imagem, e so o cenario. */
  fundo_referencia?: string | null
  forca_estilo?: number
  mascara_alvo?: string
  mascara_limiar?: number
  mascara_expandir?: number
  mascara_suavizar?: number
  tipo_controle?: string
  forca_controle?: number
  vista?: string
  azimute?: number
  elevacao?: number
  intensidade?: number
  temperatura?: string
  usar_mapa_luz?: boolean
  nivel_pele?: string
  blocos?: Record<string, boolean>
  prioridade?: string
  resolucao_edicao?: string
  metodo_angulo?: string
  metodo_luz?: string
  rosto?: Record<string, number>
  tipo_imagem?: string
  magnific_criatividade?: number
  magnific_hdr?: number
  magnific_semelhanca?: number
  magnific_fractalidade?: number
  metodo_ampliar?: string
  escala_ampliar?: number
  otimizacao?: string
  criatividade?: number
  semelhanca?: number
  microcontraste?: number
  granulacao?: number
  detalhe?: number
}

async function pedir<T>(caminho: string, opcoes?: RequestInit): Promise<T> {
  const r = await fetch(caminho, {
    headers: { 'Content-Type': 'application/json' },
    ...opcoes,
  })
  if (!r.ok) {
    const corpo = await r.text()
    throw new Error(corpo || `falha em ${caminho}`)
  }
  return r.json() as Promise<T>
}

export const api = {
  saude: () =>
    pedir<{ motor: boolean; na_fila: number; motor_carregado: string | null }>(
      '/api/saude',
    ),

  modelos: () =>
    pedir<{
      modelos: Modelo[]
      edicao: ModoEdicao[]
      grupos_edicao: { id: string; rotulo: string }[]
      modos_expansao: { id: string; rotulo: string; nota: string }[]
      proporcoes: string[]
      niveis_pele: { id: string; rotulo: string }[]
      tipos_imagem: { id: string; rotulo: string; nota: string }[]
      estilos: { id: string; rotulo: string; nota: string }[]
      nuvem: ModeloNuvem[]
      /** false quando falta a chave de API: a interface explica em vez de gerar. */
      nuvem_pronta: boolean
      proporcoes_nuvem: string[]
      video: ModeloVideo
      /** Ampliacao de um video da galeria: dois metodos, latente ou pixels. */
      /** LTX 2.5 Creative Lab (IC-LoRAs de video->video). null sem o segundo motor. */
      transformar_video: {
        id: string
        segundos_por_segundo: number
        max_segundos: number
        efeitos: { id: string; rotulo: string; nota: string; imagem_estilo?: boolean; quadros_chave?: boolean; max_segundos?: number; rotulo_imagem?: string | null; controles?: { id: string; rotulo: string }[]; imagem_opcional?: boolean; mapa_pronto?: boolean; formatos?: string[] }[]
      } | null
      ampliar_video: {
        id: string
        rotulo: string
        descricao: string
        segundos_estimados: number
        /** Teto do maior lado; a tela usa para calcular o alvo antes do clique. */
        maior_lado: number
        /** O latente do LTX so representa 8k+1 quadros e trunca o resto.
            A CONSTANTE vem do backend para a regra nao viver escrita a mao
            nos dois lados — lista duplicada ja divergiu neste projeto. */
        alinhamento_temporal?: number
        /** No espaco o no alinha a 32, e para cima. */
        alinhamento_espacial?: number
        metodos: { id: string; rotulo: string; nota: string; segundos: number }[]
      }
    }>('/api/modelos'),

  /** Envia uma imagem para a pasta de entrada do motor e devolve o nome gravado. */
  enviarReferencia: async (arquivo: File): Promise<Referencia> => {
    const corpo = new FormData()
    corpo.append('arquivo', arquivo)
    // Sem Content-Type manual: o navegador precisa pôr o boundary do multipart.
    const r = await fetch('/api/referencia', { method: 'POST', body: corpo })
    if (!r.ok) throw new Error((await r.text()) || 'falha ao enviar a imagem')
    const { nome } = (await r.json()) as { nome: string }
    return { nome, url: urlEntrada(nome) }
  },

  /** Envia um audio avulso para a pasta input do motor. */
  enviarAudio: async (arquivo: File): Promise<{ nome: string }> => {
    const corpo = new FormData()
    corpo.append('arquivo', arquivo)
    const r = await fetch('/api/referencia-audio', { method: 'POST', body: corpo })
    if (!r.ok) throw new Error((await r.text()) || 'falha ao enviar o áudio')
    return r.json() as Promise<{ nome: string }>
  },

  gerar: (p: PedidoGeracao) =>
    pedir<Tarefa>('/api/gerar', { method: 'POST', body: JSON.stringify(p) }),

  tarefas: () => pedir<Tarefa[]>('/api/tarefas'),

  /** Descarrega os modelos do motor. O backend recusa durante uma geracao. */
  liberarMemoria: () =>
    pedir<{ antes_gib: number | null; depois_gib: number | null;
            liberado_gib: number | null }>('/api/liberar-memoria', { method: 'POST' }),
  andamento: () => pedir<Andamento>('/api/andamento', { signal: AbortSignal.timeout(5000) }),

  /** Creditos restantes no ComfyUI. `ok: false` quando nao deu para perguntar
      — diferente de saldo zero, e a interface precisa distinguir os dois. */
  saldoNuvem: (forcar = false) =>
    pedir<{
      ok: boolean
      usd?: number
      pendente_usd?: number
      motivo?: string
      /** Gasto acumulado, somado do banco: sobrevive a reinicio. */
      gasto?: { imagens: number; usd: number }
    }>(
      `/api/nuvem/saldo${forcar ? '?forcar=true' : ''}`,
    ),

  cancelar: () => pedir<{ ok: boolean }>('/api/cancelar', { method: 'POST' }),
  desligar: () => pedir<{ ok: boolean; motores_fechados: boolean }>('/api/desligar', { method: 'POST' }),

  /** Roda so o encode->decode pelo VAE do LTX, para ver o que o latente perde
      NESTE video. Nao entra na fila nem na galeria: e conferencia, nao
      geracao. Leva poucos segundos porque usa uma janela de quadros. */
  previaLatente: (referencia: string) =>
    pedir<{
      antes: string
      depois: string
      tamanho: { largura: number; altura: number }
    }>('/api/video/previa-latente', {
      method: 'POST',
      body: JSON.stringify({ referencia }),
    }),

  expandir: (ideia: string) =>
    pedir<{ prompt: string }>('/api/prompt/expandir', {
      method: 'POST',
      body: JSON.stringify({ ideia }),
    }),

  // `fundo` e o nome da foto ja enviada. Com ele a sugestao sai desviando do
  // rosto, e as zonas ocupadas voltam para o editor marcar na tela.
  caption: (ideia: string, proporcao: string, fundo?: string) =>
    pedir<{ caption: Caption; zonas: Zonas }>('/api/ideogram/caption', {
      method: 'POST',
      body: JSON.stringify({ ideia, proporcao, fundo }),
    }),

  // Cinema Studio, Director mode: the scene rewritten as one film frame.
  cinemaDiretor: (cena: string, enquadramento: string, visual: string, seed = 0) =>
    pedir<{ prompt: string }>('/api/cinema/diretor', {
      method: 'POST',
      body: JSON.stringify({ cena, enquadramento, visual, seed }),
    }),

  /** Ajuste fino de rosto, fora da fila: são ~1s, dá para ver arrastando. */
  previaRosto: (referencia: string, rosto: Record<string, number>) =>
    pedir<{ nome: string; subpasta: string }>('/api/rosto/previa', {
      method: 'POST',
      body: JSON.stringify({
        modelo: 'rosto', prompt: '', proporcao: '1:1',
        referencias: [referencia], rosto,
      }),
    }),

  /** Roda só o pré-processador e devolve o mapa, para conferência. */
  previaControle: (referencia: string, tipo: string) =>
    pedir<{ nome: string; subpasta: string }>('/api/controle/previa', {
      method: 'POST',
      body: JSON.stringify({
        modelo: 'controle', prompt: 'x',
        proporcao: '1:1', referencias: [referencia], tipo_controle: tipo,
      }),
    }),

  galeria: (limite = 60, antes?: number, comTestes = false) =>
    pedir<ItemGaleria[]>(
      `/api/galeria?limite=${limite}${antes ? `&antes=${antes}` : ''}` +
      (comTestes ? '&com_testes=true' : ''),
    ),

  /** Quantas imagens de teste estão escondidas. */
  contarTestes: () =>
    pedir<{ testes: number; total: number }>('/api/galeria/testes'),

  apagar: (id: number) =>
    pedir<{ ok: boolean }>(`/api/galeria/${id}`, { method: 'DELETE' }),
}

/**
 * Sobe uma imagem já existente na galeria para a pasta de entrada do motor,
 * devolvendo-a como referência. É o caminho para encadear ações: o que saiu de
 * uma geração vira entrada da próxima.
 */
export async function referenciaDaGaleria(item: {
  arquivo: string
  subpasta: string
}): Promise<Referencia> {
  const r = await fetch(urlImagem({ nome: item.arquivo, subpasta: item.subpasta }))
  if (!r.ok) throw new Error('não consegui ler a imagem da galeria')
  const blob = await r.blob()
  return api.enviarReferencia(new File([blob], item.arquivo, { type: 'image/png' }))
}

/** Modos de edição que consomem a imagem enviada (e não geram do zero). */
export const MODOS_QUE_EDITAM =
  ['trocar', 'instrucao', 'estilo', 'controle', 'ampliar', 'angulo', 'reluz',
   'personagem']

/** Safe mode entra no endereco: ligar/desligar troca a URL, e o navegador nao reusa a versao do cache. */
export function marcaSeguro() {
  try { return localStorage.getItem('modo_seguro') === '0' ? '0' : '1' } catch { return '1' }
}

export function urlImagem(im: { nome: string; subpasta?: string }) {
  const p = new URLSearchParams({ nome: im.nome, subpasta: im.subpasta ?? '', s: marcaSeguro() })
  return `/api/imagem?${p}`
}

/** Imagem que está na pasta de entrada do motor (referências enviadas). */
export function urlEntrada(nome: string) {
  const p = new URLSearchParams({ nome, subpasta: '', tipo: 'input' })
  return `/api/imagem?${p}`
}

/** Versão reduzida e em cache, para a galeria não baixar megabytes por item. */
export function urlMiniatura(im: { nome: string; subpasta?: string }) {
  const p = new URLSearchParams({ nome: im.nome, subpasta: im.subpasta ?? '', s: marcaSeguro() })
  return `/api/miniatura?${p}`
}

/** Assina os eventos de tarefa emitidos pelo backend. */
export function ouvirTarefas(ao: (t: Tarefa) => void) {
  let sock: WebSocket | null = null
  let parado = false
  let tentativa: number | undefined

  const conectar = () => {
    if (parado) return
    const protocolo = location.protocol === 'https:' ? 'wss' : 'ws'
    sock = new WebSocket(`${protocolo}://${location.host}/ws`)
    sock.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.tipo === 'tarefa') ao(msg.dados as Tarefa)
    }
    // O backend pode reiniciar durante o desenvolvimento; reconecta sozinho.
    sock.onclose = () => {
      if (!parado) tentativa = window.setTimeout(conectar, 1500)
    }
    sock.onerror = () => sock?.close()
  }
  conectar()

  return () => {
    parado = true
    clearTimeout(tentativa)
    sock?.close()
  }
}
