from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()


class User(Base):
    """Users Tables"""
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    email = Column(String(250), nullable=False)
    picture = Column(String(250))


class Category(Base):
    """Categories Table"""
    __tablename__ = "category"

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)

    @property
    def serialize(self):
        """Return category object in an easily serializable format"""
        return {
            "id": self.id,
            "name": self.name
        }


class Product(Base):
    """Products Table"""
    __tablename__ = "product"
    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    description = Column(String(1000), nullable=False)
    price = Column(String(10))
    email = Column(String(250), nullable=False)
    phone = Column(String(20))
    category_id = Column(Integer, ForeignKey("category.id"))
    category = relationship(Category)
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship(User)

    @property
    def serialize(self):
        """Return product object in an easily serializable format"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "email": self.email,
            "phone": self.phone,
            "category": self.category.name,
        }


engine = create_engine("sqlite:///forsale2.db")

Base.metadata.create_all(engine)
