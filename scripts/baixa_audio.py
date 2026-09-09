# -*- coding: utf-8 -*-
"""Baixa os audios do xeno-canto e converte para o formato da Alexa.
MP3 48 kbps / 22050 Hz / mono / <=60 s. Licenca CC BY-NC-SA (nao comercial).
"""
import json, os, subprocess, sys, time, urllib.request, urllib.error

BASE = r"D:/cofre/projetos/alexa-aves"
OUT  = os.path.join(BASE, "audio")
UA   = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
os.makedirs(OUT, exist_ok=True)

aves = json.load(open(os.path.join(BASE, "skill/lambda/aves.json"), encoding="utf-8"))
alvos = [(m["sci"].replace(" ", "_"), m["a"]["u"]) for m in aves if m.get("a") and m["a"].get("u")]
print("total:", len(alvos), flush=True)

ok = err = pulou = 0
for n, (sci, url) in enumerate(alvos, 1):
    dest = os.path.join(OUT, sci + ".mp3")
    if os.path.exists(dest) and os.path.getsize(dest) > 5000:
        pulou += 1; continue
    tmp = os.path.join(OUT, "_tmp.mp3")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=90).read()
        if len(data) < 5000:
            raise ValueError("arquivo muito pequeno: %d bytes" % len(data))
        open(tmp, "wb").write(data)
        r = subprocess.run(["ffmpeg","-loglevel","error","-y","-i",tmp,"-t","60",
                            "-ac","1","-ar","22050","-b:a","48k",
                            "-codec:a","libmp3lame","-write_xing","0",dest],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(dest):
            raise ValueError("ffmpeg falhou: " + r.stderr.decode()[:120])
        ok += 1
    except Exception as e:
        err += 1
        print("  FALHOU %s: %s" % (sci, e), flush=True)
        if os.path.exists(dest):
            os.remove(dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if n % 25 == 0:
        print("  ... %d/%d (ok=%d pulou=%d erro=%d)" % (n, len(alvos), ok, pulou, err), flush=True)
    time.sleep(0.4)   # xeno-canto pede uso comedido

print("FIM: ok=%d pulou=%d erro=%d de %d" % (ok, pulou, err, len(alvos)), flush=True)
tot = sum(os.path.getsize(os.path.join(OUT,f)) for f in os.listdir(OUT) if f.endswith(".mp3"))
print("arquivos: %d | total: %.1f MB" % (
    len([f for f in os.listdir(OUT) if f.endswith(".mp3")]), tot/1024/1024), flush=True)
