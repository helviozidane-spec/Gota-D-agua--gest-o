import json
from datetime import datetime
from pathlib import Path

import os
import requests
from dotenv import load_dotenv

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Gota Encomenda",
    layout="wide"
)

BASE_DIR = Path(__file__).parent
# ============================================================
# CODA
# ============================================================

load_dotenv()

CODA_TOKEN = os.getenv("CODA_API_TOKEN")


def _normalizar_nome(nome):
    if nome is None:
        return ""
    return (
        str(nome)
        .strip()
        .lower()
        .replace("’", "'")
        .replace("`", "'")
    )


def _coda_headers():
    if not CODA_TOKEN:
        raise Exception(
            "CODA_API_TOKEN não encontrado no ficheiro .env"
        )

    return {
        "Authorization": f"Bearer {CODA_TOKEN}",
        "Content-Type": "application/json"
    }


def _encontrar_documento_gota():
    headers = _coda_headers()

    resposta = requests.get(
        "https://coda.io/apis/v1/docs",
        headers=headers,
        timeout=30
    )

    if resposta.status_code != 200:
        raise Exception(
            f"Erro ao procurar documentos no Coda "
            f"({resposta.status_code}): {resposta.text}"
        )

    for doc in resposta.json().get("items", []):
        if _normalizar_nome(doc.get("name")) == "gota d'agua":
            return doc.get("id"), doc.get("name")

    raise Exception(
        "Documento 'Gota D'agua' não encontrado."
    )


def _encontrar_tabela_gestao(doc_id):
    headers = _coda_headers()

    url = f"https://coda.io/apis/v1/docs/{doc_id}/tables"

    resposta = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    if resposta.status_code != 200:
        raise Exception(
            f"Erro ao procurar tabelas "
            f"({resposta.status_code}): {resposta.text}"
        )

    for tabela in resposta.json().get("items", []):
        if _normalizar_nome(tabela.get("name")) == "gestão de encomendas":
            return tabela.get("id"), tabela.get("name")

    raise Exception(
        "Tabela 'Gestão de encomendas' não encontrada."
    )


def _obter_colunas(doc_id, table_id):
    headers = _coda_headers()

    url = (
        f"https://coda.io/apis/v1/docs/"
        f"{doc_id}/tables/{table_id}/columns"
    )

    resposta = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    if resposta.status_code != 200:
        raise Exception(
            f"Erro ao procurar colunas "
            f"({resposta.status_code}): {resposta.text}"
        )

    return {
        _normalizar_nome(coluna.get("name")): coluna.get("id")
        for coluna in resposta.json().get("items", [])
        if coluna.get("name") and coluna.get("id")
    }


