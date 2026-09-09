# -*- coding: utf-8 -*-
"""
Aves do Brasil - skill Alexa (pt-BR)
Identifica aves por descricao falada e toca vocalizacoes do xeno-canto.

Motor: parser de fala livre -> pontuacao bayesiana sobre 390 especies
da regiao de Sao Paulo (GBIF >=20 registros), tracos AVONET (CC BY 4.0)
e cores HBW (CC0). Audios xeno-canto CC BY-NC-SA - USO NAO COMERCIAL.

Arquitetura v2: CatchAllIntent unico com AMAZON.SearchQuery +
roteamento interno no Lambda por classificacao de texto.
"""
import json, os, re, math, unicodedata, logging, random, datetime
import ask_sdk_core.utils as ask_utils
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_HERE = os.path.dirname(os.path.abspath(__file__))
# Dados divididos em 4 arquivos para caber no editor web da Alexa
AVES = []
for _fn in ["aves1.json", "aves2.json", "aves3.json", "aves4.json"]:
    _fp = os.path.join(_HERE, _fn)
    if os.path.exists(_fp):
        with open(_fp, encoding="utf-8") as _f:
            AVES.extend(json.load(_f))
if not AVES:
    # Fallback: arquivo único (para teste local)
    with open(os.path.join(_HERE, "aves.json"), encoding="utf-8") as _f:
        AVES = json.load(_f)

# Audio: Alexa-hosted usa pre-signed URLs para o bucket S3 privado.
# Os MP3 ficam em Media/aves/<Especie_nome>.mp3 no bucket da skill.
# O utils.py ja vem no template e expoe create_presigned_url().
_S3_IMPORT_ERROR = ""
try:
    from utils import create_presigned_url
    _HAS_S3 = True
    logger.info("S3 config: BUCKET=%s REGION=%s",
                os.environ.get('S3_PERSISTENCE_BUCKET', '<NOT SET>'),
                os.environ.get('S3_PERSISTENCE_REGION', '<NOT SET>'))
except Exception as _s3_err:
    _HAS_S3 = False
    _S3_IMPORT_ERROR = str(_s3_err)
    logger.error("Failed to import utils/create_presigned_url: %s", _s3_err)
    def create_presigned_url(s3_path):
        return None

# Mes atual (cache no nivel do modulo - ok para Lambda, reinicia periodicamente)
_MES_ATUAL = datetime.datetime.now().month

# ---------------------------------------------------------------- TTS censura
# Alexa censura algumas palavras na fala. Mapeamos para apelidos seguros.
APELIDOS_TTS = {
    "chupim": "vira-bosta",
}

def _nome_fala(m):
    """Retorna nome seguro para TTS (evita censura Alexa)."""
    return APELIDOS_TTS.get(m["pt"], m["pt"])

# ---------------------------------------------------------------- parser
def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

CORES = [("preto",0,["pret","escur","negr"]), ("branco",1,["branc"]),
    ("cinza",2,["cinz","pardacent"]),
    ("marrom",3,["marrom","pard","castanh","barrent","cafe"]),
    ("amarelo",4,["amarel","dourad"]), ("verde",5,["verd"]),
    ("azul",6,["azul","azuis","azulad"]),
    ("vermelho",7,["vermelh","laranj","alaranj","ruiv","avermelh","rux"])]
AMB = [("cidade ou quintal",0,["quintal","cidade","casa","jardim","rua","muro","fio","poste","varanda","telhad","urban","praca"]),
    ("parque arborizado",1,["parque","arboriz","pomar","chacar","sitio"]),
    ("mata",2,["mata","floresta","bosque","mato","arvored","serra","reserva"]),
    ("campo aberto",3,["campo","pasto","aberto","gramad","capim","plantac","lavour"]),
    ("beira d'agua",4,["lagoa","lago","brejo","beira d agua","beira da agua","na agua","rio","represa","riach","corrego","banhad"]),
    ("praia ou mar",5,["praia","mar ","no mar","costa","litoral","mangue"])]
POS = [("empoleirada",0,["galh","poleir","arvore","fio","cerca","empoleir","pousad","muro","antena","telhad","arbust"]),
    ("no chao",1,["chao","terra","grama","solo","andando","caminhand","ciscand","gramad"]),
    ("voando",2,["voand","voo","voava","planand","sobrevo","circuland","alcando voo"]),
    ("na agua",3,["nadand","mergulh","boiand","na agua"])]
TAM = [("do tamanho de um beija-flor",0,["beija-flor","beija flor","besouro","minusc","pequenin","dedo","polegar","abelh"]),
    ("do tamanho de um pardal",1,["pardal","pequen","canari","tico-tico","tico tico"]),
    ("do tamanho de um sabia",2,["sabia","bem-te-vi","bem te vi","medi","sanhac"]),
    ("do tamanho de uma pomba",3,["pomba","pombo","galinha pequena"]),
    ("do tamanho de um gaviao",4,["gaviao","grande","galinha"]),
    ("bem grande",5,["urubu","garca","muito grande","enorme","gigante","seriema","ema"])]
BICO = [("bico curto e grosso",0,["bico curt","bico gross","bico forte","bico conic","bico pequen"]),
    ("bico medio",1,["bico medi","bico normal"]),
    ("bico fino",2,["bico fin","bico alongad","bico delgad"]),
    ("bico muito longo",3,["bico muito long","bico enorme","bicao","bico grande","bico comprid"])]
CAUDA = [("cauda curta",0,["cauda curt","rabo curt","sem rabo","rabinh"]),
    ("cauda media",1,["cauda medi","rabo medi"]),
    ("cauda longa",2,["cauda long","rabo long","cauda compri","rabo compri"]),
    ("cauda muito longa",3,["cauda muito long","rabo muito long","rabo enorme"])]

def _achar(t, tabela):
    """Casa em fronteira de palavra; padrao mais longo vence (evita 'mar' em 'marrom')."""
    hits = []
    for nome, idx, pats in tabela:
        for pat in pats:
            for m in re.finditer(r"(?<![a-z])" + re.escape(pat), t):
                hits.append((m.start(), idx, nome, len(pat)))
    if not hits:
        return None
    hits.sort(key=lambda x: (-x[3], x[0]))
    return hits

def parse(frase):
    t = _norm(frase)
    out = {}
    c = _achar(t, CORES)
    if c:
        vistos = []
        for _, idx, nome, _l in c:
            if idx not in [v[0] for v in vistos]:
                vistos.append((idx, nome))
        out["cor"] = vistos[0]
        if len(vistos) > 1:
            out["cor2"] = vistos[1]
    for chave, tab in (("amb",AMB), ("pos",POS), ("bico",BICO), ("cauda",CAUDA), ("tam",TAM)):
        h = _achar(t, tab)
        if h:
            out[chave] = (h[0][1], h[0][2])
    return out

