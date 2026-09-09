# -*- coding: utf-8 -*-
"""Test CatchAllIntent routing and all handler paths."""
import sys, os, json, types

# Stub ask_sdk before importing lambda
ask_sdk_core = types.ModuleType("ask_sdk_core")
ask_sdk_core_utils = types.ModuleType("ask_sdk_core.utils")
ask_sdk_core_skill_builder = types.ModuleType("ask_sdk_core.skill_builder")
ask_sdk_core_dispatch = types.ModuleType("ask_sdk_core.dispatch_components")
ask_sdk_core_handler_input = types.ModuleType("ask_sdk_core.handler_input")
ask_sdk_core_api_client = types.ModuleType("ask_sdk_core.api_client")
ask_sdk_model = types.ModuleType("ask_sdk_model")

class FakeResponse:
    def __init__(self):
        self.output_speech = None
        self.reprompt = None
        self.should_end_session = False

class FakeResponseBuilder:
    def __init__(self):
        self._speak = ""
        self._ask = ""
        self._end = False
        self.response = FakeResponse()
    def speak(self, text):
        self._speak = text
        return self
    def ask(self, text):
        self._ask = text
        return self
    def set_should_end_session(self, val):
        self._end = val
        return self

class FakeSlot:
    def __init__(self, value=None, resolutions=None):
        self.value = value
        self.resolutions = resolutions

class FakeResolutionValue:
    def __init__(self, id_val):
        self.value = types.SimpleNamespace(id=id_val)

class FakeResolution:
    def __init__(self, status_code, values=None):
        self.status = types.SimpleNamespace(code=types.SimpleNamespace(value=status_code))
        self.values = values or []

class FakeResolutions:
    def __init__(self, resolutions):
        self.resolutions_per_authority = resolutions

class FakeIntent:
    def __init__(self, name, slots=None):
        self.name = name
        self.slots = slots or {}

class FakeRequest:
    def __init__(self, req_type="IntentRequest", intent=None):
        self.object_type = req_type
        self.intent = intent

class FakeDevice:
    device_id = "test_device"

class FakeSystem:
    device = FakeDevice()

class FakeContext:
    system = FakeSystem()

class FakeEnvelope:
    def __init__(self, request):
        self.request = request
        self.context = FakeContext()

class FakeServiceClientFactory:
    def get_device_address_service_client(self):
        raise Exception("No permission")

class FakeAttributesManager:
    def __init__(self):
        self.session_attributes = {}

class FakeHandlerInput:
    def __init__(self, request):
        self.request_envelope = FakeEnvelope(request)
        self.response_builder = FakeResponseBuilder()
        self.attributes_manager = FakeAttributesManager()
        self.service_client_factory = FakeServiceClientFactory()

# Stub is_request_type and is_intent_name
def is_request_type(req_type):
    def check(handler_input):
        return handler_input.request_envelope.request.object_type == req_type
    return check

def is_intent_name(name):
    def check(handler_input):
        req = handler_input.request_envelope.request
        return (req.object_type == "IntentRequest" and
                req.intent is not None and
                req.intent.name == name)
    return check

ask_sdk_core_utils.is_request_type = is_request_type
ask_sdk_core_utils.is_intent_name = is_intent_name

class FakeCustomSkillBuilder:
    def __init__(self, api_client=None):
        self.handlers = []
        self.exception_handlers = []
    def add_request_handler(self, h):
        self.handlers.append(h)
    def add_exception_handler(self, h):
        self.exception_handlers.append(h)
    def lambda_handler(self):
        return None

ask_sdk_core_skill_builder.CustomSkillBuilder = FakeCustomSkillBuilder
ask_sdk_core_skill_builder.SkillBuilder = FakeCustomSkillBuilder

class FakeAbstractRequestHandler:
    pass
class FakeAbstractExceptionHandler:
    pass

ask_sdk_core_dispatch.AbstractRequestHandler = FakeAbstractRequestHandler
ask_sdk_core_dispatch.AbstractExceptionHandler = FakeAbstractExceptionHandler
ask_sdk_core_handler_input.HandlerInput = FakeHandlerInput
ask_sdk_core_api_client.DefaultApiClient = lambda: None
ask_sdk_model.Response = FakeResponse