def enviar_encomenda_coda(dados):
    headers = _coda_headers()

    # Descobrir automaticamente o documento correto
    doc_id, doc_nome = _encontrar_documento_gota()

    # Descobrir automaticamente a tabela correta
    table_id, table_nome = _encontrar_tabela_gestao(doc_id)

    # Descobrir automaticamente os IDs das colunas
    column_ids = _obter_colunas(doc_id, table_id)

    cells = []

    def adicionar_coluna(nome, valor):
        chave = _normalizar_nome(nome)

        if chave not in column_ids:
            print(f"⚠️ Coluna não encontrada: {nome}")
            return

        if valor is None:
            return

        cells.append({
            "column": column_ids[chave],
            "value": valor
        })

    # Descrição dos artigos
    descricoes = []

    for artigo in dados.get("artigos", []):
        nome = str(artigo.get("artigo", "")).strip()
        variante = str(artigo.get("variante", "")).strip()
        unidades = artigo.get("unidades", 1)

        if variante:
            descricoes.append(
                f"{nome} - {variante} x{unidades}"
            )
        else:
            descricoes.append(
                f"{nome} x{unidades}"
            )

    descricao = "; ".join(descricoes)

    # Dados principais
    adicionar_coluna("Nº de encomenda", dados.get("numero_encomenda"))
    adicionar_coluna("Data", dados.get("data"))
    adicionar_coluna("Cliente", dados.get("cliente"))
    adicionar_coluna("Descrição", descricao)
    adicionar_coluna("Quantidade", dados.get("total_unidades"))
    adicionar_coluna("Contacto", dados.get("contacto"))

    adicionar_coluna("Câmbio Compra", dados.get("cambio_compra"))
    adicionar_coluna("Total da encomenda",dados.get("valor_euros"))
    adicionar_coluna("Pago", dados.get("percentagem"))

    # Mantemos a lógica atual do app:
    # preço/custo de compra em Kz.
    adicionar_coluna("Preço compra", dados.get("valor_custo_kz"))

    adicionar_coluna("Câmbio Venda", dados.get("cambio_venda"))
    adicionar_coluna("Preço venda", dados.get("valor_total_kz"))

    adicionar_coluna("Pagamento", dados.get("pagamento"))
    adicionar_coluna("Valor pago", dados.get("valor_pago"))
    adicionar_coluna("Valor pendente", dados.get("valor_pendente"))

    adicionar_coluna("Total artigos", dados.get("total_artigos"))
    adicionar_coluna("Total unidades", dados.get("total_unidades"))

    if not cells:
        raise Exception(
            "Nenhuma coluna da tabela foi reconhecida."
        )

    url = (
        f"https://coda.io/apis/v1/docs/"
        f"{doc_id}/tables/{table_id}/rows"
    )

    payload = {
        "rows": [
            {
                "cells": cells
            }
        ]
    }

    print("\n========== CODA ==========")
    print("DOCUMENTO:", doc_nome)
    print("DOC ID:", doc_id)
    print("TABELA:", table_nome)
    print("TABLE ID:", table_id)
    print("COLUNAS ENVIADAS:", len(cells))
    print("==========================")

    # Apenas UM POST.
    resposta = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30
    )

    print("CÓDIGO CODA:", resposta.status_code)
    print("RESPOSTA CODA:", resposta.text)

    if resposta.status_code not in [200, 201, 202]:
        raise Exception(
            f"Erro Coda {resposta.status_code}: {resposta.text}"
        )

    return resposta.json()


PASTA_FATURAS = BASE_DIR / "faturas"
PASTA_FATURAS.mkdir(exist_ok=True)

CONTADOR = BASE_DIR / "contador.json"


# ============================================================
# LOCALIZAR LOGÓTIPO
# ============================================================

possiveis_logos = [
    BASE_DIR / "logo_gota.jpg",
    BASE_DIR / "logo_gota.jpeg",
    BASE_DIR / "logo_gota.png",
]

LOGO = None

for caminho_logo in possiveis_logos:
    if caminho_logo.exists():
        LOGO = caminho_logo
        break


# ============================================================
# CONTADOR DAS ENCOMENDAS
# ============================================================

def obter_numero_encomenda():

    if not CONTADOR.exists():

        CONTADOR.write_text(
            json.dumps(
                {"ultimo_numero": 0}
            ),
            encoding="utf-8"
        )

    try:

        dados = json.loads(
            CONTADOR.read_text(
                encoding="utf-8"
            )
        )

        ultimo_numero = int(
            dados.get(
                "ultimo_numero",
                0
            )
        )

        return ultimo_numero + 1

    except Exception:

        return 1


def guardar_numero_encomenda(numero):

    CONTADOR.write_text(
        json.dumps(
            {
                "ultimo_numero": int(numero)
            },
            indent=4
        ),
        encoding="utf-8"
    )


# ============================================================
# INICIALIZAÇÃO DA SESSÃO
# ============================================================

if "numero_encomenda" not in st.session_state:

    st.session_state.numero_encomenda = (
        obter_numero_encomenda()
    )


if "artigos" not in st.session_state:

    st.session_state.artigos = [
        {
            "nome": "",
            "variante": "",
            "valor_unitario": 0.0,
            "unidades": 1
        }
    ]


if "ultima_encomenda" not in st.session_state:

    st.session_state.ultima_encomenda = None


# ============================================================
# FUNÇÕES DOS ARTIGOS
# ============================================================

def adicionar_artigo():

    st.session_state.artigos.append(
        {
            "nome": "",
            "variante": "",
            "valor_unitario": 0.0,
            "unidades": 1
        }
    )