def ranquear(frase, k=3, extra_atrib=None):
    a = parse(frase)
    # Merge extra_atrib (from previous turns) — new parse overrides
    if extra_atrib:
        for key, val in extra_atrib.items():
            if key not in a:
                a[key] = val
    res = []
    for m in AVES:
        s = m["pr"]                                  # prior de abundancia (GBIF)
        if "cor"   in a: s += m["c"][a["cor"][0]]
        if "cor2"  in a: s += 0.6 * m["c"][a["cor2"][0]]
        if "amb"   in a: s += m["h"][a["amb"][0]]
        if "pos"   in a: s += m["p"][a["pos"][0]]
        if "tam"   in a: s += m["s"][a["tam"][0]]
        if "bico"  in a: s += m["b"][a["bico"][0]]
        if "cauda" in a: s += m["t"][a["cauda"][0]]
        # Feature 3: bonus de sazonalidade
        if m.get("meses"):
            saz = m["meses"][_MES_ATUAL - 1]
            s += 0.4 * math.log(saz / 0.083 + 0.01)
        res.append((s, m))
    res.sort(key=lambda x: -x[0])
    mx = res[0][0]
    tot = sum(math.exp(s - mx) for s, _ in res)
    return a, [(m, math.exp(s - mx) / tot) for s, m in res[:k]]

def _chaves(m):
    """Nome CBRO + apelidos regionais, normalizados e sem hifen."""
    ks = [m["pt"]] + (m.get("alt") or [])
    out = []
    for k in ks:
        k = _norm(k)
        out.append(k)
        out.append(k.replace("-", " "))
    return set(out)

def buscar_especie(nome):
    """Casa nome popular falado com a especie.

    A Alexa transcreve fala sem hifen ('bem te vi', 'joao de barro'), entao a
    comparacao ignora hifens e usa a lista de apelidos regionais.
    """
    n = _norm(nome).strip()
    if not n:
        return None
    n = re.sub(r"^(o |a |um |uma |do |da |de |os |as )+", "", n).strip()
    n = re.sub(r"\s+", " ", n.replace("-", " "))
    if not n:
        return None
    exatos = [m for m in AVES if n in _chaves(m)]
    if exatos:
        return max(exatos, key=lambda m: m["n"])
    # Contains match: score by length of matching key (longer = more specific = better)
    contem = []
    for m in AVES:
        best_score = 0
        for k in _chaves(m):
            if n in k:
                # query is substring of key — good (e.g. 'urutau' in 'urutau comum')
                best_score = max(best_score, len(n) * 2)
            elif k in n and len(k) > 3:
                # key is substring of query — only if key is long enough
                best_score = max(best_score, len(k))
        if best_score > 0:
            contem.append((best_score, m))
    if contem:
        contem.sort(key=lambda x: (-x[0], -x[1]["n"]))
        return contem[0][1]
    tokens = [x for x in n.split(" ") if len(x) > 3]
    if tokens:
        cand = [m for m in AVES if any(all(tk in k for tk in tokens) for k in _chaves(m))]
        if cand:
            return max(cand, key=lambda m: m["n"])
    return None

# ---------------------------------------------------------------- fala
def _audio_ssml(m):
    """Gera tag <audio> com pre-signed URL do S3 da skill."""
    if not m.get("a") or not _HAS_S3:
        logger.info("_audio_ssml: no audio metadata or no S3. a=%s _HAS_S3=%s", m.get("a"), _HAS_S3)
        return None, None
    s3_path = "Media/aves/{}.mp3".format(m["sci"].replace(" ", "_"))
    logger.info("_audio_ssml: attempting presigned URL for %s (bucket=%s, region=%s)",
                s3_path,
                os.environ.get('S3_PERSISTENCE_BUCKET', '<NOT SET>'),
                os.environ.get('S3_PERSISTENCE_REGION', '<NOT SET>'))
    try:
        url = create_presigned_url(s3_path)
        logger.info("_audio_ssml: got URL=%s", str(url)[:100] if url else "None")
    except Exception as e:
        logger.error("_audio_ssml: create_presigned_url failed for %s: %s", s3_path, e)
        return None, None
    if not url:
        logger.info("_audio_ssml: presigned URL is None for %s", s3_path)
        return None, None
    # SSML e XML: & na URL precisa virar &amp;
    url = url.replace("&", "&amp;")
    a = m["a"]
    cred = "Gravação de {}.".format(a.get("aut") or "autor não informado")
    return '<audio src="{}"/>'.format(url), cred

def _porte(g):
    """Classifica porte pela massa em gramas."""
    if g < 15:
        return "bem pequena"
    if g < 40:
        return "pequena"
    if g < 100:
        return "de porte médio"
    if g < 500:
        return "de porte médio a grande"
    if g < 2000:
        return "grande"
    return "bem grande"

def _dieta_natural(d):
    """Torna a dieta mais natural para fala."""
    if not d:
        return ""
    mapa = {
        "onivoro": "de tudo um pouco",
        "onívoro": "de tudo um pouco",
        "insetos": "principalmente insetos",
        "frutas": "principalmente frutas",
        "sementes": "principalmente sementes",
        "peixes": "principalmente peixes",
        "vegetais": "principalmente vegetais",
        "nectar": "néctar de flores",
        "néctar": "néctar de flores",
        "carniceiro": "carniça",
        "carnivoro": "pequenos animais",
        "carnívoro": "pequenos animais",
    }
    dl = d.lower().strip()
    return mapa.get(dl, d)

def descrever(m):
    nome = _nome_fala(m)
    g = int(m["g"])
    tom = m["tom"]
    viva = m.get("viva", "")
    if str(viva) in ("None", "nan", "null", ""):
        viva = ""
    amb = m["amb"]
    dieta = _dieta_natural(m.get("dieta", ""))
    variante = random.randint(0, 2)
    if variante == 0:
        txt = "O {} é uma ave {}".format(nome, tom)
        if viva:
            txt += ", com {}".format(viva)
        txt += ". <break time='300ms'/>"
        txt += "Pesa cerca de {} gramas e costuma viver em {}.".format(g, amb)
        if dieta:
            txt += " <break time='200ms'/>Se alimenta {}.".format(dieta)
    elif variante == 1:
        txt = "{}, uma ave {}".format(nome, tom)
        if viva:
            txt += " com {}".format(viva)
        txt += ", que pesa por volta de {} gramas.".format(g)
        txt += " <break time='300ms'/>Costuma frequentar {}.".format(amb)
        if dieta:
            txt += " Come {}.".format(dieta)
    else:
        txt = "Esse é o {}, ave {}".format(nome, tom)
        if viva:
            txt += " com detalhes em {}".format(viva)
        txt += ". <break time='300ms'/>"
        txt += "Com cerca de {} gramas, vive em {}.".format(g, amb)
        if dieta:
            txt += " <break time='200ms'/>Sua dieta inclui {}.".format(dieta)
    return txt

