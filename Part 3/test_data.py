from app import db, Company, Warehouse, Supplier, Product, Inventory, Sale
from datetime import date, timedelta
import random

def create_test_data():
    with db.session.begin():
        # Create a test company
        company = Company(name="Test Company")
        db.session.add(company)
        db.session.flush()  # To get the company ID

        # Create a supplier
        supplier = Supplier(
            name="Supplier Corp",
            contact_email="orders@supplier.com",
            contact_phone="123-456-7890"
        )
        db.session.add(supplier)
        db.session.flush()

        # Create warehouses
        warehouse1 = Warehouse(
            company_id=company.id,
            name="Main Warehouse",
            location="New York"
        )
        warehouse2 = Warehouse(
            company_id=company.id,
            name="Secondary Warehouse",
            location="Los Angeles"
        )
        db.session.add_all([warehouse1, warehouse2])
        db.session.flush()

        # Create products
        products = [
            Product(
                company_id=company.id,
                name="Widget A",
                sku="WID-001",
                price=10.99,
                supplier_id=supplier.id,
                is_bundle=False
            ),
            Product(
                company_id=company.id,
                name="Widget B",
                sku="WID-002",
                price=20.99,
                supplier_id=supplier.id,
                is_bundle=True
            ),
            Product(
                company_id=company.id,
                name="Widget C",
                sku="WID-003",
                price=15.99,
                supplier_id=supplier.id,
                is_bundle=False
            )
        ]
        db.session.add_all(products)
        db.session.flush()

        # Create inventory records
        inventories = [
            # Low stock for Widget A in Main Warehouse
            Inventory(
                product_id=products[0].id,
                warehouse_id=warehouse1.id,
                quantity=5,
                min_stock=10
            ),
            # Normal stock for Widget A in Secondary Warehouse
            Inventory(
                product_id=products[0].id,
                warehouse_id=warehouse2.id,
                quantity=50,
                min_stock=10
            ),
            # Low stock for Widget B (bundle) in Main Warehouse
            Inventory(
                product_id=products[1].id,
                warehouse_id=warehouse1.id,
                quantity=8,
                min_stock=5
            ),
            # High stock for Widget C in Main Warehouse
            Inventory(
                product_id=products[2].id,
                warehouse_id=warehouse1.id,
                quantity=100,
                min_stock=20
            )
        ]
        db.session.add_all(inventories)

        # Create sales records for the last 30 days
        today = date.today()
        sales = []
        
        # Widget A - regular sales activity
        for i in range(30):
            sales.append(Sale(
                product_id=products[0].id,
                warehouse_id=warehouse1.id,
                quantity=random.randint(1, 3),
                sold_at=today - timedelta(days=i)
            ))

        # Widget B - less frequent sales
        for i in range(0, 30, 2):  # every other day
            sales.append(Sale(
                product_id=products[1].id,
                warehouse_id=warehouse1.id,
                quantity=random.randint(1, 2),
                sold_at=today - timedelta(days=i)
            ))

        # Widget C - high volume sales
        for i in range(30):
            sales.append(Sale(
                product_id=products[2].id,
                warehouse_id=warehouse1.id,
                quantity=random.randint(3, 5),
                sold_at=today - timedelta(days=i)
            ))

        db.session.add_all(sales)

if __name__ == '__main__':
    from app import app
    with app.app_context():
        # First, clear existing data
        db.drop_all()
        db.create_all()
        create_test_data()
        print("Test data has been created successfully!")
        
        # Print the company ID for easy reference
        company = Company.query.first()
        print(f"Test Company ID: {company.id}")