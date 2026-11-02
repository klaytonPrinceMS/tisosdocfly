"""Pluggable image analysis: deterministic RGB baseline plus model registry.

Camada de IA do núcleo. O repositório **não** traz modelo treinado, então a
análise padrão é um baseline determinístico por imagem (métricas RGB, índices
de vegetação e densidade de borda). Um modelo real (ONNX/Torch) pode ser
registrado em tempo de execução e passa a ter prioridade — a interface é a
mesma e o resultado sempre passa por revisão humana.

Contrato de retorno de `analisar_imagem`:

    {"modelo": str, "versao": str, "confianca": float,
     "resumo": str, "metricas": dict,
     "ocorrencias": [{"classe", "severidade", "confianca", "area_m2",
                      "evidencia"}],
     "revisao_humana_obrigatoria": bool}

Nenhuma função levanta exceção: falha vira resultado vazio + log. O baseline
não afirma o que não pode provar — em segurança pública ele **não** detecta
pessoas, veículos ou armas sem detector homologado.
"""
import os
import threading

import numpy as np
from PIL import Image

from mod_skyrover import avaliacao_imagens, geoprocessamento

_MODULO_LOG = "skyrover"
SEVERIDADES = ("baixa", "media", "alta", "indeterminada")
MODULOS_BASELINE = (
    "agro", "vistoria_predial", "ambiental", "obras", "mapeamento",
    "seguranca", "defesa_civil", "inspecao_industrial", "eventos",
    "generico",
)

_LIMITE_CONFIANCA_MIN = 0.30
_LIMITE_CONFIANCA_MAX = 0.92

# Registro global: nome -> {"nome", "versao", "funcao"}. O lock protege
# registro/leitura concorrente (o servidor NiceGUI atende em threads).
_modelos = {}
_lock = threading.RLock()
_modelos_ambiente_tentados = set()


def _log():
    """Logger loguru do núcleo; nunca falha por causa da observabilidade."""
    try:
        from mod_skyrover import observabilidade
        return observabilidade.get_logger(_MODULO_LOG)
    except Exception:
        from loguru import logger
        return logger


def _erro(contexto, exc):
    """Registra a causa sem derrubar o chamador."""
    try:
        _log().exception(f"ia.{contexto}: {exc}")
    except Exception:
        pass


# =============================================================================
# Registro de modelos
# =============================================================================

def registrar_modelo(nome, versao, funcao):
    """Registers (or replaces) an analysis model; returns True on success.

    `funcao` deve ter a assinatura `funcao(caminho, contexto) -> dict` e
    devolver (ao menos parcialmente) o contrato de `analisar_imagem`. O nome
    é normalizado para minúsculas sem espaços; o mesmo nome do módulo
    (`agro`, `seguranca`, ...) faz o modelo substituir o baseline daquele
    módulo. Registrar de novo com o mesmo nome substitui a versão anterior —
    é assim que um modelo homologado entra no lugar do anterior.
    """
    try:
        chave = _normalizar_nome(nome)
        if not chave or not callable(funcao):
            return False
        with _lock:
            _modelos[chave] = {
                "nome": chave,
                "versao": str(versao or "sem-versao"),
                "funcao": funcao,
            }
        return True
    except Exception as exc:
        _erro(f"registrar_modelo('{nome}')", exc)
        return False


def obter_modelo(nome):
    """Returns a copy of the registered model dict (or None)."""
    try:
        chave = _normalizar_nome(nome)
        with _lock:
            modelo = _modelos.get(chave)
            return dict(modelo) if modelo else None
    except Exception as exc:
        _erro(f"obter_modelo('{nome}')", exc)
        return None


def modelos_disponiveis():
    """Lists registered models as `[{"nome": ..., "versao": ...}]`."""
    try:
        with _lock:
            return [{"nome": m["nome"], "versao": m["versao"]}
                    for m in _modelos.values()]
    except Exception as exc:
        _erro("modelos_disponiveis", exc)
        return []


def remover_modelo(nome):
    """Unregisters a model (usado em teste/rollback); returns True if removed."""
    try:
        chave = _normalizar_nome(nome)
        with _lock:
            return _modelos.pop(chave, None) is not None
    except Exception as exc:
        _erro(f"remover_modelo('{nome}')", exc)
        return False