def _info_especie(m):
    """Retorna texto detalhado sobre a espécie para o InfoAveIntent."""
    nome = _nome_fala(m)
    sci = m["sci"]
    fam = m.get("fam", "não informada")
    g = int(m["g"])
    porte = _porte(g)
    amb = m["amb"]
    dieta = _dieta_natural(m.get("dieta", ""))
    variante = random.randint(0, 2)
    if variante == 0:
        txt = "O {}, cujo nome científico é {}, pertence à família {}.".format(nome, sci, fam)
        txt += " <break time='300ms'/>É uma ave {}, pesando cerca de {} gramas.".format(porte, g)
        txt += " <break time='300ms'/>Costuma frequentar {}.".format(amb)
        if dieta:
            txt += " Tem uma dieta variada, comendo {}.".format(dieta)
    elif variante == 1:
        txt = "Vamos falar do {}. <break time='200ms'/>".format(nome)
        txt += "Cientificamente conhecido como {}, da família {}.".format(sci, fam)
        txt += " <break time='300ms'/>É uma ave {}, com cerca de {} gramas.".format(porte, g)
        txt += " Vive em {}.".format(amb)
        if dieta:
            txt += " <break time='200ms'/>Na alimentação, come {}.".format(dieta)
    else:
        txt = "O {} é da família {}, ".format(nome, fam)
        txt += "e seu nome científico é {}. <break time='300ms'/>".format(sci)
        txt += "É uma ave {}, pesando por volta de {} gramas, ".format(porte, g)
        txt += "e gosta de ambientes como {}.".format(amb)
        if dieta:
            txt += " <break time='200ms'/>Se alimenta {}.".format(dieta)
    # Sazonalidade
    if m.get("meses"):
        saz = m["meses"][_MES_ATUAL - 1]
        media = sum(m["meses"]) / 12
        if media > 0 and saz / media > 1.3:
            txt += " <break time='300ms'/>É mais comum nessa época do ano."
        elif media > 0 and saz / media < 0.5:
            txt += " <break time='300ms'/>É menos comum nessa época do ano."
        else:
            txt += " <break time='300ms'/>É comum o ano todo por aqui."
    return txt

FALTA = {"cor": "de que cor ela era",
         "tam": "qual era mais ou menos o tamanho",
         "amb": "onde você estava quando viu",
         "pos": "se ela estava no chão, empoleirada ou voando"}

AVISO_PLAYBACK = "Lembre-se de usar gravações com moderação no campo."

# ---------------------------------------------------------------- aves de hoje (Feature 1)
def _aves_de_hoje():
    """Top 5 espécies mais prováveis para o mês atual, usando sazonalidade × abundância."""
    mes_idx = _MES_ATUAL - 1
    scored = []
    for m in AVES:
        if not m.get("meses"):
            continue
        saz = m["meses"][mes_idx]
        # score = sazonalidade * log(abundância)
        if m["n"] > 0:
            scored.append((saz * math.log(m["n"]), saz, m))
    scored.sort(key=lambda x: -x[0])
    top5 = scored[:5]

    # Detectar novidades sazonais: espécies onde o mês atual é top-3 para a espécie
    # E o mês anterior era significativamente menor (ratio > 2x)
    novidades = []
    mes_ant_idx = (mes_idx - 1) % 12
    for _, saz, m in scored[:20]:  # buscar entre top 20
        meses = m["meses"]
        sorted_meses = sorted(meses, reverse=True)
        if saz >= sorted_meses[2] if len(sorted_meses) >= 3 else True:
            anterior = meses[mes_ant_idx]
            if anterior > 0 and saz / anterior > 2.0:
                novidades.append(m)
            elif anterior == 0 and saz > 0.05:
                novidades.append(m)
        if len(novidades) >= 2:
            break

    return top5, novidades

# ---------------------------------------------------------------- helpers sessao
def _session_atrib_to_dict(val):
    """Converte atributo de sessão de volta para dict com tuplas onde necessário."""
    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            if isinstance(v, list) and len(v) == 2:
                out[k] = tuple(v)
            else:
                out[k] = v
        return out
    return val or {}

# ---------------------------------------------------------------- classificador de intencao
def _classificar_intencao(texto):
    """Classifica texto livre do CatchAllIntent em intencao interna."""
    t = _norm(texto)

    # SOBRE/FONTES/CONTATO — mais especificos primeiro
    if any(p in t for p in ['quem criou', 'quem fez', 'quem desenvolveu', 'sobre esta skill',
           'sobre o criador', 'quem e a evolutiva', 'contato do criador',
           'site do criador', 'e mail do criador']):
        return 'SOBRE'
    if any(p in t for p in ['de onde vem', 'fonte', 'fontes', 'banco de dados',
           'de onde sao as gravacoes', 'como voce sabe']):
        return 'FONTES'
    if any(p in t for p in ['contratar', 'skill personalizada', 'orcamento', 'chatbot',
           'quero ser cliente', 'me liga', 'me envie', 'skill para minha empresa',
           'automatizar meu negocio', 'falar com a evolutiva', 'entre em contato']):
        return 'CONTATO'

    # PERMISSAO/LOCALIZACAO — must be before QUIZ to prevent false match
    if any(p in t for p in ['acesso', 'localizacao', 'permissao', 'autorizo', 'autorizar',
           'permitir', 'habilitar', 'configuracoes', 'dou acesso']):
        return 'PERMISSAO'

    # QUIZ
    if any(p in t for p in ['quiz', 'adivinhar canto', 'jogar', 'teste meus conhecimentos',
           'acertar o canto', 'brincar de adivinhar', 'vamos jogar']):
        return 'QUIZ'
    if any(p in t for p in ['nao sei', 'nao faco ideia', 'passa', 'pular', 'desisto',
           'proximo', 'nenhuma ideia', 'nao conheco', 'nao tenho ideia']):
        return 'NAO_SEI'

    # AVES DE HOJE
    if any(p in t for p in ['aves posso ver', 'aves tem aqui', 'aves do mes', 'aparece agora',
           'passaros tem hoje', 'aves dessa epoca', 'aves comuns agora', 'aves migrantes',
           'aves novas', 'chegaram aves', 'ave nova', 'aves aparecem', 'aves posso']):
        return 'HOJE'

    # CURIOSIDADE — superlatives and general knowledge
    if any(p in t for p in ['maior ave', 'menor ave', 'mais pesada', 'mais leve',
           'mais colorida', 'mais rapida', 'mais comum', 'mais rara',
           'quantas especies', 'quantas aves', 'qual a mais', 'qual o mais',
           'a mais', 'o mais']):
        return 'CURIOSIDADE'

    # SOM/CANTO (must check before DESCREVER because 'canto do X' has bird-like words)
    if any(p in t for p in ['canto do', 'canto da', 'som do', 'som da', 'toca o canto',
           'toque o canto', 'quero ouvir o', 'quero ouvir a', 'como canta',
           'vocalizacao do', 'vocalizacao da']):
        return 'SOM'

    # OUVIR (context-dependent, no species name)
    if any(p in t for p in ['ouvir o canto', 'toca o canto', 'quero ouvir', 'toca o som',
           'deixa eu ouvir', 'toque']):
        return 'OUVIR'

    # INFO
    if any(p in t for p in ['me fala sobre', 'informacoes sobre', 'nome cientifico',
           'curiosidades sobre', 'detalhes do', 'detalhes da', 'sobre o ', 'sobre a ',
           'o que e o ', 'o que e a ', 'me conta sobre']):
        return 'INFO'

    # MAIS DETALHES
    if any(p in t for p in ['mais detalhes', 'me conta mais', 'fala mais', 'outras opcoes',
           'quais eram as outras', 'repete as opcoes', 'candidatas', 'quais as outras']):
        return 'DETALHES'

    # Default: try to describe/identify a bird
    return 'DESCREVER'


