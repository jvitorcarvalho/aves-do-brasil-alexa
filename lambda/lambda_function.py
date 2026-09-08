# -*- coding: utf-8 -*-
"""
Aves do Brasil - skill Alexa (pt-BR)
Identifica aves por descricao falada e toca vocalizacoes do xeno-canto.

Motor: parser de fala livre -> pontuacao bayesiana sobre 390 especies
da regiao de Sao Paulo (GBIF >=20 registros), tracos AVONET (CC BY 4.0)
e cores HBW (CC0). Audios xeno-canto CC BY-NC-SA - USO NAO COMERCIAL.
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
with open(os.path.join(_HERE, "aves.json"), encoding="utf-8") as _f:
    AVES = json.load(_f)

# Audio: Alexa-hosted usa pre-signed URLs para o bucket S3 privado.
# Os MP3 ficam em Media/aves/<Especie_nome>.mp3 no bucket da skill.
# O utils.py ja vem no template e expoe create_presigned_url().
try:
    from utils import create_presigned_url
    _HAS_S3 = True
except ImportError:
    _HAS_S3 = False
    def create_presigned_url(s3_path):
        return None

# Mes atual (cache no nivel do modulo - ok para Lambda, reinicia periodicamente)
_MES_ATUAL = datetime.datetime.now().month

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

def ranquear(frase, k=3):
    a = parse(frase)
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
    contem = [m for m in AVES if any(n in k or k in n for k in _chaves(m))]
    if contem:
        return max(contem, key=lambda m: m["n"])
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
        return None, None
    s3_path = "Media/aves/{}.mp3".format(m["sci"].replace(" ", "_"))
    url = create_presigned_url(s3_path)
    if not url:
        return None, None
    a = m["a"]
    cred = "Gravação de {}, xeno canto {}.".format(a.get("aut") or "autor não informado", a.get("xc") or "")
    return '<audio src="{}"/>'.format(url), cred

def descrever(m):
    p = ["{}, {}".format(m["pt"], m["tom"])]
    if m.get("viva"):
        p.append("com {}".format(m["viva"]))
    p.append("pesa cerca de {} gramas".format(int(m["g"])))
    p.append("vive em {}".format(m["amb"]))
    if m.get("dieta"):
        p.append("come {}".format(m["dieta"]))
    return ", ".join(p) + "."

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

# ---------------------------------------------------------------- handlers
class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)
    def handle(self, handler_input):
        fala = ("Bem-vindo ao Aves Brasil. Descreva a ave que você viu: "
                "a cor, o tamanho e onde estava. Por exemplo: vi uma ave parda "
                "com peito amarelo, do tamanho de um sabiá, no quintal.")
        return handler_input.response_builder.speak(fala).ask("Como era a ave que você viu?").response

class DescreverAveHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("DescreverAveIntent")(handler_input)
    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots or {}
        desc = (slots.get("descricao").value if slots.get("descricao") else "") or ""
        if not desc.strip():
            return handler_input.response_builder.speak(
                "Não entendi a descrição. Me diga a cor, o tamanho e onde você viu a ave."
            ).ask("Como ela era?").response

        atrib, top = ranquear(desc, k=3)
        if not atrib:
            return handler_input.response_builder.speak(
                "Não consegui identificar nenhuma característica. Tente dizer a cor, "
                "o tamanho e onde você a viu. Por exemplo: uma ave pequena azul na mata."
            ).ask("Como era a ave?").response

        m1, p1 = top[0]
        attrs = handler_input.attributes_manager.session_attributes
        attrs["cands"] = [x[0]["sci"] for x in top]
        attrs["ultima"] = m1["sci"]

        if p1 > 0.55:
            fala = "Pelo que você descreveu, é bem provável que seja o {}. ".format(m1["pt"])
            fala += descrever(m1) + " "
        elif p1 > 0.30:
            fala = "O mais provável é o {}. Mas também pode ser o {}".format(m1["pt"], top[1][0]["pt"])
            if len(top) > 2:
                fala += ", ou o {}".format(top[2][0]["pt"])
            fala += ". "
        else:
            fala = "Não dá para ter certeza. As candidatas mais prováveis são: {}".format(
                ", ".join(x[0]["pt"] for x in top)) + ". "
            faltando = [k for k in FALTA if k not in atrib]
            if faltando:
                fala += "Para melhorar o palpite, me diga {}.".format(FALTA[faltando[0]])
                return handler_input.response_builder.speak(fala).ask("Consegue me dizer?").response

        if m1.get("a") and _HAS_S3:
            fala += "Quer ouvir o {} dele?".format(m1["a"].get("tp") or "canto")
            return handler_input.response_builder.speak(fala).ask("Quer ouvir?").response
        fala += "Quer descrever outra ave?"
        return handler_input.response_builder.speak(fala).ask("Quer descrever outra ave?").response

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

class SomDaAveHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SomDaAveIntent")(handler_input)
    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots or {}
        slot = slots.get("especie")
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
                "Não encontrei essa ave na minha lista. Tente dizer o nome popular, "
                "como bem-te-vi, sabiá laranjeira ou joão de barro."
            ).ask("Qual ave você quer ouvir?").response
        handler_input.attributes_manager.session_attributes["ultima"] = m["sci"]
        ssml, cred = _audio_ssml(m)
        if not ssml:
            return handler_input.response_builder.speak(
                "Ainda não tenho a gravação do {}. Mas posso te contar sobre ela: {} "
                "Quer tentar outra?".format(m["pt"], descrever(m))
            ).ask("Quer ouvir outra ave?").response
        tp = m["a"].get("tp") or "vocalização"
        fala = "Esse é o {} do {}. {} {} {} Quer ouvir outra?".format(
            tp, m["pt"], ssml, cred, AVISO_PLAYBACK)
        return handler_input.response_builder.speak(fala).ask("Quer ouvir outra ave?").response

class OuvirHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (ask_utils.is_intent_name("OuvirIntent")(handler_input)
                or ask_utils.is_intent_name("AMAZON.YesIntent")(handler_input))
    def handle(self, handler_input):
        attrs = handler_input.attributes_manager.session_attributes
        sci = attrs.get("ultima")
        m = next((x for x in AVES if x["sci"] == sci), None)
        if not m:
            return handler_input.response_builder.speak(
                "Me diga qual ave você quer ouvir."
            ).ask("Qual ave?").response
        ssml, cred = _audio_ssml(m)
        if not ssml:
            return handler_input.response_builder.speak(
                "Ainda não tenho a gravação do {}. Quer descrever outra ave?".format(m["pt"])
            ).ask("Quer descrever outra ave?").response
        tp = m["a"].get("tp") or "vocalização"
        fala = "Esse é o {} do {}. {} {} {} Quer descrever outra ave?".format(
            tp, m["pt"], ssml, cred, AVISO_PLAYBACK)
        return handler_input.response_builder.speak(fala).ask("Quer descrever outra ave?").response

class MaisDetalhesHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("MaisDetalhesIntent")(handler_input)
    def handle(self, handler_input):
        attrs = handler_input.attributes_manager.session_attributes
        scis = attrs.get("cands") or []
        if not scis:
            return handler_input.response_builder.speak(
                "Ainda não descrevemos nenhuma ave. Me conte como ela era."
            ).ask("Como era a ave?").response
        ms = [x for s in scis for x in AVES if x["sci"] == s]
        fala = " ".join(descrever(m) for m in ms) + " Quer ouvir o canto de alguma?"
        return handler_input.response_builder.speak(fala).ask("Quer ouvir o canto de alguma?").response

# ---------------------------------------------------------------- Feature 1: Aves de Hoje
class AvesDeHojeHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AvesDeHojeIntent")(handler_input)
    def handle(self, handler_input):
        top5, novidades = _aves_de_hoje()
        if not top5:
            return handler_input.response_builder.speak(
                "Não tenho dados de sazonalidade suficientes. Quer identificar uma ave?"
            ).ask("Descreva a ave que você viu.").response

        nomes = [item[2]["pt"] for item in top5]
        if len(nomes) >= 5:
            lista = ", ".join(nomes[:4]) + " e " + nomes[4]
        else:
            lista = ", ".join(nomes[:-1]) + " e " + nomes[-1] if len(nomes) > 1 else nomes[0]

        fala = "Neste mês, as aves mais comuns por aqui são: {}. Quer que eu descreva alguma?".format(lista)

        if novidades:
            nov = novidades[0]
            fala += " E uma novidade: o {} costuma aparecer nessa época!".format(nov["pt"])

        # Guardar a primeira como última para permitir follow-up
        attrs = handler_input.attributes_manager.session_attributes
        attrs["ultima"] = top5[0][2]["sci"]
        attrs["cands"] = [item[2]["sci"] for item in top5[:3]]

        return handler_input.response_builder.speak(fala).ask("Quer que eu descreva alguma?").response

# ---------------------------------------------------------------- Feature 2: Quiz de Cantos
class QuizHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("QuizIntent")(handler_input)
    def handle(self, handler_input):
        if not _HAS_S3:
            return handler_input.response_builder.speak(
                "O quiz de cantos ainda não está disponível. Quer identificar uma ave?"
            ).ask("Descreva a ave que você viu.").response

        # Filtrar espécies com audio e razoavelmente comuns
        candidatos = [m for m in AVES if m.get("a") and m["n"] >= 1000]
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

        if acertou:
            attrs["quiz_acertos"] = attrs.get("quiz_acertos", 0) + 1
            desc = descrever(m_certo) if m_certo else ""
            fala = "Isso! É o {}! {} Quer tentar outro?".format(m_certo["pt"], desc)
        else:
            nome_certo = m_certo["pt"] if m_certo else "uma ave desconhecida"
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
        fala = "Sobre o {}: {} Quer saber mais ou ouvir o canto?".format(m["pt"], descrever(m))
        return handler_input.response_builder.speak(fala).ask("Quer ouvir o canto?").response

class HelpHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)
    def handle(self, handler_input):
        fala = ("Eu ajudo a identificar aves pela descrição. Diga por exemplo: "
                "vi uma ave parda com peito amarelo do tamanho de um sabiá no quintal. "
                "Você também pode pedir: qual é o canto do bem-te-vi. "
                "Ou diga: que aves posso ver hoje, para saber as aves do mês. "
                "E se quiser testar seus conhecimentos, diga: quiz de cantos. "
                "Eu conheço 390 espécies da região de São Paulo.")
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

class FallbackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)
    def handle(self, handler_input):
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
sb.add_request_handler(DescreverAveHandler())
sb.add_request_handler(AvesDeHojeHandler())
sb.add_request_handler(QuizHandler())
sb.add_request_handler(QuizRespostaHandler())  # Before SomDaAve — takes priority when quiz active
sb.add_request_handler(QuizRespostaFallbackHandler())  # When no quiz, treat as species lookup
sb.add_request_handler(SomDaAveHandler())
sb.add_request_handler(OuvirHandler())
sb.add_request_handler(MaisDetalhesHandler())
sb.add_request_handler(HelpHandler())
sb.add_request_handler(CancelStopHandler())
sb.add_request_handler(FallbackHandler())
sb.add_request_handler(SessionEndedHandler())
sb.add_exception_handler(CatchAllExceptionHandler())
lambda_handler = sb.lambda_handler()
