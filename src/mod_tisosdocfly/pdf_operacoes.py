"""Shared pure-PDF operations (no database, no per-module state).

Operacoes PDF puras compartilhadas (sem banco, sem estado de modulo).

Motor de manipulacao de PDFs (cortar/juntar/reduzir/dividir/verificar)
usado pelo Editor de PDF e pelo Renomear de Empenhos. Morava em
`mod_edit_pdf/bd_manipulador.py`; foi movido para o nucleo para que
nenhum modulo de negocio importe outro (`mod_renomear_empenho` agora
importa daqui). `mod_edit_pdf/bd_manipulador.py` re-exporta estes nomes,
portanto sua superficie publica nao muda.
"""
import os


def _log():
    """Logger do motor PDF (loguru) — arquivo dedicado logs/pdf_operacoes_<data>.log."""
    from mod_tisosdocfly import observabilidade
    return observabilidade.get_logger("pdf_operacoes")


# ================= OPERAÇÕES =================

def hash_sha256(caminho):
    """SHA-256 de um arquivo (leitura em blocos)."""
    import hashlib
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def op_reduzir(caminho_in, caminho_out, qualidade=50, dpi=None, modo="leve", biblioteca="auto"):
    """Reduz o tamanho do PDF.

    modo 'leve': recompressão de streams — biblioteca 'auto' (pymupdf→pikepdf→pypdf)
                 ou fixa ('pymupdf'|'pikepdf'|'pypdf').
    modo 'agressivo': rasteriza cada página no DPI alvo como JPEG (qualidade 10-100),
                      sempre via pymupdf; texto vira imagem — ganho real de tamanho.
    Retorna (ok, msg).
    """
    qualidade = max(10, min(100, int(qualidade)))
    if str(modo).lower() == "agressivo":
        return _reduzir_agressivo(caminho_in, caminho_out, qualidade, dpi)
    return _reduzir_leve(caminho_in, caminho_out, biblioteca)


def _reduzir_leve(caminho_in, caminho_out, biblioteca):
    """Light reduction: stream recompression via pymupdf/pikepdf/pypdf.

    Tenta as bibliotecas na ordem escolhida ('auto' = pymupdf → pikepdf →
    pypdf); retorna (ok, msg) com o nome da que funcionou ou os erros."""
    ordem = {
        "pymupdf": ["pymupdf"],
        "pikepdf": ["pikepdf"],
        "pypdf": ["pypdf"],
    }.get(str(biblioteca).lower(), ["pymupdf", "pikepdf", "pypdf"])
    erros = []
    for lib in ordem:
        try:
            if lib == "pymupdf":
                import pymupdf
                doc = pymupdf.open(caminho_in)
                doc.save(caminho_out, garbage=4, deflate=True, deflate_images=True,
                         deflate_fonts=True, clean=True)
                doc.close()
            elif lib == "pikepdf":
                import pikepdf
                with pikepdf.open(caminho_in) as pdf:
                    pdf.save(caminho_out, compress_streams=True,
                             object_stream_mode=pikepdf.ObjectStreamMode.generate)
            elif lib == "pypdf":
                from pypdf import PdfWriter
                escritor = PdfWriter(clone_from=caminho_in)
                for pagina in escritor.pages:
                    try:
                        pagina.compress_content_streams(level=9)
                    except Exception:
                        pass
                escritor.compress_identical_objects(remove_duplicates=True,
                                                    remove_orphans=True)
                with open(caminho_out, "wb") as f:
                    escritor.write(f)
            else:
                continue
            if os.path.isfile(caminho_out):
                return True, f"OK ({lib})"
        except Exception as ex:
            erros.append(f"{lib}: {ex}")
    _log().error(f"falha ao reduzir (leve) {caminho_in}: " +
                 (" | ".join(erros) or "nenhuma biblioteca disponível"))
    return False, " | ".join(erros) or "nenhuma biblioteca disponível"