def _extrair_nome_especie(texto, intencao):
    """Extrai nome de espécie a partir do texto, baseado na intenção."""
    t = _norm(texto)

    if intencao == 'SOM':
        for prefix in ['toca o canto do ', 'toca o canto da ', 'toque o canto do ',
                        'toque o canto da ', 'quero ouvir o canto do ', 'quero ouvir o canto da ',
                        'quero ouvir o ', 'quero ouvir a ',
                        'como canta o ', 'como canta a ',
                        'vocalizacao do ', 'vocalizacao da ',
                        'qual e o canto do ', 'qual e o canto da ',
                        'qual o canto do ', 'qual o canto da ',
                        'qual e o som do ', 'qual e o som da ',
                        'qual o som do ', 'qual o som da ',
                        'canto do ', 'canto da ', 'som do ', 'som da ',
                        'tocar o som do ', 'tocar o som da ',
                        'como e a voz do ', 'como e a voz da ']:
            if prefix in t:
                nome = t.split(prefix, 1)[1].strip()
                if nome:
                    return nome
        # Fallback: return the whole text
        return texto

    if intencao == 'INFO':
        for prefix in ['me fala sobre o ', 'me fala sobre a ',
                        'informacoes sobre o ', 'informacoes sobre a ',
                        'qual o nome cientifico do ', 'qual o nome cientifico da ',
                        'curiosidades sobre o ', 'curiosidades sobre a ',
                        'detalhes do ', 'detalhes da ',
                        'sobre o ', 'sobre a ',
                        'o que e o ', 'o que e a ',
                        'me conta sobre o ', 'me conta sobre a ']:
            if prefix in t:
                nome = t.split(prefix, 1)[1].strip()
                if nome:
                    return nome
        return texto

    return texto


# ---------------------------------------------------------------- handlers

# Mapeamento CEP -> regiao para exemplo contextualizado na saudacao
# CEPs brasileiros: 2 primeiros digitos indicam a regiao
_CEP_REGIOES = {
    "01":"São Paulo","02":"São Paulo","03":"São Paulo","04":"São Paulo","05":"São Paulo",
    "06":"Grande SP","07":"Grande SP","08":"Grande SP","09":"Grande SP",
    "10":"Interior de SP","11":"Litoral de SP","12":"Vale do Paraíba","13":"Campinas",
    "14":"Ribeirão Preto","15":"Interior de SP","16":"Interior de SP","17":"Interior de SP",
    "18":"Interior de SP","19":"Interior de SP",
    "20":"Rio de Janeiro","21":"Rio de Janeiro","22":"Rio de Janeiro","23":"Rio de Janeiro",
    "24":"Niterói","25":"Grande Rio","26":"Grande Rio","27":"Interior do RJ","28":"Interior do RJ",
    "30":"Belo Horizonte","31":"Belo Horizonte","32":"Grande BH","33":"Grande BH",
    "34":"Grande BH","35":"Interior de MG","36":"Interior de MG","37":"Interior de MG",
    "38":"Interior de MG","39":"Interior de MG",
    "40":"Salvador","41":"Salvador","42":"Grande Salvador","43":"Interior da BA","44":"Interior da BA",
    "45":"Interior da BA","46":"Interior da BA","47":"Interior da BA","48":"Interior da BA","49":"Sergipe",
    "50":"Recife","51":"Recife","52":"Grande Recife","53":"Grande Recife",
    "54":"Interior de PE","55":"Interior de PE","56":"Interior de PE",
    "57":"Alagoas","58":"Paraíba","59":"Rio Grande do Norte",
    "60":"Fortaleza","61":"Fortaleza","62":"Interior do CE","63":"Interior do CE",
    "64":"Piauí","65":"Maranhão","66":"Belém","67":"Mato Grosso do Sul",
    "68":"Amapá e Amazônia","69":"Amazônia",
    "70":"Brasília","71":"Brasília","72":"Grande Brasília","73":"Goiás",
    "74":"Goiânia","75":"Goiás","76":"Goiás e Tocantins","77":"Tocantins",
    "78":"Mato Grosso","79":"Mato Grosso do Sul",
    "80":"Curitiba","81":"Curitiba","82":"Grande Curitiba","83":"Grande Curitiba",
    "84":"Interior do PR","85":"Interior do PR","86":"Interior do PR","87":"Interior do PR",
    "88":"Florianópolis e litoral de SC","89":"Interior de SC",
    "90":"Porto Alegre","91":"Porto Alegre","92":"Grande POA","93":"Grande POA",
    "94":"Grande POA","95":"Interior do RS","96":"Interior do RS","97":"Interior do RS",
    "98":"Interior do RS","99":"Interior do RS",
}

def _regiao_do_cep(cep):
    """Extrai a região a partir dos 2 primeiros dígitos do CEP."""
    if not cep:
        return None
    digitos = re.sub(r"\D", "", str(cep))
    if len(digitos) < 2:
        return None
    return _CEP_REGIOES.get(digitos[:2])

def _obter_cep(handler_input):
    """Tenta obter o CEP via Device Address API. Retorna None se sem permissão."""
    # Device Address API requer CustomSkillBuilder + apiAccessToken.
    # Por ora, retorna None — a skill funciona sem localização.
    # TODO: reativar quando a permissão estiver configurada.
    return None

# Exemplos regionalizados: ave comum + caracteristica marcante por regiao
_EXEMPLOS_REGIONAIS = {
    "default": "vi uma ave parda com peito amarelo, do tamanho de um sabiá, no quintal",
    "São Paulo": "vi uma ave parda com peito amarelo, do tamanho de um sabiá, no quintal",
    "Rio de Janeiro": "vi uma ave azul empoleirada num galho no parque",
    "Belo Horizonte": "vi uma ave preta grande voando sobre a cidade",
    "Brasília": "vi uma ave colorida no cerrado, do tamanho de um pardal",
    "Salvador": "vi uma ave branca grande na beira da lagoa",
    "Curitiba": "vi um passarinho verde pequeno no jardim",
    "Porto Alegre": "vi uma ave marrom no chão do parque, do tamanho de uma pomba",
}

def _exemplo_regional(regiao):
    if regiao:
        for k, v in _EXEMPLOS_REGIONAIS.items():
            if k in regiao:
                return v
    return _EXEMPLOS_REGIONAIS["default"]

class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)
    def handle(self, handler_input):
        cep = _obter_cep(handler_input)
        regiao = _regiao_do_cep(cep)
        attrs = handler_input.attributes_manager.session_attributes
        if regiao:
            attrs["regiao"] = regiao
        exemplo = _exemplo_regional(regiao)
        if regiao:
            fala = ("Bem-vindo ao Aves Brasil! Parece que você está em {}. "
                    "Descreva a ave que você viu: a cor, o tamanho e onde estava. "
                    "Por exemplo: {}.").format(regiao, exemplo)
        else:
            fala = ("Bem-vindo ao Aves Brasil. Descreva a ave que você viu: "
                    "a cor, o tamanho e onde estava. Por exemplo: {}. "
                    "Dica: se você autorizar o acesso à sua localização nas "
                    "configurações da skill, posso dar exemplos da sua região.").format(exemplo)
        return handler_input.response_builder.speak(fala).ask("Como era a ave que você viu?").response


