"""PDF report generation for T! SOS DocFly (ReportLab).

Gera o laudo em PDF a partir de metadados, resumo textual, tabela de
ocorrências, métricas e imagens opcionais. Tudo que vem do banco/usuário é
escapado antes de virar `Paragraph` (o ReportLab interpreta um subconjunto
de XML). Um laudo nunca sobrescreve outro: o nome recebe timestamp quando já
existe.

`gerar_pdf_laudo` grava onde o chamador pedir; `gerar_pdf_modulo` usa a pasta
`src/mod_tisosdocfly/laudos/<chave>/` (ou `TISOSDOCFLY_DIR_LAUDOS`).
"""
import os
import re
import unicodedata
from datetime import datetime
from xml.sax.saxutils import escape

from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_MODULO_LOG = "tisosdocfly"
_COR_PRIMARIA = colors.HexColor("#1F4E5F")
_COR_LINHA = colors.HexColor("#B8C4C9")
_COR_FUNDO_TABELA = colors.HexColor("#EEF3F4")
_LARGURA_UTIL = A4[0] - 4 * cm
_LARGURA_IMAGEM = 15.0 * cm
_ALTURA_IMAGEM_MAX = 11.0 * cm


def _log():
    """Logger loguru do núcleo; nunca falha por causa da observabilidade."""
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger(_MODULO_LOG)
    except Exception:
        from loguru import logger
        return logger


def _erro(contexto, exc):
    """Registra a causa sem derrubar o chamador."""
    try:
        _log().exception(f"relatorio.{contexto}: {exc}")
    except Exception:
        pass