def _normalizar_nome(nome):
    """Normalizes a model name to lowercase without spaces/dashes."""
    try:
        base = str(nome or "").strip().lower()
        for caractere in (" ", "-", "/", "\\"):
            base = base.replace(caractere, "_")
        return base.strip("_")
    except Exception:
        return ""


# =============================================================================
# Normalização do resultado
# =============================================================================

def _limitar(valor, minimo=0.0, maximo=1.0, padrao=0.0):
    """Clamps a numeric value to `[minimo, maximo]`."""
    try:
        numero = float(valor)
        if numero != numero:  # NaN
            return padrao
        return float(min(maximo, max(minimo, numero)))
    except (TypeError, ValueError):
        return padrao


def _ocorrencia(classe, severidade, confianca, area_m2, evidencia):
    """Builds one occurrence dict with the exact contract fields."""
    try:
        severidade = str(severidade or "indeterminada").strip().lower()
        if severidade not in SEVERIDADES:
            severidade = "indeterminada"
        return {
            "classe": str(classe or "indeterminado").strip()[:80],
            "severidade": severidade,
            "confianca": round(_limitar(confianca), 4),
            "area_m2": round(max(0.0, _limitar_area(area_m2)), 2),
            "evidencia": str(evidencia or "")[:500],
        }
    except Exception as exc:
        _erro("_ocorrencia", exc)
        return None


def _limitar_area(valor):
    """Converts an area to a non-negative float (0.0 when unknown)."""
    try:
        numero = float(valor)
        if numero != numero or numero < 0:
            return 0.0
        return numero
    except (TypeError, ValueError):
        return 0.0


def _resultado_vazio(modelo="avaliacao-pura-v1", versao="1.0"):
    """Empty-but-valid analysis result (used for failure and no-model cases)."""
    return {
        "modelo": str(modelo),
        "versao": str(versao),
        "confianca": 0.0,
        "resumo": "",
        "metricas": {},
        "ocorrencias": [],
        "revisao_humana_obrigatoria": True,
    }


def _normalizar_resultado(resultado, modelo, versao, metricas=None,
                          revisao_padrao=True):
    """Forces any model/baseline output into the public contract.

    Preenche campo ausente, limita confianças e áreas, descarta ocorrência
    sem classe e garante que `revisao_humana_obrigatoria` seja booleano.
    """
    base = _resultado_vazio(modelo, versao)
    try:
        if not isinstance(resultado, dict):
            return base
        base["modelo"] = str(resultado.get("modelo") or modelo)
        base["versao"] = str(resultado.get("versao") or versao)
        base["confianca"] = round(_limitar(resultado.get("confianca")), 4)
        base["resumo"] = str(resultado.get("resumo") or "")
        metricas_final = resultado.get("metricas")
        if not isinstance(metricas_final, dict):
            metricas_final = metricas if isinstance(metricas, dict) else {}
        base["metricas"] = dict(metricas_final)
        ocorrencias = []
        for item in (resultado.get("ocorrencias") or []):
            if not isinstance(item, dict):
                continue
            if not str(item.get("classe") or "").strip():
                continue
            normalizada = _ocorrencia(
                item.get("classe"), item.get("severidade"),
                item.get("confianca"), item.get("area_m2"),
                item.get("evidencia"))
            if normalizada:
                ocorrencias.append(normalizada)
        base["ocorrencias"] = ocorrencias
        base["revisao_humana_obrigatoria"] = bool(
            resultado.get("revisao_humana_obrigatoria", revisao_padrao))
        return base
    except Exception as exc:
        _erro("_normalizar_resultado", exc)
        return base


# =============================================================================
# Contexto e área
# =============================================================================

def _contexto_com_metricas(caminho, contexto=None, indices=True):
    """Builds the internal context with precomputed metrics and dimensions."""
    ctx = dict(contexto or {}) if isinstance(contexto, dict) else {}
    try:
        # Caminho padrão: avaliação 100% em Python (PNG/BMP/PPM com stdlib;
        # JPEG apenas decodificado pelo Pillow). O geoprocessamento fica como
        # fallback se a avaliação pura não conseguir ler a imagem.
        metricas = avaliacao_imagens.avaliar_imagem(caminho) or {}
        if not metricas:
            metricas = (geoprocessamento.indices_vegetacao(caminho)
                        if indices
                        else geoprocessamento.metricas_rgb(caminho)) or {}
        estatisticas = geoprocessamento.estatisticas_imagem(caminho) or {}
        ctx["_metricas"] = metricas
        ctx["_estatisticas"] = estatisticas
        ctx["_area_m2"] = _area_total(ctx, estatisticas)
    except Exception as exc:
        _erro("_contexto_com_metricas", exc)
        ctx.setdefault("_metricas", {})
        ctx.setdefault("_estatisticas", {})
        ctx.setdefault("_area_m2", 0.0)
    return ctx