# ================================================================
# Logica de cada "sub-handler" (chamada pelo CatchAllHandler)
# ================================================================

def _handle_descrever(handler_input, texto):
    """Logica de identificação de ave por descrição."""
    desc = texto
    if not desc.strip():
        return handler_input.response_builder.speak(
            "Não entendi a descrição. Me diga a cor, o tamanho e onde você viu a ave."
        ).ask("Como ela era?").response

    attrs = handler_input.attributes_manager.session_attributes

    # Merge com desc_parcial de turnos anteriores
    extra = _session_atrib_to_dict(attrs.get("desc_parcial"))

    atrib, top = ranquear(desc, k=3, extra_atrib=extra if extra else None)
    if not atrib and not extra:
        # Pode ser um nome de especie ao inves de descricao
        m = buscar_especie(desc)
        if m:
            attrs["ultima"] = m["sci"]
            fala = "Sobre o {}: {} Quer ouvir o canto ou saber mais?".format(
                _nome_fala(m), descrever(m))
            return handler_input.response_builder.speak(fala).ask("Quer ouvir o canto?").response
        return handler_input.response_builder.speak(
            "Não consegui identificar nenhuma característica. Tente dizer a cor, "
            "o tamanho e onde você a viu. Por exemplo: uma ave pequena azul na mata."
        ).ask("Como era a ave?").response

    # Merge: atrib (novo) + extra (anterior) — novo tem prioridade
    merged = dict(extra) if extra else {}
    merged.update(atrib)

    m1, p1 = top[0]
    attrs["cands"] = [x[0]["sci"] for x in top]
    attrs["ultima"] = m1["sci"]

    nome1 = _nome_fala(m1)

    if p1 > 0.55:
        fala = "Pelo que você descreveu, é bem provável que seja o {}. ".format(nome1)
        fala += descrever(m1) + " "
        attrs.pop("desc_parcial", None)
    elif p1 > 0.30:
        nome2 = _nome_fala(top[1][0])
        fala = "O mais provável é o {}. Mas também pode ser o {}".format(nome1, nome2)
        if len(top) > 2:
            nome3 = _nome_fala(top[2][0])
            fala += ", ou o {}".format(nome3)
        fala += ". "
        attrs.pop("desc_parcial", None)
    else:
        nomes_top = [_nome_fala(x[0]) for x in top]
        fala = "Não dá para ter certeza. As candidatas mais prováveis são: {}".format(
            ", ".join(nomes_top)) + ". "
        # Ask for the next missing attribute (not already in merged)
        faltando = [k for k in FALTA if k not in merged]
        if faltando:
            # Store merged for next turn
            # Convert tuples to lists for JSON serialization
            attrs["desc_parcial"] = {k: list(v) if isinstance(v, tuple) else v for k, v in merged.items()}
            fala += "Para melhorar o palpite, me diga {}.".format(FALTA[faltando[0]])
            return handler_input.response_builder.speak(fala).ask("Consegue me dizer?").response
        attrs.pop("desc_parcial", None)

    if m1.get("a") and _HAS_S3:
        fala += "Quer ouvir o {} dele?".format(m1["a"].get("tp") or "canto")
        return handler_input.response_builder.speak(fala).ask("Quer ouvir?").response
    fala += "Quer descrever outra ave?"
    return handler_input.response_builder.speak(fala).ask("Quer descrever outra ave?").response


def _handle_som(handler_input, texto):
    """Logica de tocar o canto de uma espécie nomeada."""
    nome = _extrair_nome_especie(texto, 'SOM')
    m = buscar_especie(nome)
    if not m:
        return handler_input.response_builder.speak(
            "Não encontrei essa ave na minha lista. Tente dizer o nome popular, "
            "como bem-te-vi, sabiá laranjeira ou joão de barro."
        ).ask("Qual ave você quer ouvir?").response
    handler_input.attributes_manager.session_attributes["ultima"] = m["sci"]
    nome_fala = _nome_fala(m)
    ssml, cred = _audio_ssml(m)
    # DEBUG: include diagnostic info in session attributes
    debug_info = {
        "has_a": bool(m.get("a")),
        "_HAS_S3": _HAS_S3,
        "bucket": os.environ.get("S3_PERSISTENCE_BUCKET", "<NOT SET>"),
        "region": os.environ.get("S3_PERSISTENCE_REGION", "<NOT SET>"),
        "s3_path": "Media/aves/{}.mp3".format(m["sci"].replace(" ", "_")),
        "ssml_result": ssml[:50] if ssml else "None",
        "s3_import_err": _S3_IMPORT_ERROR or "none",
    }
    handler_input.attributes_manager.session_attributes["_debug"] = debug_info
    if not ssml:
        return handler_input.response_builder.speak(
            "Ainda não tenho a gravação do {}. Mas posso te contar sobre ela: {} "
            "Quer tentar outra?".format(nome_fala, descrever(m))
        ).ask("Quer ouvir outra ave?").response
    tp = m["a"].get("tp") or "vocalização"
    fala = "{} do {}. {} {} Quer ouvir outra?".format(
        tp, nome_fala, ssml, cred)
    return handler_input.response_builder.speak(fala).ask("Quer ouvir outra ave?").response


def _handle_ouvir(handler_input):
    """Logica de ouvir canto (context-dependent, usa ultima especie)."""
    attrs = handler_input.attributes_manager.session_attributes
    sci = attrs.get("ultima")
    m = next((x for x in AVES if x["sci"] == sci), None)
    if not m:
        return handler_input.response_builder.speak(
            "Me diga qual ave você quer ouvir."
        ).ask("Qual ave?").response
    nome_fala = _nome_fala(m)
    ssml, cred = _audio_ssml(m)
    if not ssml:
        return handler_input.response_builder.speak(
            "Ainda não tenho a gravação do {}. Quer descrever outra ave?".format(nome_fala)
        ).ask("Quer descrever outra ave?").response
    tp = m["a"].get("tp") or "vocalização"
    fala = "{} do {}. {} {} Quer descrever outra ave?".format(
        tp, nome_fala, ssml, cred)
    return handler_input.response_builder.speak(fala).ask("Quer descrever outra ave?").response


def _handle_detalhes(handler_input):
    """Logica de mais detalhes sobre candidatas."""
    attrs = handler_input.attributes_manager.session_attributes
    scis = attrs.get("cands") or []
    if not scis:
        return handler_input.response_builder.speak(
            "Ainda não descrevemos nenhuma ave. Me conte como ela era."
        ).ask("Como era a ave?").response
    ms = [x for s in scis for x in AVES if x["sci"] == s]
    fala = " ".join(descrever(m) for m in ms) + " Quer ouvir o canto de alguma?"
    return handler_input.response_builder.speak(fala).ask("Quer ouvir o canto de alguma?").response


