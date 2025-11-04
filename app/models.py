from datetime import datetime
from . import db  # haalt db uit __init__.py

class Company(db.Model):
    __tablename__ = 'Companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime)
    emailaddress = db.Column(db.String(120))


class Farmer(db.Model):
    __tablename__ = 'Farmer'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime)
    emailaddress = db.Column(db.String(120))
    company_id = db.Column(db.Integer, db.ForeignKey('Companies.id'))


class Employee(db.Model):
    __tablename__ = 'Employees'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime)
    company_id = db.Column(db.Integer, db.ForeignKey('Companies.id'))
    last_name = db.Column(db.String(100))
    first_name = db.Column(db.String(100))
    employee_type = db.Column(db.String(50))


class Address(db.Model):
    __tablename__ = 'Address'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime)
    farmer_id = db.Column(db.Integer, db.ForeignKey('Farmer.id'))
    street_name = db.Column(db.String(100))
    house_number = db.Column(db.String(10))
    city = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))


class Order(db.Model):
    __tablename__ = 'Orders'
    id = db.Column(db.Integer, primary_key=True)
    deadline = db.Column(db.Date)
    task_type = db.Column(db.String(100))
    created_at = db.Column(db.DateTime)
    address_id = db.Column(db.Integer, db.ForeignKey('Address.id'))
    product_type = db.Column(db.String(100))
    

def get_user_by_email(email):
    return db.session.query(Farmer).filter(Farmer.emailaddress == email).first()


def insert_order(data):
    order = Order(
        deadline=data.get('deadline'),
        task_type=data.get('task_type'),
        created_at=datetime.utcnow(),
        address_id=data.get('address_id'),
        product_type=data.get('product_type')
    )
    db.session.add(order)
    db.session.commit()
    return order


def insert_farmer(data):
    farmer = Farmer(
        emailaddress=data.get('emailaddress'),
        company_id=data.get('company_id'),
        created_at=datetime.utcnow()
    )
    db.session.add(farmer)
    db.session.commit()
    return farmer


def insert_address(data):
    address = Address(
        created_at=datetime.utcnow(),
        farmer_id=data.get('farmer_id'),
        street_name=data.get('street_name'),
        house_number=data.get('house_number'),
        city=data.get('city'),
        phone_number=data.get('phone_number')
    )
    db.session.add(address)
    db.session.commit()
    return address