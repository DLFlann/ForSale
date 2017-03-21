from flask import Flask, render_template, request, redirect, jsonify, \
    url_for, flash, make_response

from flask import session as login_session

from sqlalchemy import create_engine

from sqlalchemy.orm import sessionmaker

from database_setup import Base, User, Category, Product

from oauth2client.client import flow_from_clientsecrets, FlowExchangeError, \
    verify_id_token, crypt, credentials_from_clientsecrets_and_code

import httplib2, json, requests, random, string

# Connet to database and create database session
engine = create_engine("sqlite:///forsale.db")
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()

# Instantiate instance of Flask
app = Flask(__name__)


# Function to create json response
def jsonResponse(message, code):
    response = make_response(json.dumps(message), code)
    response.headers["Content-Type"] = "application/json"
    return response


# Function to create user entry for database
def createUser(login_session):
    newUser = User(name=login_session['username'],
                   email=login_session['email'],
                   picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


# Function to get user object from database
def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


# Function to get user ID from database, given a user's email
def getUserId(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


@app.route("/login")
def login():
    """Login page handler. Creates and stores a state token to prevent request
    forgery and stores it in the login session for later validation"""
    state = "".join(random.choice(string.ascii_uppercase + string.digits) for
                    x in xrange(32))
    login_session["state"] = state
    return render_template("login2.html", state=state)


@app.route("/fbconnect", methods=["POST"])
def fbconnect():
    """Facebook connect function. Validates state token generated in 'login'
    function and exchanges client token for long-lived token to make server
    side api calls on behalf of the user"""

    # Validate state token generated in login function
    if request.args.get("state") != login_session["state"]:
        return jsonResponse("Invalid state parameter.", 401)

    # Store the access token given to client from facebook login
    access_token = request.data

    # Get app id from facebook json file
    app_id = json.loads(open("fb_client_secrets.json", "r").read())["web"] \
        ["app_id"]

    # Get app secret from facebook json file
    app_secret = json.loads(open("fb_client_secrets.json",
                                 "r").read())["web"]["app_secret"]

    # Store url for exchanging token
    api_url = "https://graph.facebook.com/oauth/access_token?" \
              "&grant_type=fb_exchange_token&client_id=%s&client_secret=%s&" \
              "fb_exchange_token=%s" % (app_id, app_secret, access_token)

    # Exchange client token for long-lived token and store in session
    http = httplib2.Http()
    fullResult = http.request(api_url, "GET")
    result = fullResult[1]
    token = result.split("&")[0]
    login_session["access_token"] = token.split("=")[1]

    # Use long-lived token to get user info from facebook API
    api_url = "https://graph.facebook.com/v2.8/me?%s&fields=" \
              "name,id,email" % token
    result = http.request(api_url, "GET")[1]
    data = json.loads(result)

    # Store user info returned from api in session
    login_session["provider"] = "facebook"
    login_session["username"] = data["name"]
    login_session["email"] = data["email"]
    login_session["facebook_id"] = data["id"]

    # Get user profile picture dimensions 300x300
    api_url = "https://graph.facebook.com/v2.8/%s/picture?redirect=0&" \
              "height=300&width=300&access_token=%s" % \
              (login_session["facebook_id"], access_token)
    result = http.request(api_url, "GET")[1]
    data = json.loads(result)
    login_session["picture"] = data["data"]["url"]

    # Check if user exist in database, if not create them
    user_id = getUserId(login_session["email"])
    if user_id is not None:
        login_session["user_id"] = user_id
    else:
        login_session["user_id"] = createUser(login_session)

    # Print welcome message to user along with profile picture
    return redirect(url_for("showCategories"))


@app.route("/gconnect", methods=["POST"])
def gconnect():
    """Google connect function. Validates state token generated in 'login'
    function and exchanges client token for long-lived token to make server
    side api calls on behalf of the user"""
    # Validate state token generated in login function
    if request.args.get("state") != login_session["state"]:
        return jsonResponse("Invalid state parameter.", 401)

    # Store authorization code given to client from google signin
    auth_code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets("google_client_secrets.json",
                                             scope="")
        oauth_flow.redirect_uri = "postmessage"
        credentials = oauth_flow.step2_exchange(auth_code)
    except FlowExchangeError:
        return jsonResponse("Failed to upgrade the authorization code.", 401)

    # Check that the access token is valid
    access_token = credentials.access_token
    api_url = ("https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s"
               % access_token)
    http = httplib2.Http()
    result = json.loads(http.request(api_url, "GET")[1])

    # If there was an error in the access token infor, abort
    if result.get("error") is not None:
        return jsonResponse(result.get("error"), 500)

    # Verify that the access token is used for the intended user
    google_id = credentials.id_token["sub"]
    if result["user_id"] != google_id:
        return jsonResponse("Token's user ID doesn't match fiver user ID", 401)

    # Verify the access token is vallid for this app
    CLIENT_ID =json.loads(open('google_client_secrets.json',
                               'r').read())['web']['client_id']
    if result["issued_to"] != CLIENT_ID:
        return jsonResponse("Token's client ID doesn't mathch app's", 401)

    # Check to see if user is already logged in
    stored_credentials = login_session.get("credentials")
    stored_google_id = login_session.get("goodle_id")
    if stored_credentials is not None and stored_google_id == google_id:
        login_session["credentials"] = credentials.access_token
        return jsonResponse("Current user is already connected.", 200)

    # Store the id info in the session for later use
    login_session["provider"] = "google"
    login_session["credentials"] = credentials.access_token
    login_session["google_id"] = google_id

    # Get user info using google api
    api_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {"access_token": credentials.access_token, "alt": "json"}
    answer = requests.get(api_url, params=params)
    data = answer.json()

    # Store user info returned from api in session
    login_session["username"] = data["name"]
    login_session["email"] = data["email"]
    login_session["picture"] = data["picture"]

    # Check if user exist in database, if not create them
    user_id = getUserId(login_session["email"])
    if user_id is not None:
        login_session["user_id"] = user_id
    else:
        login_session["user_id"] = createUser(login_session)

    # Print welcome message to user along with profile picture
    return redirect(url_for("showCategories"))


# @app.route("/fbdisconnect")
def fbdisconnect():
    """Facebook disconnect function.  Revokes app
    authorization for the given user"""

    # Obtain facebook ID and access token
    facebook_id = login_session["facebook_id"]
    access_token = login_session["access_token"]

    # Make facebook api call to revoke app access
    api_url = "https://graph.facebook.com/%s/permissions?access_token=%s" % \
              (facebook_id, access_token)
    http = httplib2.Http()
    fullResult = http.request(api_url, "DELETE")
    result = fullResult[0]

    # Verify facebook api call response
    if result["status"]:
        # Reset the user's session
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        del login_session['user_id']
        del login_session['facebook_id']

        return jsonResponse("You have successfully logged out.", 200)
    else:
        # Token revoke call failed
        print(result)
        return jsonResponse("Failed to revoke token for user", 400)


# @app.route("/gdisconnect")
def gdisconnect():
    # Only disconnect a connected user
    credentials = login_session.get("credentials")
    if credentials is None:
        return jsonResponse("Current user is not connected", 401)

    # Make Google api call to revoke app access
    access_token = login_session["credentials"]
    api_url = "https://accounts.google.com/o/oauth2/revoke?token=%s" % \
              access_token
    http = httplib2.Http()
    result = http.request(api_url, "GET")[0]

    if result["status"] == "200":
        # Reset the user's session
        del login_session['credentials']
        del login_session['google_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']

        return jsonResponse("You have successfully logged out.", 200)
    else:
        # Token revoke call failed
        print(result)
        return jsonResponse("Failed to revoke token for user", 400)


# JSON API to view category listings
@app.route("/<string:category_name>/JSON/")
def showItemsJSON(category_name):
    """Show a category's items API endpoint, returns item
    information for given category in JSON format"""

    # Get category from database
    category = session.query(Category).filter_by(name=category_name).one()

    # Use category ID to get items from database
    items = session.query(Product).filter_by(category_id=category.id).all()

    # Return JSON formatted items for the give category
    return jsonify(CategoryListings=[item.serialize for item in items])


# JSON API to view item listing's information
@app.route("/<string:category_name>/<int:item_id>/JSON/")
def showItemInfoJSON(category_name, item_id):
    """Show an item's information API endpoint, returns
    information for a specific item in JSON format"""

    # Get item from the database
    item = session.query(Product).filter_by(id=item_id).one()

    # Return JSON formatted item information
    return jsonify(Item=item.serialize)


# JSON API to view all categories
@app.route("/categories/JSON/")
def showCategoriesJSON():
    """Show all categories API endpoint, returns
    all categories in JSON format"""

    # Get categories from database
    categories = session.query(Category).all()

    # Return JSON formatted categories
    return jsonify(Categories=[category.serialize for category in categories])


@app.route("/logout")
def logout():
    """Logout handler, determines Oauth2 provider and logs user out"""
    if "provider" in login_session:
        if login_session["provider"] == "google":
            # If Oauth prider is Google user gdisconnect
            gdisconnect()
        if login_session["provider"] == "facebook":
            # If Oauth prider is Facebook user gdisconnect
            fbdisconnect()

        # Redirect to home page
        flash("You have successfully logged out of ForSale")
        return redirect(url_for("showCategories"))
    else:
        flash("You are not logged in to ForSale")


@app.route("/")
@app.route("/categories/")
def showCategories():
    """Show categories handler retrieves categories from database and renders
    categories page, displaying categories for user to select"""

    # Get categories from database
    categories = session.query(Category).all()

    # Get 4 categories for the first column and 4 for the second
    column1 = categories[0:4]
    column2 = categories[4:]

    if "username" not in login_session:
        # If user is not logged in, render public categories page
        return render_template("publiccategories.html", column1=column1,
                               column2=column2)
    else:
        # User is logged in, render authorized categories page
        return render_template("categories.html", column1=column1,
                               column2=column2,
                               profile=login_session["picture"])


@app.route("/<string:category_name>/")
def showItems(category_name):
    """Show items handler retrieves all items for a the given category from
    the database and render the category items page, displaying all items
     for the user"""

    # Get category from database
    category = session.query(Category).filter_by(name=category_name).one()

    # Use category ID to get items from database
    items = session.query(Product).filter_by(category_id=category.id).all()

    if "username" not in login_session:
        # If user is not logged in, render public category items page
        return render_template("publiccategoryitems.html",
                               category_name=category_name, items=items)
    else:
        # User is logged in, render authorized categories page
        return render_template("categoryitems.html",
                               category_name=category_name, items=items,
                               profile=login_session["picture"])


@app.route("/<string:category_name>/new/", methods=["GET", "POST"])
def newItem(category_name):
    """New item handler retireves item entry page with form to
    post a new item to the database"""

    category = session.query(Category).filter_by(name=category_name).one()

    #Verify user is logged in
    if "username" not in login_session:
        # User is not logged in, redirect to login page
        redirect(url_for("login"))
    elif request.method == "POST":
        # Handle post request
        newItem = Product(name=request.form["name"],
                            description=request.form["description"],
                            price=request.form["price"],
                            email=login_session["email"],
                            phone=request.form["phone"],
                            category_id=category.id,
                            user_id=login_session["user_id"])
        session.add(newItem)
        session.commit()
        flash('New %s Item Successfully Posted For Sale' % newItem.name)
        return redirect(url_for("showItemInfo", category_name=category_name,
                                item_id=newItem.id))
    else:
        # User is logged in, render new item template
        return render_template("newitem.html", category_name=category_name,
                               profile=login_session["picture"])


@app.route("/<string:category_name>/<int:item_id>/")
def showItemInfo(category_name, item_id):
    """Item description page handler, retrieves an item from the database
    and renders the item information page"""
    # Get item from the database
    item = session.query(Product).filter_by(id=item_id).one()

    if "username" not in login_session:
        # If user is not logged in, render public item info page
        return render_template("publiciteminfo.html",
                               category_name=category_name, item=item)
    elif item.user.email != login_session["email"]:
        # User is not the creator, render page without edit/delete options
        return render_template("iteminfo.html",
                               category_name=category_name, item=item,
                               profile=login_session["picture"])
    else:
        # User is the owner, render authorized item info page
        return render_template("owneriteminfo.html",
                               category_name=category_name, item=item,
                               profile=login_session["picture"])


@app.route("/<string:category_name>/<int:item_id>/edit/", methods=["GET",
                                                                  "POST"])
def editItem(category_name, item_id):
    """Item edit page handler, retrieves item from database
    and renders the edit item page"""

    # Get item from the database
    item = session.query(Product).filter_by(id=item_id).one()

    if "username" not in login_session:
        # If user not logged in, redirect to login page
        return redirect("/login")
    elif item.user.email != login_session["email"]:
        # If user not the creator, javascript alert they are not authorized
        return "<script>function myFunction() {alert('Only the seller may " \
               "edit this item.');};</script><body onload='myFunction()''>"
    elif request.method == "POST":
        # Handle post request, retrieve user info
        if request.form["name"]:
            item.name = request.form["name"]
        if request.form["description"]:
            item.description = request.form["description"]
        if request.form["price"]:
            item.price = request.form["price"]
        if request.form["phone"]:
            item.phone = request.form["phone"]

        # Update database
        session.add(item)
        session.commit()

        # Redirect to the items info page
        flash('%s Successfully Updated' % item.name)
        return redirect(url_for("showItemInfo", category_name=category_name,
                                item_id=item.id))
    else:
        # Render edit item template
        return render_template("edititem.html", category_name=category_name,
                               item=item, profile=login_session["picture"])


@app.route("/<string:category_name>/<int:item_id>/delete/", methods=["GET",
                                                                     "POST"])
def deleteItem(category_name, item_id):
    """Delete item page handler, retrieves item from database
    and render delete confirmation page"""

    # Get item from the database
    item = session.query(Product).filter_by(id=item_id).one()

    if "username" not in login_session:
        # If user not logged in, redirect to login page
        return redirect("/login")
    elif item.user.email != login_session["email"]:
        # If user not the creator, javascript alert they are not authorized
        return "<script>function myFunction() {alert('Only the seller may " \
               "remove this item.');};</script><body onload='myFunction()''>"
    elif request.method == "POST":
        # Handle post request, deteling item from database
        session.delete(item)
        session.commit()

        # Redirect to the category page
        flash('Item Successfully Deleted')
        return redirect(url_for('showItems', category_name=category_name))
    else:
        # Render delete confirmation page
        return render_template("deleteitem.html",
                               category_name=category_name, item=item,
                               profile=login_session["picture"])


if __name__ == "__main__":
    # Set app secret key
    app.secret_key = "something_secret"
    # Run Flask app
    app.debug = True
    app.run(host="0.0.0.0", port=8000)