def _handle_hoje(handler_input):
    """Logica de aves de hoje/mes."""
    top5, novidades = _aves_de_hoje()
    if not top5:
        return handler_input.response_builder.speak(
            "Não tenho dados de sazonalidade suficientes. Quer identificar uma ave?"
        ).ask("Descreva a ave que você viu.").response

    nomes = [_nome_fala(item[2]) for item in top5]
    if len(nomes) >= 5:
        lista = ", ".join(nomes[:4]) + " e " + nomes[4]
    else:
        lista = ", ".join(nomes[:-1]) + " e " + nomes[-1] if len(nomes) > 1 else nomes[0]

    fala = "Neste mês, as aves mais comuns por aqui são: {}. Quer que eu descreva alguma?".format(lista)

    if novidades:
        nov = novidades[0]
        fala += " E uma novidade: o {} costuma aparecer nessa época!".format(_nome_fala(nov))

    # Guardar a primeira como última para permitir follow-up
    attrs = handler_input.attributes_manager.session_attributes
    attrs["ultima"] = top5[0][2]["sci"]
    attrs["cands"] = [item[2]["sci"] for item in top5[:3]]

    return handler_input.response_builder.speak(fala).ask("Quer que eu descreva alguma?").response


def _handle_quiz(handler_input):
    """Logica de iniciar quiz de cantos."""
    if not _HAS_S3:
        return handler_input.response_builder.speak(
            "O quiz de cantos ainda não está disponível. Quer identificar uma ave?"
        ).ask("Descreva a ave que você viu.").response

    # Filtrar espécies com audio e razoavelmente comuns
    candidatos = [m for m in AVES if m.get("a") and m["n"] >= 20]
    if not candidatos:
        return handler_input.response_builder.speak(
            "Não encontrei espécies suficientes para o quiz. Quer identificar uma ave?"
        ).ask("Descreva a ave que você viu.").response

    escolhida = random.choice(candidatos)
    ssml_audio, cred = _audio_ssml(escolhida)

    attrs = handler_input.attributes_manager.session_attributes
    attrs["quiz_resposta"] = escolhida["sci"]
    attrs["quiz_acertos"] = attrs.get("quiz_acertos", 0)
    attrs["quiz_total"] = attrs.get("quiz_total", 0)

    fala = "Escute esse canto. {} De que ave é esse canto? Diga o nome.".format(ssml_audio)
    return handler_input.response_builder.speak(fala).ask("De que ave é esse canto?").response


def _handle_nao_sei(handler_input):
    """Logica de 'não sei' — revela resposta do quiz ou mensagem genérica."""
    attrs = handler_input.attributes_manager.session_attributes
    sci_certo = attrs.get("quiz_resposta")
    if sci_certo:
        m_certo = next((x for x in AVES if x["sci"] == sci_certo), None)
        attrs["quiz_total"] = attrs.get("quiz_total", 0) + 1
        attrs.pop("quiz_resposta", None)
        if m_certo:
            nome_certo = _nome_fala(m_certo)
            fala = "A resposta era {}. {} Quer tentar outro?".format(nome_certo, descrever(m_certo))
        else:
            fala = "A resposta era uma ave que não encontrei nos dados. Quer tentar outro?"
        return handler_input.response_builder.speak(fala).ask("Quer tentar outro?").response
    # Fora do quiz
    return handler_input.response_builder.speak(
        "Tudo bem! Se quiser, descreva a ave que você viu ou peça um quiz de cantos."
    ).ask("O que você quer fazer?").response


def _handle_permissao(handler_input):
    """Logica de quando o usuário fala sobre permissão/localização."""
    fala = ("Para autorizar o acesso à localização, abra o aplicativo Alexa no celular, "
            "vá em Mais, depois Configurações, selecione esta skill e ative a permissão "
            "de CEP e país. Assim posso dar exemplos de aves da sua região. "
            "Enquanto isso, quer descrever uma ave ou ouvir um canto?")
    return handler_input.response_builder.speak(fala).ask(
        "Quer descrever uma ave?").response


def _handle_curiosidade(handler_input, texto):
    """Logica de curiosidades: maior, menor, mais pesada, etc."""
    t = _norm(texto)
    attrs = handler_input.attributes_manager.session_attributes

    if 'menor' in t or 'mais leve' in t:
        # Menor ave por peso
        validas = [a for a in AVES if a.get("g") and a["g"] > 0]
        validas.sort(key=lambda a: a["g"])
        m = validas[0] if validas else None
        if m:
            attrs["ultima"] = m["sci"]
            fala = ("A menor ave do Brasil que eu conheço é o {}, com apenas {:.0f} gramas. "
                    "{} Quer saber mais ou ouvir o canto?").format(
                _nome_fala(m), m["g"], descrever(m))
        else:
            fala = "Não tenho dados suficientes para responder. Quer descrever uma ave?"
        return handler_input.response_builder.speak(fala).ask("Quer ouvir o canto?").response

    if 'maior' in t or 'mais pesada' in t:
        validas = [a for a in AVES if a.get("g") and a["g"] > 0]
        validas.sort(key=lambda a: -a["g"])
        m = validas[0] if validas else None
        if m:
            attrs["ultima"] = m["sci"]
            fala = ("A maior ave do Brasil que eu conheço é o {}, com impressionantes {:.0f} gramas. "
                    "{} Quer saber mais ou ouvir o canto?").format(
                _nome_fala(m), m["g"], descrever(m))
        else:
            fala = "Não tenho dados suficientes para responder. Quer descrever uma ave?"
        return handler_input.response_builder.speak(fala).ask("Quer ouvir o canto?").response

    if 'mais comum' in t:
        validas = [a for a in AVES if a.get("n") and a["n"] > 0]
        validas.sort(key=lambda a: -a["n"])
        m = validas[0] if validas else None
        if m:
            attrs["ultima"] = m["sci"]
            fala = ("A ave mais registrada na minha base é o {}, com {} registros no GBIF. "
                    "{} Quer saber mais?").format(_nome_fala(m), m["n"], descrever(m))
        else:
            fala = "Não tenho dados suficientes. Quer descrever uma ave?"
        return handler_input.response_builder.speak(fala).ask("Quer saber mais?").response

    if 'quantas' in t:
        fala = ("Eu conheço {} espécies de aves do Brasil. "
                "Quer identificar alguma? Descreva a ave que você viu.").format(len(AVES))
        return handler_input.response_builder.speak(fala).ask(
            "Descreva a ave que você viu.").response

    # Fallback curiosidade genérica
    fala = ("Posso te dizer qual é a maior ou menor ave do Brasil, "
            "a mais comum, ou quantas espécies eu conheço. O que você quer saber?")
    return handler_input.response_builder.speak(fala).ask(
        "Quer saber a maior, a menor ou a mais comum?").response


def _handle_info(handler_input, texto):
    """Logica de informação sobre uma espécie nomeada."""
    nome = _extrair_nome_especie(texto, 'INFO')
    m = buscar_especie(nome)
    if not m:
        return handler_input.response_builder.speak(
            "Não encontrei essa ave na minha lista. Tente dizer o nome popular, "
            "como bem-te-vi, sabiá laranjeira ou joão de barro."
        ).ask("Sobre qual ave você quer saber?").response
    handler_input.attributes_manager.session_attributes["ultima"] = m["sci"]
    fala = _info_especie(m) + " Quer ouvir o canto ou saber sobre outra ave?"
    return handler_input.response_builder.speak(fala).ask("Quer ouvir o canto?").response