def _reduzir_agressivo(caminho_in, caminho_out, qualidade, dpi):
    """Aggressive reduction: rasterizes each page as JPEG (always pymupdf).

    DPI 50–400 (default 150), qualidade 10–100; texto vira imagem — ganho
    real de tamanho com perda de seleção/busca. Retorna (ok, msg)."""
    try:
        import pymupdf
        dpi = max(50, min(400, int(dpi or 150)))
        doc = pymupdf.open(caminho_in)
        novo = pymupdf.open()
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=dpi)
            img = pix.tobytes("jpeg", jpg_quality=qualidade)
            ret = pagina.rect
            folha = novo.new_page(width=ret.width, height=ret.height)
            folha.insert_image(ret, stream=img)
        novo.save(caminho_out, garbage=4, deflate=True)
        novo.close()
        doc.close()
        return True, f"OK (agressivo {dpi}dpi q{qualidade})"
    except Exception as e:
        _log().exception(f"falha ao reduzir (agressivo) {caminho_in}")
        return False, f"agressivo: {e}"


def op_juntar(caminhos_in, caminho_out):
    """Une SOMENTE os arquivos PDF válidos; ignora e REPORTA os demais
    (ex.: ZIPs ou corrompidos misturados na seleção).

    Retorna (ok, msg) — msg lista os ignorados quando houver.
    """
    import pymupdf
    validos, problemas = [], []
    for c in caminhos_in:
        base = os.path.basename(c)
        if not str(c).lower().endswith(".pdf"):
            problemas.append(f"'{base}': não é PDF")
            continue
        try:
            doc = pymupdf.open(c)
            n = len(doc)
            doc.close()
        except Exception as ex:
            problemas.append(f"'{base}': ilegível ({ex})")
            continue
        if n <= 0:
            problemas.append(f"'{base}': sem páginas")
            continue
        validos.append(c)

    if len(validos) < 2:
        motivo = ("; ".join(problemas)) or "menos de 2 PDFs válidos"
        return False, f"Nada para juntar ({motivo})"

    try:
        saida = pymupdf.open()
        for c in validos:
            src = pymupdf.open(c)
            saida.insert_pdf(src)
            src.close()
        saida.save(caminho_out, garbage=4, deflate=True)
        saida.close()
        msg = f"OK ({len(validos)} unidos)"
        if problemas:
            msg += " — IGNORADOS: " + "; ".join(problemas)
        _log().info(f"juncao: {len(validos)} arquivo(s) unido(s)" +
                    (f" | ignorados: {'; '.join(problemas)}" if problemas else ""))
        return True, msg
    except Exception as e:
        _log().exception(f"falha ao juntar PDFs -> {caminho_out}")
        return False, str(e)


def _paginas_de_filtro(filtro, total):
    """Converts '2-5,8' (or 'todas') into a set of valid 1-based page numbers."""
    selecionadas = set()
    if isinstance(filtro, str) and filtro.strip().lower() in ("all", "todas", ""):
        return set(range(1, total + 1))
    for parte in str(filtro).split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            a, b = parte.split("-", 1)
            try:
                ini, fim = int(a), int(b)
            except ValueError:
                continue
            selecionadas.update(range(max(1, ini), min(total, fim) + 1))
        elif parte.isdigit():
            p = int(parte)
            if 1 <= p <= total:
                selecionadas.add(p)
    return selecionadas


def op_dividir(caminho_in, paginas, pasta_saida, base_name):
    """Splits by page list (1-based) or range '2-5'. Returns list of files."""
    import pymupdf
    doc = pymupdf.open(caminho_in)
    total = len(doc)
    selecionadas = _paginas_de_filtro(paginas, total)

    arquivos = []
    for p in sorted(selecionadas):
        novo = pymupdf.open()
        novo.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
        destino = os.path.join(pasta_saida, f"{base_name}_pag{p}.pdf")
        novo.save(destino, garbage=4, deflate=True)
        novo.close()
        arquivos.append((destino, p))
    doc.close()
    return True, arquivos


def _libs_da_preferencia(biblioteca):
    """Resolve a escolha de biblioteca numa lista de tentativas ordenadas.
    'auto' segue o fallback padrão do módulo: pymupdf → pikepdf → pypdf."""
    bib = (biblioteca or "auto").strip().lower()
    if bib == "auto":
        return ["pymupdf", "pikepdf", "pypdf"]
    return [bib]


