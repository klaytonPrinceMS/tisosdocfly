"""Leitura de usuários para a Lista Telefônica (27/09/2026).

Fica em arquivo próprio, e não dentro de `bd_manipulador.py`, por dois motivos
concretos:

1. **Não quebra quem já consome.** `obter_usuario` e `listar_usuarios` devolvem
   tuplas de tamanho fixo e são lidas **por índice** em vários pontos do
   sistema. Acrescentar as colunas novas (`cargo`, `unidade`, `lotacao`) a essas
   tuplas mudaria a forma do retorno e quebraria quem consome. Aqui as funções
   devolvem **dicionário**, que não tem posição fixa.
2. **A ponte entre os dois módulos é pequena e óbvia.** Tudo que a lista
   telefônica precisa saber de um usuário está nesta página.

O que a lista telefônica enxerga de um servidor: nome para exibição (primeiro +
último), cargo, unidade, lotação e o telefone **da empresa**. O telefone
particular existe no cadastro, mas **não sai daqui** — é a diferença entre o
que a prefeitura publica e o que é do servidor.

EN: Read-only bridge for the phone directory. Returns dicts (not fixed-size
tuples) so the existing positional callers of `obter_usuario` keep working, and
exposes only COMPANY phone numbers to the directory.
"""

import re
import unicodedata

from mod_gest_cad_usuario import bd_manipulador as bd  # noqa: E402


def _norm(texto):
    """Normaliza para busca: sem acento, sem pontuação, minúsculo.

    Fica AQUI, e não>importado de outro módulo', por três motivos:
    o banco de usuários é deste módulo e não pode depender do organograma
    (e a regra de isolamento do projeto cobra); a
    função é de duas linhas; e o outro módulo pode mudar a sua sem quebrar
    este. O mesmo desenho de `bd_manipulador._norm`, copiado de propósito.
    """
    try:
        limpo = unicodedata.normalize("NFKD", str(texto or "")) \
            .encode("ascii", "ignore").decode().lower()
        return " ".join(re.findall(r"[a-z0-9]+", limpo))
    except Exception:
        return str(texto or "").lower()


def _log():
    """Logger do módulo (loguru), com fallback para o logger do bd."""
    try:
        from mod_tisosdocfly import observabilidade
        return observabilidade.get_logger("lista_telefonica")
    except Exception:
        import logging
        return logging.getLogger("lista_telefonica")


def nome_para_exibicao(nome_completo: str) -> str:
    """Nome como a LISTA TELEFÔNICA mostra: primeiro + último nome.

    "Ana Beatriz Souza Rocha" vira "Ana Rocha". A lista é um diretório, não um
    prontuário: o nome inteiro fica no cadastro, que é onde ele serve. Sem
    sobrenome, devolve o que houver.
    """
    partes = [p for p in (nome_completo or "").split() if p]
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0]
    return f"{partes[0]} {partes[-1]}"


def _para_dict(linha):
    """Converte a linha do SELECT no dicionário que a lista consome.

    Índice 7 e 8 são `vinculo` e `situacao` (veja `_SELECT`). São lidos com
    `len(linha) > n` porque esta função também pode receber linha de um SELECT
    mais curto em outro ponto do módulo — e um `IndexError` aqui derrubaria a
    tela inteira em vez de devolver um campo a menos.
    """
    nome_exibicao = nome_para_exibicao(linha[1])
    return {
        "user_nome": linha[0],
        "nome_completo": linha[1] or "",
        "nome_exibicao": nome_exibicao,
        "cargo": linha[2] or "",
        "unidade": linha[3] or "",
        "lotacao": linha[4] or "",
        "ativo": bool(linha[5]) and not bool(linha[6]),
        "vinculo": (linha[7] or "") if len(linha) > 7 else "",
        "situacao": (linha[8] or "") if len(linha) > 8 else "",
        "telefone": bd.telefone_empresa_principal(linha[0]),
        "recado": bd.telefone_e_recado(linha[0]),
    }


# `vinculo` e `situacao` entram na leitura (28/09/2026) porque a lista
# telefônica precisa responder "é efetivo?" e "está ativo?" de quem não
# autorizou telefone. A leitura é sobre o CADASTRO, não sobre o diretório
# publicado: nome, cargo, secretaria e lotação são publicação legal (Lei
# 12.527/2011) e quem está na folha é quem ocupa o posto — o que é privado é o
# NÚMERO, e o número continua vindo só de quem autorizou.
_SELECT = ("SELECT user_nome, user_nome_completo, cargo, unidade, lotacao, "
           "user_ativo, user_deletado, vinculo, situacao FROM tb_usuarios")


def obter_usuario_para_lista(user_nome):
    """Dados do usuário para a lista telefônica, ou None.

    Devolve `user_nome` (matrícula), `nome_exibicao` (1º + último),
    `nome_completo`, `cargo`, `unidade`, `lotacao`, `ativo` e `telefone` (o da
    empresa marcado como principal, ou o primeiro da empresa). `telefone` pode
    vir None — servidor sem telefone de empresa fica sem número, que é
    honesto.
    """
    try:
        conn = bd.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(_SELECT + " WHERE user_nome=?", (user_nome,))
            linha = cur.fetchone()
        finally:
            conn.close()
        return _para_dict(linha) if linha else None
    except Exception as e:
        _log().exception(
            f"obter_usuario_para_lista: falha em {user_nome} | {e}")
        return None