def _area_total(ctx, estatisticas):
    """Total ground area of the frame, from context GSD or camera parameters."""
    try:
        gsd = ctx.get("gsd_cm")
        if gsd in (None, "") and all(
                ctx.get(chave) not in (None, "") for chave in
                ("altitude_m", "sensor_largura_mm", "focal_mm")):
            largura = estatisticas.get("largura") or ctx.get("largura_px")
            if largura:
                try:
                    gsd = geoprocessamento.gsd_cm(
                        ctx.get("altitude_m"), ctx.get("sensor_largura_mm"),
                        ctx.get("focal_mm"), largura)
                except ValueError:
                    gsd = None
        if gsd in (None, "") or not estatisticas:
            return 0.0
        return geoprocessamento.area_imagem_m2(
            estatisticas.get("largura"), estatisticas.get("altura"), gsd)
    except Exception as exc:
        _erro("_area_total", exc)
        return 0.0


def _area_afetada(ctx, fracao):
    """Ground area corresponding to a fraction of the frame."""
    try:
        total = _limitar_area(ctx.get("_area_m2"))
        return total * _limitar(fracao)
    except Exception:
        return 0.0


def _confianca(valor, limiar, escala=1.0):
    """Maps 'how far above threshold' to a bounded confidence."""
    try:
        excesso = max(0.0, float(valor) - float(limiar))
        return round(min(_LIMITE_CONFIANCA_MAX,
                         _LIMITE_CONFIANCA_MIN + excesso * escala), 4)
    except (TypeError, ValueError):
        return _LIMITE_CONFIANCA_MIN


def _severidade(confianca):
    """Maps confidence to baixa/media/alta (never claims more than it knows)."""
    if confianca >= 0.70:
        return "alta"
    if confianca >= 0.50:
        return "media"
    return "baixa"


def _maior_confianca(ocorrencias):
    """Returns the highest confidence among valid occurrences (0.0 if none)."""
    try:
        valores = [float(o.get("confianca", 0.0))
                   for o in (ocorrencias or []) if isinstance(o, dict)]
        return max(valores or [0.0])
    except Exception:
        return 0.0


def _fmt(metricas, chave, casas=3):
    """Formats a metric for the human-readable evidence string."""
    try:
        return f"{float(metricas.get(chave)):.{casas}f}"
    except (TypeError, ValueError):
        return "-"


# =============================================================================
# Baselines por módulo
# =============================================================================

