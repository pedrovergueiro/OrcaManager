import os
from datetime import datetime, date
from decimal import Decimal
from io import BytesIO

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, scoped_session
from werkzeug.security import generate_password_hash, check_password_hash

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

APP_NAME = "Orça Fácil PRO"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///orcafacil.db")
engine = create_engine(DB_PATH, echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True))
Base = declarative_base()

# ------------------------ MODELS ------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(50))
    email = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow)

    sales = relationship("Sale", back_populates="customer")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    sku = Column(String(80), unique=True)
    cost_price = Column(Numeric(10,2), default=0)
    sale_price = Column(Numeric(10,2), nullable=False)
    stock = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("SaleItem", back_populates="product")

class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    total = Column(Numeric(10,2), default=0)
    payment_method = Column(String(40), default="dinheiro")
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # quem registrou a venda

    customer = relationship("Customer", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")

class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sales.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=1)
    unit_price = Column(Numeric(10,2), nullable=False)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="items")

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    description = Column(String(200), nullable=False)
    amount = Column(Numeric(10,2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # quem lançou

Base.metadata.create_all(engine)

# ------------------------ HELPERS ------------------------
def get_db():
    return SessionLocal()

def as_decimal(v):
    try:
        return Decimal(str(v)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")

def get_cart():
    return session.setdefault("cart", [])

def save_cart(cart):
    session["cart"] = cart
    session.modified = True

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    return db.get(User, uid)

@app.context_processor
def inject_ctx():
    return {"current_user": current_user(), "app_name": APP_NAME}

@app.before_request
def require_login():
    open_endpoints = {"login", "register", "static"}
    if not getattr(request, "endpoint", None):
        return
    if request.endpoint in open_endpoints or (request.endpoint or "").startswith("static"):
        return
    if not current_user():
        if request.endpoint != "register":
            return redirect(url_for("login"))

# ------------------------ AUTH ------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if not name or not email or not password:
            flash("Preencha todos os campos.", "danger")
            return redirect(url_for("register"))
        if db.query(User).filter_by(email=email).first():
            flash("E-mail já cadastrado!", "danger")
            return redirect(url_for("register"))
        user = User(name=name, email=email, password_hash=generate_password_hash(password))
        db.add(user)
        db.commit()
        flash("Usuário registrado! Faça login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = db.query(User).filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            flash("Login bem-sucedido!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("E-mail ou senha inválidos.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Saiu da conta.", "info")
    return redirect(url_for("login"))

# ------------------------ ROUTES ------------------------
@app.route("/")
def dashboard():
    db = get_db()
    today = date.today()
    start = datetime(today.year, today.month, today.day)
    end = datetime(today.year, today.month, today.day, 23, 59, 59)

    daily_revenue = db.query(func.coalesce(func.sum(Sale.total), 0)).filter(Sale.created_at.between(start, end)).scalar()
    month_start = datetime(today.year, today.month, 1)
    monthly_revenue = db.query(func.coalesce(func.sum(Sale.total), 0)).filter(Sale.created_at >= month_start).scalar()
    monthly_expenses = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.created_at >= month_start).scalar()

    profit_q = (
        db.query(func.coalesce(func.sum((SaleItem.unit_price - Product.cost_price) * SaleItem.quantity), 0))
        .join(Product, Product.id == SaleItem.product_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= month_start)
        .scalar()
    )
    approx_profit = (profit_q or 0) - (monthly_expenses or 0)

    top_products = (
        db.query(Product.name, func.sum(SaleItem.quantity).label("qty"))
        .join(SaleItem, Product.id == SaleItem.product_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= month_start)
        .group_by(Product.name)
        .order_by(func.sum(SaleItem.quantity).desc())
        .limit(5)
        .all()
    )

    return render_template("index.html",
                           daily_revenue=daily_revenue or 0,
                           monthly_revenue=monthly_revenue or 0,
                           monthly_expenses=monthly_expenses or 0,
                           approx_profit=approx_profit or 0,
                           top_products=top_products)

# --------- Customers
@app.route("/customers", methods=["GET", "POST"])
def customers():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name","").strip()
        phone = request.form.get("phone","").strip()
        email = request.form.get("email","").strip()
        if not name:
            flash("Nome é obrigatório.", "danger")
        else:
            db.add(Customer(name=name, phone=phone, email=email))
            db.commit()
            flash("Cliente adicionado.", "success")
        return redirect(url_for("customers"))

    data = db.query(Customer).order_by(Customer.created_at.desc()).all()
    return render_template("customers.html", customers=data)

@app.route("/customers/<int:cid>/delete")
def delete_customer(cid):
    db = get_db()
    c = db.get(Customer, cid)
    if c:
        db.delete(c)
        db.commit()
        flash("Cliente removido.", "info")
    return redirect(url_for("customers"))

# --------- Products
@app.route("/products", methods=["GET", "POST"])
def products():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name","").strip()
        sku = request.form.get("sku","").strip() or None
        cost = as_decimal(request.form.get("cost_price","0"))
        price = as_decimal(request.form.get("sale_price","0"))
        stock = int(request.form.get("stock","0"))
        if not name or price <= 0:
            flash("Nome e preço de venda são obrigatórios.", "danger")
        else:
            db.add(Product(name=name, sku=sku, cost_price=cost, sale_price=price, stock=stock))
            db.commit()
            flash("Produto adicionado.", "success")
        return redirect(url_for("products"))
    data = db.query(Product).order_by(Product.created_at.desc()).all()
    return render_template("products.html", products=data)

@app.route("/products/<int:pid>/delete")
def delete_product(pid):
    db = get_db()
    p = db.get(Product, pid)
    if p:
        db.delete(p)
        db.commit()
        flash("Produto removido.", "info")
    return redirect(url_for("products"))

# --------- Expenses
@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    db = get_db()
    if request.method == "POST":
        description = request.form.get("description","").strip()
        amount = as_decimal(request.form.get("amount","0"))
        if not description or amount <= 0:
            flash("Descrição e valor são obrigatórios.", "danger")
        else:
            e = Expense(description=description, amount=amount, user_id=session.get("user_id"))
            db.add(e)
            db.commit()
            flash("Despesa lançada.", "success")
        return redirect(url_for("expenses"))
    data = db.query(Expense).order_by(Expense.created_at.desc()).all()
    return render_template("expenses.html", expenses=data)

@app.route("/expenses/<int:eid>/delete")
def delete_expense(eid):
    db = get_db()
    e = db.get(Expense, eid)
    if e:
        db.delete(e)
        db.commit()
        flash("Despesa removida.", "info")
    return redirect(url_for("expenses"))

# --------- Sales (cart-based)
@app.route("/sales/new", methods=["GET", "POST"])
def sales_new():
    db = get_db()
    cart = get_cart()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_item":
            product_id = int(request.form.get("product_id"))
            qty = int(request.form.get("quantity","1"))
            product = db.get(Product, product_id)
            if not product:
                flash("Produto inválido.", "danger")
            elif qty <= 0:
                flash("Quantidade deve ser positiva.", "danger")
            else:
                cart.append({"product_id": product.id, "name": product.name, "qty": qty, "unit_price": float(product.sale_price)})
                save_cart(cart)
                flash("Item adicionado ao carrinho.", "success")
            return redirect(url_for("sales_new"))
        elif action == "clear_cart":
            save_cart([])
            flash("Carrinho limpo.", "info")
            return redirect(url_for("sales_new"))
        elif action == "finalize":
            if not cart:
                flash("Carrinho vazio.", "danger")
                return redirect(url_for("sales_new"))
            customer_id = request.form.get("customer_id")
            customer_id = int(customer_id) if customer_id else None
            payment_method = request.form.get("payment_method","dinheiro")
            sale = Sale(customer_id=customer_id, payment_method=payment_method, user_id=session.get("user_id"))
            db.add(sale)
            db.flush()
            total = Decimal("0.00")
            for it in cart:
                unit_price = as_decimal(it["unit_price"])
                qty = int(it["qty"])
                db.add(SaleItem(sale_id=sale.id, product_id=it["product_id"], quantity=qty, unit_price=unit_price))
                total += unit_price * qty
                prod = db.get(Product, it["product_id"])
                if prod:
                    prod.stock = (prod.stock or 0) - qty
            sale.total = total
            db.commit()
            save_cart([])
            flash(f"Venda #{sale.id} registrada. Total R$ {total:.2f}", "success")
            return redirect(url_for("sales_list"))
    products = db.query(Product).order_by(Product.name.asc()).all()
    customers = db.query(Customer).order_by(Customer.name.asc()).all()
    cart_total = sum(Decimal(str(i["unit_price"])) * i["qty"] for i in cart) if cart else Decimal("0")
    return render_template("sales_new.html", products=products, customers=customers, cart=cart, cart_total=cart_total)

@app.route("/sales")
def sales_list():
    db = get_db()
    data = db.query(Sale).order_by(Sale.created_at.desc()).limit(200).all()
    return render_template("sales_list.html", sales=data)

# --------- PDF REPORT
@app.route("/report/pdf")
def report_pdf():
    db = get_db()
    sales = db.query(Sale).order_by(Sale.created_at.desc()).limit(200).all()
    expenses = db.query(Expense).order_by(Expense.created_at.desc()).limit(200).all()

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(200, height - 50, "Relatório Orça Fácil PRO")

    c.setFont("Helvetica-Bold", 12)
    y = height - 90
    c.drawString(50, y, "Vendas (até 200):")
    y -= 20
    c.setFont("Helvetica", 11)
    for s in sales:
        cust = s.customer.name if s.customer else "—"
        line = f"#{s.id} {s.created_at.strftime('%d/%m/%Y %H:%M')}  Cliente: {cust}  Total: R$ {s.total:.2f}  Pgto: {s.payment_method}"
        c.drawString(55, y, line[:110])
        y -= 14
        if y < 80:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 11)

    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Despesas (até 200):")
    y -= 20
    c.setFont("Helvetica", 11)
    for e in expenses:
        line = f"{e.created_at.strftime('%d/%m/%Y %H:%M')}  {e.description}  Valor: R$ {e.amount:.2f}"
        c.drawString(55, y, line[:110])
        y -= 14
        if y < 80:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 11)

    c.showPage()
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="relatorio_orcafacil.pdf", mimetype="application/pdf")

# ------------------------ FILTERS ------------------------
@app.template_filter("fmt")
def fmt_currency(val):
    try:
        return f"R$ {Decimal(val):.2f}"
    except Exception:
        return f"R$ {val}"

@app.template_filter("dt")
def fmt_dt(val):
    if not val:
        return ""
    return val.strftime("%d/%m/%Y %H:%M")

if __name__ == "__main__":
    app.run(debug=True)