def _extrair_paginas(caminho_in, paginas, destino, biblioteca):
    """Gera `destino` contendo as páginas informadas (lista 1-based,
    aceita não-contíguas). biblioteca: pymupdf | pikepdf | pypdf.
    Levanta exceção em falha (quem chama decide o fallback)."""
    bib = (biblioteca or "").strip().lower()
    if bib == "pymupdf":
        import pymupdf
        doc = pymupdf.open(caminho_in)
        try:
            out = pymupdf.open()
            for p in paginas:
                out.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
            out.save(destino, garbage=4, deflate=True)
            out.close()
        finally:
            doc.close()
    elif bib == "pikepdf":
        import pikepdf
        src = pikepdf.open(caminho_in)
        try:
            dst = pikepdf.Pdf.new()
            for p in paginas:
                dst.pages.append(src.pages[p - 1])
            dst.save(destino)
        finally:
            src.close()
    elif bib == "pypdf":
        from pypdf import PdfReader, PdfWriter
        leitor = PdfReader(caminho_in)
        escritor = PdfWriter()
        for p in paginas:
            escritor.add_page(leitor.pages[p - 1])
        with open(destino, "wb") as fh:
            escritor.write(fh)
    else:
        raise ValueError(f"biblioteca desconhecida: {biblioteca}")


def op_cortar(caminho_in, filtro, pasta_saida, base_name, biblioteca="pymupdf"):
    """Corta páginas em UM ÚNICO PDF.

    filtro: 'pares' | 'impares' | lista tipo '2-5,8'.
    biblioteca: 'auto' | 'pymupdf' | 'pikepdf' | 'pypdf'
      ('auto' tenta pymupdf → pikepdf → pypdf).
    Retorna (ok, caminho_out|msg).
    """
    import pymupdf
    filtro_norm = str(filtro or "").strip().lower()
    doc = pymupdf.open(caminho_in)
    total = len(doc)
    doc.close()
    if filtro_norm == "pares":
        pags = list(range(2, total + 1, 2))
    elif filtro_norm == "impares":
        pags = list(range(1, total + 1, 2))
    else:
        pags = sorted(_paginas_de_filtro(filtro_norm, total))
    if not pags:
        return False, "Nenhuma página válida para o corte"
    destino = os.path.join(pasta_saida, f"{base_name}.pdf")
    erros = []
    for bib in _libs_da_preferencia(biblioteca):
        try:
            _extrair_paginas(caminho_in, pags, destino, bib)
            _log().info(f"corte: {caminho_in} -> {destino} (filtro='{filtro}')")
            return True, destino
        except Exception as e:
            erros.append(f"{bib}: {e}")
    _log().error(f"falha no corte de {caminho_in} (filtro='{filtro}'): " +
                 " | ".join(erros))
    return False, ("falha no corte — " + " | ".join(erros))


# ---------- Divisão em várias partes ----------

def partes_pares_impares(total):
    """Duas partes complementares: [('pares',[2,4..]), ('impares',[1,3..])]."""
    return [("pares", list(range(2, total + 1, 2))),
            ("impares", list(range(1, total + 1, 2)))]


def partes_de_cortes(total, pontos):
    """Pontos de corte APÓS a página X: '5' ou '5,12' →
    [(parte1,[1..5]), (parte2,[6..12]), (parte3,[13..fim])].
    Pontos fora de 1..total-1 são ignorados."""
    ps = set()
    for pedaco in str(pontos or "").split(","):
        pedaco = pedaco.strip()
        if pedaco.isdigit() and 1 <= int(pedaco) < total:
            ps.add(int(pedaco))
    limites = [0] + sorted(ps) + [total]
    return [(f"parte{i + 1}", list(range(limites[i] + 1, limites[i + 1] + 1)))
            for i in range(len(limites) - 1)]