def _baseline_agro(caminho, contexto):
    """Agro baseline: vegetation indices drive stress/failure/weed findings.

    Limiares (documentados em `docs/1_sistema/01_ferramentas/ia_geoprocessamento.md`):
      - `estresse_metabolico`: ExG < 0,05 e brilho > 0,22 (pouca vegetação
        ativa em cena iluminada).
      - `falha_plantio`: ExG < 0,08 com `marrom_ratio` > 0,35 (solo exposto).
      - `matocompeticao`: `verde_ratio` > 0,55 e `densidade_borda` > 0,18
        (verde abundante e heterogêneo, típico de mistura de espécies).
    Confiança cresce com a distância do limiar, limitada a 0,92.
    """
    metricas = contexto.get("_metricas") or {}
    brilho = metricas.get("brilho", 0.0)
    exg = metricas.get("ExG", 0.0)
    marrom = metricas.get("marrom_ratio", 0.0)
    verde = metricas.get("verde_ratio", 0.0)
    borda = metricas.get("densidade_borda", 0.0)
    tipo = (contexto.get("tipo_analise") or "lavoura")
    ocorrencias = []

    # Pecuária: o baseline de cor NÃO conta gado. Contagem/identificação de
    # animais exige detector treinado, dataset anotado e validação em campo
    # (Embrapa, 2024). Devolver "contagem" aqui seria número inventado.
    if tipo == "rebanho":
        return {
            "modelo": "avaliacao-pura-v1",
            "versao": "1.0",
            "confianca": 0.0,
            "resumo": (
                "Modo rebanho: a avaliação pura mede pasto e cena, mas NÃO "
                "conta animais. Contagem de gado exige detector treinado "
                "(YOLO/Mask R-CNN), dataset anotado e validação em campo. "
                "Registre a contagem observada e marque a revisão humana."
            ),
            "metricas": metricas,
            "ocorrencias": [],
            "revisao_humana_obrigatoria": True,
        }

    if exg < 0.05 and brilho > 0.22:
        conf = _confianca(0.05 - exg, 0.0, escala=2.2)
        ocorrencias.append(_ocorrencia(
            "estresse_metabolico", _severidade(conf), conf,
            _area_afetada(contexto, 1.0 - verde),
            f"ExG medio {_fmt(metricas, 'ExG')} (< 0,05) e brilho "
            f"{_fmt(metricas, 'brilho')}; vegetacao ativa em "
            f"{verde * 100:.1f}% da cena."))

    if exg < 0.08 and marrom > 0.35:
        conf = _confianca(marrom, 0.35, escala=0.9)
        ocorrencias.append(_ocorrencia(
            "falha_plantio", _severidade(conf), conf,
            _area_afetada(contexto, marrom),
            f"marrom_ratio {_fmt(metricas, 'marrom_ratio')} (> 0,35) com "
            f"ExG {_fmt(metricas, 'ExG')}; solo exposto na cena."))

    if verde > 0.55 and borda > 0.18:
        conf = _confianca(verde, 0.55, escala=1.4)
        ocorrencias.append(_ocorrencia(
            "matocompeticao", _severidade(conf), conf,
            _area_afetada(contexto, verde),
            f"verde_ratio {_fmt(metricas, 'verde_ratio')} (> 0,55) e "
            f"densidade_borda {_fmt(metricas, 'densidade_borda')} (> 0,18); "
            "cobertura verde heterogenea."))

    if not ocorrencias:
        resumo = ("Vegetacao sem indicio de estresse pelos limiares do "
                  "baseline RGB.")
    else:
        resumo = (f"Baseline RGB encontrou {len(ocorrencias)} indicio(s) em "
                  f"agro. Indices: ExG {_fmt(metricas, 'ExG')}, VARI "
                  f"{_fmt(metricas, 'VARI')}, GLI {_fmt(metricas, 'GLI')}, "
                  f"TGI {_fmt(metricas, 'TGI')}. Confirmar em campo.")
    confianca = _maior_confianca(ocorrencias)
    return {
        "modelo": "avaliacao-pura-v1",
        "versao": "1.0",
        "confianca": confianca,
        "resumo": resumo,
        "metricas": metricas,
        "ocorrencias": ocorrencias,
        "revisao_humana_obrigatoria": True,
    }


def _baseline_vistoria_predial(caminho, contexto):
    """Building-inspection baseline: edges→crack, dark→infiltration, green→moss.

    Limiares:
      - `trinca`: `densidade_borda` > 0,22.
      - `infiltracao`: `escuro_ratio` > 0,30 (mancha escura/umidade).
      - `vegetacao`: `verde_ratio` > 0,20 (musgo/vegetação em fachada/coberta).
    """
    metricas = contexto.get("_metricas") or {}
    borda = metricas.get("densidade_borda", 0.0)
    escuro = metricas.get("escuro_ratio", 0.0)
    verde = metricas.get("verde_ratio", 0.0)
    ocorrencias = []

    if borda > 0.22:
        conf = _confianca(borda, 0.22, escala=2.0)
        ocorrencias.append(_ocorrencia(
            "trinca", _severidade(conf), conf, _area_afetada(contexto, borda),
            f"densidade_borda {_fmt(metricas, 'densidade_borda')} (> 0,22); "
            "padrao linear de alto contraste compativel com fissura."))

    if escuro > 0.30:
        conf = _confianca(escuro, 0.30, escala=1.6)
        ocorrencias.append(_ocorrencia(
            "infiltracao", _severidade(conf), conf, _area_afetada(contexto, escuro),
            f"escuro_ratio {_fmt(metricas, 'escuro_ratio')} (> 0,30); "
            "area escura pode indicar umidade/mancha."))

    if verde > 0.20:
        conf = _confianca(verde, 0.20, escala=1.2)
        ocorrencias.append(_ocorrencia(
            "vegetacao", _severidade(conf), conf, _area_afetada(contexto, verde),
            f"verde_ratio {_fmt(metricas, 'verde_ratio')} (> 0,20); "
            "vegetacao/musgo sobre a superficie."))

    if not ocorrencias:
        resumo = ("Sem indicio de patologia pelos limiares do baseline RGB; "
                  "inspecao visual continua recomendada.")
    else:
        resumo = (f"Baseline RGB encontrou {len(ocorrencias)} indicio(s) em "
                  "vistoria predial. Sao hipoteses de triagem, nao diagnostico "
                  "de engenharia.")
    return {
        "modelo": "avaliacao-pura-v1",
        "versao": "1.0",
        "confianca": _maior_confianca(ocorrencias),
        "resumo": resumo,
        "metricas": metricas,
        "ocorrencias": ocorrencias,
        "revisao_humana_obrigatoria": True,
    }