def remover_artigo(indice):

    if len(st.session_state.artigos) > 1:

        st.session_state.artigos.pop(indice)


def calcular_total_artigo(artigo):

    return (
        float(artigo["valor_unitario"])
        *
        int(artigo["unidades"])
    )


def obter_artigos_validos():

    return [
        artigo
        for artigo in st.session_state.artigos
        if artigo["nome"].strip()
    ]


def calcular_total_encomenda():

    total = 0.0

    for artigo in obter_artigos_validos():

        total += calcular_total_artigo(
            artigo
        )

    return total


# ============================================================
# GERAR FATURA PDF
# ============================================================

def gerar_fatura(
    numero,
    cliente,
    contacto,
    artigos,
    valor_euros,
    cambio_venda,
    valor_total,
    pagamento,
    valor_pago,
    valor_pendente
):

    ficheiro = (
        PASTA_FATURAS
        /
        f"Encomenda_{numero:02d}.pdf"
    )

    pdf = canvas.Canvas(
        str(ficheiro),
        pagesize=A4
    )

    largura, altura = A4

    # ========================================================
    # LOGÓTIPO
    # ========================================================

    if LOGO is not None:

        try:

            logo = ImageReader(
                str(LOGO)
            )

            pdf.drawImage(
                logo,
                225,
                altura - 130,
                width=140,
                height=100,
                preserveAspectRatio=True,
                mask="auto"
            )

        except Exception:

            pass


    # ========================================================
    # CABEÇALHO
    # ========================================================

    y = altura - 145

    pdf.setFont(
        "Helvetica-Bold",
        18
    )

    pdf.drawCentredString(
        largura / 2,
        y,
        "GOTA D'ÁGUA"
    )

    y -= 20

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawCentredString(
        largura / 2,
        y,
        "DRIP COLLECTION"
    )

    y -= 25

    pdf.line(
        50,
        y,
        largura - 50,
        y
    )


    # ========================================================
    # NÚMERO
    # ========================================================

    y -= 30

    pdf.setFont(
        "Helvetica-Bold",
        16
    )

    pdf.drawCentredString(
        largura / 2,
        y,
        f"ENCOMENDA {numero:02d}"
    )


    # ========================================================
    # CLIENTE
    # ========================================================

    y -= 30

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        55,
        y,
        f"Data: "
        f"{datetime.now().strftime('%d/%m/%Y')}"
    )

    y -= 18

    pdf.drawString(
        55,
        y,
        f"Cliente: {cliente}"
    )

    if contacto:

        y -= 18

        pdf.drawString(
            55,
            y,
            f"Contacto: {contacto}"
        )


    # ========================================================
    # TABELA DE ARTIGOS
    # ========================================================

    y -= 30

    pdf.setFont(
        "Helvetica-Bold",
        8.5
    )

    pdf.drawString(
        45,
        y,
        "Nº"
    )

    pdf.drawString(
        70,
        y,
        "ARTIGO"
    )

    pdf.drawString(
        215,
        y,
        "COR / VARIANTE"
    )

    pdf.drawRightString(
        375,
        y,
        "UNIT."
    )

    pdf.drawRightString(
        445,
        y,
        "UNID."
    )

    pdf.drawRightString(
        540,
        y,
        "TOTAL"
    )

    y -= 12

    pdf.line(
        45,
        y,
        540,
        y
    )

    y -= 18

    pdf.setFont(
        "Helvetica",
        8.5
    )

    artigos_validos = [
        artigo
        for artigo in artigos
        if artigo["nome"].strip()
    ]

    for indice, artigo in enumerate(
        artigos_validos,
        start=1
    ):

        total_artigo = (
            calcular_total_artigo(
                artigo
            )
        )

        pdf.drawString(
            45,
            y,
            str(indice)
        )

        pdf.drawString(
            70,
            y,
            artigo["nome"][:24]
        )

        pdf.drawString(
            215,
            y,
            artigo["variante"][:25]
        )

        pdf.drawRightString(
            375,
            y,
            f"{artigo['valor_unitario']:,.2f} €"
        )

        pdf.drawRightString(
            445,
            y,
            str(artigo["unidades"])
        )

        pdf.drawRightString(
            540,
            y,
            f"{total_artigo:,.2f} €"
        )

        y -= 20


    # ========================================================
    # TOTAIS DOS ARTIGOS
    # ========================================================

    total_tipos = len(
        artigos_validos
    )

    total_unidades = sum(
        artigo["unidades"]
        for artigo in artigos_validos
    )

    y -= 10

    pdf.line(
        45,
        y,
        540,
        y
    )

    y -= 22

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawRightString(
        540,
        y,
        f"TIPOS DE ARTIGOS: {total_tipos}"
    )

    y -= 18

    pdf.drawRightString(
        540,
        y,
        f"TOTAL DE UNIDADES: {total_unidades}"
    )

    y -= 22

    pdf.drawRightString(
        540,
        y,
        f"TOTAL DA ENCOMENDA: "
        f"{valor_euros:,.2f} €"
    )


    # ========================================================
    # FINANCEIRO
    # ========================================================

    y -= 35

    pdf.setFont(
        "Helvetica",
        10
    )

    # IMPORTANTE:
    # NÃO mostramos o câmbio de compra na fatura.
    # Apenas o câmbio de venda.

    pdf.drawString(
        55,
        y,
        f"Câmbio de venda: "
        f"{cambio_venda:,.2f} Kz/€"
    )

    y -= 25

    pdf.setFont(
        "Helvetica-Bold",
        14
    )

    pdf.drawString(
        55,
        y,
        f"TOTAL A PAGAR: "
        f"{valor_total:,.0f} Kz"
    )


    # ========================================================
    # PAGAMENTO
    # ========================================================

    y -= 30

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawString(
        55,
        y,
        f"Pagamento: {pagamento}"
    )

    y -= 18

    pdf.drawString(
        55,
        y,
        f"Valor pago: "
        f"{valor_pago:,.0f} Kz"
    )

    y -= 18

    pdf.drawString(
        55,
        y,
        f"Valor em falta: "
        f"{valor_pendente:,.0f} Kz"
    )


    # ========================================================
    # RODAPÉ
    # ========================================================

    y -= 40

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawCentredString(
        largura / 2,
        y,
        "Obrigado pela sua preferência!"
    )

    pdf.save()

    return ficheiro