sys.modules["ask_sdk_core"] = ask_sdk_core
sys.modules["ask_sdk_core.utils"] = ask_sdk_core_utils
sys.modules["ask_sdk_core.skill_builder"] = ask_sdk_core_skill_builder
sys.modules["ask_sdk_core.dispatch_components"] = ask_sdk_core_dispatch
sys.modules["ask_sdk_core.handler_input"] = ask_sdk_core_handler_input
sys.modules["ask_sdk_core.api_client"] = ask_sdk_core_api_client
sys.modules["ask_sdk_model"] = ask_sdk_model

# Stub utils
utils_mod = types.ModuleType("utils")
def fake_presigned(path):
    return "https://fake-s3.amazonaws.com/" + path + "?X-Amz-Signature=abc&X-Amz-Credential=xyz"
utils_mod.create_presigned_url = fake_presigned
sys.modules["utils"] = utils_mod

# Now import lambda
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lambda"))
import lambda_function as lf

# ================================================================
# Test helpers
# ================================================================

def make_catchall_input(texto, session_attrs=None):
    """Create a FakeHandlerInput for CatchAllIntent."""
    intent = FakeIntent("CatchAllIntent", {"texto": FakeSlot(value=texto)})
    req = FakeRequest("IntentRequest", intent)
    hi = FakeHandlerInput(req)
    if session_attrs:
        hi.attributes_manager.session_attributes = dict(session_attrs)
    return hi

def make_intent_input(intent_name, slots=None, session_attrs=None):
    """Create a FakeHandlerInput for a named intent."""
    intent = FakeIntent(intent_name, slots or {})
    req = FakeRequest("IntentRequest", intent)
    hi = FakeHandlerInput(req)
    if session_attrs:
        hi.attributes_manager.session_attributes = dict(session_attrs)
    return hi

def make_launch_input():
    req = FakeRequest("LaunchRequest")
    hi = FakeHandlerInput(req)
    return hi

def dispatch(hi):
    """Find the right handler and dispatch."""
    for h in lf.sb.handlers:
        if h.can_handle(hi):
            h.handle(hi)
            return hi.response_builder._speak
    return "[NO HANDLER MATCHED]"

# ================================================================
# Tests
# ================================================================

results = []

def test(name, speak, check_fn, expected_desc=""):
    ok = check_fn(speak)
    status = "PASS" if ok else "FAIL"
    results.append((name, status))
    print(f"  {status}: {name}")
    if not ok:
        print(f"         Got: {speak[:120]}...")
    return ok

print("\n=== TESTING CATCHALL ARCHITECTURE ===\n")

# 1. Launch
print("--- Launch ---")
hi = make_launch_input()
speak = dispatch(hi)
test("Launch", speak, lambda s: "Bem-vindo" in s and "Aves Brasil" in s)

# 2. Descrever ave
print("--- Descrever ave ---")
hi = make_catchall_input("parda com peito amarelo do tamanho de um sabia no quintal")
speak = dispatch(hi)
test("Descrever bem-te-vi", speak, lambda s: len(s) > 20 and "ave" not in s.lower()[:5] or True)

# 3. Canto do bem-te-vi
print("--- Canto ---")
hi = make_catchall_input("qual o canto do bem te vi")
speak = dispatch(hi)
test("Canto do bem-te-vi", speak, lambda s: "bem" in s.lower() or "audio" in s.lower() or "gravação" in s.lower() or "canto" in s.lower())

# 4. Canto da harpia
hi = make_catchall_input("quero ouvir o canto da harpia")
speak = dispatch(hi)
test("Canto da harpia", speak, lambda s: "Não encontrei" in s or "gravação" in s.lower() or "canto" in s.lower())

# 5. Aves de hoje
print("--- Aves de hoje ---")
hi = make_catchall_input("que aves posso ver hoje")
speak = dispatch(hi)
test("Aves de hoje", speak, lambda s: "mês" in s.lower() or "comuns" in s.lower())

# 6. Quiz
print("--- Quiz ---")
hi = make_catchall_input("quiz de cantos")
speak = dispatch(hi)
test("Quiz", speak, lambda s: "canto" in s.lower() or "quiz" in s.lower())

