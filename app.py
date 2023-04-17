import os
import time

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
    cash = rows[0]["cash"]
    grand_total = cash

    # Select stocks which the user owns shares of
    stocks = db.execute(
        "SELECT stock, shares FROM funds WHERE user_id=?", session["user_id"])

    # Add price info to stocks
    for stock in stocks:
        stock["price"] = lookup(stock["stock"])["price"]
        grand_total += stock["shares"] * stock["price"]

    return render_template("index.html", stocks=stocks, cash=cash, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        # Not stonks
        if not stock:
            return apology("That's not a valid stock symbol!", 400)
        symbol = stock["symbol"]

        shares = request.form.get("shares")
        if not shares or not shares.isdigit() or int(shares) < 1:
            return apology("Provide a valid number of shares", 400)
        shares = int(shares)

        rows = db.execute("SELECT cash FROM users WHERE id=?",
                          session["user_id"])
        cash = rows[0]["cash"]
        total = stock["price"] * shares
        if total > cash:
            return apology("Not enough cash to buy.", 400)

        datetime = time.strftime('%Y-%m-%d %H:%M:%S')
        db.execute("INSERT INTO transactions (user_id, stock, price, shares, type, datetime) VALUES (?, ?, ?, ?, ?, ?)",
                   session["user_id"], symbol, stock["price"], shares, "buy", datetime)

        new_cash = cash - total
        db.execute("UPDATE users SET cash=?", new_cash)

        rows = db.execute(
            "SELECT shares FROM funds WHERE user_id=? AND stock=?", session["user_id"], symbol)
        if len(rows) == 0:
            db.execute("INSERT INTO funds (user_id, stock, shares) VALUES (?, ?, ?)",
                       session["user_id"], symbol, shares)
        else:
            shares += rows[0]["shares"]
            db.execute("UPDATE funds SET shares=? WHERE user_id=? AND stock=?",
                       shares, session["user_id"], symbol)

        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add cash to user's account"""
    if request.method == "POST":
        cash = request.form.get("cash")

        try:
            float(cash)
        except ValueError:
            return apology("Not a valid amount of cash!", 400)
        cash = round(float(cash), 2)

        if cash <= 0:
            return apology("Not a valid amount of cash", 400)

        rows = db.execute("SELECT cash FROM users WHERE id=?",
                          session["user_id"])
        old_cash = rows[0]["cash"]

        new_cash = old_cash + cash
        db.execute("UPDATE users SET cash=?", new_cash)

        return redirect("/")
    else:
        return render_template("add_cash.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute(
        "SELECT * FROM transactions WHERE user_id=? ORDER BY datetime DESC", session["user_id"])

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        if not stock:
            return apology("That's not a valid stock symbol!", 400)

        return render_template("quoted.html", stock=stock)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Validate username
        if not username:
            return apology("Must provide username", 400)

        # Check if username already exists
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(rows) == 1:
            return apology("Username already exists", 400)

        # Validate password
        if not password or password != confirmation:
            return apology("Provide a valid password", 400)

        # Generate hash from password and store username data into database
        hash = generate_password_hash(
            password, method='pbkdf2:sha256', salt_length=8)
        db.execute(
            "INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)

        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Provide a valid stock symbol", 400)

        stock = lookup(symbol)
        # Not stonks
        if not stock:
            return apology("That's not a valid stock symbol!", 400)
        symbol = stock["symbol"]

        rows = db.execute(
            "SELECT shares FROM funds WHERE user_id=? AND stock=?", session["user_id"], symbol)
        if len(rows) == 0:
            return apology("You do not own shares of the selected stock", 400)
        shares_owned = rows[0]["shares"]

        shares = request.form.get("shares")
        if not shares or not shares.isdigit() or int(shares) < 1:
            return apology("Provide a valid number of shares", 400)
        shares = int(shares)

        if shares > shares_owned:
            return apology("You do not own that many shares", 400)

        # Record transaction
        datetime = time.strftime('%Y-%m-%d %H:%M:%S')
        db.execute("INSERT INTO transactions (user_id, stock, price, shares, type, datetime) VALUES (?, ?, ?, ?, ?, ?)",
                   session["user_id"], symbol, stock["price"], shares, "sell", datetime)

        # Update cash
        rows = db.execute("SELECT cash FROM users WHERE id=?",
                          session["user_id"])
        cash = rows[0]["cash"]
        new_cash = cash + stock["price"] * shares
        db.execute("UPDATE users SET cash=?", new_cash)

        # Update shares owned
        new_shares = shares_owned - shares
        db.execute("UPDATE funds SET shares=? WHERE user_id=? AND stock=?",
                   new_shares, session["user_id"], symbol)
        db.execute("DELETE FROM funds WHERE user_id=? AND shares=0",
                   session["user_id"])

        return redirect("/")
    else:
        stocks = db.execute(
            "SELECT stock FROM funds WHERE user_id=?", session["user_id"])

        return render_template("sell.html", stocks=stocks)