# ============================================================
# INTERFACE
# ============================================================

st.title(
    " Gota Encomenda"
)

st.caption(
    "Sistema de Registo de Encomendas"
)

st.divider()


# ============================================================
# DUAS COLUNAS
# ============================================================

coluna_esquerda, coluna_direita = st.columns(
    [1.05, 0.95]
)


# ============================================================
# ESQUERDA
# ============================================================

with coluna_esquerda:

    st.subheader(
        " ENCOMENDA"
    )


    # ========================================================
    # NÚMERO EDITÁVEL
    # ========================================================

    numero_encomenda = st.number_input(
        "Número da encomenda",
        min_value=1,
        value=int(
            st.session_state.numero_encomenda
        ),
        step=1
    )


    # ========================================================
    # CLIENTE
    # ========================================================

    st.markdown(
        "### 👤 Dados do cliente"
    )

    nome_cliente = st.text_input(
        "Nome do cliente",
        placeholder="Ex.: João Manuel"
    )

    contacto = st.text_input(
        "Contacto",
        placeholder="Ex.: +244 9XX XXX XXX"
    )


    # ========================================================
    # ARTIGOS
    # ========================================================

    st.markdown(
        "### 🛍️ Artigos"
    )


    # Cabeçalho

    h1, h2, h3, h4, h5 = st.columns(
        [2.8, 2, 1.4, 0.9, 0.6]
    )

    h1.markdown("**Artigo**")
    h2.markdown("**Cor / Variante**")
    h3.markdown("**Valor Unit. €**")
    h4.markdown("**Unid.**")
    h5.markdown("**Ação**")


    for i, artigo in enumerate(
        st.session_state.artigos
    ):

        c1, c2, c3, c4, c5 = st.columns(
            [2.8, 2, 1.4, 0.9, 0.6]
        )


        with c1:

            artigo["nome"] = st.text_input(
                "Artigo",
                value=artigo["nome"],
                key=f"nome_artigo_{i}",
                label_visibility="collapsed",
                placeholder="Nome do artigo"
            )


        with c2:

            artigo["variante"] = st.text_input(
                "Variante",
                value=artigo["variante"],
                key=f"variante_artigo_{i}",
                label_visibility="collapsed",
                placeholder="Cor / Tamanho"
            )


        with c3:

            artigo["valor_unitario"] = st.number_input(
                "Valor unitário",
                min_value=0.0,
                value=float(
                    artigo["valor_unitario"]
                ),
                step=0.50,
                format="%.2f",
                key=f"valor_unitario_{i}",
                label_visibility="collapsed"
            )


        with c4:

            artigo["unidades"] = st.number_input(
                "Unidades",
                min_value=1,
                value=int(
                    artigo["unidades"]
                ),
                step=1,
                key=f"unidades_artigo_{i}",
                label_visibility="collapsed"
            )


        with c5:

            if st.button(
                "🗑️",
                key=f"remover_artigo_{i}"
            ):

                remover_artigo(i)

                st.rerun()


        # Total automático do artigo

        if artigo["nome"].strip():

            total_artigo = (
                calcular_total_artigo(
                    artigo
                )
            )

            st.caption(
                f"Total do artigo: "
                f"{total_artigo:,.2f} €"
            )


    # ========================================================
    # ADICIONAR ARTIGO
    # ========================================================

    if st.button(
        "➕ Adicionar artigo",
        use_container_width=True
    ):

        adicionar_artigo()

        st.rerun()


    # ========================================================
    # RESUMO
    # ========================================================

    artigos_validos = (
        obter_artigos_validos()
    )

    total_tipos = len(
        artigos_validos
    )

    total_unidades = sum(
        artigo["unidades"]
        for artigo in artigos_validos
    )

    valor_euros = (
        calcular_total_encomenda()
    )


    resumo1, resumo2, resumo3 = st.columns(3)

    resumo1.metric(
        "Tipos de artigos",
        total_tipos
    )

    resumo2.metric(
        "Total de unidades",
        total_unidades
    )

    resumo3.metric(
        "Total da encomenda",
        f"{valor_euros:,.2f} €"
    )


    # ========================================================
    # FINANCEIRO
    # ========================================================

    st.markdown(
        "### 💰 Dados financeiros"
    )


    f1, f2 = st.columns(2)


    with f1:

        if "cambio_compra" not in st.session_state:
            st.session_state.cambio_compra = 1300.0

        cambio_compra = st.number_input(
            "Câmbio de compra (Kz/€)",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="cambio_compra"
        )


    with f2:

        if "cambio_venda" not in st.session_state:
            st.session_state.cambio_venda = 1600.0

        cambio_venda = st.number_input(
            "Câmbio de venda (Kz/€)",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="cambio_venda"
        )


    # ========================================================
    # CÁLCULOS
    # ========================================================

    valor_custo_kz = (
        valor_euros
        *
        cambio_compra
    )

    valor_venda_kz = (
        valor_euros
        *
        cambio_venda
    )

    margem = (
        valor_venda_kz
        -
        valor_custo_kz
    )


    r1, r2, r3 = st.columns(3)


    r1.metric(
        "Custo",
        f"{valor_custo_kz:,.0f} Kz"
    )

    r2.metric(
        "Total a pagar",
        f"{valor_venda_kz:,.0f} Kz"
    )

    r3.metric(
        "Margem",
        f"{margem:,.0f} Kz"
    )


    # ========================================================
    # PAGAMENTO
    # ========================================================

    st.markdown(
        "### 💳 Pagamento"
    )


    pagamento = st.selectbox(
        "Estado do pagamento",
        [
            "Não pago",
            "50% pago",
            "100% pago"
        ]
    )


    if pagamento == "Não pago":

        valor_pago = 0

    elif pagamento == "50% pago":

        valor_pago = (
            valor_venda_kz
            *
            0.50
        )

    else:

        valor_pago = valor_venda_kz


    valor_pendente = (
        valor_venda_kz
        -
        valor_pago
    )


    p1, p2 = st.columns(2)


    p1.metric(
        "Valor pago",
        f"{valor_pago:,.0f} Kz"
    )

    p2.metric(
        "Valor em falta",
        f"{valor_pendente:,.0f} Kz"
    )


    # ========================================================
    # BOTÃO
    # ========================================================

    st.markdown("---")


    if st.button(
        "✅ REGISTAR ENCOMENDA E GERAR FATURA",
        type="primary",
        use_container_width=True
    ):

        if not nome_cliente.strip():

            st.error(
                "Indique o nome do cliente."
            )

        elif not artigos_validos:

            st.error(
                "Adicione pelo menos um artigo."
            )

        elif any(
            artigo["valor_unitario"] <= 0
            for artigo in artigos_validos
        ):

            st.error(
                "Indique o valor unitário de todos os artigos."
            )

        elif cambio_compra <= 0:

            st.error(
                "Indique o câmbio de compra."
            )

        elif cambio_venda <= 0:

            st.error(
                "Indique o câmbio de venda."
            )

        else:

            # Número que está na caixa
            numero = int(
                numero_encomenda
            )


            # =================================================
            # GERAR PDF
            # =================================================

            ficheiro = gerar_fatura(
                numero=numero,
                cliente=nome_cliente.strip(),
                contacto=contacto.strip(),
                artigos=artigos_validos,
                valor_euros=valor_euros,
                cambio_venda=cambio_venda,
                valor_total=valor_venda_kz,
                pagamento=pagamento,
                valor_pago=valor_pago,
                valor_pendente=valor_pendente
            )


            # =================================================
            # GUARDAR O NÚMERO
            # =================================================

            guardar_numero_encomenda(
                numero
            )


            # =================================================
            # PREPARAR PRÓXIMO NÚMERO
            # =================================================

            proximo_numero = (
                numero + 1
            )

            st.session_state.numero_encomenda = (
                proximo_numero
            )


            # =================================================
            # DADOS PARA O CODA
            # =================================================

            dados_coda = {

                "numero_encomenda":
                    f"{numero:02d}",

                "data":
                    datetime.now().strftime(
                        "%Y-%m-%d"
                    ),


                "cliente":
                    nome_cliente.strip(),

                "contacto":
                    contacto.strip(),

                "valor_euros":
                    round(
                        valor_euros,
                        2
                    ),

                "cambio_compra":
                    cambio_compra,

                "cambio_venda":
                    cambio_venda,

                "valor_custo_kz":
                    round(
                        valor_custo_kz,
                        2
                    ),

                "valor_total_kz":
                    round(
                        valor_venda_kz,
                        2
                    ),

                "pagamento":
                    pagamento,
                "percentagem":
                    0
                    if pagamento == "Não pago"
                    else 0.50
                    if pagamento == "50% pago"
                    else 1.00,

                "valor_pago":
                    round(
                        valor_pago,
                        2
                    ),

                "valor_pendente":
                    round(
                        valor_pendente,
                        2
                    ),

                "total_artigos":
                    total_tipos,

                "total_unidades":
                    total_unidades,

                "artigos": [

                    {
                        "artigo":
                            artigo["nome"],

                        "variante":
                            artigo["variante"],

                        "valor_unitario":
                            round(
                                artigo[
                                    "valor_unitario"
                                ],
                                2
                            ),

                        "unidades":
                            artigo["unidades"],

                        "total_artigo":
                            round(
                                calcular_total_artigo(
                                    artigo
                                ),
                                2
                            )
                    }

                    for artigo
                    in artigos_validos
                ]
            }


            st.session_state.ultima_encomenda = (
                dados_coda
            )
            # ============================================================
            # ENVIAR ENCOMENDA PARA O CODA
            # ============================================================

            try:

                resposta_coda = enviar_encomenda_coda(
                    dados_coda
                )

                st.success(
                    "☑️ Encomenda enviada para o Coda com sucesso!"
                )

                st.write(
                    "Resposta do Coda:"
                )

                st.json(
                    resposta_coda
                )

            except Exception as erro:

                st.error(
                    "❌ A encomenda foi criada, "
                    "mas não foi possível enviá-la para o Coda."
                )

                st.code(
                    str(erro)
                )


            # =================================================
            # MENSAGEM
            # =================================================

            st.success(
                f"✅ ENCOMENDA "
                f"{numero:02d} "
                f"registada com sucesso!"
            )


            st.info(
                "A fatura foi gerada com sucesso."
            )


            # =================================================
            # DOWNLOAD
            # =================================================

            with open(
                ficheiro,
                "rb"
            ) as pdf_file:

                st.download_button(
                    label="🧾 Descarregar Fatura PDF",
                    data=pdf_file,
                    file_name=(
                        f"Encomenda_{numero:02d}.pdf"
                    ),
                    mime="application/pdf",
                    use_container_width=True
                )


            st.write(
                f"**Próxima encomenda:** "
                f"{proximo_numero:02d}"
            )


            # =================================================
            # LIMPAR ARTIGOS
            # =================================================

            st.session_state.artigos = [
                {
                    "nome": "",
                    "variante": "",
                    "valor_unitario": 0.0,
                    "unidades": 1
                }
            ]