def _baseline_ambiental(caminho, contexto):
    """Environmental baseline: exposed soil→deforestation, orange→fire.

    Limiares:
      - `desmatamento`: `marrom_ratio` > 0,35 com `verde_ratio` < 0,25.
      - `queimada`: `laranja_ratio` > 0,12 ou (`brilho` > 0,65 e
        `laranja_ratio` > 0,08).
    """
    metricas = contexto.get("_metricas") or {}
    marrom = metricas.get("marrom_ratio", 0.0)
    verde = metricas.get("verde_ratio", 0.0)
    laranja = metricas.get("laranja_ratio", 0.0)
    brilho = metricas.get("brilho", 0.0)
    ocorrencias = []

    if marrom > 0.35 and verde < 0.25:
        conf = _confianca(marrom, 0.35, escala=0.9)
        ocorrencias.append(_ocorrencia(
            "desmatamento", _severidade(conf), conf,
            _area_afetada(contexto, marrom),
            f"marrom_ratio {_fmt(metricas, 'marrom_ratio')} (> 0,35) e "
            f"verde_ratio {_fmt(metricas, 'verde_ratio')} (< 0,25); solo "
            "exposto no lugar de cobertura vegetal."))

    if laranja > 0.12 or (brilho > 0.65 and laranja > 0.08):
        conf = _confianca(max(laranja, 0.08 if brilho > 0.65 else 0.0),
                          max(0.12 if laranja > 0.12 else 0.08, 0.0),
                          escala=1.8)
        ocorrencias.append(_ocorrencia(
            "queimada", _severidade(conf), conf, _area_afetada(contexto, laranja),
            f"laranja_ratio {_fmt(metricas, 'laranja_ratio')} e brilho "
            f"{_fmt(metricas, 'brilho')}; coloracao compativel com area "
            "queimada/incandescente."))

    if not ocorrencias:
        resumo = "Sem indicio ambiental pelos limiares do baseline RGB."
    else:
        resumo = (f"Baseline RGB encontrou {len(ocorrencias)} indicio(s) "
                  "ambiental(is). Comparar com imagens anteriores do mesmo "
                  "ponto antes de qualquer conclusao.")
    return {
        "modelo": "avaliacao-pura-v1",
        "versao": "1.0",
        "confianca": _maior_confianca(ocorrencias),
        "resumo": resumo,
        "metricas": metricas,
        "ocorrencias": ocorrencias,
        "revisao_humana_obrigatoria": True,
    }


def _baseline_obras(caminho, contexto):
    """Construction baseline: structure/texture hints with low confidence only.

    Limiares conservadores:
      - `avanco`: `densidade_borda` > 0,25 (estrutura com muitas arestas).
      - `falha`: `contraste` < 0,05 e `brilho` < 0,35 (area chapada/escura).
    Ambas saem com confiança <= 0,45 e revisão humana obrigatória: sem modelo
    treinado, "avanço" e "falha" são apenas pistas para o engenheiro.
    """
    metricas = contexto.get("_metricas") or {}
    borda = metricas.get("densidade_borda", 0.0)
    contraste = metricas.get("contraste", 0.0)
    brilho = metricas.get("brilho", 0.0)
    ocorrencias = []

    if borda > 0.25:
        conf = min(0.45, _confianca(borda, 0.25, escala=0.8))
        ocorrencias.append(_ocorrencia(
            "avanco", _severidade(conf), conf, _area_afetada(contexto, borda),
            f"densidade_borda {_fmt(metricas, 'densidade_borda')} (> 0,25); "
            "possivel estrutura/equipamento em atividade. Baixa confianca."))

    if contraste < 0.05 and brilho < 0.35:
        conf = min(0.45, _confianca(0.35 - brilho, 0.0, escala=1.2))
        ocorrencias.append(_ocorrencia(
            "falha", _severidade(conf), conf, _area_afetada(contexto, 1.0),
            f"contraste {_fmt(metricas, 'contraste')} e brilho "
            f"{_fmt(metricas, 'brilho')}; area uniforme/escura. "
            "Baixa confianca."))

    resumo = ("Baseline conservador de obras: pistas de avanco/falha sao "
              "somente para triagem humana; sem modelo treinado o sistema "
              "nao mede progresso fisico.")
    return {
        "modelo": "avaliacao-pura-v1",
        "versao": "1.0",
        "confianca": _maior_confianca(ocorrencias),
        "resumo": resumo,
        "metricas": metricas,
        "ocorrencias": ocorrencias,
        "revisao_humana_obrigatoria": True,
    }


