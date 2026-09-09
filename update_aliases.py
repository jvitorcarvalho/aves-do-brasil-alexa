import json

with open('lambda/aves.json', 'r', encoding='utf-8') as f:
    db = json.load(f)

sci_idx = {sp['sci']: i for i, sp in enumerate(db)}

aliases_to_add = {
    'Nyctibius griseus': ['urutau', 'urutau comum', 'urutau-comum'],
    'Nyctibius grandis': ['urutau gigante', 'urutau-gigante'],
    'Nyctibius aethereus': ['urutau pardo', 'urutau-pardo'],
    'Cyphorhinus arada': ['uirapuru', 'uirapuru verdadeiro', 'uirapuru-verdadeiro', 'musico'],
    'Nyctidromus albicollis': ['curiango', 'bacurau comum', 'bacurau-comum'],
    'Athene cunicularia': ['coruja buraqueira', 'coruja-buraqueira', 'coruja do campo'],
    'Bubo virginianus': ['corujao', 'coruja grande', 'jacurutu'],
    'Megascops choliba': ['corujinha do mato', 'corujinha-do-mato', 'caburezinho'],
    'Asio flammeus': ['coruja do banhado', 'mocho do banhado'],
    'Rupicola rupicola': ['galo da serra'],
    'Guira guira': ['anu branco', 'anu-branco', 'rabo de palha'],
    'Crotophaga major': ['anu grande', 'anu-grande', 'anu coroca'],
    'Paroaria dominicana': ['cardeal', 'cardeal do nordeste', 'galo de campina'],
    'Sporophila caerulescens': ['coleira', 'papa capim', 'papa-capim'],
    'Coereba flaveola': ['mariquita', 'cambacica amarela'],
    'Ramphastos toco': ['tucano', 'tucano toco', 'tucanucu', 'tucanaco', 'tucano grande'],
    'Ramphastos vitellinus': ['tucano de bico preto', 'tucano bico preto'],
    'Ara ararauna': ['arara caninde', 'arara azul e amarela', 'arara amarela'],
    'Ara chloropterus': ['arara vermelha grande', 'araracanga'],
    'Anodorhynchus hyacinthinus': ['arara azul', 'arara azul grande', 'arara jacinta'],
    'Jabiru mycteria': ['tuiuiu', 'jaburu grande'],
    'Mycteria americana': ['jabiru', 'cegonha'],
    'Harpia harpyja': ['harpia', 'gaviao real', 'gaviao de penacho', 'aguia real'],
    'Cariama cristata': ['sariema'],
    'Rhea americana': ['ema', 'ema americana', 'nhandu'],
    'Procnias nudicollis': ['ferreiro', 'araponga de barba'],
    'Antilophia galeata': ['soldadinho do araripe'],
    'Chiroxiphia caudata': ['tangara danca'],
    'Pionus maximiliani': ['maritaca', 'baitaca'],
    'Pionus menstruus': ['maritaca de cabeca azul', 'maitaca azul'],
    'Brotogeris chiriri': ['periquito de asa amarela', 'periquito chiriri'],
    'Myiopsitta monachus': ['periquito verde', 'catorra'],
    'Tyrannus savana': ['tesourinha', 'tesoura', 'tesoura do campo'],
    'Fluvicola nengeta': ['lavadeira branca', 'noivinha da agua'],
    'Volatinia jacarina': ['tiziu', 'tizio', 'saltador', 'serra serra'],
    'Saltator similis': ['trinca ferro', 'trinca-ferro', 'trinca ferro verdadeiro', 'tempera viola', 'pixarro'],
    'Cyanoloxia brissonii': ['azulao verdadeiro', 'azulao do nordeste'],
    'Sporophila nigricollis': ['cabecinha preta', 'coleiro baiano', 'papa arroz'],
    'Stilpnia cayana': ['saira amarela', 'saira'],
    'Tangara seledon': ['saira sete cores', 'saira-de-sete-cores', 'saira colorida'],
    'Dacnis cayana': ['sai azul', 'dacnis azul'],
    'Euphonia violacea': ['gaturamo', 'gaturamo verdadeiro', 'gaturamo bandeira'],
    'Megaceryle torquata': ['martim pescador grande', 'guarda rios'],
    'Trogon surrucura': ['surucua', 'surucua de peito azul', 'surucua variado'],
    'Baryphthengus ruficapillus': ['udu', 'juruva verde'],
    'Momotus momota': ['udu de coroa azul', 'udu azul', 'juruva azul'],
    'Psarocolius decumanus': ['japu', 'japuacu', 'japu guacu', 'japim grande'],
    'Cacicus haemorrhous': ['cacique', 'xexeu', 'japim'],
    'Molothrus bonariensis': ['maria preta', 'gauderio'],
    'Xolmis irupero': ['noivinha', 'noivinha branca', 'viuvinha branca'],
    'Pyrocephalus rubinus': ['principe', 'principe vermelho'],
    'Anhinga anhinga': ['carara', 'biguatinga', 'mergulhao cobra'],
    'Ardea alba': ['garca branca grande', 'garcao', 'garca real'],
    'Platalea ajaja': ['colhereiro', 'colhereiro rosa'],
    'Theristicus caudatus': ['curucaca'],
    'Butorides striata': ['soco mirim', 'garcinha verde'],
    'Nycticorax nycticorax': ['taquiri'],
    'Fregata magnificens': ['fragata', 'tesourao do mar'],
    'Piaya cayana': ['chincoa', 'peixe frito'],
    'Chlorostilbon lucidus': ['besourinho', 'besourinho bico vermelho', 'beija flor verde'],
    'Eupetomena macroura': ['beija flor grande', 'beija flor rabo de tesoura'],
    'Patagioenas picazuro': ['pomba do sertao', 'pombao cinza'],
    'Leptotila verreauxi': ['juriti gemedeira'],
    'Manacus manacus': ['tangarazinho', 'manaquim'],
    'Icterus cayanensis': ['corrupiao', 'sofre', 'xexeu de banana'],
    'Zonotrichia capensis': ['tico tico comum', 'tico tico verdadeiro'],
    'Columbina talpacoti': ['rolinha comum', 'pomba de sangue'],
    'Tyrannus melancholicus': ['suiriri comum', 'bem te vi cinza'],
    'Tachyphonus coronatus': ['tie sangue', 'tie preto verdadeiro'],
    'Pteroglossus aracari': ['aracari', 'aracari minhoca', 'tucano pequeno'],
    'Crax blumenbachii': ['mutum', 'mutum de bico vermelho', 'mutum do sudeste'],
    'Penelope obscura': ['jacu', 'jacu acu', 'jacuacu'],
    'Penelope superciliaris': ['jacu verdadeiro'],
    'Turdus leucomelas': ['sabia de barranco', 'sabia cinza'],
    'Turdus amaurochalinus': ['sabia cinzento'],
    'Mimus saturninus': ['arremedador', 'galo do campo'],
    'Thraupis sayaca': ['sanhaco azul'],
    'Ramphocelus carbo': ['pipira', 'pipira vermelha', 'tie fogo'],
    'Jacana jacana': ['cafezinho', 'asa de telha'],
    'Phalacrocorax brasilianus': ['corvo marinho'],
    'Coragyps atratus': ['urubu comum'],
    'Sarcoramphus papa': ['urubu colorido'],
}

added = 0
for sci, new_alts in aliases_to_add.items():
    if sci not in sci_idx:
        print(f'SKIP (not in DB): {sci}')
        continue
    idx = sci_idx[sci]
    existing = set(db[idx].get('alt', []))
    existing_norm = {a.lower().replace('-', ' ') for a in existing}
    for a in new_alts:
        if a.lower().replace('-', ' ') not in existing_norm:
            if 'alt' not in db[idx]:
                db[idx]['alt'] = []
            db[idx]['alt'].append(a)
            existing_norm.add(a.lower().replace('-', ' '))
            added += 1

with open('lambda/aves.json', 'w', encoding='utf-8') as f:
    json.dump(db, f, ensure_ascii=False, separators=(',', ':'))

print(f'Added {added} new aliases')
print(f'DB size: {len(db)} species')
sp = db[sci_idx['Nyctibius griseus']]
print(f"Nyctibius griseus alt: {sp['alt']}")
sp2 = db[sci_idx['Volatinia jacarina']]
print(f"Volatinia jacarina alt: {sp2['alt']}")
