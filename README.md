# Pipeline CI/CD — Validação de Duplicidade de Claims

Projeto acadêmico (Engenharia de Dados — DevOps e DataOps) que implementa uma
pipeline automatizada de **Integração Contínua (CI)** e **Entrega/Implantação
Contínua (CD)** utilizando **GitHub Actions**, aplicada a um problema real de
qualidade de dados: **detecção de reembolsos/claims lançados em duplicidade**.

## Problema resolvido

A base `data/duplicates_2.csv` simula lançamentos de reembolsos corporativos.
Falhas operacionais (reenvio de formulário, integração duplicada entre
sistemas) podem gerar o mesmo `claim_id` mais de uma vez, gerando risco de
pagamento em duplicidade. Este projeto automatiza a **detecção** desses casos
e a **publicação** de um painel com o resultado, toda vez que o código é
atualizado.

## O que a pipeline automatiza

1. **CI**: a cada `push`, o GitHub Actions instala as dependências, roda os
   testes automatizados (`pytest`) e executa o script de validação
   (`src/validar_duplicatas.py`) sobre a base de claims.
2. **Portão de qualidade**: se a taxa de duplicidade ultrapassar 15%, o
   script retorna código de erro e a pipeline **falha de propósito**
   (cenário de falha).
3. **CD**: se a etapa de CI passar na branch `main`, a pipeline publica
   automaticamente o painel HTML gerado (`site/index.html`) no
   **GitHub Pages**.

## Estrutura do projeto

```
.
├── .github/workflows/pipeline.yml   # workflow de CI/CD
├── data/duplicates_2.csv            # base de dados analisada
├── src/validar_duplicatas.py        # script de validação/deteccão
├── tests/test_validar_duplicatas.py # testes automatizados (sucesso e falha)
├── requirements.txt
└── README.md
```

## Rodando localmente

```bash
pip install -r requirements.txt
pytest tests/ -v
python src/validar_duplicatas.py data/duplicates_2.csv
# resultados em reports/ e site/index.html
```

## Como esta pipeline foi publicada

1. Repositório criado no GitHub com este conteúdo.
2. Em **Settings → Pages**, a opção "Source" configurada como **GitHub
   Actions**.
3. A cada `push` na branch `main`, o workflow `pipeline.yml` roda
   automaticamente as etapas de CI e, em seguida, publica o painel em
   `https://<usuario>.github.io/<repositorio>/`.