def _handle_sobre(handler_input):
    """Logica de quem criou a skill."""
    e = _EVOLUTIVA
    fala = (
        "O Aves Brasil foi criado por {criador}, fundador da {empresa}, "
        "com sede em {cidade}. "
        "A Evolutiva é uma agência de tecnologia e inteligência artificial "
        "que desenvolve soluções sob medida, incluindo skills para Alexa, "
        "chatbots, automações e sistemas com I.A. "
        "Se quiser sugerir melhorias para esta skill, reportar erros, "
        "ou solicitar uma skill personalizada para o seu negócio, "
        "mande um e-mail para {email}. "
        "Você também pode visitar nosso site: {site}. "
        "Quer voltar a identificar aves?"
    ).format(**e)
    return handler_input.response_builder.speak(fala).ask(
        "Quer descrever uma ave ou ouvir um canto?").response


def _handle_fontes(handler_input):
    """Logica de fontes dos dados."""
    fala = (
        "Os cantos vêm do xeno canto, uma biblioteca colaborativa com mais de "
        "um milhão de gravações de aves do mundo todo, mantida por voluntários. "
        "Cada gravação é creditada ao seu autor. "
        "A identificação usa dados do AVONET, um banco com informações de "
        "mais de onze mil espécies de aves, e do GBIF, que reúne registros "
        "de ocorrência de biodiversidade do mundo inteiro. "
        "Todos os dados são abertos e de acesso livre. "
        "Quer identificar uma ave ou ouvir um canto?"
    )
    return handler_input.response_builder.speak(fala).ask(
        "O que você quer fazer?").response


def _handle_contato(handler_input):
    """Logica de contato comercial."""
    e = _EVOLUTIVA
    fala = (
        "Que legal que você se interessou! "
        "A Evolutiva desenvolve skills para Alexa, chatbots, automações "
        "e sistemas com inteligência artificial, tudo sob medida para o seu negócio. "
        "Para solicitar um orçamento ou conversar sobre o seu projeto, "
        "mande um e-mail para {email}, "
        "ou acesse nosso site: {site}. "
        "O João Vitor, fundador da Evolutiva, vai te responder pessoalmente. "
        "Quer voltar a identificar aves?"
    ).format(**e)
    return handler_input.response_builder.speak(fala).ask(
        "Quer descrever uma ave?").response


_EVOLUTIVA = {
    "criador": "João Vitor Reis de Carvalho",
    "empresa": "Evolutiva Negócios Digitais",
    "cidade": "João Monlevade, Minas Gerais",
    "site": "evolutiva negócios digitais ponto com ponto b r",
    "site_url": "evolutivanegociosdigitais.com.br",
    "email": "jv arroba evolutiva negócios digitais ponto com ponto b r",
    "email_raw": "jv@evolutivanegociosdigitais.com.br",
}


# ================================================================
# CatchAllHandler — THE universal handler
# ================================================================

class CatchAllHandler(AbstractRequestHandler):
    """Handles CatchAllIntent: classifies text and routes to sub-handler."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("CatchAllIntent")(handler_input)
    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots or {}
        texto = (slots.get("texto").value if slots.get("texto") else "") or ""
        if not texto.strip():
            return handler_input.response_builder.speak(
                "Não entendi. Descreva a ave que você viu ou diga o que quer saber."
            ).ask("Como era a ave?").response

        intencao = _classificar_intencao(texto)
        logger.info("CatchAll texto=%s intencao=%s", texto, intencao)

        # Context-aware: if desc_parcial is active and the utterance looks like a
        # short answer (few words, no clear other intent), treat it as additional
        # description to merge with the partial description from the previous turn.
        attrs = handler_input.attributes_manager.session_attributes
        if (attrs.get("desc_parcial") and intencao == 'DESCREVER'
                and len(texto.split()) <= 5):
            # Short answer like "no chão", "verde", "pequena" — merge with previous
            logger.info("Short follow-up answer, merging with desc_parcial")
            return _handle_descrever(handler_input, texto)

        # Also: follow-up about the last bird mentioned (use session attribute "ultima")
        if attrs.get("ultima") and intencao in ('DESCREVER', 'INFO'):
            t = _norm(texto)
            # Check if asking about the last bird: "nome científico?", "quanto pesa?"
            follow_up_patterns = ['nome cientifico', 'quanto pesa', 'onde vive',
                                  'o que come', 'qual a familia', 'qual familia',
                                  'qual o peso', 'qual o tamanho']
            if any(p in t for p in follow_up_patterns):
                # Only if the text does NOT contain a species name (short question)
                nome_check = _extrair_nome_especie(texto, intencao)
                m_check = buscar_especie(nome_check) if nome_check != texto else None
                if not m_check:
                    sci = attrs["ultima"]
                    m = next((x for x in AVES if x["sci"] == sci), None)
                    if m:
                        fala = _info_especie(m) + " Quer ouvir o canto?"
                        return handler_input.response_builder.speak(fala).ask(
                            "Quer ouvir o canto?").response

        if intencao == 'SOBRE':
            return _handle_sobre(handler_input)
        elif intencao == 'FONTES':
            return _handle_fontes(handler_input)
        elif intencao == 'CONTATO':
            return _handle_contato(handler_input)
        elif intencao == 'PERMISSAO':
            return _handle_permissao(handler_input)
        elif intencao == 'QUIZ':
            return _handle_quiz(handler_input)
        elif intencao == 'NAO_SEI':
            return _handle_nao_sei(handler_input)
        elif intencao == 'HOJE':
            return _handle_hoje(handler_input)
        elif intencao == 'CURIOSIDADE':
            return _handle_curiosidade(handler_input, texto)
        elif intencao == 'SOM':
            return _handle_som(handler_input, texto)
        elif intencao == 'OUVIR':
            return _handle_ouvir(handler_input)
        elif intencao == 'INFO':
            return _handle_info(handler_input, texto)
        elif intencao == 'DETALHES':
            return _handle_detalhes(handler_input)
        else:  # DESCREVER
            return _handle_descrever(handler_input, texto)


# ================================================================
# Remaining handlers (not merged into CatchAll)
# ================================================================

def _id_resolvido(slot):
    """ID canonico que o slot LISTA_AVES resolveu (ex.: 'Pitangus_sulphuratus').

    Mais confiavel que casar o texto falado: a Alexa ja resolve sinonimos.
    """
    try:
        for r in slot.resolutions.resolutions_per_authority:
            if r.status.code.value == "ER_SUCCESS_MATCH":
                return r.values[0].value.id
    except Exception:
        pass
    return None


class OuvirHandler(AbstractRequestHandler):
    """Handles AMAZON.YesIntent — plays sound of last bird."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.YesIntent")(handler_input)
    def handle(self, handler_input):
        return _handle_ouvir(handler_input)


class QuizRespostaHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        if not ask_utils.is_intent_name("QuizRespostaIntent")(handler_input):
            return False
        attrs = handler_input.attributes_manager.session_attributes
        return bool(attrs.get("quiz_resposta"))
    def handle(self, handler_input):
        attrs = handler_input.attributes_manager.session_attributes
        sci_certo = attrs.get("quiz_resposta", "")
        m_certo = next((x for x in AVES if x["sci"] == sci_certo), None)

        slots = handler_input.request_envelope.request.intent.slots or {}
        slot = slots.get("resposta")
        nome_resp = (slot.value if slot else "") or ""

        # Tentar resolver pelo slot ou busca textual
        m_resp = None
        if slot is not None:
            sid = _id_resolvido(slot)
            if sid:
                sci = sid.replace("_", " ")
                m_resp = next((x for x in AVES if x["sci"] == sci), None)
        if m_resp is None:
            m_resp = buscar_especie(nome_resp)

        attrs["quiz_total"] = attrs.get("quiz_total", 0) + 1
        acertou = m_resp is not None and m_certo is not None and m_resp["sci"] == m_certo["sci"]

        nome_certo = _nome_fala(m_certo) if m_certo else "uma ave desconhecida"

        if acertou:
            attrs["quiz_acertos"] = attrs.get("quiz_acertos", 0) + 1
            desc = descrever(m_certo) if m_certo else ""
            fala = "Isso! É o {}! {} Quer tentar outro?".format(nome_certo, desc)
        else:
            desc = descrever(m_certo) if m_certo else ""
            fala = "Não era não. Esse é o canto do {}. {} Quer tentar outro?".format(nome_certo, desc)

        # Limpar a resposta do quiz para permitir novo round ou sair
        attrs.pop("quiz_resposta", None)

        return handler_input.response_builder.speak(fala).ask("Quer tentar outro?").response


class QuizRespostaFallbackHandler(AbstractRequestHandler):
    """Handles QuizRespostaIntent when no quiz is active — treat as species lookup."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("QuizRespostaIntent")(handler_input)
    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots or {}
        slot = slots.get("resposta")
        nome = (slot.value if slot else "") or ""
        m = None
        if slot is not None:
            sid = _id_resolvido(slot)
            if sid:
                sci = sid.replace("_", " ")
                m = next((x for x in AVES if x["sci"] == sci), None)
        if m is None:
            m = buscar_especie(nome)
        if not m:
            return handler_input.response_builder.speak(
                "Não tem nenhum quiz ativo. Quer começar um? Diga: quiz de cantos."
            ).ask("Quer jogar o quiz de cantos?").response
        handler_input.attributes_manager.session_attributes["ultima"] = m["sci"]
        nome_fala = _nome_fala(m)
        fala = "Sobre o {}: {} Quer saber mais ou ouvir o canto?".format(nome_fala, descrever(m))
        return handler_input.response_builder.speak(fala).ask("Quer ouvir o canto?").response


# ---------------------------------------------------------------- standard handlers
class HelpHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)
    def handle(self, handler_input):
        fala = ("Eu ajudo a identificar aves pela descrição. Diga por exemplo: "
                "vi uma ave parda com peito amarelo do tamanho de um sabiá no quintal. "
                "Você também pode pedir: qual é o canto do bem-te-vi. "
                "Ou diga: que aves posso ver hoje, para saber as aves do mês. "
                "E se quiser testar seus conhecimentos, diga: quiz de cantos. "
                "Para saber sobre uma espécie, diga: me fala sobre o tucano. "
                "E para saber quem criou esta skill ou de onde vêm os cantos, "
                "diga: quem criou esta skill. "
                "Eu conheço mais de 1.600 espécies de aves do Brasil.")
        return handler_input.response_builder.speak(fala).ask("Como era a ave que você viu?").response

class CancelStopHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input)
                or ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input)
                or ask_utils.is_intent_name("AMAZON.NoIntent")(handler_input))
    def handle(self, handler_input):
        attrs = handler_input.attributes_manager.session_attributes
        acertos = attrs.get("quiz_acertos", 0)
        total = attrs.get("quiz_total", 0)
        if total > 0:
            fala = "Você acertou {} de {}. Bons passarinhos!".format(acertos, total)
        else:
            fala = "Até a próxima. Bons passarinhos!"
        return handler_input.response_builder.speak(fala).set_should_end_session(True).response


# ---------------------------------------------------------------- Fallback contextual
class FallbackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)
    def handle(self, handler_input):
        attrs = handler_input.attributes_manager.session_attributes

        # Context: mid-description follow-up — try to parse the short answer as attributes
        if attrs.get("desc_parcial"):
            # The user might have said a short answer like "no chão", "verde", "pequena"
            # Try to extract attributes from whatever the Alexa captured
            # Since FallbackIntent has no slots, we attempt to use the raw input
            # Unfortunately FallbackIntent doesn't carry the text, so guide the user
            fala = ("Tente responder numa frase completa incluindo a descrição. "
                    "Por exemplo: era uma ave pequena preta no chão da lagoa. "
                    "Ou diga: começar de novo.")
            return handler_input.response_builder.speak(fala).ask(
                "Como era a ave?").response

        # Context: quiz active
        if attrs.get("quiz_resposta"):
            sci_certo = attrs["quiz_resposta"]
            m_certo = next((x for x in AVES if x["sci"] == sci_certo), None)
            attrs["quiz_total"] = attrs.get("quiz_total", 0) + 1
            attrs.pop("quiz_resposta", None)
            if m_certo:
                nome_certo = _nome_fala(m_certo)
                fala = "Não entendi. A resposta era {}. Quer tentar outro?".format(nome_certo)
            else:
                fala = "Não entendi. Quer tentar outro quiz?"
            return handler_input.response_builder.speak(fala).ask(
                "Quer tentar outro?").response

        # Context: has a recent bird
        if attrs.get("ultima"):
            fala = ("Não entendi. Quer ouvir o canto, descrever outra ave, "
                    "ou saber as aves do mês?")
            return handler_input.response_builder.speak(fala).ask(
                "O que você quer fazer?").response

        # Default
        return handler_input.response_builder.speak(
            "Não entendi. Descreva a ave que você viu, com a cor, o tamanho e o lugar."
        ).ask("Como era a ave?").response

class SessionEndedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)
    def handle(self, handler_input):
        return handler_input.response_builder.response

class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True
    def handle(self, handler_input, exception):
        logger.error(exception, exc_info=True)
        return handler_input.response_builder.speak(
            "Desculpe, tive um problema. Pode tentar de novo?"
        ).ask("Pode repetir?").response

sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(QuizRespostaHandler())  # Before CatchAll — takes priority when quiz active
sb.add_request_handler(QuizRespostaFallbackHandler())  # When no quiz, treat as species lookup
sb.add_request_handler(CatchAllHandler())  # THE universal handler for all free text
sb.add_request_handler(OuvirHandler())  # AMAZON.YesIntent
sb.add_request_handler(HelpHandler())
sb.add_request_handler(CancelStopHandler())
sb.add_request_handler(FallbackHandler())
sb.add_request_handler(SessionEndedHandler())
sb.add_exception_handler(CatchAllExceptionHandler())
lambda_handler = sb.lambda_handler()