def partes_de_intervalos(total, texto):
    """'1-4,5-9' → [('grupo1',[1..4]), ('grupo2',[5..9])] na ordem digitada;
    grupos sem páginas válidas são ignorados."""
    partes = []
    for idx, pedaco in enumerate(str(texto or "").split(","), start=1):
        sels = sorted(_paginas_de_filtro(pedaco, total))
        if sels:
            partes.append((f"grupo{idx}", sels))
    return partes


def partes_pagina_a_pagina(total, texto_filtro):
    """'todas' ou '1,3-5' → uma parte por página ([('pag1',[1]), …])."""
    return [(f"pag{p}", [p])
            for p in sorted(_paginas_de_filtro(texto_filtro, total))]


def op_dividir_partes(caminho_in, modo, parametro, pasta_saida, base_name,
                      biblioteca="pymupdf"):
    """Divide em VÁRIOS PDFs. modo: 'pagina' | 'parimpar' | 'cortes' |
    'intervalos'; parametro depende do modo ('' para parimpar).
    biblioteca: 'auto'|'pymupdf'|'pikepdf'|'pypdf' (aplicada por parte;
    'auto' tenta pymupdf → pikepdf → pypdf).

    Retorna (ok, dados, aviso):
      ok=True  → dados=[(caminho, sufixo)], aviso='' ou falhas parciais
      ok=False → dados=msg do motivo, aviso=''
    """
    import pymupdf
    try:
        doc = pymupdf.open(caminho_in)
        total = len(doc)
        doc.close()
    except Exception as e:
        _log().error(f"PDF ilegível para divisão: {caminho_in}")
        return False, f"PDF ilegível: {e}", ""

    modo_norm = (modo or "").strip().lower()
    if modo_norm == "pagina":
        partes = partes_pagina_a_pagina(total, parametro)
    elif modo_norm == "parimpar":
        partes = partes_pares_impares(total)
    elif modo_norm == "cortes":
        partes = partes_de_cortes(total, parametro)
        if len(partes) <= 1:
            # sem ponto válido (< total) não há divisão: recusar em vez de
            # devolver o documento inteiro disfarçado de "parte1"
            return False, ("Nenhum ponto de corte válido — informe páginas "
                           f"entre 1 e {total - 1} (ex.: 5 ou 5,12)"), ""
    elif modo_norm == "intervalos":
        partes = partes_de_intervalos(total, parametro)
    else:
        return False, f"modo de divisão desconhecido: {modo}", ""

    if not partes:
        return False, "Nenhuma página válida para este modo/filtro", ""
    if any(not pags for _s, pags in partes):
        return False, "Uma das partes ficou vazia (verifique pontos/limites)", ""

    libs = _libs_da_preferencia(biblioteca)
    resultados, erros = [], []
    for sufixo, pags in partes:
        destino = os.path.join(pasta_saida, f"{base_name}_{sufixo}.pdf")
        feito = False
        ultimo_erro = ""
        for bib in libs:
            try:
                _extrair_paginas(caminho_in, pags, destino, bib)
                resultados.append((destino, sufixo))
                feito = True
                break
            except Exception as e:
                ultimo_erro = f"{sufixo} via {bib}: {e}"
        if not feito:
            erros.append(ultimo_erro)

    if not resultados:
        _log().error(f"falha na divisão em partes de {caminho_in}: " +
                     ("; ".join(erros) if erros else "sem partes geradas"))
        return False, ("falha na divisão — " + "; ".join(erros)), ""
    if erros:
        _log().warning(f"divisão parcial de {caminho_in}: {len(erros)} falha(s) — " +
                       "; ".join(erros))
    aviso = ("FALHAS parciais: " + "; ".join(erros)) if erros else ""
    return True, resultados, aviso


def op_verificar(caminho_in):
    """Checks PDF integrity (opens and counts pages). Returns (ok, msg)."""
    try:
        import pymupdf
        doc = pymupdf.open(caminho_in)
        n = len(doc)
        doc.close()
        return True, f"PDF íntegro ({n} página(s))"
    except Exception as e:
        _log().error(f"PDF inválido/corrompido: {caminho_in}")
        return False, f"PDF corrompido ou inválido: {e}"
