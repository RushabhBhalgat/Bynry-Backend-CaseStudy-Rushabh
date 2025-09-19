from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import date, timedelta

# Initialize Flask app and database
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'  # or your DB URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Model definitions (matching Part 2 schema exactly)
class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())

class Warehouse(db.Model):
    __tablename__ = 'warehouses'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200))
    
    __table_args__ = (
        db.UniqueConstraint('company_id', 'name', name='unique_company_warehouse'),
    )

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    contact_email = db.Column(db.String(100))
    contact_phone = db.Column(db.String(20))

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False)  # global SKU unique
    price = db.Column(db.DECIMAL(10, 2), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    is_bundle = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())
    
    __table_args__ = (
        db.CheckConstraint('price >= 0'),
    )

class Inventory(db.Model):
    __tablename__ = 'inventory'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id', ondelete='CASCADE'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    min_stock = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    __table_args__ = (
        db.UniqueConstraint('product_id', 'warehouse_id', name='unique_product_warehouse'),
        db.CheckConstraint('quantity >= 0'),
        db.CheckConstraint('min_stock >= 0'),
    )

class BundleItem(db.Model):
    __tablename__ = 'bundle_items'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bundle_product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    component_product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    
    __table_args__ = (
        db.UniqueConstraint('bundle_product_id', 'component_product_id', name='unique_bundle_component'),
        db.CheckConstraint('quantity > 0'),
    )

class InventoryAudit(db.Model):
    __tablename__ = 'inventory_audit'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id', ondelete='CASCADE'), nullable=False)
    change_qty = db.Column(db.Integer, nullable=False)
    new_quantity = db.Column(db.Integer, nullable=False)
    changed_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())
    note = db.Column(db.Text)

class Sale(db.Model):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    quantity = db.Column(db.Integer, nullable=False)
    sold_at = db.Column(db.Date, nullable=False, default=db.func.current_date())
    
    __table_args__ = (
        db.CheckConstraint('quantity > 0'),
    )

@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def low_stock_alerts(company_id):
    try:
        # Validate company exists
        company = db.session.query(Company).filter_by(id=company_id).first()
        if not company:
            return jsonify({"error": "Company not found"}), 404
        
        # Define threshold by product type
        threshold_by_type = {
            'standard': 20,
            'bundle': 10,
            # add more types if needed
        }
        recent_days = 30
        since_date = date.today() - timedelta(days=recent_days)

        alerts = []
        
        # First, get all recent sales data for this company's products in one query
        # This avoids N+1 query problem
        recent_sales = (
            db.session.query(
                Sale.product_id,
                func.sum(Sale.quantity).label('total_sales')
            )
            .join(Product, Sale.product_id == Product.id)
            .join(Inventory, Product.id == Inventory.product_id)
            .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
            .filter(
                Warehouse.company_id == company_id,
                Sale.sold_at >= since_date
            )
            .group_by(Sale.product_id)
            .all()
        )
        
        # Create a lookup dictionary for sales data
        sales_lookup = {product_id: total_sales for product_id, total_sales in recent_sales}
        
        # Query inventory records for this company via warehouses
        inventories = (
            db.session.query(Inventory, Product, Warehouse, Supplier)
            .join(Product, Inventory.product_id == Product.id)
            .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
            .outerjoin(Supplier, Product.supplier_id == Supplier.id)
            .filter(Warehouse.company_id == company_id)
            .all()
        )

        for inventory, product, warehouse, supplier in inventories:
            # Only consider products with recent sales
            sales_sum = sales_lookup.get(product.id, 0)
            if sales_sum == 0:
                continue  # No recent sales, skip

            # Compute average daily sales over the period
            daily_avg = sales_sum / recent_days

            # Determine threshold for this product
            # Assume product type stored as a string field, default to 'standard'
            ptype = 'bundle' if product.is_bundle else 'standard'
            threshold = threshold_by_type.get(ptype, threshold_by_type['standard'])

            current_qty = inventory.quantity
            if current_qty >= threshold:
                continue  # No alert if stock is above threshold

            # Calculate days until stockout, avoid division by zero
            days_until_stockout = int(current_qty / daily_avg) if daily_avg > 0 else None

            # Build alert entry
            alert = {
                "product_id": product.id,
                "product_name": product.name,
                "sku": product.sku,
                "warehouse_id": warehouse.id,
                "warehouse_name": warehouse.name,
                "current_stock": current_qty,
                "threshold": threshold,
                "days_until_stockout": days_until_stockout,
                "supplier": {
                    "id": supplier.id if supplier else None,
                    "name": supplier.name if supplier else None,
                    "contact_email": supplier.contact_email if supplier else None
                }
            }
            alerts.append(alert)

        response = {
            "alerts": alerts,
            "total_alerts": len(alerts)
        }
        return jsonify(response), 200
        
    except Exception as e:
        # Log the error in production
        return jsonify({"error": "Internal server error"}), 500

# Add a simple app runner for testing
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
    app.run(debug=True)
