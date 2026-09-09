# 🐦 Aves BR — Skill Alexa de Identificação de Aves Brasileiras

[![pt-BR](https://img.shields.io/badge/idioma-pt--BR-green)](README.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Alexa Skill](https://img.shields.io/badge/Alexa-Skill-00CAFF?logo=amazon-alexa)](https://www.amazon.com.br/dp/B0XXXXXXXXXX)

Skill para Amazon Alexa que identifica aves brasileiras por descrição falada, toca cantos reais e testa seu conhecimento em um quiz interativo. Cobre **1.627 espécies** da avifauna do Brasil.

## ✨ O que a skill faz

| Feature | Comando de exemplo |
|---|---|
| 🔍 **Identificação por descrição** | *"Vi uma ave parda com peito amarelo no quintal"* |
| 🎵 **Cantos e vocalizações** | *"Qual o canto do urutau?"* |
| 🧠 **Quiz de cantos** | *"Quiz de cantos"* |
| 📚 **Curiosidades** | *"Qual a maior ave do Brasil?"* |
| 🗓️ **Aves do mês** | *"Que aves posso ver hoje?"* |
| ℹ️ **Informações sobre espécies** | *"Me fala sobre o tucano"* |

### Como funciona a identificação

O motor usa um **scorer bayesiano** que pontua 1.627 espécies com base em:
- **Cor** (tom dominante + cor viva)
- **Tamanho** (de beija-flor a ema)
- **Ambiente** (quintal, mata, lagoa, praia...)
- **Posição** (chão, empoleirada, voando, nadando)
- **Bico e cauda** (formato e comprimento)
- **Prior de abundância** (GBIF)

A skill responde com confiança proporcional: afirma quando tem certeza, lista candidatas quando não tem, e pede mais detalhes quando faltam atributos.

## 🏗️ Arquitetura

```
┌──────────────┐     ┌──────────────────────┐     ┌───────────┐
│  Alexa NLU   │────>│  CatchAllIntent      │────>│  Lambda   │
│  (pt-BR)     │     │  AMAZON.SearchQuery   │     │  Python   │
└──────────────┘     └──────────────────────┘     └─────┬─────┘
                                                        │
         ┌──────────────────────────────────────────────┘
         │
    ┌────▼────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
    │Classif. │    │  Scorer  │    │  S3      │    │  SSML   │
    │intencao │    │ Bayesiano│    │  Audio   │    │ <audio> │
    └─────────┘    └──────────┘    └──────────┘    └─────────┘
```

**Intent único inteligente**: em vez de N intents Alexa (que confundem a NLU em pt-BR), usamos um `CatchAllIntent` com `AMAZON.SearchQuery` e classificamos a intenção no Lambda com matching de padrões — zero confusão NLU, fácil de estender.

## 📂 Estrutura do repo

```
├── lambda/
│   ├── lambda_function.py   # Código principal (~1200 linhas)
│   ├── utils.py             # Pre-signed URLs S3 (Alexa-hosted)
│   ├── requirements.txt     # ask-sdk-core + urllib3<2
│   └── aves*.json           # Dados de 1.627 espécies
├── skill-package/
│   └── interactionModels/
│       └── custom/
│           └── pt-BR.json   # Modelo de interação Alexa
├── Media/
│   └── aves/                # MP3s de cantos (não commitados — ver abaixo)
└── scripts/
    └── baixa_audio.py       # Script para baixar áudios do xeno-canto
```

## 🔊 Áudios de cantos

Os MP3s de cantos (~730 arquivos, 122 MB) **não estão no repositório** por questão de tamanho.

**Fonte**: [xeno-canto](https://xeno-canto.org) — licença CC BY-NC-SA 4.0.

Para baixar os áudios para uso local:

```bash
python scripts/baixa_audio.py
```

O script lê os metadados de `aves*.json` (campo `a.xc`), baixa os MP3s do xeno-canto, converte para o formato Alexa (48 kbps, 22050 Hz, mono) e salva em `Media/aves/`.

**⚠️ Importante**: Os áudios do xeno-canto são licenciados como **CC BY-NC-SA 4.0** (uso não-comercial). A skill é gratuita e cumpre essa licença. Se você derivar um produto comercial, precisará de áudios de outra fonte.

## 🚀 Setup para desenvolvimento

### Pré-requisitos
- [ASK CLI](https://developer.amazon.com/en-US/docs/alexa/smapi/quick-start-alexa-skills-kit-command-line-interface.html) configurado
- Python 3.8+ (para testes locais)
- Conta de desenvolvedor Amazon

### Clonar e testar

```bash
# Clonar
git clone https://github.com/jvitorcarvalho/aves-do-brasil-alexa.git
cd aves-do-brasil-alexa

# Rodar testes locais (não precisa de ask-sdk instalado)
python test_catchall.py
```

### Deploy (Alexa-hosted)

A skill usa Alexa-hosted (Python), que provê Lambda + S3 grátis. O deploy é via git push para o CodeCommit da Amazon:

```bash
# Inicializar (primeira vez)
ask init --hosted-skill-id amzn1.ask.skill.SEU_SKILL_ID

# Desativar o pre-push hook (bug conhecido)
mv .git/hooks/pre-push .git/hooks/pre-push.disabled

# Deploy
git add -A && git commit -m "sua mensagem" && git push origin master
```

## 📊 Fontes de dados

| Fonte | Licença | Uso |
|---|---|---|
| [AVONET](https://doi.org/10.6084/m9.figshare.16586228) | CC BY 4.0 | Morfologia, ecologia |
| [Cores HBW](https://doi.org/10.5061/dryad.70rxwdc6s) | CC0 | 24 cores por prancha |
| [GBIF](https://www.gbif.org) | Aberta | Abundância, nomes populares |
| [xeno-canto](https://xeno-canto.org) | CC BY-NC-SA 4.0 | Áudios de cantos |

## 🧪 Testes

```bash
# Testes com stubs (sem ask-sdk necessário)
python test_catchall.py

# Resultado esperado: 47/47 passed
```

Os testes cobrem:
- Classificação de intenção (18 cenários)
- Extração de nomes de espécies (4 cenários)
- Todos os handlers: Launch, descrever, canto, quiz, info, curiosidade, permissão...
- Edge cases: nomes curtos, follow-up contextual, desc_parcial

## 🤝 Contribuindo

Contribuições são bem-vindas! Algumas ideias:

- [ ] Expandir aliases populares (campo `alt` no JSON)
- [ ] Melhorar SSML de nomes científicos
- [ ] Adicionar mais perguntas de curiosidade
- [ ] Protótipo web espelhando o motor de identificação
- [ ] Suporte a outros idiomas (en-US)

## 📜 Licença

O código-fonte está licenciado sob [MIT](LICENSE).

Os dados de espécies seguem suas respectivas licenças (CC BY 4.0, CC0).
Os áudios do xeno-canto são CC BY-NC-SA 4.0 — uso não-comercial apenas.

## 👤 Autor

**João Vitor Reis de Carvalho**
[Evolutiva Negócios Digitais](https://evolutivanegociosdigitais.com.br) — João Monlevade, MG

Skill de identificação de aves por voz, com dados de 1.627 espécies brasileiras.
