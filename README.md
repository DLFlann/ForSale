# ForSale
ForSale is a content management system in the form of a Craigslist clone application utilizing the python framework Flask for template rendering, URL mapping, and providing user feedback in the form of flash notifications. User authentication is supplied via OAuth2 providers by employing Google and Facebook's Graph API. And data is stored in a PostgreSQL database using the python object relation mapper SQLAlchemy. Additionally, RESTful API services are implemented with the use of serialization methods on database classes and API endpoints returning JSON formatted data.

## Dependancies
Running ForSale requires the following dependancies
- Python 2.7 [download here](https://www.python.org/downloads/)
- Flask Python Framework [download here](https://pypi.python.org/pypi/Flask/0.12)
- SQL Alchemy Python ORM [download here](https://www.sqlalchemy.org/download.html)

## Getting Started
Getting started with ForSale is easy.  After downloading the previously mentioned dependancies, you can simply navigate to the directory you have where you have ForSale downloaded and set up the database definitions by running `python database_setup.py`.  Now that you have setup the database, simply run `python application.py` from the same directory to start the development server.  You can now visit the ForSale site on your local machine at `http://localhost:8000`.

## APIs
ForSale offers API endpoints, which return JSON formatted data, at the following URLs
- `http://localhost:8000/[CATEGORY NAME]/JSON/` Returns a category's listed items
- `http://localhost:8000/[CATEGORY NAME]/[ITEM ID]/JSON/` Returns a single item
- `http://localhost:8000/categories/JSON/` Returns all category IDs and names

## License
The content of ForSale is licensed under a [Creative Commons Attribution License](https://creativecommons.org/licenses/by/3.0/us/).
