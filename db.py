import pymongo
from werkzeug.security import generate_password_hash as bruh
from werkzeug.security import check_password_hash
import os

client = pymongo.MongoClient()
ThoughtDB = client["ThoughtDB"]
userdb = ThoughtDB["userdb"]


def login_check(username, password):
	user = userdb.find_one({"name":username})
	p = user['password']
	x = check_password_hash(p, password)
	return str(user['id'])

	


def add_user(username, password, email,invite_code):
	client = pymongo.MongoClient()
	ThoughtDB = client["ThoughtDB"]
	userdb = ThoughtDB["userdb"]
	id = os.urandom(32)
	check = userdb.find_one({"id":id})
	if check == None:
		p = bruh(password)
		x = {
			'id' : id,
			"name" : username,
			"password" : p,
			"invite_code" : invite_code,
			"email" : email,
			"aboutme" : "Hello, I am new to thoughts"}
		userdb.insert(x)
		return "OK"
	else:
		return str(check)