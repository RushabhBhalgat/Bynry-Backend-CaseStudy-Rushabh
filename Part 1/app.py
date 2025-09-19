from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from typing import Dict, Any, Optional
from marshmallow import Schema, fields, ValidationError
import logging
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Database Models
class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    sku = db.Column(db.String(100), unique=True, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    supplier_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with inventory
    inventories = db.relationship('Inventory', backref='product', lazy=True)

class Inventory(db.Model):
    __tablename__ = 'inventory'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HTTP Status Codes
HTTP_200_OK = 200
HTTP_201_CREATED = 201
HTTP_400_BAD_REQUEST = 400
HTTP_500_INTERNAL_SERVER_ERROR = 500

# Error Messages
ERROR_MISSING_FIELDS = "Missing required fields: {}"
ERROR_INVALID_VALUES = "Invalid price or initial_quantity - must be non-negative numbers"
ERROR_SKU_EXISTS = "SKU already exists"
ERROR_DATABASE = "Database error occurred"
SUCCESS_PRODUCT_CREATED = "Product created successfully"

# API Response structure
def create_response(success: bool, data: Optional[Dict] = None, error: Optional[str] = None, status_code: int = HTTP_200_OK) -> tuple:
    response = {
        "success": success,
        "data": data or {},
    }
    if error:
        response["error"] = error
    return jsonify(response), status_code

# Custom validation functions
def validate_non_negative(value):
    if value < 0:
        raise ValidationError('Must be non-negative')

def validate_positive_price(value):
    if value <= 0:
        raise ValidationError('Price must be greater than 0')

# Product Schema
class ProductSchema(Schema):
    name = fields.Str(required=True, validate=fields.Length(min=1, max=255))
    sku = fields.Str(required=True, validate=fields.Length(min=1, max=100))
    price = fields.Float(required=True, validate=validate_positive_price)
    warehouse_id = fields.Int(required=True, validate=lambda x: x > 0)
    initial_quantity = fields.Int(required=True, validate=validate_non_negative)
    supplier_id = fields.Int(allow_none=True, validate=lambda x: x is None or x > 0)

product_schema = ProductSchema()

# Error handlers
@app.errorhandler(ValidationError)
def handle_validation_error(error):
    logger.error(f"Validation error: {error.messages}")
    return create_response(False, error=str(error.messages), status_code=HTTP_400_BAD_REQUEST)

@app.errorhandler(IntegrityError)
def handle_integrity_error(error):
    logger.error(f"Database integrity error: {str(error)}")
    if 'UNIQUE constraint' in str(error.orig) or 'duplicate key' in str(error.orig):
        return create_response(False, error=ERROR_SKU_EXISTS, status_code=HTTP_400_BAD_REQUEST)
    return create_response(False, error=ERROR_DATABASE, status_code=HTTP_500_INTERNAL_SERVER_ERROR)

@app.route('/api/products', methods=['POST'])
def create_product() -> tuple:
    """Create a new product with associated inventory.
    
    This endpoint creates a new product and its initial inventory record in a single
    atomic transaction. It validates the input data using Marshmallow schema and
    ensures data consistency.
    
    Returns:
        tuple: A tuple containing (response_json, status_code)
               - response_json: Contains success status, data/error message
               - status_code: HTTP status code
    """
    logger.info("Processing new product creation request")
    
    # Check if request has JSON data
    if not request.json:
        logger.error("No JSON data provided in request")
        return create_response(
            success=False,
            error="No JSON data provided",
            status_code=HTTP_400_BAD_REQUEST
        )
    
    try:
        # Validate input data using schema - this will raise ValidationError if invalid
        data = product_schema.load(request.json)
        logger.info("Input validation passed")
        
        # Perform DB operations atomically
        with db.session.begin():
            product = Product(
                name=data['name'],
                sku=data['sku'],
                price=data['price'],
                supplier_id=data.get('supplier_id')
            )
            db.session.add(product)
            db.session.flush()  # assign product.id
            
            inventory = Inventory(
                product_id=product.id,
                warehouse_id=data['warehouse_id'],
                quantity=data['initial_quantity']
            )
            db.session.add(inventory)
            
        logger.info(f"Successfully created product with ID: {product.id}")
        return create_response(
            success=True,
            data={"product_id": product.id},
            status_code=HTTP_201_CREATED
        )
        
    except ValidationError as e:
        logger.error(f"Validation error during product creation: {e.messages}")
        return create_response(
            success=False,
            error=f"Validation failed: {e.messages}",
            status_code=HTTP_400_BAD_REQUEST
        )
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Database integrity error: {str(e)}")
        if 'UNIQUE constraint' in str(e.orig) or 'duplicate key' in str(e.orig):
            return create_response(False, error=ERROR_SKU_EXISTS, status_code=HTTP_400_BAD_REQUEST)
        return create_response(False, error=ERROR_DATABASE, status_code=HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error during product creation: {str(e)}")
        return create_response(False, error=ERROR_DATABASE, status_code=HTTP_500_INTERNAL_SERVER_ERROR)

# Create database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