def buscar_usuarios_para_lista(termo: str = "", limite: int = 50):
    """Busca usuários cadastráveis para vincular a um contato da lista.

    Serve à tela da lista telefônica quando o administrador quer atrelar um
    contato a um servidor já cadastrado, em vez de digitar o nome de novo.
    Filtra por nome (com ou sem acento), matrícula, cargo, unidade e lotação, e
    entra quem está **ativo OU bloqueado, desde que não excluído** — o
    diretório mostra o posto público (nome, cargo, secretaria), e bloqueio de
    acesso não apaga posto (decisão de 07/10/2026). Só o excluído (remoção pelo
    administrador) fica de fora. Desde 17/10/2026 filtra também pelo
    **telefone da empresa** (só dígitos, para achar por ramal/celular).

    A ordem é alfabética pelo nome de exibição, que é como o diretório mostra.
    """
    try:
        termo_n = _norm(termo) if termo else ""
        conn = bd.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(_SELECT + " WHERE (user_deletado IS NULL OR user_deletado=0)")
            linhas = cur.fetchall()
        finally:
            conn.close()
        achados = []
        try:
            fones = bd.telefones_empresa_em_lote()
        except Exception:
            fones = {}
        try:
            recados = bd.telefones_de_recado_em_lote(
                [r[0] for r in linhas])
        except Exception:
            recados = {}
        for r in linhas:
            nome_exibicao = nome_para_exibicao(r[1])
            try:
                fone = "".join(
                    c for c in str(fones.get(r[0]) or "") if c.isdigit())
            except Exception:
                fone = ""
            alvo = " ".join([r[0] or "", nome_exibicao, r[1] or "", r[2] or "",
                             r[3] or "", r[4] or "", fone])
            if termo_n and termo_n not in _norm(alvo):
                continue
            # Monta o dict AQUI em vez de `_para_dict`: ele abre 2 conexões
            # por usuário (`telefone_empresa_principal` + `telefone_e_recado`
            # — medido: 6,5 s para 1.157 usuários). Telefone e recado já
            # vieram nos lotes acima; o resto é coluna do SELECT.
            achados.append({
                "user_nome": r[0],
                "nome_completo": r[1] or "",
                "nome_exibicao": nome_exibicao,
                "cargo": r[2] or "",
                "unidade": r[3] or "",
                "lotacao": r[4] or "",
                "ativo": True,
                "vinculo": (r[7] or "") if len(r) > 7 else "",
                "situacao": (r[8] or "") if len(r) > 8 else "",
                "telefone": fones.get(r[0]),
                "recado": bool(recados.get(r[0], False)),
            })
        achados.sort(key=lambda d: (d["nome_exibicao"].casefold(), d["user_nome"]))
        return achados[:limite] if limite else achados
    except Exception as e:
        _log().exception(f"buscar_usuarios_para_lista: falha com {termo!r} | {e}")
        return []


def listar_para_vinculo(limite: int = 20):
    """Usuários ativos e bloqueados (não excluídos), para a lista de escolha."""
    return buscar_usuarios_para_lista("", limite=limite)


def listar_para_lista_telefonica():
    """Todos os usuários não excluídos, com o telefone publicável, para a lista.

    É esta função que alimenta `sincronizar_contatos_do_cadastro` no módulo
    da lista telefônica. Traz **só quem não foi excluído: ativo e bloqueado**.
    Servidor bloqueado (acesso ainda não liberado pelo DTI) ENTRA — o
    diretório mostra o posto público (decisão de 07/10/2026), e bloqueio de
    acesso não apaga posto. Excluído (remoção pelo administrador) continua
    fora. Quem não liberou número entra com o telefone vazio, que é honesto.

    Os telefones vêm de UMA consulta (`bd.telefones_publicaveis_em_lote`) e
    não de uma por pessoa. A prefeitura tem mais de mil servidores, e
    abrir uma conexão por linha transformava a montagem da lista em uma
    eternidade — o sintoma era a tela "carregando" sem nunca terminar.
    """
    try:
        conn = bd.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(_SELECT + " WHERE (user_deletado IS NULL OR user_deletado=0)")
            linhas = cur.fetchall()
        finally:
            conn.close()
        if not linhas:
            return []
        telefones = bd.telefones_publicaveis_em_lote([r[0] for r in linhas])
        telefones_recado = bd.telefones_de_recado_em_lote([r[0] for r in linhas])
        try:
            todos_tels = bd.telefones_publicaveis_todos_em_lote(
                [r[0] for r in linhas])
        except Exception:
            todos_tels = {}
        saida = []
        for r in linhas:
            # NÃO usar `_para_dict` aqui: ela chama `telefone_empresa_principal`,
            # que abre uma conexão POR LINHA. Com mais de mil servidores isso
            # levava seis segundos — e o resultado era jogado fora logo abaixo,
            # substituído pelo telefone do lote. A versão abaixo monta o mesmo
            # dicionário sem essa ida ao banco.
            saida.append({
                "user_nome": r[0],
                "nome_completo": r[1] or "",
                "nome_exibicao": nome_para_exibicao(r[1]),
                "cargo": r[2] or "",
                "unidade": r[3] or "",
                "lotacao": r[4] or "",
                "ativo": True,
                "vinculo": (r[7] or "") if len(r) > 7 else "",
                "situacao": (r[8] or "") if len(r) > 8 else "",
                "telefone": telefones.get(r[0]),
                "telefones": list((todos_tels or {}).get(r[0]) or []),
                "recado": telefones_recado.get(r[0], False),
            })
        saida.sort(key=lambda d: (d["nome_exibicao"].casefold(), d["user_nome"]))
        return saida
    except Exception as e:
        _log().exception(f"listar_para_lista_telefonica: falha | {e}")
        return []