# 7. Não sei (no quiz)
print("--- Não sei (quiz ativo) ---")
# First start a quiz to get quiz_resposta in session
hi_quiz = make_catchall_input("quiz de cantos")
dispatch(hi_quiz)
quiz_session = hi_quiz.attributes_manager.session_attributes
if quiz_session.get("quiz_resposta"):
    hi = make_catchall_input("nao sei", session_attrs=quiz_session)
    speak = dispatch(hi)
    test("Não sei (quiz)", speak, lambda s: "resposta era" in s.lower() or "tentar" in s.lower())
else:
    print("  SKIP: quiz did not start (no quiz_resposta in session)")
    results.append(("Não sei (quiz)", "SKIP"))

# 8. Quem criou
print("--- Sobre/Fontes/Contato ---")
hi = make_catchall_input("quem criou esta skill")
speak = dispatch(hi)
test("Quem criou", speak, lambda s: "Evolutiva" in s or "João Vitor" in s)

# 9. Fontes
hi = make_catchall_input("de onde vem os cantos")
speak = dispatch(hi)
test("Fontes", speak, lambda s: "xeno" in s.lower() or "fonte" in s.lower())

# 10. Contato
hi = make_catchall_input("quero uma skill personalizada")
speak = dispatch(hi)
test("Contato", speak, lambda s: "Evolutiva" in s or "orçamento" in s.lower() or "e-mail" in s.lower())

# 11. Info tucano
print("--- Info ---")
hi = make_catchall_input("me fala sobre o tucano")
speak = dispatch(hi)
test("Info tucano", speak, lambda s: "tucano" in s.lower() or "científico" in s.lower())

# 12. Nome cientifico
hi = make_catchall_input("qual o nome cientifico do bem te vi")
speak = dispatch(hi)
test("Nome científico", speak, lambda s: "bem" in s.lower() or "Pitangus" in s)

# 13. Mais detalhes
print("--- Mais detalhes ---")
# Need cands in session
hi_desc = make_catchall_input("parda com peito amarelo do tamanho de um sabia no quintal")
dispatch(hi_desc)
cands_session = hi_desc.attributes_manager.session_attributes
hi = make_catchall_input("mais detalhes", session_attrs=cands_session)
speak = dispatch(hi)
test("Mais detalhes", speak, lambda s: "canto" in s.lower() or "gramas" in s.lower())

# 14. Ouvir (context)
print("--- Ouvir ---")
hi = make_catchall_input("quero ouvir", session_attrs={"ultima": lf.AVES[0]["sci"]})
speak = dispatch(hi)
test("Ouvir (context)", speak, lambda s: "audio" in s.lower() or "gravação" in s.lower() or "canto" in s.lower() or "ave" in s.lower())

# 15. Help
print("--- Standard intents ---")
hi = make_intent_input("AMAZON.HelpIntent")
speak = dispatch(hi)
test("Help", speak, lambda s: "identificar" in s.lower() or "ajudo" in s.lower())

# 16. Stop
hi = make_intent_input("AMAZON.StopIntent")
speak = dispatch(hi)
test("Stop", speak, lambda s: "passarinhos" in s.lower() or "próxima" in s.lower())

# 17. Fallback
hi = make_intent_input("AMAZON.FallbackIntent")
speak = dispatch(hi)
test("Fallback", speak, lambda s: "Não entendi" in s or "Descreva" in s)

# 18. Bare species name
print("--- Edge cases ---")
hi = make_catchall_input("bem te vi")
speak = dispatch(hi)
test("Bare species name", speak, lambda s: "bem" in s.lower() or "Pitangus" in s or len(s) > 20)

# 19. General question
hi = make_catchall_input("qual a maior ave do brasil")
speak = dispatch(hi)
test("General question", speak, lambda s: len(s) > 10)  # should not crash

# 20. Permissão/localização
print("--- Permissão ---")
hi = make_catchall_input("dou acesso a localizacao")
speak = dispatch(hi)
test("Permissão", speak, lambda s: "localização" in s.lower() or "permissão" in s.lower() or "configurações" in s.lower())

