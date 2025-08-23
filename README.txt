Orça Fácil PRO — Login + Relatório PDF
======================================

Recursos
- Autenticação (cadastro, login, logout).
- Painel com faturamento diário/mensal, despesas e lucro aproximado.
- CRUD de Produtos, Clientes e Despesas.
- Vendas com carrinho, baixa de estoque e formas de pagamento.
- Relatório em PDF de Vendas e Despesas.

Como rodar
----------
1) (Opcional) criar venv
   Windows (PowerShell):
     python -m venv venv
     .\venv\Scripts\Activate.ps1
   Linux/macOS:
     python3 -m venv venv
     source venv/bin/activate

2) Instalar dependências:
     pip install -r requirements.txt

3) Rodar a aplicação:
     python app.py

4) Acessar no navegador:
     http://127.0.0.1:5000

5) Criar usuário em /register e efetuar login.

Configuração
------------
- SECRET_KEY: defina no ambiente para produção.
- DATABASE_URL: por padrão usa SQLite (orcafacil.db). Para usar outro banco, defina a URL (ex: PostgreSQL).

Observação
----------
Com SQLAlchemy 2.x, o esquema é criado automaticamente na primeira execução (Base.metadata.create_all).