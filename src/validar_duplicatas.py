"""
validar_duplicatas.py

Etapa de VALIDACAO AUTOMATIZADA da pipeline de CI/CD.

Problema de negocio:
    A base de reembolsos/sinistros (claims) recebe lancamentos de varios
    setores. Por falha operacional (duplo clique, reenvio de formulario,
    integracao duplicada entre sistemas), o MESMO claim_id pode acabar
    inserido mais de uma vez na base, gerando risco de pagamento em
    duplicidade.

O que este script automatiza:
    1. Le a base de claims (CSV).
    2. Identifica linhas com claim_id repetido (duplicidade exata de
       lancamento) e calcula metricas de qualidade de dados.
    3. Compara a deteccao automatica com o rotulo historico "is_duplicate"
       ja existente na base, calculando precisao/recall (validacao do
       modelo de deteccao).
    4. Gera relatorios (JSON e TXT) em reports/ e uma pagina HTML em
       site/index.html, publicada depois via GitHub Pages.
    5. Define um "portao de qualidade": se a taxa de duplicidade
       ultrapassar o limite configurado, o script termina com codigo de
       saida != 0, fazendo a etapa de CI falhar de propósito
       (cenario de falha exigido pelo trabalho).

Uso:
    python src/validar_duplicatas.py data/duplicates_2.csv \
        --limite-duplicidade 0.15
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

COLUNAS_OBRIGATORIAS = [
    "claim_id",
    "employee_id",
    "employee_name",
    "department",
    "submitter_id",
    "amount",
    "date",
    "provider",
    "service_code",
    "timestamp",
    "status",
]


class ValidacaoError(Exception):
    """Erro de validacao de schema/dados de entrada."""


@dataclass
class ResultadoValidacao:
    total_linhas: int
    total_duplicados_detectados: int
    taxa_duplicidade: float
    total_rotulo_historico: int
    verdadeiros_positivos: int
    falsos_positivos: int
    falsos_negativos: int
    precisao: float
    recall: float
    por_departamento: dict
    valor_total_em_risco: float
    limite_duplicidade: float
    passou_no_portao_de_qualidade: bool


def carregar_base(caminho_csv: str) -> pd.DataFrame:
    """Carrega e valida o schema minimo da base de claims."""
    caminho = Path(caminho_csv)
    if not caminho.exists():
        raise ValidacaoError(f"Arquivo nao encontrado: {caminho_csv}")

    df = pd.read_csv(caminho)

    faltantes = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltantes:
        raise ValidacaoError(
            "Schema invalido. Colunas obrigatorias ausentes: "
            f"{', '.join(faltantes)}"
        )

    if df.empty:
        raise ValidacaoError("A base de claims esta vazia.")

    if df["claim_id"].isnull().any():
        raise ValidacaoError("Existem linhas sem claim_id preenchido.")

    return df


def detectar_duplicatas(df: pd.DataFrame) -> pd.Series:
    """Marca como duplicado toda ocorrencia repetida do mesmo claim_id."""
    return df.duplicated(subset=["claim_id"], keep="first")


def validar(df: pd.DataFrame, limite_duplicidade: float) -> ResultadoValidacao:
    detectado = detectar_duplicatas(df)
    total = len(df)
    total_detectado = int(detectado.sum())
    taxa = total_detectado / total if total else 0.0

    tem_rotulo_historico = "is_duplicate" in df.columns
    if tem_rotulo_historico:
        rotulo = df["is_duplicate"].astype(bool)
        vp = int((detectado & rotulo).sum())
        fp = int((detectado & ~rotulo).sum())
        fn = int((~detectado & rotulo).sum())
        precisao = vp / (vp + fp) if (vp + fp) else 0.0
        recall = vp / (vp + fn) if (vp + fn) else 0.0
        total_rotulo = int(rotulo.sum())
    else:
        vp = fp = fn = total_rotulo = 0
        precisao = recall = 0.0

    por_departamento = (
        df.assign(_duplicado=detectado)
        .groupby("department")["_duplicado"]
        .sum()
        .astype(int)
        .to_dict()
    )

    valor_em_risco = float(df.loc[detectado, "amount"].sum())

    passou = taxa <= limite_duplicidade

    return ResultadoValidacao(
        total_linhas=total,
        total_duplicados_detectados=total_detectado,
        taxa_duplicidade=round(taxa, 4),
        total_rotulo_historico=total_rotulo,
        verdadeiros_positivos=vp,
        falsos_positivos=fp,
        falsos_negativos=fn,
        precisao=round(precisao, 4),
        recall=round(recall, 4),
        por_departamento=por_departamento,
        valor_total_em_risco=round(valor_em_risco, 2),
        limite_duplicidade=limite_duplicidade,
        passou_no_portao_de_qualidade=passou,
    )


def gerar_relatorios(resultado: ResultadoValidacao, pasta_reports: Path, pasta_site: Path) -> None:
    pasta_reports.mkdir(parents=True, exist_ok=True)
    pasta_site.mkdir(parents=True, exist_ok=True)

    dados = asdict(resultado)

    with open(pasta_reports / "duplicates_report.json", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    with open(pasta_reports / "summary.txt", "w", encoding="utf-8") as f:
        f.write("RELATORIO DE VALIDACAO DE DUPLICIDADE DE CLAIMS\n")
        f.write("=" * 50 + "\n")
        for chave, valor in dados.items():
            f.write(f"{chave}: {valor}\n")

    status_cor = "#1e7e34" if resultado.passou_no_portao_de_qualidade else "#c0392b"
    status_texto = "PASSOU" if resultado.passou_no_portao_de_qualidade else "REPROVOU"
    linhas_departamento = "".join(
        f"<tr><td>{dep}</td><td>{qtd}</td></tr>"
        for dep, qtd in sorted(resultado.por_departamento.items())
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Pipeline CI/CD - Validacao de Claims Duplicados</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; background: #f7f7f9; color: #222; }}
  h1 {{ color: #2c3e50; }}
  .card {{ background: white; border-radius: 8px; padding: 20px 28px; margin-bottom: 20px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .status {{ display:inline-block; padding: 4px 14px; border-radius: 20px; color:white;
             background:{status_cor}; font-weight:bold; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td, th {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background:#2c3e50; color:white; }}
  .metric {{ display:inline-block; margin-right: 40px; }}
  .metric b {{ font-size: 1.4em; display:block; }}
</style>
</head>
<body>
  <h1>Pipeline CI/CD &mdash; Validacao de Duplicidade de Claims</h1>
  <div class="card">
    <p>Portao de qualidade: <span class="status">{status_texto}</span>
       (limite configurado: {resultado.limite_duplicidade*100:.1f}% de duplicidade)</p>
    <div class="metric"><b>{resultado.total_linhas}</b>Linhas processadas</div>
    <div class="metric"><b>{resultado.total_duplicados_detectados}</b>Duplicados detectados</div>
    <div class="metric"><b>{resultado.taxa_duplicidade*100:.2f}%</b>Taxa de duplicidade</div>
    <div class="metric"><b>R$ {resultado.valor_total_em_risco:,.2f}</b>Valor em risco</div>
  </div>
  <div class="card">
    <h2>Validacao contra rotulo historico (is_duplicate)</h2>
    <div class="metric"><b>{resultado.precisao*100:.1f}%</b>Precisao</div>
    <div class="metric"><b>{resultado.recall*100:.1f}%</b>Recall</div>
    <div class="metric"><b>{resultado.verdadeiros_positivos}</b>Verdadeiros positivos</div>
    <div class="metric"><b>{resultado.falsos_positivos}</b>Falsos positivos</div>
    <div class="metric"><b>{resultado.falsos_negativos}</b>Falsos negativos</div>
  </div>
  <div class="card">
    <h2>Duplicados detectados por departamento</h2>
    <table>
      <tr><th>Departamento</th><th>Qtd. de duplicados</th></tr>
      {linhas_departamento}
    </table>
  </div>
  <p style="color:#888; font-size:0.85em;">Gerado automaticamente pela pipeline de CI/CD (GitHub Actions).</p>
</body>
</html>
"""
    with open(pasta_site / "index.html", "w", encoding="utf-8") as f:
        f.write(html)


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida duplicidade de claims.")
    parser.add_argument("csv", help="Caminho para o arquivo CSV de claims.")
    parser.add_argument(
        "--limite-duplicidade",
        type=float,
        default=0.15,
        help="Taxa maxima de duplicidade aceitavel (0-1). Default: 0.15",
    )
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--site-dir", default="site")
    args = parser.parse_args()

    try:
        df = carregar_base(args.csv)
    except ValidacaoError as erro:
        print(f"[FALHA] Erro de validacao de schema: {erro}", file=sys.stderr)
        return 2

    resultado = validar(df, args.limite_duplicidade)
    gerar_relatorios(resultado, Path(args.reports_dir), Path(args.site_dir))

    print(json.dumps(asdict(resultado), ensure_ascii=False, indent=2))

    if not resultado.passou_no_portao_de_qualidade:
        print(
            f"[FALHA] Taxa de duplicidade ({resultado.taxa_duplicidade*100:.2f}%) "
            f"acima do limite ({args.limite_duplicidade*100:.2f}%).",
            file=sys.stderr,
        )
        return 1

    print("[OK] Validacao concluida dentro do limite aceitavel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