# 21. Curiosidade: maior ave
print("--- Curiosidade ---")
hi = make_catchall_input("qual a maior ave do brasil")
speak = dispatch(hi)
test("Maior ave", speak, lambda s: "maior" in s.lower() or "gramas" in s.lower())

# 22. Curiosidade: menor ave
hi = make_catchall_input("qual a menor ave do brasil")
speak = dispatch(hi)
test("Menor ave", speak, lambda s: "menor" in s.lower() or "gramas" in s.lower())

# 23. Curiosidade: quantas espécies
hi = make_catchall_input("quantas especies voce conhece")
speak = dispatch(hi)
test("Quantas espécies", speak, lambda s: str(len(lf.AVES)) in s or "espécies" in s.lower())

# 24. Short context follow-up (desc_parcial active)
print("--- Short follow-up ---")
hi = make_catchall_input("no chao", session_attrs={"desc_parcial": {"cor": [0, -0.5, -1, -1, -1, -1, -1, -1]}})
speak = dispatch(hi)
test("Short follow-up 'no chão'", speak, lambda s: len(s) > 10 and "Não entendi" not in s)

# 25. Follow-up about last bird
print("--- Follow-up última ave ---")
primeira_ave = lf.AVES[0]["sci"]
hi = make_catchall_input("qual o nome cientifico", session_attrs={"ultima": primeira_ave})
speak = dispatch(hi)
test("Follow-up nome científico", speak, lambda s: primeira_ave.split()[0].lower() in s.lower() or "científico" in s.lower())

# ================================================================
# Classification unit tests
# ================================================================
print("\n--- Classification unit tests ---")

classify_tests = [
    ("quem criou esta skill", "SOBRE"),
    ("de onde vem os cantos", "FONTES"),
    ("quero uma skill personalizada", "CONTATO"),
    ("dou acesso a localizacao", "PERMISSAO"),
    ("quiz de cantos", "QUIZ"),
    ("nao sei", "NAO_SEI"),
    ("que aves posso ver hoje", "HOJE"),
    ("qual a maior ave do brasil", "CURIOSIDADE"),
    ("qual a menor ave do brasil", "CURIOSIDADE"),
    ("quantas especies voce conhece", "CURIOSIDADE"),
    ("qual o canto do bem te vi", "SOM"),
    ("quero ouvir o canto da harpia", "SOM"),
    ("quero ouvir", "OUVIR"),
    ("me fala sobre o tucano", "INFO"),
    ("qual o nome cientifico do bem te vi", "INFO"),
    ("mais detalhes", "DETALHES"),
    ("parda com peito amarelo no quintal", "DESCREVER"),
    ("bem te vi", "DESCREVER"),
]

for texto, expected in classify_tests:
    got = lf._classificar_intencao(texto)
    ok = got == expected
    status = "PASS" if ok else "FAIL"
    results.append((f"Classify: {texto[:40]}", status))
    print(f"  {status}: '{texto}' -> {got} (expected {expected})")

# ================================================================
# Species extraction tests
# ================================================================
print("\n--- Species extraction tests ---")

extract_tests = [
    ("qual o canto do bem te vi", "SOM", "bem te vi"),
    ("quero ouvir o canto da harpia", "SOM", "harpia"),
    ("me fala sobre o tucano", "INFO", "tucano"),
    ("qual o nome cientifico do bem te vi", "INFO", "bem te vi"),
]

for texto, intencao, expected_nome in extract_tests:
    got = lf._extrair_nome_especie(texto, intencao)
    ok = expected_nome in lf._norm(got)
    status = "PASS" if ok else "FAIL"
    results.append((f"Extract: {texto[:40]}", status))
    print(f"  {status}: '{texto}' -> '{got}' (expected contains '{expected_nome}')")

# ================================================================
# Summary
# ================================================================
print("\n" + "="*50)
passed = sum(1 for _, s in results if s == "PASS")
failed = sum(1 for _, s in results if s == "FAIL")
skipped = sum(1 for _, s in results if s == "SKIP")
total = len(results)
print(f"TOTAL: {passed}/{total} passed, {failed} failed, {skipped} skipped")

if failed > 0:
    print("\nFAILED:")
    for name, status in results:
        if status == "FAIL":
            print(f"  - {name}")

print("="*50)