def _baseline_mapeamento(caminho, contexto):
    """Mapping baseline: metrics and GSD only, never a classified occurrence.

    Mapeamento não é laudo de anomalia: devolve as métricas da cena e o GSD
    quando o contexto traz `gsd_cm` ou `altitude_m`/`sensor_largura_mm`/
    `focal_mm`. Nenhuma ocorrência é emitida.
    """
    metricas = contexto.get("_metricas") or {}
    estatisticas = contexto.get("_estatisticas") or {}
    gsd = contexto.get("gsd_cm")
    if gsd in (None, "") and estatisticas.get("largura"):
        partes = (contexto.get("altitude_m"), contexto.get("sensor_largura_mm"),
                  contexto.get("focal_mm"))
        if all(parte not in (None, "") for parte in partes):
            try:
                gsd = geoprocessamento.gsd_cm(
                    *partes, estatisticas.get("largura"))
            except ValueError:
                gsd = None
    if gsd not in (None, ""):
        metricas = dict(metricas)
        metricas["gsd_cm"] = round(float(gsd), 3)
        metricas["area_m2"] = round(
            geoprocessamento.area_imagem_m2(
                estatisticas.get("largura"), estatisticas.get("altura"), gsd), 2)
    resumo = ("Analise de mapeamento: metricas de cena e GSD, sem ocorrencia "
              "classificada. Produtos geoespaciais exigem ortomosaico/GDAL.")
    return {
        "modelo": "avaliacao-pura-v1",
        "versao": "1.0",
        "confianca": 0.0,
        "resumo": resumo,
        "metricas": metricas,
        "ocorrencias": [],
        "revisao_humana_obrigatoria": False,
    }


def _baseline_seguranca(caminho, contexto):
    """Public-safety baseline: refuses to infer people, vehicles or weapons.

    Sem detector homologado, este baseline **não** gera ocorrência: qualquer
    afirmação sobre pessoa/arma/viatura exigiria base legal, convênio,
    retenção limitada, revisão humana e auditoria (AGENTS.md §2.1.1). O
    resultado entrega métricas de cena para triagem, com revisão obrigatória,
    e explica por que não classificou nada.
    """
    metricas = contexto.get("_metricas") or {}
    resumo = ("Nenhum detector homologado registrado para seguranca. O "
              "baseline nao infere pessoas, veiculos, placas ou armas: "
              "qualquer deteccao exige modelo treinado, base legal, "
              "convenio oficial, retencao limitada, revisao humana e "
              "auditoria. A imagem fica apenas com metricas de cena "
              "para triagem.")
    return {
        "modelo": "avaliacao-pura-v1",
        "versao": "1.0",
        "confianca": 0.0,
        "resumo": resumo,
        "metricas": metricas,
        "ocorrencias": [],
        "revisao_humana_obrigatoria": True,
    }


def _baseline_conservador(caminho, contexto, modulo):
    """Conservative baseline for modules without a validated detector.

    Entrega métricas e nenhuma classe: `defesa_civil`, `inspecao_industrial`
    e `eventos` não afirmam risco, corrosão ou público sem modelo. A revisão
    humana é sempre obrigatória.
    """
    metricas = contexto.get("_metricas") or {}
    resumo = (f"Baseline conservador de {modulo}: apenas metricas de cena. "
              "Sem modelo homologado, nenhuma classe e afirmada; a triagem "
              "e responsabilidade humana.")
    return {
        "modelo": "avaliacao-pura-v1",
        "versao": "1.0",
        "confianca": 0.0,
        "resumo": resumo,
        "metricas": metricas,
        "ocorrencias": [],
        "revisao_humana_obrigatoria": True,
    }