def _agora():
    """Local timestamp used in report names and footers."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _slug(texto, padrao="laudo", limite=60):
    """Returns a filesystem/URL-safe slug (a-z, 0-9 and hyphen)."""
    try:
        base = unicodedata.normalize("NFKD", str(texto or ""))
        base = base.encode("ascii", "ignore").decode("ascii").lower()
        base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        return (base[:limite].strip("-") or padrao)
    except Exception:
        return padrao


def _texto_seguro(valor):
    """Escapes user data for ReportLab and keeps line breaks as `<br/>`."""
    try:
        if valor is None:
            return "-"
        if isinstance(valor, (list, tuple)):
            valor = ", ".join(str(item) for item in valor)
        elif isinstance(valor, dict):
            valor = "; ".join(f"{chave}: {item}" for chave, item in valor.items())
        bruto = escape(str(valor))
        return bruto.replace("\r\n", "\n").replace("\n", "<br/>")
    except Exception:
        return "-"


def _numero(valor, casas=2, padrao="-"):
    """Formats a numeric value with a fixed number of decimals."""
    try:
        return f"{float(valor):.{casas}f}"
    except (TypeError, ValueError):
        return padrao


def _destino_unico(destino):
    """Adds a timestamp suffix instead of overwriting an existing report."""
    try:
        if not os.path.exists(destino):
            return destino
        raiz, ext = os.path.splitext(destino)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidato = f"{raiz}_{carimbo}{ext}"
        contador = 2
        while os.path.exists(candidato):
            candidato = f"{raiz}_{carimbo}_{contador}{ext}"
            contador += 1
        return candidato
    except Exception as exc:
        _erro("_destino_unico", exc)
        return destino


def _estilos():
    """Builds the paragraph styles used by the report."""
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "SkyTitulo", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, textColor=_COR_PRIMARIA,
            alignment=0, spaceAfter=10),
        "secao": ParagraphStyle(
            "SkySecao", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12.5, leading=16, textColor=_COR_PRIMARIA,
            spaceBefore=12, spaceAfter=6),
        "corpo": ParagraphStyle(
            "SkyCorpo", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.5, leading=13.5, spaceAfter=4),
        "celula": ParagraphStyle(
            "SkyCelula", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8, leading=10.5),
        "celula_cabecalho": ParagraphStyle(
            "SkyCelulaCabecalho", parent=base["BodyText"],
            fontName="Helvetica-Bold", fontSize=8, leading=10.5,
            textColor=colors.white),
        "legenda": ParagraphStyle(
            "SkyLegenda", parent=base["BodyText"], fontName="Helvetica-Oblique",
            fontSize=8, leading=10.5, textColor=colors.HexColor("#444444")),
        "rodape": ParagraphStyle(
            "SkyRodape", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8, leading=11, textColor=colors.HexColor("#666666")),
    }


def _pares(metadados):
    """Normalizes metadata (dict or sequence of pairs) into `[(chave, valor)]`."""
    try:
        if isinstance(metadados, dict):
            return [(str(chave), valor) for chave, valor in metadados.items()]
        if isinstance(metadados, (list, tuple)):
            pares = []
            for item in metadados:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    pares.append((str(item[0]), item[1]))
                elif isinstance(item, dict):
                    pares.extend((str(k), v) for k, v in item.items())
            return pares
        return []
    except Exception as exc:
        _erro("_pares", exc)
        return []


def _paragrafos_resumo(resumo, estilos):
    """Turns the free-text summary into escaped paragraphs."""
    fluxo = []
    texto = resumo if isinstance(resumo, str) else str(resumo or "")
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            fluxo.append(Spacer(1, 3))
            continue
        fluxo.append(Paragraph(_texto_seguro(linha), estilos["corpo"]))
    if not fluxo:
        fluxo.append(Paragraph("Sem resumo informado.", estilos["corpo"]))
    return fluxo


def _tabela_metadados(metadados, estilos):
    """Two-column metadata table."""
    pares = _pares(metadados)
    if not pares:
        return []
    dados = [[Paragraph("<b>Campo</b>", estilos["celula"]),
              Paragraph("<b>Valor</b>", estilos["celula"])]]
    for chave, valor in pares:
        dados.append([
            Paragraph(_texto_seguro(chave), estilos["celula"]),
            Paragraph(_texto_seguro(valor), estilos["celula"]),
        ])
    tabela = Table(dados, colWidths=[4.4 * cm, _LARGURA_UTIL - 4.4 * cm],
                   repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _COR_FUNDO_TABELA),
        ("GRID", (0, 0), (-1, -1), 0.4, _COR_LINHA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [tabela, Spacer(1, 6)]


def _tabela_ocorrencias(ocorrencias, estilos):
    """Occurrence table; empty list yields an explicit no-finding paragraph."""
    lista = [item for item in (ocorrencias or []) if isinstance(item, dict)]
    if not lista:
        return [Paragraph(
            "Nenhuma ocorrência automática registrada nesta análise.",
            estilos["corpo"])]
    colunas = [3.2, 2.0, 1.8, 2.2, 6.8]
    cabecalho = ["Classe", "Severidade", "Confiança (%)", "Área (m²)",
                 "Evidência"]
    dados = [[Paragraph(_texto_seguro(c), estilos["celula_cabecalho"])
              for c in cabecalho]]
    for item in lista:
        confianca = item.get("confianca")
        try:
            confianca_txt = f"{float(confianca) * 100:.0f}"
        except (TypeError, ValueError):
            confianca_txt = "-"
        dados.append([
            Paragraph(_texto_seguro(item.get("classe")), estilos["celula"]),
            Paragraph(_texto_seguro(item.get("severidade")), estilos["celula"]),
            Paragraph(confianca_txt, estilos["celula"]),
            Paragraph(_numero(item.get("area_m2")), estilos["celula"]),
            Paragraph(_texto_seguro(item.get("evidencia")), estilos["celula"]),
        ])
    tabela = Table(dados, colWidths=[valor * cm for valor in colunas],
                   repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _COR_PRIMARIA),
        ("GRID", (0, 0), (-1, -1), 0.4, _COR_LINHA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F7FAFB")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [tabela, Spacer(1, 6)]


def _tabela_metricas(metricas, estilos):
    """Key/value table for the numeric metrics."""
    if not isinstance(metricas, dict) or not metricas:
        return []
    dados = [[Paragraph("<b>Métrica</b>", estilos["celula"]),
              Paragraph("<b>Valor</b>", estilos["celula"])]]
    for chave, valor in metricas.items():
        if isinstance(valor, float):
            valor = f"{valor:.4f}"
        dados.append([
            Paragraph(_texto_seguro(chave), estilos["celula"]),
            Paragraph(_texto_seguro(valor), estilos["celula"]),
        ])
    tabela = Table(dados, colWidths=[6.0 * cm, _LARGURA_UTIL - 6.0 * cm],
                   repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _COR_FUNDO_TABELA),
        ("GRID", (0, 0), (-1, -1), 0.4, _COR_LINHA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return [tabela, Spacer(1, 6)]


def _bloco_imagem(caminho, legenda, estilos):
    """Builds one scaled image flowable (empty list when unreadable)."""
    try:
        if not caminho or not os.path.isfile(str(caminho)):
            return []
        with PilImage.open(caminho) as imagem:
            largura_px, altura_px = imagem.size
        if not largura_px or not altura_px:
            return []
        largura = float(_LARGURA_IMAGEM)
        altura = largura * altura_px / largura_px
        if altura > _ALTURA_IMAGEM_MAX:
            altura = float(_ALTURA_IMAGEM_MAX)
            largura = altura * largura_px / altura_px
        fluxo = [RLImage(str(caminho), width=largura, height=altura)]
        if legenda:
            fluxo.append(Paragraph(_texto_seguro(legenda), estilos["legenda"]))
        fluxo.append(Spacer(1, 8))
        return fluxo
    except Exception as exc:
        _erro(f"_bloco_imagem('{caminho}')", exc)
        return []


def _fluxo_imagens(imagens, estilos):
    """Normalizes the images argument and appends each readable image."""
    fluxo = []
    for item in (imagens or []):
        caminho, legenda = None, ""
        if isinstance(item, dict):
            caminho = item.get("caminho") or item.get("path")
            legenda = item.get("legenda") or item.get("caption") or ""
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            caminho, legenda = item[0], item[1]
        else:
            caminho = item
        fluxo.extend(_bloco_imagem(caminho, legenda, estilos))
    return fluxo


def _rodape(canvas, doc):
    """Draws the report footer with generation time and page number."""
    try:
        canvas.saveState()
        canvas.setStrokeColor(_COR_LINHA)
        canvas.setLineWidth(0.4)
        canvas.line(2 * cm, 1.9 * cm, A4[0] - 2 * cm, 1.9 * cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(2 * cm, 1.35 * cm,
                          f"T! SOS DocFly — laudo gerado em {_agora()}")
        canvas.drawRightString(A4[0] - 2 * cm, 1.35 * cm,
                               f"Página {doc.page}")
        canvas.restoreState()
    except Exception as exc:
        _erro("_rodape", exc)


def gerar_pdf_laudo(destino, titulo, metadados, resumo, ocorrencias,
                    imagens=None, metricas=None):
    """Writes the report PDF to `destino` and returns the final path (or None).

    Estrutura: título, metadados, resumo, ocorrências, métricas e imagens
    (quando existirem). A pasta de destino é criada; se o arquivo já existir,
    o nome recebe `_AAAAMMDD_HHMMSS` — nunca sobrescreve. Retorna `None` em
    falha (com log) e remove o arquivo parcial.
    """
    caminho_final = None
    try:
        if not destino:
            return None
        destino = str(destino)
        if not destino.lower().endswith(".pdf"):
            destino += ".pdf"
        pasta = os.path.dirname(os.path.abspath(destino))
        os.makedirs(pasta, exist_ok=True)
        caminho_final = _destino_unico(destino)

        estilos = _estilos()
        documento = SimpleDocTemplate(
            caminho_final, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2.4 * cm,
            title=str(titulo or "Laudo T! SOS DocFly"),
            author="T! SOS DocFly",
            subject="Laudo de voo",
        )
        fluxo = [
            Paragraph(_texto_seguro(titulo or "Laudo T! SOS DocFly"),
                      estilos["titulo"]),
            Paragraph(
                f"Documento gerado em {_agora()} pelo pipeline do T! SOS DocFly.",
                estilos["rodape"]),
            Spacer(1, 8),
            Paragraph("Metadados", estilos["secao"]),
        ]
        fluxo.extend(_tabela_metadados(metadados, estilos))
        fluxo.append(Paragraph("Resumo", estilos["secao"]))
        fluxo.extend(_paragrafos_resumo(resumo, estilos))
        fluxo.append(Paragraph("Ocorrências", estilos["secao"]))
        fluxo.extend(_tabela_ocorrencias(ocorrencias, estilos))
        if isinstance(metricas, dict) and metricas:
            fluxo.append(Paragraph("Métricas da imagem", estilos["secao"]))
            fluxo.extend(_tabela_metricas(metricas, estilos))
        bloco_imagens = _fluxo_imagens(imagens, estilos)
        if bloco_imagens:
            fluxo.append(Paragraph("Imagens", estilos["secao"]))
            fluxo.extend(bloco_imagens)
        fluxo.append(Spacer(1, 10))
        fluxo.append(Paragraph(
            "Saída automática sujeita a revisão humana. Em segurança pública, "
            "o sistema não decide culpa nem identifica pessoas sem detector "
            "homologado e base legal.", estilos["rodape"]))

        documento.build(fluxo, onFirstPage=_rodape, onLaterPages=_rodape)
        if not os.path.isfile(caminho_final) or os.path.getsize(caminho_final) <= 0:
            return None
        return caminho_final
    except Exception as exc:
        _erro(f"gerar_pdf_laudo('{destino}')", exc)
        try:
            if caminho_final and os.path.isfile(caminho_final):
                os.remove(caminho_final)
        except Exception:
            pass
        return None


def diretorio_laudos():
    """Returns the report root (`TISOSDOCFLY_DIR_LAUDOS` overrides the default)."""
    try:
        custom = os.environ.get("TISOSDOCFLY_DIR_LAUDOS", "").strip()
        if custom:
            return custom
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "laudos")
    except Exception as exc:
        _erro("diretorio_laudos", exc)
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "laudos")


def gerar_pdf_modulo(chave_modulo, titulo, metadados, resumo, ocorrencias,
                     imagens=None):
    """Writes the module report under `laudos/<chave>/<slug>.pdf`.

    A chave do módulo é reduzida a `[a-z0-9_-]` para nunca escapar da pasta
    de laudos. O nome do arquivo é o slug do título; se já existir, recebe
    timestamp. Devolve o caminho final ou `None` em falha.
    """
    try:
        chave = re.sub(r"[^a-z0-9_-]+", "", _slug(chave_modulo, "geral"))
        chave = chave or "geral"
        pasta = os.path.join(diretorio_laudos(), chave)
        os.makedirs(pasta, exist_ok=True)
        nome = _slug(titulo, "laudo")
        destino = os.path.join(pasta, f"{nome}.pdf")
        return gerar_pdf_laudo(destino, titulo, metadados, resumo,
                               ocorrencias, imagens=imagens)
    except Exception as exc:
        _erro(f"gerar_pdf_modulo('{chave_modulo}')", exc)
        return None