# ============================================================
# DIREITA — PRÉ-VISUALIZAÇÃO
# ============================================================

with coluna_direita:

    st.subheader(
        "🧾 Pré-visualização da Fatura"
    )


    # ========================================================
    # LOGÓTIPO
    # ========================================================

    if LOGO is not None:

        st.image(
            str(LOGO),
            width=180
        )

    else:

        st.warning(
            "⚠️ Logótipo não encontrado."
        )


    # ========================================================
    # NÚMERO
    # ========================================================

    st.markdown(
        f"## ENCOMENDA "
        f"{int(numero_encomenda):02d}"
    )


    # ========================================================
    # CLIENTE
    # ========================================================

    st.write(
        f"**Data:** "
        f"{datetime.now().strftime('%d/%m/%Y')}"
    )

    st.write(
        f"**Cliente:** "
        f"{nome_cliente or '—'}"
    )


    if contacto:

        st.write(
            f"**Contacto:** "
            f"{contacto}"
        )


    st.divider()


    # ========================================================
    # ARTIGOS
    # ========================================================

    st.markdown(
        "#### 🛍️ Artigos"
    )


    if artigos_validos:

        for i, artigo in enumerate(
            artigos_validos,
            start=1
        ):

            total_artigo = (
                calcular_total_artigo(
                    artigo
                )
            )


            variante = (
                artigo["variante"]
                if artigo["variante"].strip()
                else "—"
            )


            c1, c2, c3 = st.columns(
                [4, 2, 1.5]
            )


            with c1:

                st.write(
                    f"**{i}. "
                    f"{artigo['nome']}**"
                )

                st.caption(
                    variante
                )


            with c2:

                st.write(
                    f"{artigo['valor_unitario']:,.2f} €"
                )

                st.caption(
                    f"× {artigo['unidades']}"
                )


            with c3:

                st.write(
                    f"**{total_artigo:,.2f} €**"
                )


        st.success(
            f"{total_tipos} tipos de artigos · "
            f"{total_unidades} unidades"
        )


    else:

        st.info(
            "Adicione os artigos da encomenda."
        )


    st.divider()


    # ========================================================
    # TOTAL EM EUROS
    # ========================================================

    st.markdown(
        f"### TOTAL DA ENCOMENDA: "
        f"{valor_euros:,.2f} €"
    )


    # ========================================================
    # FINANCEIRO
    # ========================================================

    st.write(
        f"**Câmbio de venda:** "
        f"{cambio_venda:,.2f} Kz/€"
    )


    st.markdown(
        f"### TOTAL A PAGAR: "
        f"{valor_venda_kz:,.0f} Kz"
    )


    # ========================================================
    # PAGAMENTO
    # ========================================================

    st.write(
        f"**Pagamento:** "
        f"{pagamento}"
    )

    st.write(
        f"**Valor pago:** "
        f"{valor_pago:,.0f} Kz"
    )

    st.write(
        f"**Valor em falta:** "
        f"{valor_pendente:,.0f} Kz"
    )


    # ========================================================
    # CODA
    # ========================================================

    if st.session_state.ultima_encomenda:

        st.divider()

        st.subheader(
            "📊 Resumo da encomenda para Coda"
        )

        st.json(
            st.session_state.ultima_encomenda

        )