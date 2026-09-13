"""
Testes automatizados executados pela etapa de CI (Continuous Integration).

Cobrem:
  - Cenario de SUCESSO: deteccao correta de duplicidade em uma base valida.
  - Cenario de FALHA: base com schema invalido deve ser rejeitada.
  - Cenario de FALHA: taxa de duplicidade acima do limite deve reprovar
    o portao de qualidade (retorno != 0 na funcao principal).
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from validar_duplicatas import (  # noqa: E402
    ValidacaoError,
    carregar_base,
    detectar_duplicatas,
    validar,
)

RAIZ = Path(__file__).resolve().parents[1]
CSV_REAL = RAIZ / "data" / "duplicates_2.csv"


# ---------------------------------------------------------------------------
# CENARIO DE SUCESSO
# ---------------------------------------------------------------------------

def test_deteccao_encontra_claim_id_repetido():
    df = pd.DataFrame(
        {
            "claim_id": ["C1", "C2", "C1", "C3"],
            "employee_id": ["E1", "E2", "E1", "E3"],
            "employee_name": ["A", "B", "A", "C"],
            "department": ["TI", "TI", "TI", "RH"],
            "submitter_id": ["x", "y", "x", "z"],
            "amount": [100.0, 200.0, 100.0, 300.0],
            "date": ["2024-01-01"] * 4,
            "provider": ["P1", "P2", "P1", "P3"],
            "service_code": ["S1", "S2", "S1", "S3"],
            "timestamp": ["2024-01-01 10:00:00"] * 4,
            "status": ["Approved"] * 4,
        }
    )
    duplicados = detectar_duplicatas(df)
    assert duplicados.tolist() == [False, False, True, False]


def test_validar_com_base_real_passa_no_portao_de_qualidade():
    df = carregar_base(str(CSV_REAL))
    resultado = validar(df, limite_duplicidade=0.15)

    assert resultado.total_linhas == len(df)
    assert resultado.total_duplicados_detectados > 0
    assert resultado.passou_no_portao_de_qualidade is True
    # A deteccao por claim_id encontra 100% dos GRUPOS de duplicidade
    # (todo claim_id repetido tem uma ocorrencia marcada). A precisao
    # linha-a-linha contra o rotulo historico fica em torno de 47%,
    # porque a base historica marca ora a 1a, ora a 2a ocorrencia como
    # "is_duplicate" -- um achado de qualidade de dados documentado no
    # relatorio tecnico.
    grupos_com_duplicidade = df["claim_id"].value_counts()
    grupos_com_duplicidade = grupos_com_duplicidade[grupos_com_duplicidade > 1].index
    grupos_marcados_por_rotulo = df.loc[df["is_duplicate"], "claim_id"].unique()
    assert set(grupos_com_duplicidade) == set(grupos_marcados_por_rotulo)
    assert resultado.recall > 0.4


def test_execucao_via_linha_de_comando_sucesso(tmp_path):
    script = RAIZ / "src" / "validar_duplicatas.py"
    resultado = subprocess.run(
        [sys.executable, str(script), str(CSV_REAL),
         "--reports-dir", str(tmp_path / "reports"),
         "--site-dir", str(tmp_path / "site")],
        capture_output=True, text=True,
    )
    assert resultado.returncode == 0
    assert (tmp_path / "reports" / "duplicates_report.json").exists()
    assert (tmp_path / "site" / "index.html").exists()


# ---------------------------------------------------------------------------
# CENARIOS DE FALHA
# ---------------------------------------------------------------------------

def test_schema_invalido_gera_erro(tmp_path):
    csv_invalido = tmp_path / "claims_sem_colunas.csv"
    csv_invalido.write_text("id,nome\n1,teste\n")

    with pytest.raises(ValidacaoError):
        carregar_base(str(csv_invalido))


def test_arquivo_inexistente_gera_erro():
    with pytest.raises(ValidacaoError):
        carregar_base("caminho/que/nao/existe.csv")


def test_execucao_via_linha_de_comando_falha_schema_invalido(tmp_path):
    script = RAIZ / "src" / "validar_duplicatas.py"
    csv_invalido = tmp_path / "invalido.csv"
    csv_invalido.write_text("coluna_errada\nvalor\n")

    resultado = subprocess.run(
        [sys.executable, str(script), str(csv_invalido)],
        capture_output=True, text=True,
    )
    assert resultado.returncode == 2
    assert "Erro de validacao de schema" in resultado.stderr


def test_execucao_falha_quando_taxa_de_duplicidade_e_maior_que_limite():
    df = carregar_base(str(CSV_REAL))
    # forcamos um limite extremamente baixo para simular reprovacao do portao
    resultado = validar(df, limite_duplicidade=0.001)
    assert resultado.passou_no_portao_de_qualidade is False