def _baseline_generico(caminho, contexto):
    """Fallback for an unknown module: metrics only, no occurrence."""
    return _normalizar_resultado(
        _baseline_conservador(caminho, contexto, "modulo desconhecido"),
        "avaliacao-pura-v1", "1.0", revisao_padrao=True)


_BASELINES = {
    "agro": _baseline_agro,
    "vistoria_predial": _baseline_vistoria_predial,
    "ambiental": _baseline_ambiental,
    "obras": _baseline_obras,
    "mapeamento": _baseline_mapeamento,
    "seguranca": _baseline_seguranca,
    "defesa_civil": lambda c, x: _baseline_conservador(c, x, "defesa_civil"),
    "inspecao_industrial": lambda c, x: _baseline_conservador(
        c, x, "inspecao_industrial"),
    "eventos": lambda c, x: _baseline_conservador(c, x, "eventos"),
    "generico": _baseline_generico,
}

# Módulos que usam índices de vegetação (agro/ambiental) e o restante, que
# usa só métricas RGB. Calcular índice a mais seria custo sem uso.
_MODULOS_COM_INDICES = ("agro", "ambiental", "mapeamento")


# =============================================================================
# Modelos ONNX (opcional)
# =============================================================================

def modelo_onnx(caminho_modelo, tamanho_entrada=224, nome=None):
    """Loads an ONNX model and returns an analysis callable (None if absent).

    `onnxruntime` é OPCIONAL: sem ele (ou sem o arquivo) devolve `None` sem
    levantar exceção. O callable devolvido tem a assinatura
    `funcao(caminho, contexto)` e é compatível com `registrar_modelo`.

    A imagem é redimensionada para `tamanho_entrada`x`tamanho_entrada`, em
    RGB, float32, NCHW e faixa `[0,1]` (padrão de transfer learning). O
    resultado expõe índice e probabilidade bruta da saída — **sem** inventar
    rótulo semântico: o mapa de classes deve ser validado e traduzido pelo
    módulo que registra o modelo.
    """
    try:
        try:
            import onnxruntime as ort  # noqa: WPS433 (import opcional)
        except Exception:
            return None
        if not caminho_modelo or not os.path.isfile(str(caminho_modelo)):
            return None
        sessao = ort.InferenceSession(str(caminho_modelo),
                                      providers=["CPUExecutionProvider"])
        entrada = sessao.get_inputs()[0]
        nome_entrada = entrada.name
        versao = f"onnx:{os.path.basename(str(caminho_modelo))}"

        def _inferir(caminho, contexto=None):
            """Runs one image through the ONNX session (never raises)."""
            try:
                arr = geoprocessamento.carregar_rgb(caminho)
                if arr is None:
                    return _resultado_vazio(nome or "onnx", versao)
                imagem = Image.fromarray(
                    (arr.clip(0, 1) * 255).astype(np.uint8))
                try:
                    redimensionada = imagem.resize(
                        (int(tamanho_entrada), int(tamanho_entrada)),
                        Image.Resampling.BILINEAR)
                finally:
                    imagem.close()
                try:
                    # `np.array` copia: o buffer do Pillow some no close().
                    dados = np.array(redimensionada, dtype=np.float32) / 255.0
                finally:
                    redimensionada.close()
                tensor = np.transpose(dados, (2, 0, 1))[None, ...]
                saidas = sessao.run(None, {nome_entrada: tensor})
                bruto = np.asarray(saidas[0], dtype=np.float32).reshape(-1)
                confianca = 0.0
                indice = 0
                if bruto.size:
                    indice = int(np.argmax(bruto))
                    amostra = bruto
                    if np.all(amostra >= 0) and abs(float(amostra.sum()) - 1.0) > 0.05:
                        exp = np.exp(amostra - amostra.max())
                        amostra = exp / (exp.sum() + 1e-6)
                    confianca = float(amostra[indice])
                return {
                    "modelo": nome or "onnx",
                    "versao": versao,
                    "confianca": round(_limitar(confianca), 4),
                    "resumo": ("Saida bruta do modelo ONNX registrado. O "
                               "mapa de classes precisa ser homologado antes "
                               "de virar laudo."),
                    "metricas": {
                        "indice_saida": indice,
                        "probabilidade": round(_limitar(confianca), 4),
                        "tamanho_entrada": int(tamanho_entrada),
                    },
                    "ocorrencias": [],
                    "revisao_humana_obrigatoria": True,
                }
            except Exception as exc:
                _erro("modelo_onnx.executar", exc)
                return _resultado_vazio(nome or "onnx", versao)

        return _inferir
    except Exception as exc:
        _erro(f"modelo_onnx('{caminho_modelo}')", exc)
        return None


