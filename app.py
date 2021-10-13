from flask import Flask, render_template, flash, redirect
from forms import *
import os
from db import *



app = Flask(__name__)
SECRET_KEY = os.urandom(32)
app.config['SECRET_KEY'] = SECRET_KEY

@app.route('/')
@app.route('/home')
def index():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        x = login_check(form.username.data,form.password.data)
        flash(str(x))
        return redirect('/home')
    return render_template('login.html', title='Sign In', form=form)

@app.route('/create', methods=['GET', 'POST'])
def create():
    form = CreateUserForm()
    if form.validate_on_submit():
        x = add_user(form.username.data, form.password.data, form.email.data, form.invcode.data)
        '''if x == "OK":
            return redirect('/home')
        else:'''
        flash(str(x))
        return redirect('/home')
    return render_template('create.html', title='Sign In', form=form)



@app.route('/loggingin')  
def cookie():  
    res = make_response("<h1>cookie is set</h1>")  
    res.set_cookie('foo','bar')  
    return res  