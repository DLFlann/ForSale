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
    return render_template("login.html", state=state)


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
    app_id = json.loads(open("fb_client_secrets.json", "r").read())["web"]\
        ["app_id"]

    # Get app secret from facebook json file
    app_secret = json.loads(open("fb_client_secrets.json", "r").read())["web"]\
        ["app_secret"]

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
    output = "Welcome " + login_session["username"]
    output += "<br><img src='%s'" % login_session["picture"]
    output += "style='height: 300px; width: 300px;'>"
    return output


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

    # Exchange auth code for accesss token, refresh token, and ID token
    # credentials = credentials_from_clientsecrets_and_code(
    #     "/google_client_secrets.json",
    #     ["https://www.googleapis.com/auth/drive.appdata", "profile", "email"],
    #     auth_code)
    #
    # # Call Google API
    # http_auth = credentials.authorize(httplib2.Http())
    # drive_service = discovery.build("drive", "v3", http=http_auth)
    # appfolder = drive_service.files().get(fieldId="appfolder").execute()

    # # Get app id from google json file
    # app_id = json.loads(open("google_client_secrets.json", "r").read())\
    #     ["web"]["client_id"]
    #
    # # Verify ID token integrity
    # try:
    #     idinfo = verify_id_token(id_token, app_id)
    #
    #     if idinfo["iss"] not in ["accounts.google.com",
    #                              "https://accounts.google.com"]:
    #         raise crypt.AppIdentityError("Wrong issuer.")
    # except crypt.AppIdentityError:
    #     # Invalid token
    #     return jsonResponse("Failed to verify token integrity", 401)


    # Check to see if user is already logged in
    stored_credentials = login_session.get("credentials")
    stored_google_id = login_session.get("goodle_id")
    if stored_credentials is not None and stored_google_id == idinfo["sub"]:
        login_session["credentials"] = idinfo
        return jsonResponse("Current user is already connected.", 200)

    # Store the id info in the session for later use
    login_session["provider"] = "google"
    login_session["credentials"] = credentials.access_token
    login_session["google_id"] = google_id

    # Get user info
    api_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {"access_token": credentials.access_token, "alt": "json"}
    answer = requests.get(api_url, params=params)
    data = answer.json()

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
    output = "Welcome " + login_session["username"]
    output += "<br><img src='%s'" % login_session["picture"]
    output += "style='height: 300px; width: 300px;'>"
    return output


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


@app.route("/disconnect")
def disconnect():
    if "provider" in login_session:
        if login_session["provider"] == "google":
            gdisconnect()
        if login_session["provider"] == "facebook":
            fbdisconnect()
        flash("You have successfully logged out of ForSale")
        print("You have successfully logged out of ForSale")
        return redirect(url_for("showCategories"))
    else:
        flash("You are not logged in to ForSale")


@app.route("/")
@app.route("/categories")
def showCategories():
    return "Hello World!!"


@app.route("/<string:category_name>/")
def showItems(category_name):
    return category_name + " category will be shown here."


@app.route("/<string:category_name>/new/")
def newItem(category_name):
    return "A new item for " + category_name + " will be created here."


@app.route("/<string:category_name>/<int:item_id>/")
def showItemInfo(category_name, item_id):
    return "Information for " + str(item_id) + " in " + category_name + " will be shown here."


@app.route("/<string:category_name>/<int:item_id>/edit/")
def editItem(category_name, item_id):
    return "Edit page for " + str(item_id) + " in " + category_name + " will be shown here."


@app.route("/<string:category_name>/<int:item_id>/delete/")
def deleteItem(category_name, item_id):
    return "Delete confirmation page for " + str(item_id) + " in " + category_name + " will be shown here."


if __name__ == "__main__":
    # Set app secret key
    app.secret_key = "something_secret"
    # Run Flask app
    app.debug = True
    app.run(host="0.0.0.0", port=8000)