def _modelo_ambiente(modulo):
    """Lazily loads an ONNX model from environment variables, if configured.

    Ordem: `SKYROVER_MODELO_ONNX_<MODULO>` e depois `SKYROVER_MODELO_ONNX`.
    O caminho é tentado uma única vez por módulo (cache de falha) para não
    repetir IO em cada análise. Sem onnxruntime/arquivo, devolve `None`.
    """
    try:
        chave = _normalizar_nome(modulo)
        if not chave or chave in _modelos_ambiente_tentados:
            return None
        especifica = os.environ.get(f"SKYROVER_MODELO_ONNX_{chave.upper()}")
        caminho = (especifica or os.environ.get("SKYROVER_MODELO_ONNX") or "").strip()
        _modelos_ambiente_tentados.add(chave)
        if not caminho:
            return None
        funcao = modelo_onnx(caminho, nome=chave)
        if not funcao:
            return None
        versao = f"onnx:{os.path.basename(caminho)}"
        registrar_modelo(chave, versao, funcao)
        return obter_modelo(chave)
    except Exception as exc:
        _erro(f"_modelo_ambiente('{modulo}')", exc)
        return None


# =============================================================================
# API pública
# =============================================================================

def analisar_imagem(caminho, modulo, contexto=None):
    """Analyzes one image with the registered model or the RGB baseline.

    Resolve o modelo nesta ordem:
      1. modelo registrado com o nome exato do módulo (`registrar_modelo`);
      2. modelo ONNX apontado por `SKYROVER_MODELO_ONNX[_<MODULO>]`;
      3. baseline determinístico do módulo (último recurso, sempre disponível).

    O retorno segue o contrato do topo do arquivo. Nunca levanta exceção:
    caminho inválido devolve resultado vazio com `revisao_humana_obrigatoria`.
    """
    modulo_norm = _normalizar_nome(modulo) or "generico"
    resultado = _resultado_vazio()
    try:
        if not caminho or not os.path.isfile(str(caminho)):
            resultado["resumo"] = (
                "Imagem indisponivel ou inexistente; nenhuma analise foi "
                "executada.")
            return resultado

        usa_indices = modulo_norm in _MODULOS_COM_INDICES
        ctx = _contexto_com_metricas(caminho, contexto, indices=usa_indices)
        metricas = ctx.get("_metricas") or {}

        modelo = obter_modelo(modulo_norm) or _modelo_ambiente(modulo_norm)
        if modelo:
            try:
                saida = modelo["funcao"](caminho, ctx)
                return _normalizar_resultado(
                    saida, modelo["nome"], modelo["versao"], metricas)
            except Exception as exc:
                _erro(f"analisar_imagem.modelo('{modulo_norm}')", exc)
                # Modelo quebrado não derruba a análise: cai no baseline.

        funcao = _BASELINES.get(modulo_norm, _baseline_generico)
        saida = funcao(caminho, ctx)
        return _normalizar_resultado(saida, "avaliacao-pura-v1", "1.0", metricas)
    except Exception as exc:
        _erro(f"analisar_imagem('{caminho}', '{modulo}')", exc)
        resultado["resumo"] = (
            "Falha interna na analise; a imagem precisa de revisao manual.")
        return resultado


def analisar_lote(caminhos, modulo, contexto=None):
    """Analyzes a list of images and returns one contract dict per image.

    Caminhos inválidos também entram no resultado (com resumo de falha), de
    forma que a posição da lista sempre corresponde à da entrada. O contexto
    é compartilhado; cada análise o copia internamente.
    """
    try:
        return [analisar_imagem(caminho, modulo, contexto)
                for caminho in (caminhos or [])]
    except Exception as exc:
        _erro(f"analisar_lote('{modulo}')", exc)
        return []
